"""Chart of Accounts loader and Yardi AP batch CSV/JSON exporter."""

import csv
import io
import json
import re
from pathlib import Path
from typing import List

from app.models import ChartOfAccountsEntry, YardiExportPayload, YardiExportResponse

COA_PATH = Path(__file__).resolve().parent.parent / "data" / "chart_of_accounts.json"


def load_chart_of_accounts() -> List[ChartOfAccountsEntry]:
    """Load the mock CRE Chart of Accounts from JSON."""
    raw = json.loads(COA_PATH.read_text(encoding="utf-8"))
    return [ChartOfAccountsEntry(**entry) for entry in raw]


def _safe_filename_part(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", value.strip())
    return cleaned.strip("-") or "export"


def export_yardi_payload(payload: YardiExportPayload) -> YardiExportResponse:
    """Enforce HITL approval and format a Yardi-ready CSV + JSON audit response."""
    if not payload.human_approved:
        raise ValueError(
            "Human approval is required before exporting. Set human_approved=True to proceed."
        )

    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(
        [
            "BatchID",
            "VendorName",
            "InvoiceNumber",
            "InvoiceDate",
            "PropertyAddress",
            "GLCode",
            "GLAccountName",
            "AmountDue",
            "ApprovedBy",
            "ApprovedAt",
            "TraceID",
        ]
    )
    writer.writerow(
        [
            payload.batch_id,
            payload.vendor_name,
            payload.invoice_number,
            payload.invoice_date.isoformat(),
            payload.property_address,
            payload.gl_code,
            payload.gl_account_name,
            f"{payload.amount_due:.2f}",
            payload.approved_by,
            payload.approved_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            payload.langfuse_trace_id or "",
        ]
    )

    filename = (
        f"{_safe_filename_part(payload.batch_id)}_"
        f"{_safe_filename_part(payload.invoice_number)}.csv"
    )

    return YardiExportResponse(
        csv_content=output.getvalue(),
        filename=filename,
        json_payload=payload,
    )
