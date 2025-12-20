from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ローカルは .env から読める（無ければ env var のみ）
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Render では環境変数で必ず渡す（必須）
    database_url: str

    # 無いときはローカル開発のデフォルトに倒す
    cors_origins: str = "http://localhost:5173"


settings = Settings()
