from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "postgresql+asyncpg://localhost/autotiers"
    database_url_sync: str = "postgresql+psycopg2://localhost/autotiers"
    debug: bool = False
    # No credentialed cookies travel anymore (accounts/auth were removed), but
    # explicit origins are still required over a wildcard for a locked-down
    # CORS policy. Override via CORS_ORIGINS env (JSON array, e.g.
    # '["https://app.example.com"]').
    cors_origins: list[str] = ["http://localhost:5173"]
    run_scheduler: bool = False
    admin_api_key: str = ""
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

    @field_validator("trusted_proxy_count")
    @classmethod
    def _non_negative_trusted_proxy_count(cls, v: int) -> int:
        # A negative hop count would silently corrupt rate-limit keying (all
        # clients could bucket under the proxy IP behind the ALB). Fail fast at
        # startup rather than degrade at runtime.
        if v < 0:
            raise ValueError("trusted_proxy_count must be non-negative")
        return v


settings = Settings()
