"""Unit tests for deterministic arithmetic and completeness validation gates."""

from datetime import date
from typing import Any

from app.models import ExtractedInvoice, InvoiceLineItem
from app.services.validator import validate_invoice


def _base_invoice(**overrides: Any) -> ExtractedInvoice:
    data: dict[str, Any] = {
        "vendor_name": "Apex Commercial HVAC LLC",
        "invoice_number": "INV-88412",
        "invoice_date": date(2026, 11, 10),
        "due_date": date(2026, 12, 10),
        "property_address": "4500 Commerce Park Dr, Dallas, TX 75201",
        "line_items": [
            InvoiceLineItem(
                description="RTU-3 condenser coil cleaning",
                quantity=1.0,
                unit_price=1450.00,
                line_total=1450.00,
            ),
            InvoiceLineItem(
                description="Damper actuator replacement",
                quantity=2.0,
                unit_price=420.00,
                line_total=840.00,
            ),
        ],
        "subtotal": 2290.00,
        "tax_amount": 160.00,
        "discount_amount": 0.00,
        "amount_due": 2450.00,
        "extraction_confidence": 0.97,
    }
    data.update(overrides)
    return ExtractedInvoice(**data)


def test_valid_invoice_passes():
    report = validate_invoice(_base_invoice())
    assert report.math_valid is True
    assert report.math_discrepancy == 0.0
    assert report.status == "VALID"
    assert report.warnings == []


def test_rounding_within_two_cents_passes():
    invoice = _base_invoice(amount_due=2450.02)
    report = validate_invoice(invoice)
    assert report.math_valid is True
    assert report.status == "VALID"


def test_math_mismatch_flags_needs_review():
    invoice = _base_invoice(amount_due=2500.00)
    report = validate_invoice(invoice)
    assert report.math_valid is False
    assert report.math_discrepancy == 50.00
    assert report.status == "NEEDS_REVIEW"
    assert any("Total math mismatch" in w for w in report.warnings)


def test_line_item_multiplication_mismatch_flags_warning():
    bad_items = [
        InvoiceLineItem(
            description="Damper actuator",
            quantity=2.0,
            unit_price=420.00,
            line_total=800.00,  # Should be 840.00
        )
    ]
    invoice = _base_invoice(line_items=bad_items, subtotal=800.00, tax_amount=0.0, amount_due=800.00)
    report = validate_invoice(invoice)
    assert report.status == "NEEDS_REVIEW"
    assert any("Line 1" in w for w in report.warnings)


def test_low_confidence_flags_needs_review():
    invoice = _base_invoice(extraction_confidence=0.84)
    report = validate_invoice(invoice)
    assert report.math_valid is True
    assert report.status == "NEEDS_REVIEW"
    assert any("Low extraction confidence" in w for w in report.warnings)


def test_missing_required_fields_flags_needs_review():
    invoice = _base_invoice(vendor_name="   ", amount_due=0.0)
    report = validate_invoice(invoice)
    assert report.status == "NEEDS_REVIEW"
    assert any("vendor_name" in w for w in report.warnings)
    assert any("amount_due" in w for w in report.warnings)


def test_discount_is_subtracted_properly():
    invoice = _base_invoice(discount_amount=100.00, amount_due=2350.00)
    report = validate_invoice(invoice)
    assert report.math_valid is True
    assert report.status == "VALID"
