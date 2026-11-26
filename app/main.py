"""FastAPI backend for CRE-Agent AP invoice extraction, validation, GL coding, and Yardi export."""

import logging
import time
from typing import List, Optional, Tuple

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, get_settings
from app.models import (
    ChartOfAccountsEntry,
    InvoiceAnalysisResponse,
    YardiExportPayload,
    YardiExportResponse,
)
from app.services.exporter import export_yardi_payload, load_chart_of_accounts
from app.services.llm_client import LLMService, TraceContext, record_hitl_feedback
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


_PROVIDER_KEY_FIELDS = {
    "gemini": "gemini_api_key",
    "openai": "openai_api_key",
    "anthropic": "anthropic_api_key",
}
MAX_PDF_BYTES = 10 * 1024 * 1024  # 10 MB upload cap for public demo safety


def _resolve_request_llm(
    settings: Settings,
    default_service: LLMService,
    provider_header: Optional[str],
    api_key_header: Optional[str],
) -> Tuple[Settings, LLMService]:
    """Resolve per-request Settings and LLMService from optional BYOK/Mock headers."""
    if not provider_header or not provider_header.strip():
        return settings, default_service

    provider = provider_header.strip().lower()
    if provider == "mock":
        effective = settings.model_copy(update={"llm_provider": "mock"})
        return effective, LLMService(settings=effective)

    if provider not in _PROVIDER_KEY_FIELDS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported X-LLM-Provider: {provider_header}",
        )

    api_key = (api_key_header or "").strip()
    if api_key:
        updates = {"llm_provider": provider, _PROVIDER_KEY_FIELDS[provider]: api_key}
        if provider == "gemini":
            updates["gemini_api_keys"] = ""
        effective = settings.model_copy(update=updates)
        return effective, LLMService(settings=effective)

    has_server_key = (
        bool(settings.gemini_key_list)
        if provider == "gemini"
        else bool(getattr(settings, _PROVIDER_KEY_FIELDS[provider]).strip())
    )
    if not has_server_key:
        raise HTTPException(
            status_code=400,
            detail=f"API key is required when using provider '{provider}'.",
        )

    effective = settings.model_copy(update={"llm_provider": provider})
    return effective, LLMService(settings=effective)


@app.get("/health")
def health_check(settings: Settings = Depends(get_settings)) -> dict:
    """Return service health and active provider/observability status."""
    return {
        "status": "ok",
        "llm_provider": settings.llm_provider,
        "langfuse_enabled": settings.langfuse_enabled,
    }


@app.get("/api/v1/chart-of-accounts", response_model=List[ChartOfAccountsEntry])
def get_chart_of_accounts() -> List[ChartOfAccountsEntry]:
    """Return the mock CRE Chart of Accounts."""
    return load_chart_of_accounts()


@app.post("/api/v1/invoices/analyze", response_model=InvoiceAnalysisResponse)
async def analyze_invoice(
    file: UploadFile = File(...),
    x_llm_provider: Optional[str] = Header(default=None, alias="X-LLM-Provider"),
    x_llm_api_key: Optional[str] = Header(default=None, alias="X-LLM-Api-Key"),
    settings: Settings = Depends(get_settings),
    llm_service: LLMService = Depends(get_llm_service),
) -> InvoiceAnalysisResponse:
    """Ingest a PDF invoice, run LLM extraction, deterministic math gate, and GL matching."""
    filename = file.filename or "invoice.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only .pdf files are supported.")

    effective_settings, effective_llm_service = _resolve_request_llm(
        settings=settings,
        default_service=llm_service,
        provider_header=x_llm_provider,
        api_key_header=x_llm_api_key,
    )

    pdf_bytes = await file.read()
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise HTTPException(
            status_code=413,
            detail="PDF file exceeds maximum allowed size of 10 MB.",
        )
    parse_start = time.perf_counter()
    try:
        parsed_pdf = parse_pdf(
            pdf_bytes=pdf_bytes,
            min_chars_per_page=effective_settings.pdf_min_chars_per_page,
            max_vision_pages=effective_settings.pdf_max_vision_pages,
            dpi=effective_settings.pdf_render_dpi,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    parse_latency_ms = (time.perf_counter() - parse_start) * 1000

    trace = TraceContext(settings=effective_settings, filename=filename, mode=parsed_pdf.mode)
    trace.log_span(
        name="pdf_parse",
        as_type="tool",
        input_payload={"filename": filename, "size_bytes": len(pdf_bytes)},
        output_payload={
            "mode": parsed_pdf.mode,
            "page_count": parsed_pdf.page_count,
            "char_count": len(parsed_pdf.text),
            "image_count": len(parsed_pdf.images_b64),
        },
        latency_ms=parse_latency_ms,
    )
    try:
        extracted_invoice, model_used = effective_llm_service.extract_invoice(parsed_pdf, trace)
        gate_start = time.perf_counter()
        validation = validate_invoice(
            extracted_invoice,
            confidence_threshold=effective_settings.confidence_threshold,
            math_tolerance=effective_settings.math_tolerance,
        )
        gate_latency_ms = (time.perf_counter() - gate_start) * 1000
        trace.log_span(
            name="math_validation_gate",
            as_type="guardrail",
            input_payload={
                "subtotal": extracted_invoice.subtotal,
                "tax_amount": extracted_invoice.tax_amount,
                "discount_amount": extracted_invoice.discount_amount,
                "amount_due": extracted_invoice.amount_due,
                "extraction_confidence": extracted_invoice.extraction_confidence,
            },
            output_payload=validation.model_dump(mode="json"),
            latency_ms=gate_latency_ms,
            level="WARNING" if validation.status == "NEEDS_REVIEW" else "DEFAULT",
            status_message="; ".join(validation.warnings) if validation.warnings else None,
        )
        coa = load_chart_of_accounts()
        gl_recommendation = effective_llm_service.match_gl_account(extracted_invoice, coa, trace)

        trace.log_score(
            name="extraction_confidence",
            value=round(extracted_invoice.extraction_confidence, 4),
            data_type="NUMERIC",
            comment=f"Mode={parsed_pdf.mode}",
        )
        trace.log_score(
            name="math_gate_passed",
            value=1.0 if validation.math_valid else 0.0,
            data_type="BOOLEAN",
            comment="; ".join(validation.warnings) if validation.warnings else "Math & confidence checks passed",
        )
        trace.finalize(
            output_payload={
                "vendor_name": extracted_invoice.vendor_name,
                "invoice_number": extracted_invoice.invoice_number,
                "amount_due": extracted_invoice.amount_due,
                "gl_code": gl_recommendation.gl_code,
                "gl_account_name": gl_recommendation.gl_account_name,
                "validation_status": validation.status,
            },
            metadata={
                "model_used": model_used,
                "validation_status": validation.status,
                "gl_code": gl_recommendation.gl_code,
            },
        )
    except ValueError as exc:
        trace.finalize(error=str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        trace.finalize(error=str(exc))
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
def export_invoice(
    payload: YardiExportPayload,
    settings: Settings = Depends(get_settings),
) -> YardiExportResponse:
    """Validate HITL approval and generate Yardi-ready CSV and JSON audit payload."""
    try:
        result = export_yardi_payload(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    record_hitl_feedback(
        settings=settings,
        trace_id=payload.langfuse_trace_id,
        approved=payload.human_approved,
        gl_code=payload.gl_code,
        vendor_name=payload.vendor_name,
        approved_by=payload.approved_by,
    )
    return result
