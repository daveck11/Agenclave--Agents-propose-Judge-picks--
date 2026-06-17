# Central configuration. Reads .env; nothing here requires keys for Stage 1.

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo-root-relative paths so scripts work regardless of CWD.
ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
MODELS_DIR = ROOT / "models"
RESULTS_DIR = ROOT / "results"


class Settings(BaseSettings):
    # Runtime settings, overridable via environment / .env.

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Provider selection (Stage 2) ---
    # "direct" -> Claude/OpenAI; "blackbox" -> BlackBox Agents API.
    provider: str = "direct"
    agent_models: str = "claude-sonnet-4-6,gpt-4o-mini"
    chairman_model: str = "claude-opus-4-8"

    # --- Keys (Stage 2 only) ---
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    blackbox_api_key: str | None = None
    blackbox_api_base: str = "https://cloud.blackbox.ai/api"

    @property
    def agent_model_list(self) -> list[str]:
        return [m.strip() for m in self.agent_models.split(",") if m.strip()]


settings = Settings()
