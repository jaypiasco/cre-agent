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

    llm_provider: Literal["openai", "anthropic", "gemini", "mock"] = "gemini"

    openai_api_key: str = ""
    openai_fast_model: str = "gpt-6-luna"
    openai_vision_model: str = "gpt-6.2-sol"

    anthropic_api_key: str = ""
    anthropic_fast_model: str = "claude-haiku-5-5"
    anthropic_vision_model: str = "claude-sonnet-5-5"

    gemini_api_key: str = ""
    gemini_api_keys: str = ""
    gemini_fast_model: str = "gemini-3.8-flash"
    gemini_vision_model: str = "gemini-3.8-flash"

    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"
    langfuse_base_url: str = ""
    langfuse_environment: str = "dev"

    api_base_url: str = "http://127.0.0.1:8000"

    # PDF & validation thresholds
    pdf_min_chars_per_page: int = 50
    pdf_max_vision_pages: int = 5
    pdf_render_dpi: int = 150
    confidence_threshold: float = 0.90
    math_tolerance: float = 0.02

    @property
    def gemini_key_list(self) -> list[str]:
        """Return configured Gemini API keys, preferring comma-separated GEMINI_API_KEYS."""
        keys = [k.strip() for k in self.gemini_api_keys.split(",") if k.strip()]
        if keys:
            return keys
        single = self.gemini_api_key.strip()
        return [single] if single else []

    @property
    def langfuse_enabled(self) -> bool:
        """Return True when both Langfuse keys are configured."""
        return bool(self.langfuse_public_key.strip() and self.langfuse_secret_key.strip())


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
