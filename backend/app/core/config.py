from __future__ import annotations

from pathlib import Path
import os

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _resolve_env_file() -> str | None:
    backend_dir = Path(__file__).resolve().parents[2]
    override = os.getenv("ENV_FILE")
    candidates: list[Path] = []

    if override:
        ov_path = Path(override)
        if not ov_path.is_absolute():
            ov_path = backend_dir / ov_path
        candidates.append(ov_path)

    candidates.extend(
        [
            backend_dir / ".env.local",
            backend_dir / ".env",
            backend_dir / ".env.example",
        ]
    )

    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


_ENV_FILE = _resolve_env_file()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    openai_api_key: SecretStr | None = Field(default=None)
    openai_offline: bool = Field(False, alias="OPENAI_OFFLINE")
    database_url: str = Field(...)
    cors_origin: str = Field(...)
    upload_dir: str = Field("data/uploads")
    app_env: str = Field("dev", alias="APP_ENV")
    max_upload_bytes: int = Field(20_000_000, alias="MAX_UPLOAD_BYTES")

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalize_database_url(cls, v: object) -> object:
        """
        Accept common Postgres URL forms and normalize to psycopg(v3) for SQLAlchemy.

        - postgres://...            -> postgresql+psycopg://...
        - postgresql://...          -> postgresql+psycopg://...
        - postgresql+psycopg://...  -> keep as-is
        """
        if not isinstance(v, str):
            return v

        if v.startswith("postgresql+psycopg://"):
            return v

        if v.startswith("postgres://"):
            return "postgresql+psycopg://" + v.split("://", 1)[1]

        if v.startswith("postgresql://"):
            return "postgresql+psycopg://" + v.split("://", 1)[1]

        return v

    @model_validator(mode="after")
    def _validate_env(self) -> "Settings":
        env = (self.app_env or "dev").strip().lower()
        if env == "prod" and bool(self.openai_offline):
            raise ValueError(
                "OPENAI_OFFLINE cannot be enabled in production (APP_ENV=prod)"
            )
        return self


settings = Settings()
