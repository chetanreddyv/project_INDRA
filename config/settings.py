"""
config/settings.py — Centralized configuration via Pydantic Settings.

All env vars are loaded from .env and validated at startup.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # ── Telegram ──────────────────────────────────────────────
    telegram_bot_token: str = Field(..., description="Telegram bot token from @BotFather")
    telegram_secret_token: str = Field(
        default="", description="Secret token for webhook verification"
    )
    allowed_chat_ids: str = Field(
        default="", description="Comma-separated list of allowed Telegram chat IDs"
    )

    # ── LLM (Gemini) ─────────────────────────────────────────
    google_api_key: str = Field(..., description="Google AI Studio API key (used by Pydantic AI)")

    # ── Observability (optional) ──────────────────────────────
    langchain_tracing_v2: bool = Field(default=False)
    langsmith_api_key: Optional[str] = Field(default=None)
    logfire_token: Optional[str] = Field(default=None)

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    @property
    def allowed_chat_id_list(self) -> list[int]:
        """Parse comma-separated chat IDs into a list of ints."""
        if not self.allowed_chat_ids:
            return []
        return [int(cid.strip()) for cid in self.allowed_chat_ids.split(",") if cid.strip()]


# Singleton — import this across the app
settings = Settings()
