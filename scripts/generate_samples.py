"""Generate 4 realistic CRE vendor invoice PDFs (2 clean text, 1 scanned, 1 math-mismatch)."""

import io
from pathlib import Path

import pymupdf as fitz
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples"


def _build_invoice_pdf_bytes(
    vendor: str,
    invoice_no: str,
    inv_date: str,
    due_date: str,
    property_addr: str,
    rows: list,
    subtotal: str,
    tax: str,
    total: str,
) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, title=f"Invoice {invoice_no}")
    styles = getSampleStyleSheet()
    elements = [
        Paragraph(f"<b>{vendor}</b>", styles["Title"]),
        Spacer(1, 8),
        Paragraph(f"<b>Invoice Number:</b> {invoice_no}", styles["Normal"]),
        Paragraph(f"<b>Invoice Date:</b> {inv_date}", styles["Normal"]),
        Paragraph(f"<b>Due Date:</b> {due_date}", styles["Normal"]),
        Paragraph(f"<b>Service Property:</b> {property_addr}", styles["Normal"]),
        Spacer(1, 16),
    ]

    table_data = [["Description", "Qty", "Unit Price", "Line Total"], *rows]
    table_data.extend(
        [
            ["", "", "Subtotal", subtotal],
            ["", "", "Tax", tax],
            ["", "", "Amount Due", total],
        ]
    )
    table = Table(table_data, colWidths=[270, 55, 90, 90])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                ("GRID", (0, 0), (-1, len(rows)), 0.5, colors.grey),
                ("FONTNAME", (2, -1), (-1, -1), "Helvetica-Bold"),
                ("LINEABOVE", (2, -3), (-1, -3), 1, colors.black),
                ("LINEABOVE", (2, -1), (-1, -1), 1.5, colors.black),
            ]
        )
    )
    elements.append(table)
    doc.build(elements)
    return buf.getvalue()


def _convert_to_scanned_pdf(text_pdf_bytes: bytes) -> bytes:
    """Rasterize a PDF to a PNG image and wrap it in a new PDF with zero text layer."""
    src = fitz.open(stream=text_pdf_bytes, filetype="pdf")
    dst = fitz.open()
    for page_idx in range(len(src)):
        page = src[page_idx]
        pix = page.get_pixmap(dpi=150)
        img_pdf = fitz.open()
        rect = fitz.Rect(0, 0, page.rect.width, page.rect.height)
        new_page = img_pdf.new_page(width=page.rect.width, height=page.rect.height)
        new_page.insert_image(rect, stream=pix.tobytes("png"))
        dst.insert_pdf(img_pdf)
        img_pdf.close()
    out_bytes = dst.tobytes()
    src.close()
    dst.close()
    return out_bytes


def main() -> None:
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Text-based HVAC Invoice
    hvac_bytes = _build_invoice_pdf_bytes(
        vendor="Apex Commercial HVAC LLC",
        invoice_no="INV-88412",
        inv_date="2026-11-10",
        due_date="2026-12-10",
        property_addr="4500 Commerce Park Dr, Dallas, TX 75201",
        rows=[
            ["RTU-3 condenser coil cleaning & refrigerant recharge", "1.00", "$1,450.00", "$1,450.00"],
            ["Chiller economizer damper actuator replacement", "2.00", "$420.00", "$840.00"],
        ],
        subtotal="$2,290.00",
        tax="$160.00",
        total="$2,450.00",
    )
    (SAMPLES_DIR / "hvac_apex_inv_88412.pdf").write_bytes(hvac_bytes)

    # 2. Text-based Roofing Invoice
    roof_bytes = _build_invoice_pdf_bytes(
        vendor="Summit Commercial Roofing Co.",
        invoice_no="SCR-2026-4419",
        inv_date="2026-11-12",
        due_date="2026-12-12",
        property_addr="1200 Westheimer Plaza, Houston, TX 77027",
        rows=[
            ["TPO membrane puncture patching (North parapet)", "2.00", "$850.00", "$1,700.00"],
            ["Scupper & flashing resealing", "1.00", "$650.00", "$650.00"],
        ],
        subtotal="$2,350.00",
        tax="$193.88",
        total="$2,543.88",
    )
    (SAMPLES_DIR / "roofing_summit_scr_4419.pdf").write_bytes(roof_bytes)

    # 3. Scanned Image-Only Landscaping Invoice (triggers Vision fallback)
    landscaping_text_bytes = _build_invoice_pdf_bytes(
        vendor="GreenView Grounds & Landscaping LLC",
        invoice_no="GV-90218",
        inv_date="2026-11-15",
        due_date="2026-12-15",
        property_addr="8800 Preston Center Pkwy, Plano, TX 75024",
        rows=[
            ["Monthly commercial lawn & bed maintenance", "1.00", "$1,250.00", "$1,250.00"],
            ["Irrigation zone 4 valve replacement", "2.00", "$225.00", "$450.00"],
        ],
        subtotal="$1,700.00",
        tax="$140.25",
        total="$1,840.25",
    )
    scanned_bytes = _convert_to_scanned_pdf(landscaping_text_bytes)
    (SAMPLES_DIR / "landscaping_greenview_scanned.pdf").write_bytes(scanned_bytes)

    # 4. Text-based Utility Invoice with intentional math mismatch ($2,250 + $180 = $2,430 != $2,580)
    utility_error_bytes = _build_invoice_pdf_bytes(
        vendor="Metro Municipal Water & Power",
        invoice_no="MMWP-2026-9914",
        inv_date="2026-11-18",
        due_date="2026-12-18",
        property_addr="3100 Oak Lawn Ave, Dallas, TX 75219",
        rows=[
            ["Commercial water & sewer service (Oct-Nov)", "1.00", "$820.00", "$820.00"],
            ["Common area electric demand & usage", "1.00", "$1,430.00", "$1,430.00"],
        ],
        subtotal="$2,250.00",
        tax="$180.00",
        total="$2,580.00",
    )
    (SAMPLES_DIR / "utility_math_error_sample.pdf").write_bytes(utility_error_bytes)

    print(f"Generated 4 sample PDFs in {SAMPLES_DIR}")


if __name__ == "__main__":
    main()
