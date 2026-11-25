"""Golden evaluation harness across sample CRE vendor invoice PDFs."""

import argparse
import os
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.config import Settings  # noqa: E402
from app.services.exporter import load_chart_of_accounts  # noqa: E402
from app.services.llm_client import LLMService, TraceContext  # noqa: E402
from app.services.pdf_parser import parse_pdf  # noqa: E402
from app.services.validator import validate_invoice  # noqa: E402

SAMPLES_DIR = ROOT_DIR / "samples"

EXPECTED = {
    "hvac_apex_inv_88412.pdf": {
        "mode": "text",
        "gl_code": "6100",
        "status": "VALID",
    },
    "roofing_summit_scr_4419.pdf": {
        "mode": "text",
        "gl_code": "6200",
        "status": "VALID",
    },
    "landscaping_greenview_scanned.pdf": {
        "mode": "vision",
        "gl_code": "6300",
        "status": {"VALID", "NEEDS_REVIEW"},
    },
    "utility_math_error_sample.pdf": {
        "mode": "text",
        "gl_code": "6500",
        "status": "NEEDS_REVIEW",
    },
}


def run_eval(provider: str) -> int:
    """Run extraction, validation, and GL matching across all sample PDFs."""
    settings = Settings(llm_provider=provider)  # type: ignore[arg-type]
    llm = LLMService(settings=settings)
    coa = load_chart_of_accounts()

    print(f"### CRE-Agent Evaluation Report (`LLM_PROVIDER={provider}`)\n")
    print("| Sample PDF | Mode | GL Code | Status | Latency (ms) | Pass |")
    print("| :--- | :--- | :--- | :--- | ---: | :---: |")

    all_passed = True
    for filename, exp in EXPECTED.items():
        pdf_path = SAMPLES_DIR / filename
        if not pdf_path.exists():
            print(f"| `{filename}` | - | - | MISSING | 0 | FAIL |")
            all_passed = False
            continue

        start = time.perf_counter()
        parsed = parse_pdf(
            pdf_bytes=pdf_path.read_bytes(),
            min_chars_per_page=settings.pdf_min_chars_per_page,
            max_vision_pages=settings.pdf_max_vision_pages,
            dpi=settings.pdf_render_dpi,
        )
        trace = TraceContext(
            settings=settings,
            filename=filename,
            mode=parsed.mode,
            tags=["eval"],
            trace_name="cre_invoice_eval",
        )
        trace.log_span(
            name="pdf_parse",
            as_type="tool",
            input_payload={"filename": filename},
            output_payload={"mode": parsed.mode, "page_count": parsed.page_count},
        )
        invoice, model_used = llm.extract_invoice(parsed, trace)
        validation = validate_invoice(
            invoice,
            confidence_threshold=settings.confidence_threshold,
            math_tolerance=settings.math_tolerance,
        )
        trace.log_span(
            name="math_validation_gate",
            as_type="guardrail",
            input_payload={"amount_due": invoice.amount_due, "confidence": invoice.extraction_confidence},
            output_payload=validation.model_dump(mode="json"),
            level="WARNING" if validation.status == "NEEDS_REVIEW" else "DEFAULT",
        )
        gl = llm.match_gl_account(invoice, coa, trace)

        expected_statuses = (
            exp["status"] if isinstance(exp["status"], set) else {exp["status"]}
        )
        passed = (
            parsed.mode == exp["mode"]
            and gl.gl_code == exp["gl_code"]
            and validation.status in expected_statuses
        )
        trace.log_score(
            name="extraction_confidence",
            value=round(invoice.extraction_confidence, 4),
            data_type="NUMERIC",
        )
        trace.log_score(
            name="math_gate_passed",
            value=1.0 if validation.math_valid else 0.0,
            data_type="BOOLEAN",
        )
        trace.log_score(
            name="eval_passed",
            value=1.0 if passed else 0.0,
            data_type="BOOLEAN",
            comment=f"expected_gl={exp['gl_code']} actual_gl={gl.gl_code}",
        )
        trace.finalize(
            output_payload={
                "vendor_name": invoice.vendor_name,
                "invoice_number": invoice.invoice_number,
                "amount_due": invoice.amount_due,
                "gl_code": gl.gl_code,
                "validation_status": validation.status,
                "eval_passed": passed,
            },
            metadata={"model_used": model_used, "eval_passed": passed},
        )
        trace.flush()
        latency_ms = (time.perf_counter() - start) * 1000

        if not passed:
            all_passed = False

        badge = "PASS" if passed else "FAIL"
        print(
            f"| `{filename}` | `{parsed.mode}` | `{gl.gl_code}` | "
            f"`{validation.status}` | {latency_ms:.1f} | {badge} |"
        )

    return 0 if all_passed else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate CRE-Agent pipeline on sample PDFs.")
    parser.add_argument(
        "--provider",
        default=os.getenv("LLM_PROVIDER", "mock"),
        choices=["mock", "gemini", "openai", "anthropic"],
        help="LLM provider to evaluate (default: LLM_PROVIDER env or mock).",
    )
    args = parser.parse_args()
    sys.exit(run_eval(args.provider))


if __name__ == "__main__":
    main()
