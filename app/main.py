"""FastAPI backend for CRE-Agent AP invoice extraction, validation, GL coding, and Yardi export."""

import logging
from typing import List

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, get_settings
from app.models import (
    ChartOfAccountsEntry,
    InvoiceAnalysisResponse,
    YardiExportPayload,
    YardiExportResponse,
)
from app.services.exporter import export_yardi_payload, load_chart_of_accounts
from app.services.llm_client import LLMService, TraceContext
from app.services.pdf_parser import parse_pdf
from app.services.validator import validate_invoice

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

app = FastAPI(
    title="CRE-Agent API",
    description=(
        "Commercial Real Estate Accounts Payable automation: PDF extraction, "
        "deterministic arithmetic gates, GL coding, Langfuse tracing, and HITL Yardi export."
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_llm_service(settings: Settings = Depends(get_settings)) -> LLMService:
    """Dependency provider for LLMService (easily overridable in tests)."""
    return LLMService(settings=settings)


@app.get("/health")
def health_check(settings: Settings = Depends(get_settings)) -> dict:
    """Return service health and active model/observability configuration."""
    if settings.llm_provider == "openai":
        fast_model = settings.openai_fast_model
        vision_model = settings.openai_vision_model
    elif settings.llm_provider == "anthropic":
        fast_model = settings.anthropic_fast_model
        vision_model = settings.anthropic_vision_model
    else:
        fast_model = "mock-extractor-v1"
        vision_model = "mock-extractor-v1"

    return {
        "status": "ok",
        "llm_provider": settings.llm_provider,
        "fast_model": fast_model,
        "vision_model": vision_model,
        "langfuse_enabled": settings.langfuse_enabled,
    }


@app.get("/api/v1/chart-of-accounts", response_model=List[ChartOfAccountsEntry])
def get_chart_of_accounts() -> List[ChartOfAccountsEntry]:
    """Return the mock CRE Chart of Accounts."""
    return load_chart_of_accounts()


@app.post("/api/v1/invoices/analyze", response_model=InvoiceAnalysisResponse)
async def analyze_invoice(
    file: UploadFile = File(...),
    settings: Settings = Depends(get_settings),
    llm_service: LLMService = Depends(get_llm_service),
) -> InvoiceAnalysisResponse:
    """Ingest a PDF invoice, run LLM extraction, deterministic math gate, and GL matching."""
    filename = file.filename or "invoice.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only .pdf files are supported.")

    pdf_bytes = await file.read()
    try:
        parsed_pdf = parse_pdf(
            pdf_bytes=pdf_bytes,
            min_chars_per_page=settings.pdf_min_chars_per_page,
            max_vision_pages=settings.pdf_max_vision_pages,
            dpi=settings.pdf_render_dpi,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    trace = TraceContext(settings=settings, filename=filename, mode=parsed_pdf.mode)
    try:
        extracted_invoice, model_used = llm_service.extract_invoice(parsed_pdf, trace)
        validation = validate_invoice(
            extracted_invoice,
            confidence_threshold=settings.confidence_threshold,
            math_tolerance=settings.math_tolerance,
        )
        coa = load_chart_of_accounts()
        gl_recommendation = llm_service.match_gl_account(extracted_invoice, coa, trace)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM processing error: {exc}") from exc
    finally:
        trace.flush()

    return InvoiceAnalysisResponse(
        trace_id=trace.trace_id,
        extraction_mode=parsed_pdf.mode,
        model_used=model_used,
        invoice=extracted_invoice,
        gl_recommendation=gl_recommendation,
        validation=validation,
    )


@app.post("/api/v1/invoices/export", response_model=YardiExportResponse)
def export_invoice(payload: YardiExportPayload) -> YardiExportResponse:
    """Validate HITL approval and generate Yardi-ready CSV and JSON audit payload."""
    try:
        return export_yardi_payload(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
