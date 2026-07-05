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
    # Recipient inbox for in-app "Provide Feedback" submissions. Must be a verified
    # SES recipient while SES is in sandbox (we send to this fixed address, not to the
    # submitting user). Override via FEEDBACK_RECIPIENT env. Not hardcoded in the route.
    feedback_recipient: str = "feedback@autotiers.example"
    # Data-freshness alarm threshold (issue #401). The /api/data/health endpoint
    # reports `stale` (and returns HTTP 503) when the oldest source's
    # last_attempted is older than this many hours — catching a scheduler that
    # has crash-looped or frozen and stopped refreshing data. Override via
    # DATA_FRESHNESS_THRESHOLD_HOURS.
    data_freshness_threshold_hours: float = 2.0
    # Number of trusted reverse-proxy hops in front of the app (issue #519). In
    # production ECS Fargate sits behind a single ALB, so the default is 1. The
    # ALB does NOT strip a client-supplied X-Forwarded-For; it appends the real
    # peer IP to the right of whatever the client sent. Rate-limit keying reads
    # the entry this many hops from the right so a client can't forge its bucket
    # by sending its own XFF. Set to 0 only when there is no trusted proxy (the
    # app is directly internet-facing) — then XFF is fully untrusted and only the
    # socket peer is used. Override via TRUSTED_PROXY_COUNT.
    trusted_proxy_count: int = 1


settings = Settings()
