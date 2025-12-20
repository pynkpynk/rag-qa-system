from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    - Render: env vars が本番の正。DATABASE_URL が必須。
    - Local: .env があれば読む（無くても env var で動く）
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        case_sensitive=False,
    )

    # 明示的に env 名を指定（Renderでの事故を減らす）
    database_url: str = Field(validation_alias="DATABASE_URL")

    cors_origins: str = "http://localhost:5173"


settings = Settings()
