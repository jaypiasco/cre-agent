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


def run_dataset_experiment(provider: str, run_name: str) -> int:
    """Run a Langfuse Dataset Experiment against `cre-golden-invoices`."""
    from langfuse import Evaluation, Langfuse

    settings = Settings(llm_provider=provider)  # type: ignore[arg-type]
    if not settings.langfuse_enabled:
        raise RuntimeError("Langfuse credentials are required for --dataset-run.")

    client = Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        base_url=settings.langfuse_base_url or settings.langfuse_host,
        environment=settings.langfuse_environment,
    )
    dataset = client.get_dataset("cre-golden-invoices")
    llm = LLMService(settings=settings)
    coa = load_chart_of_accounts()

    def task(*, item, **kwargs):
        filename = item.input["filename"]
        pdf_path = SAMPLES_DIR / filename
        parsed = parse_pdf(
            pdf_bytes=pdf_path.read_bytes(),
            min_chars_per_page=settings.pdf_min_chars_per_page,
            max_vision_pages=settings.pdf_max_vision_pages,
            dpi=settings.pdf_render_dpi,
        )
        dummy_trace = TraceContext(
            settings=Settings(llm_provider=provider, langfuse_public_key="", langfuse_secret_key=""),  # type: ignore[arg-type]
            filename=filename,
            mode=parsed.mode,
        )
        invoice, _ = llm.extract_invoice(parsed, dummy_trace)
        validation = validate_invoice(
            invoice,
            confidence_threshold=settings.confidence_threshold,
            math_tolerance=settings.math_tolerance,
        )
        gl = llm.match_gl_account(invoice, coa, dummy_trace)
        return {
            "mode": parsed.mode,
            "gl_code": gl.gl_code,
            "status": validation.status,
            "confidence": round(invoice.extraction_confidence, 4),
        }

    def gl_accuracy_evaluator(*, output, expected_output, **kwargs):
        matched = output.get("gl_code") == expected_output.get("gl_code")
        return Evaluation(name="gl_code_match", value=1.0 if matched else 0.0)

    def status_evaluator(*, output, expected_output, **kwargs):
        exp_status = expected_output.get("status")
        valid_set = {"VALID", "NEEDS_REVIEW"} if exp_status == "VALID_OR_NEEDS_REVIEW" else {exp_status}
        matched = output.get("status") in valid_set
        return Evaluation(name="status_match", value=1.0 if matched else 0.0)

    result = dataset.run_experiment(
        name=run_name,
        description=f"CRE-Agent golden invoice evaluation (provider={provider})",
        task=task,
        evaluators=[gl_accuracy_evaluator, status_evaluator],
        metadata={"provider": provider, "environment": settings.langfuse_environment},
    )
    client.flush()
    print(f"Langfuse Dataset Experiment '{run_name}' completed: {len(result.item_results)} items.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate CRE-Agent pipeline on sample PDFs.")
    parser.add_argument(
        "--provider",
        default=os.getenv("LLM_PROVIDER", "mock"),
        choices=["mock", "gemini", "openai", "anthropic"],
        help="LLM provider to evaluate (default: LLM_PROVIDER env or mock).",
    )
    parser.add_argument(
        "--dataset-run",
        default="",
        help="Optional Langfuse Dataset Experiment run name against 'cre-golden-invoices'.",
    )
    args = parser.parse_args()
    if args.dataset_run:
        sys.exit(run_dataset_experiment(args.provider, args.dataset_run))
    sys.exit(run_eval(args.provider))


if __name__ == "__main__":
    main()
