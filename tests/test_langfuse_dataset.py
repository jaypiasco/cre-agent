"""Unit tests for Langfuse prompt resolution and evaluation helpers."""

from app.config import Settings
from app.services.llm_client import EXTRACTION_SYSTEM_PROMPT, TraceContext
from scripts.eval_pipeline import run_eval


def test_resolve_prompt_falls_back_when_langfuse_disabled():
    settings = Settings(llm_provider="mock", langfuse_public_key="", langfuse_secret_key="")
    trace = TraceContext(settings=settings, filename="sample.pdf", mode="text")
    text, prompt_obj = trace.resolve_prompt("cre-invoice-extraction", EXTRACTION_SYSTEM_PROMPT)
    assert text == EXTRACTION_SYSTEM_PROMPT
    assert prompt_obj is None


def test_log_generation_attaches_non_fallback_prompt():
    class _FakeGen:
        def end(self):
            pass

    class _FakeRoot:
        def __init__(self) -> None:
            self.kwargs: dict = {}

        def start_observation(self, **kwargs):
            self.kwargs = kwargs
            return _FakeGen()

    class _FakePrompt:
        is_fallback = False

    settings = Settings(llm_provider="mock", langfuse_public_key="", langfuse_secret_key="")
    trace = TraceContext(settings=settings, filename="sample.pdf", mode="text")
    fake_root = _FakeRoot()
    trace._trace = fake_root
    trace._is_otel_span = True

    fake_prompt = _FakePrompt()
    trace.log_generation(
        name="invoice_extraction",
        model="gemini-3.5-flash-lite",
        input_payload={"mode": "text"},
        output_payload={"vendor": "Apex"},
        prompt=fake_prompt,
    )
    assert fake_root.kwargs["prompt"] is fake_prompt


def test_eval_pipeline_mock_passes():
    assert run_eval("mock") == 0
