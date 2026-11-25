"""LLM client for structured invoice extraction, GL coding, and Langfuse observability."""

import json
import logging
import time
import uuid
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from app.config import Settings, get_settings
from app.models import ChartOfAccountsEntry, ExtractedInvoice, GLRecommendation, InvoiceLineItem
from app.services.pdf_parser import ParsedPDF

logger = logging.getLogger("cre_agent.llm")

EXTRACTION_SYSTEM_PROMPT = (
    "You are a Commercial Real Estate (CRE) Accounts Payable specialist. "
    "Extract all structured header fields and line items from the vendor invoice accurately. "
    "Dates must be ISO format YYYY-MM-DD. Set extraction_confidence between 0.0 and 1.0 "
    "reflecting how legible and unambiguous the document is."
)

GL_SYSTEM_PROMPT = (
    "You are a Commercial Real Estate (CRE) property accountant. "
    "Given an extracted vendor invoice and the property's Chart of Accounts, "
    "select the single best matching GL code and provide a concise 1-2 sentence explanation "
    "referencing the specific invoice line items."
)


class TraceContext:
    """Lightweight wrapper around a Langfuse trace (or local no-op trace)."""

    def __init__(self, settings: Settings, filename: str, mode: str) -> None:
        self.trace_id: str = f"local-trace-{uuid.uuid4().hex[:12]}"
        self._langfuse: Any = None
        self._trace: Any = None

        if settings.langfuse_enabled:
            try:
                from langfuse import Langfuse

                self._langfuse = Langfuse(
                    public_key=settings.langfuse_public_key,
                    secret_key=settings.langfuse_secret_key,
                    host=settings.langfuse_host,
                )
                self._trace = self._langfuse.trace(
                    name="cre_invoice_analysis",
                    metadata={"filename": filename, "extraction_mode": mode},
                )
                if getattr(self._trace, "id", None):
                    self.trace_id = str(self._trace.id)
            except Exception as exc:
                logger.warning("Langfuse initialization failed; falling back to local log: %s", exc)
                self._langfuse = None
                self._trace = None

    def log_generation(
        self,
        name: str,
        model: str,
        input_payload: Any,
        output_payload: Any,
        usage: Optional[Dict[str, int]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        latency_ms: float = 0.0,
    ) -> None:
        """Record a child generation span in Langfuse or structured local logs."""
        logger.info(
            "trace=%s span=%s model=%s latency_ms=%.1f usage=%s",
            self.trace_id,
            name,
            model,
            latency_ms,
            usage or {},
        )
        if self._trace is not None:
            try:
                self._trace.generation(
                    name=name,
                    model=model,
                    input=input_payload,
                    output=output_payload,
                    usage=usage,
                    metadata={**(metadata or {}), "latency_ms": round(latency_ms, 1)},
                )
            except Exception as exc:
                logger.warning("Failed to log Langfuse generation '%s': %s", name, exc)

    def flush(self) -> None:
        """Flush buffered Langfuse events if enabled."""
        if self._langfuse is not None:
            try:
                self._langfuse.flush()
            except Exception as exc:
                logger.warning("Failed to flush Langfuse client: %s", exc)


class LLMService:
    """Unified LLM service supporting OpenAI, Anthropic, and offline Mock mode."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()

    def extract_invoice(
        self,
        parsed_pdf: ParsedPDF,
        trace: TraceContext,
    ) -> Tuple[ExtractedInvoice, str]:
        """Extract structured invoice data from text or rendered PNG pages."""
        provider = self.settings.llm_provider
        start = time.perf_counter()

        if provider == "mock":
            model_name = "mock-extractor-v1"
            invoice = self._mock_extract(parsed_pdf)
            usage = {"input": 420, "output": 180}
        elif provider == "openai":
            model_name = (
                self.settings.openai_vision_model
                if parsed_pdf.mode == "vision"
                else self.settings.openai_fast_model
            )
            invoice, usage = self._openai_extract(parsed_pdf, model_name)
        elif provider == "anthropic":
            model_name = (
                self.settings.anthropic_vision_model
                if parsed_pdf.mode == "vision"
                else self.settings.anthropic_fast_model
            )
            invoice, usage = self._anthropic_extract(parsed_pdf, model_name)
        else:
            raise ValueError(f"Unsupported LLM_PROVIDER: {provider}")

        latency_ms = (time.perf_counter() - start) * 1000
        trace.log_generation(
            name="invoice_extraction",
            model=model_name,
            input_payload={
                "mode": parsed_pdf.mode,
                "page_count": parsed_pdf.page_count,
                "text_preview": parsed_pdf.text[:500] if parsed_pdf.text else "<vision-images>",
            },
            output_payload=invoice.model_dump(mode="json"),
            usage=usage,
            metadata={"extraction_confidence": invoice.extraction_confidence},
            latency_ms=latency_ms,
        )
        return invoice, model_name

    def match_gl_account(
        self,
        invoice: ExtractedInvoice,
        chart_of_accounts: List[ChartOfAccountsEntry],
        trace: TraceContext,
    ) -> GLRecommendation:
        """Match the extracted invoice to the best CRE Chart of Accounts GL code."""
        provider = self.settings.llm_provider
        start = time.perf_counter()

        if provider == "mock":
            model_name = "mock-gl-matcher-v1"
            recommendation = self._mock_match_gl(invoice, chart_of_accounts)
            usage = {"input": 310, "output": 85}
        elif provider == "openai":
            model_name = self.settings.openai_fast_model
            recommendation, usage = self._openai_match_gl(invoice, chart_of_accounts, model_name)
        elif provider == "anthropic":
            model_name = self.settings.anthropic_fast_model
            recommendation, usage = self._anthropic_match_gl(invoice, chart_of_accounts, model_name)
        else:
            raise ValueError(f"Unsupported LLM_PROVIDER: {provider}")

        latency_ms = (time.perf_counter() - start) * 1000
        trace.log_generation(
            name="gl_coding_match",
            model=model_name,
            input_payload={
                "vendor_name": invoice.vendor_name,
                "line_items": [item.description for item in invoice.line_items],
            },
            output_payload=recommendation.model_dump(mode="json"),
            usage=usage,
            metadata={"gl_code": recommendation.gl_code},
            latency_ms=latency_ms,
        )
        return recommendation

    # ------------------------------------------------------------------
    # OpenAI implementation
    # ------------------------------------------------------------------
    def _get_openai_client(self) -> Any:
        if not self.settings.openai_api_key.strip():
            raise ValueError("OPENAI_API_KEY is required when LLM_PROVIDER=openai.")
        from openai import OpenAI

        return OpenAI(api_key=self.settings.openai_api_key)

    def _openai_extract(
        self, parsed_pdf: ParsedPDF, model: str
    ) -> Tuple[ExtractedInvoice, Dict[str, int]]:
        client = self._get_openai_client()
        if parsed_pdf.mode == "text":
            user_content: Any = (
                "Extract the structured invoice fields from the following PDF text:\n\n"
                f"{parsed_pdf.text}"
            )
        else:
            user_content = [
                {
                    "type": "text",
                    "text": "Extract all structured invoice fields from these scanned invoice pages.",
                },
                *[
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{img_b64}"},
                    }
                    for img_b64 in parsed_pdf.images_b64
                ],
            ]

        response = client.beta.chat.completions.parse(
            model=model,
            temperature=0.0,
            messages=[
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            response_format=ExtractedInvoice,
        )
        parsed = response.choices[0].message.parsed
        if parsed is None:
            raise RuntimeError("OpenAI returned an empty structured response for invoice extraction.")
        usage = {
            "input": getattr(response.usage, "prompt_tokens", 0) or 0,
            "output": getattr(response.usage, "completion_tokens", 0) or 0,
        }
        return parsed, usage

    def _openai_match_gl(
        self,
        invoice: ExtractedInvoice,
        chart_of_accounts: List[ChartOfAccountsEntry],
        model: str,
    ) -> Tuple[GLRecommendation, Dict[str, int]]:
        client = self._get_openai_client()
        coa_json = json.dumps([c.model_dump() for c in chart_of_accounts], indent=2)
        invoice_summary = json.dumps(
            {
                "vendor_name": invoice.vendor_name,
                "property_address": invoice.property_address,
                "line_items": [item.model_dump() for item in invoice.line_items],
                "amount_due": invoice.amount_due,
            },
            indent=2,
        )
        response = client.beta.chat.completions.parse(
            model=model,
            temperature=0.0,
            messages=[
                {"role": "system", "content": GL_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Chart of Accounts:\n{coa_json}\n\n"
                        f"Extracted Invoice:\n{invoice_summary}"
                    ),
                },
            ],
            response_format=GLRecommendation,
        )
        parsed = response.choices[0].message.parsed
        if parsed is None:
            raise RuntimeError("OpenAI returned an empty structured response for GL matching.")
        usage = {
            "input": getattr(response.usage, "prompt_tokens", 0) or 0,
            "output": getattr(response.usage, "completion_tokens", 0) or 0,
        }
        return parsed, usage

    # ------------------------------------------------------------------
    # Anthropic implementation (via forced tool use for strict JSON)
    # ------------------------------------------------------------------
    def _get_anthropic_client(self) -> Any:
        if not self.settings.anthropic_api_key.strip():
            raise ValueError("ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic.")
        from anthropic import Anthropic

        return Anthropic(api_key=self.settings.anthropic_api_key)

    def _anthropic_extract(
        self, parsed_pdf: ParsedPDF, model: str
    ) -> Tuple[ExtractedInvoice, Dict[str, int]]:
        client = self._get_anthropic_client()
        if parsed_pdf.mode == "text":
            content: Any = (
                "Extract the structured invoice fields from the following PDF text:\n\n"
                f"{parsed_pdf.text}"
            )
        else:
            content = [
                *[
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": img_b64,
                        },
                    }
                    for img_b64 in parsed_pdf.images_b64
                ],
                {
                    "type": "text",
                    "text": "Extract all structured invoice fields from these scanned invoice pages.",
                },
            ]

        response = client.messages.create(
            model=model,
            max_tokens=2048,
            temperature=0.0,
            system=EXTRACTION_SYSTEM_PROMPT,
            tools=[
                {
                    "name": "record_extracted_invoice",
                    "description": "Record the structured invoice extraction.",
                    "input_schema": ExtractedInvoice.model_json_schema(),
                }
            ],
            tool_choice={"type": "tool", "name": "record_extracted_invoice"},
            messages=[{"role": "user", "content": content}],
        )
        tool_block = next((b for b in response.content if b.type == "tool_use"), None)
        if tool_block is None:
            raise RuntimeError("Anthropic did not return a structured tool_use block.")
        parsed = ExtractedInvoice.model_validate(tool_block.input)
        usage = {
            "input": getattr(response.usage, "input_tokens", 0) or 0,
            "output": getattr(response.usage, "output_tokens", 0) or 0,
        }
        return parsed, usage

    def _anthropic_match_gl(
        self,
        invoice: ExtractedInvoice,
        chart_of_accounts: List[ChartOfAccountsEntry],
        model: str,
    ) -> Tuple[GLRecommendation, Dict[str, int]]:
        client = self._get_anthropic_client()
        coa_json = json.dumps([c.model_dump() for c in chart_of_accounts], indent=2)
        invoice_summary = json.dumps(
            {
                "vendor_name": invoice.vendor_name,
                "property_address": invoice.property_address,
                "line_items": [item.model_dump() for item in invoice.line_items],
                "amount_due": invoice.amount_due,
            },
            indent=2,
        )
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            temperature=0.0,
            system=GL_SYSTEM_PROMPT,
            tools=[
                {
                    "name": "record_gl_recommendation",
                    "description": "Record the best matching GL code and explanation.",
                    "input_schema": GLRecommendation.model_json_schema(),
                }
            ],
            tool_choice={"type": "tool", "name": "record_gl_recommendation"},
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Chart of Accounts:\n{coa_json}\n\n"
                        f"Extracted Invoice:\n{invoice_summary}"
                    ),
                }
            ],
        )
        tool_block = next((b for b in response.content if b.type == "tool_use"), None)
        if tool_block is None:
            raise RuntimeError("Anthropic did not return a GL recommendation tool_use block.")
        parsed = GLRecommendation.model_validate(tool_block.input)
        usage = {
            "input": getattr(response.usage, "input_tokens", 0) or 0,
            "output": getattr(response.usage, "output_tokens", 0) or 0,
        }
        return parsed, usage

    # ------------------------------------------------------------------
    # Offline Mock implementation (for demos without API keys)
    # ------------------------------------------------------------------
    def _mock_extract(self, parsed_pdf: ParsedPDF) -> ExtractedInvoice:
        lower_text = parsed_pdf.text.lower()

        if "roof" in lower_text or "summit" in lower_text:
            return ExtractedInvoice(
                vendor_name="Summit Commercial Roofing Co.",
                invoice_number="SCR-2026-4419",
                invoice_date=date(2026, 11, 12),
                due_date=date(2026, 12, 12),
                property_address="1200 Westheimer Plaza, Houston, TX 77027",
                line_items=[
                    InvoiceLineItem(
                        description="TPO membrane puncture patching (North parapet)",
                        quantity=2.0,
                        unit_price=850.00,
                        line_total=1700.00,
                    ),
                    InvoiceLineItem(
                        description="Scupper & flashing resealing",
                        quantity=1.0,
                        unit_price=650.00,
                        line_total=650.00,
                    ),
                ],
                subtotal=2350.00,
                tax_amount=193.88,
                amount_due=2543.88,
                extraction_confidence=0.96,
            )

        if parsed_pdf.mode == "vision" or "landscap" in lower_text or "greenview" in lower_text:
            return ExtractedInvoice(
                vendor_name="GreenView Grounds & Landscaping LLC",
                invoice_number="GV-90218",
                invoice_date=date(2026, 11, 15),
                due_date=date(2026, 12, 15),
                property_address="8800 Preston Center Pkwy, Plano, TX 75024",
                line_items=[
                    InvoiceLineItem(
                        description="Monthly commercial lawn & bed maintenance",
                        quantity=1.0,
                        unit_price=1250.00,
                        line_total=1250.00,
                    ),
                    InvoiceLineItem(
                        description="Irrigation zone 4 valve replacement",
                        quantity=2.0,
                        unit_price=225.00,
                        line_total=450.00,
                    ),
                ],
                subtotal=1700.00,
                tax_amount=140.25,
                amount_due=1840.25,
                extraction_confidence=0.88,  # Intentionally < 0.90 to showcase HITL review flag
            )

        # Default: Apex Commercial HVAC LLC
        return ExtractedInvoice(
            vendor_name="Apex Commercial HVAC LLC",
            invoice_number="INV-88412",
            invoice_date=date(2026, 11, 10),
            due_date=date(2026, 12, 10),
            property_address="4500 Commerce Park Dr, Dallas, TX 75201",
            line_items=[
                InvoiceLineItem(
                    description="RTU-3 condenser coil cleaning & refrigerant recharge",
                    quantity=1.0,
                    unit_price=1450.00,
                    line_total=1450.00,
                ),
                InvoiceLineItem(
                    description="Chiller economizer damper actuator replacement",
                    quantity=2.0,
                    unit_price=420.00,
                    line_total=840.00,
                ),
            ],
            subtotal=2290.00,
            tax_amount=160.00,
            amount_due=2450.00,
            extraction_confidence=0.97,
        )

    def _mock_match_gl(
        self,
        invoice: ExtractedInvoice,
        chart_of_accounts: List[ChartOfAccountsEntry],
    ) -> GLRecommendation:
        haystack = " ".join(
            [invoice.vendor_name, *[item.description for item in invoice.line_items]]
        ).lower()

        keyword_map = [
            ("6100", ["hvac", "rtu", "chiller", "refrigerant", "thermostat", "duct"]),
            ("6200", ["roof", "membrane", "flashing", "gutter", "parapet"]),
            ("6300", ["landscap", "lawn", "irrigation", "grounds", "snow", "sweeping"]),
            ("6400", ["janitor", "clean", "porter", "waste", "dumpster"]),
            ("6500", ["electric", "water", "gas", "utility", "municipal"]),
            ("6600", ["security", "alarm", "sprinkler", "fire", "extinguisher"]),
            ("5100", ["tax", "county", "assessment"]),
            ("5200", ["insurance", "liability", "hazard"]),
            ("7100", ["legal", "counsel", "lease", "cpa", "audit"]),
        ]

        selected_code = "6100"
        for code, keywords in keyword_map:
            if any(kw in haystack for kw in keywords):
                selected_code = code
                break

        account = next(
            (c for c in chart_of_accounts if c.gl_code == selected_code),
            chart_of_accounts[0],
        )
        first_item = invoice.line_items[0].description if invoice.line_items else invoice.vendor_name
        return GLRecommendation(
            gl_code=account.gl_code,
            gl_account_name=account.account_name,
            gl_confidence=0.95,
            explanation=(
                f"Matched to {account.gl_code} ({account.account_name}) based on vendor "
                f"'{invoice.vendor_name}' and line item '{first_item}'."
            ),
        )
