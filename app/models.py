"""Pydantic v2 data models for CRE-Agent invoice extraction, validation, and export."""

from datetime import date, datetime, timezone
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class InvoiceLineItem(BaseModel):
    """Single line item extracted from a vendor invoice."""

    description: str
    quantity: float = 1.0
    unit_price: float
    line_total: float


class ExtractedInvoice(BaseModel):
    """Structured header and line-item data extracted from an invoice PDF."""

    vendor_name: str
    invoice_number: str
    invoice_date: date
    due_date: Optional[date] = None
    property_address: str
    line_items: List[InvoiceLineItem]
    subtotal: float
    tax_amount: float = 0.0
    discount_amount: float = 0.0
    amount_due: float
    extraction_confidence: float = Field(ge=0.0, le=1.0)


class GLRecommendation(BaseModel):
    """Recommended General Ledger account from the CRE Chart of Accounts."""

    gl_code: str
    gl_account_name: str
    gl_confidence: float = Field(ge=0.0, le=1.0)
    explanation: str


class ValidationReport(BaseModel):
    """Deterministic arithmetic and completeness validation outcome."""

    math_valid: bool
    math_discrepancy: float = 0.0
    status: Literal["VALID", "NEEDS_REVIEW"]
    warnings: List[str] = Field(default_factory=list)


class InvoiceAnalysisResponse(BaseModel):
    """Complete analysis payload returned by POST /api/v1/invoices/analyze."""

    trace_id: Optional[str] = None
    extraction_mode: Literal["text", "vision"] = "text"
    model_used: str = ""
    invoice: ExtractedInvoice
    gl_recommendation: GLRecommendation
    validation: ValidationReport


class YardiExportPayload(BaseModel):
    """Human-approved invoice payload formatted for Yardi AP batch export."""

    batch_id: str
    vendor_name: str
    invoice_number: str
    invoice_date: date
    property_address: str
    gl_code: str
    gl_account_name: str
    amount_due: float
    human_approved: bool
    approved_by: str = "ap_reviewer"
    approved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    langfuse_trace_id: Optional[str] = None


class YardiExportResponse(BaseModel):
    """Response from POST /api/v1/invoices/export containing CSV text and JSON audit payload."""

    csv_content: str
    filename: str
    json_payload: YardiExportPayload


class ChartOfAccountsEntry(BaseModel):
    """Single account entry in the CRE Chart of Accounts."""

    gl_code: str
    account_name: str
    examples: str
