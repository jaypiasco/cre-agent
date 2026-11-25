"""FastAPI endpoint tests using mock LLM mode and generated PDFs."""

import io

import pymupdf as fitz
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app, get_llm_service
from app.services.llm_client import LLMService, TraceContext, record_hitl_feedback


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


def test_analyze_math_error_sample_triggers_needs_review():
    pdf_bytes = _make_text_pdf(
        "Metro Municipal Water & Power\nInvoice MMWP-2026-9914\n"
        "Commercial water & sewer service $820.00\n"
        "Common area electric demand $1430.00\nTotal Due: $2580.00"
    )
    resp = client.post(
        "/api/v1/invoices/analyze",
        files={"file": ("utility_math_error_sample.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["extraction_mode"] == "text"
    assert body["gl_recommendation"]["gl_code"] == "6500"
    assert body["validation"]["math_valid"] is False
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


def test_settings_gemini_key_list_parses_pool_and_fallback():
    pooled = Settings(gemini_api_keys=" key1 , , key2 ", gemini_api_key="single")
    assert pooled.gemini_key_list == ["key1", "key2"]

    fallback = Settings(gemini_api_keys="  ", gemini_api_key=" single ")
    assert fallback.gemini_key_list == ["single"]

    empty = Settings(gemini_api_keys="", gemini_api_key="")
    assert empty.gemini_key_list == []


def test_gemini_rotation_retries_on_quota_error(monkeypatch):
    settings = Settings(llm_provider="gemini", gemini_api_keys="key-a,key-b")
    svc = LLMService(settings=settings)
    used_keys: list[str] = []

    def fake_client(api_key=None):
        used_keys.append(api_key)
        return api_key

    monkeypatch.setattr(svc, "_get_gemini_client", fake_client)

    def fake_call(client_key):
        if client_key == "key-a":
            raise RuntimeError("429 RESOURCE_EXHAUSTED: quota exceeded")
        return f"ok:{client_key}"

    result = svc._call_gemini_with_rotation(fake_call)
    assert result == "ok:key-b"
    assert used_keys == ["key-a", "key-b"]


def test_trace_context_and_hitl_feedback_safe_when_disabled():
    settings = _mock_settings()
    trace = TraceContext(settings=settings, filename="sample.pdf", mode="text", tags=["unit"])
    trace.log_span("pdf_parse", as_type="tool", input_payload={"a": 1}, output_payload={"b": 2})
    trace.log_score("extraction_confidence", 0.99, data_type="NUMERIC")
    trace.finalize(output_payload={"status": "VALID"})
    trace.flush()
    record_hitl_feedback(
        settings=settings,
        trace_id=trace.trace_id,
        approved=True,
        gl_code="6100",
        vendor_name="Apex HVAC",
        approved_by="ap_reviewer",
    )


def test_trace_context_logs_otel_spans_scores_and_finalize():
    class _FakeSpan:
        def __init__(self, trace_id: str = "otel-trace-abc") -> None:
            self.trace_id = trace_id
            self.children: list[dict] = []
            self.scores: list[dict] = []
            self.updated: dict | None = None
            self.ended = False

        def start_observation(self, **kwargs):
            child = _FakeSpan()
            self.children.append(kwargs)
            return child

        def score_trace(self, **kwargs):
            self.scores.append(kwargs)

        def update(self, **kwargs):
            self.updated = kwargs

        def end(self):
            self.ended = True

    settings = _mock_settings()
    trace = TraceContext(settings=settings, filename="sample.pdf", mode="text")
    fake_root = _FakeSpan()
    trace._trace = fake_root
    trace._is_otel_span = True

    trace.log_span("math_validation_gate", as_type="guardrail", output_payload={"status": "VALID"})
    trace.log_score("math_gate_passed", 1.0, data_type="BOOLEAN")
    trace.finalize(output_payload={"gl_code": "6100"})
    trace.flush()

    assert fake_root.children[0]["name"] == "math_validation_gate"
    assert fake_root.children[0]["as_type"] == "guardrail"
    assert fake_root.scores[0]["name"] == "math_gate_passed"
    assert fake_root.updated == {"output": {"gl_code": "6100"}, "metadata": None}
    assert fake_root.ended is True
