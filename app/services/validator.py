"""Deterministic arithmetic and completeness validation gates."""

from decimal import Decimal
from typing import List

from app.models import ExtractedInvoice, ValidationReport


def validate_invoice(
    invoice: ExtractedInvoice,
    confidence_threshold: float = 0.90,
    math_tolerance: float = 0.02,
) -> ValidationReport:
    """Run deterministic Decimal math checks and required-field gates on an extracted invoice."""
    warnings: List[str] = []
    tol = Decimal(str(math_tolerance))

    # 1. Required fields check
    if not invoice.vendor_name.strip():
        warnings.append("Missing required field: vendor_name.")
    if not invoice.invoice_number.strip():
        warnings.append("Missing required field: invoice_number.")
    if not invoice.property_address.strip():
        warnings.append("Missing required field: property_address.")
    if invoice.amount_due <= 0:
        warnings.append(f"Invalid amount_due ({invoice.amount_due:.2f}); must be greater than 0.")
    if not invoice.line_items:
        warnings.append("Invoice contains no extracted line items.")

    # 2. Date sanity check
    if invoice.due_date is not None and invoice.due_date < invoice.invoice_date:
        warnings.append(
            f"Due date ({invoice.due_date}) precedes invoice date ({invoice.invoice_date})."
        )

    # 3. Line-item arithmetic checks (quantity * unit_price == line_total)
    line_sum = Decimal("0.00")
    for idx, item in enumerate(invoice.line_items, start=1):
        qty = Decimal(str(item.quantity))
        unit_price = Decimal(str(item.unit_price))
        line_total = Decimal(str(item.line_total))
        expected_line = qty * unit_price
        line_diff = abs(expected_line - line_total)
        if line_diff > tol:
            warnings.append(
                f"Line {idx} ('{item.description[:40]}'): {qty} x ${unit_price:.2f} = "
                f"${expected_line:.2f}, but extracted line_total is ${line_total:.2f} "
                f"(diff ${line_diff:.2f})."
            )
        line_sum += line_total

    # 4. Subtotal check
    subtotal_dec = Decimal(str(invoice.subtotal))
    subtotal_diff = abs(line_sum - subtotal_dec)
    if invoice.line_items and subtotal_diff > tol:
        warnings.append(
            f"Subtotal mismatch: sum of line items is ${line_sum:.2f}, "
            f"but extracted subtotal is ${subtotal_dec:.2f} (diff ${subtotal_diff:.2f})."
        )

    # 5. Grand total check: sum(line_items) + tax - discount == amount_due
    tax_dec = Decimal(str(invoice.tax_amount))
    discount_dec = Decimal(str(invoice.discount_amount))
    amount_due_dec = Decimal(str(invoice.amount_due))
    expected_total = line_sum + tax_dec - discount_dec
    discrepancy = abs(expected_total - amount_due_dec)
    math_valid = discrepancy <= tol

    if not math_valid:
        warnings.append(
            f"Total math mismatch: line items (${line_sum:.2f}) + tax (${tax_dec:.2f}) "
            f"- discount (${discount_dec:.2f}) = ${expected_total:.2f}, "
            f"but amount_due is ${amount_due_dec:.2f} (discrepancy ${discrepancy:.2f})."
        )

    # 6. Confidence gate
    if invoice.extraction_confidence < confidence_threshold:
        warnings.append(
            f"Low extraction confidence ({invoice.extraction_confidence:.0%} < "
            f"{confidence_threshold:.0%} threshold). Manual review required."
        )

    status = "VALID" if (math_valid and not warnings) else "NEEDS_REVIEW"

    return ValidationReport(
        math_valid=math_valid,
        math_discrepancy=float(round(discrepancy, 2)),
        status=status,
        warnings=warnings,
    )
