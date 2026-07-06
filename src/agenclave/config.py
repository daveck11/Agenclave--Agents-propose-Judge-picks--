# Central configuration. Reads .env; nothing here requires keys for Stage 1.

from __future__ import annotations

from pathlib import Path

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo-root-relative paths so scripts work regardless of CWD.
ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
MODELS_DIR = ROOT / "models"
RESULTS_DIR = ROOT / "results"


class Settings(BaseSettings):
    # Runtime settings, overridable via environment / .env.
    #
    # The app's own settings use the AGENCLAVE_ prefix (e.g. AGENCLAVE_PROVIDER,
    # AGENCLAVE_AGENT_MODELS) so they never clash with unrelated env vars. The API
    # keys deliberately keep their conventional vendor names (ANTHROPIC_API_KEY,
    # OPENAI_API_KEY, BLACKBOX_API_KEY) - so this app and the SDKs read the same
    # variable - while still accepting the AGENCLAVE_-prefixed form.
    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="AGENCLAVE_", extra="ignore"
    )

    # --- Provider selection (Stage 2) ---
    # "direct" -> Claude/OpenAI; "blackbox" -> everything via BlackBox's API.
    provider: str = "direct"
    agent_models: str = "claude-sonnet-4-6,gpt-4o-mini"
    chairman_model: str = "claude-opus-4-8"
    # Trust-scored routing: dispatch only the top-`route_k` models for a task's
    # category (Thompson sampling over per-model reliability). route() returns
    # min(route_k, len(panel)), so a small panel is used whole.
    route_k: int = 3

    # --- Keys (Stage 2 only; read from the conventional names, prefix optional) ---
    anthropic_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("ANTHROPIC_API_KEY", "AGENCLAVE_ANTHROPIC_API_KEY"),
    )
    openai_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENAI_API_KEY", "AGENCLAVE_OPENAI_API_KEY"),
    )
    blackbox_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("BLACKBOX_API_KEY", "AGENCLAVE_BLACKBOX_API_KEY"),
    )
    # BlackBox exposes an OpenAI-compatible API; this is the client base_url the
    # adapter points the OpenAI SDK at. Override via AGENCLAVE_BLACKBOX_API_BASE.
    blackbox_api_base: str = "https://api.blackbox.ai/v1"

    # --- Accounts / persistence (Stage 3) ---
    # Override the secret in production via SECRET_KEY (or AGENCLAVE_SECRET_KEY).
    secret_key: str = Field(
        default="dev-insecure-change-me-in-prod",
        validation_alias=AliasChoices("SECRET_KEY", "AGENCLAVE_SECRET_KEY"),
    )
    access_token_expire_minutes: int = 60 * 24 * 7  # one week
    database_url: str = Field(
        default=f"sqlite+aiosqlite:///{DATA_DIR}/agenclave.db",
        # Accept the conventional DATABASE_URL (what Render/Neon inject) as well as
        # the prefixed form, so account persistence works with either name.
        validation_alias=AliasChoices("DATABASE_URL", "AGENCLAVE_DATABASE_URL"),
    )

    @property
    def agent_model_list(self) -> list[str]:
        return [m.strip() for m in self.agent_models.split(",") if m.strip()]

    @field_validator("database_url")
    @classmethod
    def _normalize_db_url(cls, v: str) -> str:
        # Accept a plain Postgres URL as-is (e.g. Neon:
        # postgresql://user:pass@host/db?sslmode=require) and coerce it to the async
        # driver, dropping libpq-only query params asyncpg rejects. SSL for Postgres
        # is enabled via connect_args in api/db.py.
        for prefix in ("postgresql://", "postgres://"):
            if v.startswith(prefix):
                v = "postgresql+asyncpg://" + v[len(prefix):]
                break
        if v.startswith("postgresql+asyncpg://") and "?" in v:
            v = v.split("?", 1)[0]
        return v


settings = Settings()
