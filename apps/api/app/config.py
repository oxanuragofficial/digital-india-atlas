"""Application settings, loaded from environment variables and an optional `.env` file.

Security notes:
- There are deliberately NO default credentials. If DATABASE_URL is unset the API still
  starts, and database-dependent endpoints report "not configured".
- The database URL is a SecretStr so it is masked in reprs/logs.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]
PLACEHOLDER_MARKERS = ("CHANGE_ME", "changeme", "<password>")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"
    database_url: SecretStr | None = None
    cors_allowed_origins: str = "http://localhost:3000"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    @model_validator(mode="after")
    def _reject_placeholder_secrets_in_production(self) -> Settings:
        if self.app_env == "production":
            if self.database_url is None:
                raise ValueError("DATABASE_URL must be set when APP_ENV=production")
            raw = self.database_url.get_secret_value()
            if any(marker.lower() in raw.lower() for marker in PLACEHOLDER_MARKERS):
                raise ValueError("DATABASE_URL contains a placeholder value")
            if "*" in self.cors_origins:
                raise ValueError("CORS_ALLOWED_ORIGINS must not contain '*' in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
