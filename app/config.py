"""Application configuration loaded from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for CRE-Agent."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_provider: Literal["openai", "anthropic", "mock"] = "openai"

    openai_api_key: str = ""
    openai_fast_model: str = "gpt-4o-mini"
    openai_vision_model: str = "gpt-4o"

    anthropic_api_key: str = ""
    anthropic_fast_model: str = "claude-3-5-haiku-latest"
    anthropic_vision_model: str = "claude-3-5-sonnet-latest"

    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    api_base_url: str = "http://127.0.0.1:8000"

    # PDF & validation thresholds
    pdf_min_chars_per_page: int = 50
    pdf_max_vision_pages: int = 5
    pdf_render_dpi: int = 150
    confidence_threshold: float = 0.90
    math_tolerance: float = 0.02

    @property
    def langfuse_enabled(self) -> bool:
        """Return True when both Langfuse keys are configured."""
        return bool(self.langfuse_public_key.strip() and self.langfuse_secret_key.strip())


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
