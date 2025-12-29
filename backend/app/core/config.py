from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: str = Field(...)
    openai_offline: bool = Field(False, alias="OPENAI_OFFLINE")
    database_url: str = Field(...)
    cors_origin: str = Field(...)
    upload_dir: str = Field("data/uploads")

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


settings = Settings()
