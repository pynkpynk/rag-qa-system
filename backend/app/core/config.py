from __future__ import annotations

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: SecretStr = Field(...)
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
            raise ValueError("OPENAI_OFFLINE cannot be enabled in production (APP_ENV=prod)")
        return self


settings = Settings()
