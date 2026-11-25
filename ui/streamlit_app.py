"""Streamlit Human-in-the-Loop (HITL) review workbench for CRE-Agent."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples"

st.set_page_config(
    page_title="CRE-Agent | AP Invoice & GL Coding Workbench",
    page_icon="🏢",
    layout="wide",
)

st.markdown(
    """
    <style>
    .status-badge {
        display: inline-block;
        padding: 0.25rem 0.65rem;
        border-radius: 999px;
        font-size: 0.82rem;
        font-weight: 600;
        letter-spacing: 0.02em;
    }
    .badge-valid {
        background-color: #dcfce7;
        color: #166534;
        border: 1px solid #86efac;
    }
    .badge-review {
        background-color: #fef3c7;
        color: #92400e;
        border: 1px solid #fcd34d;
    }
    .badge-mode {
        background-color: #e0f2fe;
        color: #075985;
        border: 1px solid #7dd3fc;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def fetch_health() -> Optional[Dict[str, Any]]:
    try:
        resp = httpx.get(f"{API_BASE_URL}/health", timeout=5.0)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


def fetch_chart_of_accounts() -> List[Dict[str, Any]]:
    resp = httpx.get(f"{API_BASE_URL}/api/v1/chart-of-accounts", timeout=5.0)
    resp.raise_for_status()
    return resp.json()


def analyze_pdf(filename: str, pdf_bytes: bytes) -> Dict[str, Any]:
    resp = httpx.post(
        f"{API_BASE_URL}/api/v1/invoices/analyze",
        files={"file": (filename, pdf_bytes, "application/pdf")},
        timeout=60.0,
    )
    if resp.status_code >= 400:
        detail = resp.json().get("detail", resp.text)
        raise RuntimeError(detail)
    return resp.json()


def request_export(payload: Dict[str, Any]) -> Dict[str, Any]:
    resp = httpx.post(
        f"{API_BASE_URL}/api/v1/invoices/export",
        json=payload,
        timeout=15.0,
    )
    if resp.status_code >= 400:
        detail = resp.json().get("detail", resp.text)
        raise RuntimeError(detail)
    return resp.json()


# ------------------------------------------------------------------
# Header & Sidebar
# ------------------------------------------------------------------
st.title("CRE-Agent: AP Invoice & GL Coding Workbench")
st.caption(
    "Automated Commercial Real Estate invoice extraction, deterministic math verification, "
    "GL coding, and Human-in-the-Loop Yardi batch export."
)

with st.sidebar:
    st.subheader("System Status")
    health = fetch_health()
    if health:
        st.success(f"API Connected ({health['llm_provider'].upper()})")
        st.caption(
            f"Fast: `{health['fast_model']}`  \n"
            f"Vision: `{health['vision_model']}`  \n"
            f"Langfuse: `{'enabled' if health['langfuse_enabled'] else 'local fallback'}`"
        )
    else:
        st.error(f"Cannot reach FastAPI at `{API_BASE_URL}`")
        st.caption("Start backend with: `uvicorn app.main:app --reload`")

    st.divider()
    st.subheader("1. Select or Upload Invoice")
    sample_files = sorted(SAMPLES_DIR.glob("*.pdf")) if SAMPLES_DIR.exists() else []
    source_mode = st.radio(
        "Invoice Source",
        options=["Upload PDF", "Sample Invoices"] if sample_files else ["Upload PDF"],
        horizontal=True,
    )

    selected_name: Optional[str] = None
    selected_bytes: Optional[bytes] = None

    if source_mode == "Upload PDF":
        uploaded = st.file_uploader("Upload Vendor Invoice (.pdf)", type=["pdf"])
        if uploaded is not None:
            selected_name = uploaded.name
            selected_bytes = uploaded.getvalue()
    else:
        sample_names = [f.name for f in sample_files]
        chosen_sample = st.selectbox("Choose a sample CRE invoice", sample_names)
        if chosen_sample:
            sample_path = SAMPLES_DIR / chosen_sample
            selected_name = chosen_sample
            selected_bytes = sample_path.read_bytes()

    analyze_clicked = st.button(
        "Analyze Invoice",
        type="primary",
        use_container_width=True,
        disabled=selected_bytes is None or health is None,
    )

if analyze_clicked and selected_bytes is not None and selected_name is not None:
    with st.spinner(f"Analyzing `{selected_name}`..."):
        try:
            st.session_state["analysis"] = analyze_pdf(selected_name, selected_bytes)
            st.session_state["source_filename"] = selected_name
            st.session_state["human_approved"] = False
            st.session_state.pop("export_result", None)
        except Exception as exc:
            st.error(f"Analysis failed: {exc}")

analysis: Optional[Dict[str, Any]] = st.session_state.get("analysis")

if not analysis:
    st.info("Select a sample invoice or upload a vendor PDF in the sidebar, then click **Analyze Invoice**.")
    st.stop()

# ------------------------------------------------------------------
# Main Review Workspace
# ------------------------------------------------------------------
invoice = analysis["invoice"]
validation = analysis["validation"]
gl_rec = analysis["gl_recommendation"]

is_valid = validation["status"] == "VALID"
badge_cls = "badge-valid" if is_valid else "badge-review"
badge_label = "Math Verified" if is_valid else "Needs Review"
mode_label = f"{analysis['extraction_mode'].upper()} · {analysis['model_used']}"

st.markdown(
    f'<span class="status-badge {badge_cls}">{badge_label}</span> '
    f'<span class="status-badge badge-mode">{mode_label}</span>',
    unsafe_allow_html=True,
)
st.caption(f"Trace ID: `{analysis.get('trace_id', 'n/a')}` · File: `{st.session_state.get('source_filename', '')}`")

if validation["warnings"]:
    for warn in validation["warnings"]:
        st.warning(warn)

col_left, col_right = st.columns([3, 2], gap="large")

with col_left:
    st.subheader("Extracted Invoice Data")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Amount Due", f"${invoice['amount_due']:,.2f}")
    m2.metric("Subtotal", f"${invoice['subtotal']:,.2f}")
    m3.metric("Tax", f"${invoice['tax_amount']:,.2f}")
    m4.metric("Confidence", f"{invoice['extraction_confidence']:.0%}")

    h1, h2 = st.columns(2)
    h1.text_input("Vendor Name", value=invoice["vendor_name"], disabled=True)
    h2.text_input("Invoice Number", value=invoice["invoice_number"], disabled=True)

    h3, h4 = st.columns(2)
    h3.text_input("Invoice Date", value=invoice["invoice_date"], disabled=True)
    h4.text_input("Due Date", value=invoice.get("due_date") or "—", disabled=True)

    st.text_input("Property Address", value=invoice["property_address"], disabled=True)

    st.markdown("**Line Items**")
    st.dataframe(
        invoice["line_items"],
        use_container_width=True,
        hide_index=True,
        column_config={
            "description": "Description",
            "quantity": st.column_config.NumberColumn("Qty", format="%.2f"),
            "unit_price": st.column_config.NumberColumn("Unit Price", format="$%.2f"),
            "line_total": st.column_config.NumberColumn("Line Total", format="$%.2f"),
        },
    )

with col_right:
    st.subheader("GL Account Coding")
    try:
        coa = fetch_chart_of_accounts()
    except Exception as exc:
        st.error(f"Could not load Chart of Accounts: {exc}")
        st.stop()

    coa_options = {f"{c['gl_code']} — {c['account_name']}": c for c in coa}
    default_label = next(
        (lbl for lbl, c in coa_options.items() if c["gl_code"] == gl_rec["gl_code"]),
        next(iter(coa_options)),
    )
    option_list = list(coa_options.keys())
    selected_gl_label = st.selectbox(
        "Recommended GL Code (Override if needed)",
        options=option_list,
        index=option_list.index(default_label),
    )
    chosen_gl = coa_options[selected_gl_label]

    st.info(
        f"**AI Rationale ({gl_rec['gl_confidence']:.0%} confidence):**\n\n{gl_rec['explanation']}"
    )

    st.divider()
    st.subheader("Human-in-the-Loop Approval & Yardi Export")

    reviewer_name = st.text_input("Reviewer / Approver", value="ap_reviewer")
    batch_id = st.text_input(
        "Yardi Batch ID",
        value=f"BATCH-{datetime.now(timezone.utc).strftime('%Y%m%d')}-001",
    )

    human_approved = st.toggle(
        "Human Approval: Approved",
        key="human_approved",
        help="Export remains locked until an AP reviewer explicitly approves this invoice.",
    )

    if st.button(
        "Generate Yardi Export Payload",
        type="primary",
        use_container_width=True,
        disabled=not human_approved,
    ):
        payload = {
            "batch_id": batch_id,
            "vendor_name": invoice["vendor_name"],
            "invoice_number": invoice["invoice_number"],
            "invoice_date": invoice["invoice_date"],
            "property_address": invoice["property_address"],
            "gl_code": chosen_gl["gl_code"],
            "gl_account_name": chosen_gl["account_name"],
            "amount_due": invoice["amount_due"],
            "human_approved": True,
            "approved_by": reviewer_name or "ap_reviewer",
            "approved_at": datetime.now(timezone.utc).isoformat(),
            "langfuse_trace_id": analysis.get("trace_id"),
        }
        try:
            st.session_state["export_result"] = request_export(payload)
        except Exception as exc:
            st.error(f"Export failed: {exc}")

    export_result: Optional[Dict[str, Any]] = st.session_state.get("export_result")
    if export_result:
        st.success("Yardi export payload generated.")
        dl1, dl2 = st.columns(2)
        dl1.download_button(
            label="Download Yardi CSV",
            data=export_result["csv_content"],
            file_name=export_result["filename"],
            mime="text/csv",
            use_container_width=True,
        )
        dl2.download_button(
            label="Download Audit JSON",
            data=json.dumps(export_result["json_payload"], indent=2),
            file_name=export_result["filename"].replace(".csv", ".json"),
            mime="application/json",
            use_container_width=True,
        )
        with st.expander("Preview Yardi CSV & JSON"):
            st.code(export_result["csv_content"], language="csv")
            st.json(export_result["json_payload"])
