from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # "dev" | "production". Production refuses to boot with default secrets,
    # disables the dev header-auth stub, and never surfaces dev_otp.
    environment: str = "dev"

    database_url: str = "postgresql+psycopg://interview:interview@localhost:5432/interview"
    # migrations run as the table owner; the app runs as non-superuser app_user
    migrations_database_url: str = ""
    redis_url: str = "redis://localhost:6379/0"

    llm_provider: str = "anthropic"  # anthropic | openrouter
    anthropic_api_key: str = ""
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    conduct_model: str = "claude-haiku-4-5"
    eval_model: str = "claude-opus-5"
    prompt_cache_enabled: bool = True

    livekit_url: str = "ws://localhost:7880"
    livekit_api_key: str = "devkey"
    livekit_api_secret: str = "secret"

    s3_endpoint: str = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "recordings"

    judge0_url: str = "http://localhost:2358"
    exec_cpu_limit_s: int = 5
    exec_mem_mb: int = 256

    eval_queue: str = "evaluate_session"
    retention_days_default: int = 90

    # T11 lifecycle
    resend_api_key: str = ""
    email_from: str = "interviews@example.dev"
    app_base_url: str = "http://localhost:3000"
    reschedule_max: int = 2
    reschedule_cutoff_h: int = 2
    org_max_concurrent_sessions_default: int = 5
    consent_policy_version: str = "2026-08-23.1"

    # T10 tenancy
    candidate_link_secret: str = "dev-candidate-secret-change-me"
    candidate_link_ttl_h: int = 24
    internal_api_key: str = "dev-internal-key"
    dev_default_org: bool = True  # Phase 1 UI compatibility; off in production

    # Accounts (login / signup)
    session_secret: str = "dev-session-secret-change-me"
    session_ttl_h: int = 24 * 7
    otp_ttl_min: int = 10
    google_client_id: str = ""  # enables "Sign in with Google" when set


    # extra browser origins allowed by CORS, comma-separated (prod domains)
    cors_extra_origins: str = ""

    def cors_origins(self) -> list[str]:
        origins = [self.app_base_url]
        origins += [o.strip() for o in self.cors_extra_origins.split(",") if o.strip()]
        return origins


@lru_cache
def get_settings() -> Settings:
    return Settings()
