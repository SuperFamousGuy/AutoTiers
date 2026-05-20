from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "postgresql+asyncpg://localhost/autotiers"
    database_url_sync: str = "postgresql+psycopg2://localhost/autotiers"
    debug: bool = False
    cors_origins: list[str] = ["*"]
    run_scheduler: bool = False
    admin_api_key: str = ""


settings = Settings()
