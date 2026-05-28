from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "postgresql+asyncpg://localhost/autotiers"
    database_url_sync: str = "postgresql+psycopg2://localhost/autotiers"
    debug: bool = False
    # Specific origins required — wildcards are incompatible with
    # credentialed requests (the frontend's fetch sets
    # `credentials: "include"` so the JWT cookie travels with each request).
    # Override via CORS_ORIGINS env (JSON array, e.g. '["https://app.example.com"]').
    cors_origins: list[str] = ["http://localhost:5173"]
    run_scheduler: bool = False
    admin_api_key: str = ""
    jwt_secret: str = "dev-only-replace-in-prod"
    yahoo_client_id: str = ""
    yahoo_client_secret: str = ""
    yahoo_redirect_uri: str = "http://localhost:8000/api/auth/yahoo/callback"
    frontend_url: str = "http://localhost:5173"


settings = Settings()
