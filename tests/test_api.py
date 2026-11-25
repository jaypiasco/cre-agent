"""FastAPI endpoint tests using mock LLM mode and generated PDFs."""

import io
from pathlib import Path

import pymupdf as fitz
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app, get_llm_service
from app.services.llm_client import LLMService


def _mock_settings() -> Settings:
    return Settings(llm_provider="mock", langfuse_public_key="", langfuse_secret_key="")


app.dependency_overrides[get_settings] = _mock_settings
app.dependency_overrides[get_llm_service] = lambda: LLMService(settings=_mock_settings())

client = TestClient(app)


def _make_text_pdf(text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def _make_scanned_pdf() -> bytes:
    # Render a blank/image-only page with 0 extractable text
    doc = fitz.open()
    page = doc.new_page()
    page.draw_rect(fitz.Rect(50, 50, 200, 100), color=(0, 0, 0))
    data = doc.tobytes()
    doc.close()
    return data


def test_health_endpoint():
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["llm_provider"] == "mock"


def test_chart_of_accounts_endpoint():
    resp = client.get("/api/v1/chart-of-accounts")
    assert resp.status_code == 200
    coa = resp.json()
    assert len(coa) == 9
    assert any(entry["gl_code"] == "6100" for entry in coa)


def test_analyze_text_pdf_routes_to_text_mode():
    pdf_bytes = _make_text_pdf(
        "Apex Commercial HVAC LLC\nInvoice INV-88412\nRTU-3 condenser coil cleaning $1450.00\n"
        "Chiller economizer damper actuator replacement $840.00\nTotal Due: $2450.00"
    )
    resp = client.post(
        "/api/v1/invoices/analyze",
        files={"file": ("hvac.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["extraction_mode"] == "text"
    assert body["gl_recommendation"]["gl_code"] == "6100"
    assert body["validation"]["status"] == "VALID"
    assert body["trace_id"].startswith("local-trace-")


def test_analyze_scanned_pdf_triggers_vision_fallback():
    pdf_bytes = _make_scanned_pdf()
    resp = client.post(
        "/api/v1/invoices/analyze",
        files={"file": ("scanned.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["extraction_mode"] == "vision"
    assert body["validation"]["status"] == "NEEDS_REVIEW"


def test_analyze_rejects_non_pdf():
    resp = client.post(
        "/api/v1/invoices/analyze",
        files={"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert resp.status_code == 400


def test_export_rejects_unapproved_payload():
    payload = {
        "batch_id": "BATCH-20261125-001",
        "vendor_name": "Apex Commercial HVAC LLC",
        "invoice_number": "INV-88412",
        "invoice_date": "2026-11-10",
        "property_address": "4500 Commerce Park Dr, Dallas, TX",
        "gl_code": "6100",
        "gl_account_name": "HVAC & Mechanical R&M",
        "amount_due": 2450.00,
        "human_approved": False,
        "approved_by": "ap_reviewer",
        "langfuse_trace_id": "local-trace-1234",
    }
    resp = client.post("/api/v1/invoices/export", json=payload)
    assert resp.status_code == 400
    assert "Human approval is required" in resp.json()["detail"]


def test_export_returns_yardi_csv_and_json_when_approved():
    payload = {
        "batch_id": "BATCH-20261125-001",
        "vendor_name": "Apex Commercial HVAC LLC",
        "invoice_number": "INV-88412",
        "invoice_date": "2026-11-10",
        "property_address": "4500 Commerce Park Dr, Dallas, TX",
        "gl_code": "6100",
        "gl_account_name": "HVAC & Mechanical R&M",
        "amount_due": 2450.00,
        "human_approved": True,
        "approved_by": "ap_reviewer",
        "langfuse_trace_id": "local-trace-1234",
    }
    resp = client.post("/api/v1/invoices/export", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["filename"] == "BATCH-20261125-001_INV-88412.csv"
    lines = body["csv_content"].strip().splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("BatchID,VendorName,InvoiceNumber,InvoiceDate")
    assert "Apex Commercial HVAC LLC" in lines[1]
    assert "6100" in lines[1]
    assert "2450.00" in lines[1]
