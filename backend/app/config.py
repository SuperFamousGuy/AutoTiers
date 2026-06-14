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
    # Fernet key — base64-urlsafe 32 bytes. Override in production.
    # Generate one with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    secret_key: str = "dKkY-w0jHF6kBE_oTzx7JtAYxHB1yyaJYBNz3X1eYdY="
    yahoo_client_id: str = ""
    yahoo_client_secret: str = ""
    yahoo_redirect_uri: str = "http://localhost:8000/api/auth/yahoo/callback"
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/auth/google/callback"
    frontend_url: str = "http://localhost:5173"
    # Email sender configuration.
    # email_sender_backend: "ses" sends via AWS SES (requires ECS task role with ses:SendEmail).
    #                        "fake" (or any other value) collects emails in-process — used in
    #                        development and ALL tests.  When debug=True the fake sender is
    #                        always used regardless of this setting.
    email_sender_backend: str = "fake"
    ses_from_address: str = "AutoTiers <noreply@autotiers.example>"
    ses_region: str = "us-east-1"


settings = Settings()
