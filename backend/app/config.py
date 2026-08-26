from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # "dev" | "production". Production refuses to boot with default secrets,
    # disables the dev header-auth stub, and never surfaces dev_otp.
    environment: str = "dev"

    @field_validator("environment")
    @classmethod
    def _canonical_environment(cls, v: str) -> str:
        """Every production gate compares against the exact string
        "production" — a typo ('prod', 'Production ', 'PROD') must not
        silently fail open into dev behavior. Normalize the common aliases
        and refuse anything unrecognized at boot."""
        norm = v.strip().lower()
        if norm in ("prod", "production"):
            return "production"
        if norm in ("dev", "development", "local", "test"):
            return norm if norm == "test" else "dev"
        raise ValueError(
            f"ENVIRONMENT={v!r} is not a recognized value (dev | production); "
            "refusing to guess which security posture you meant"
        )

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
    # Public-facing URL the browser uses to reach LiveKit (must be wss:// in
    # production).  Falls back to livekit_url for local dev where Caddy isn't
    # in front.
    livekit_public_url: str = ""
    livekit_api_key: str = "devkey"
    livekit_api_secret: str = "secret"

    s3_endpoint: str = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "recordings"

    judge0_url: str = "http://localhost:2358"
    # sent as X-Auth-Token when set; production requires it (judge0.conf
    # AUTHN_TOKEN must match) so a reachable Judge0 is never an open RCE
    judge0_auth_token: str = ""
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
    # fail-closed: anonymous default-org access is something a dev opts INTO
    # (.env DEV_DEFAULT_ORG=true), never something a deployment forgets to
    # turn off
    dev_default_org: bool = False
    # practice interviews (POST /auth/demo); isolated in the demo org
    demo_enabled: bool = True

    # Accounts (login / signup)
    session_secret: str = "dev-session-secret-change-me"
    session_ttl_h: int = 24 * 7
    otp_ttl_min: int = 10
    google_client_id: str = ""  # enables "Sign in with Google" when set
    # production only: the first-user-bootstraps-admin path requires this
    # email to match, closing the fresh-deploy race where whoever registers
    # first owns the org
    first_admin_email: str = ""


    # extra browser origins allowed by CORS, comma-separated (prod domains)
    cors_extra_origins: str = ""

    def cors_origins(self) -> list[str]:
        origins = [self.app_base_url]
        origins += [o.strip() for o in self.cors_extra_origins.split(",") if o.strip()]
        return origins


@lru_cache
def get_settings() -> Settings:
    return Settings()


_DEV_SECRET_DEFAULTS = {
    "candidate_link_secret": "dev-candidate-secret-change-me",
    "internal_api_key": "dev-internal-key",
    "session_secret": "dev-session-secret-change-me",
}
# secrets that sign tokens need real entropy, not just a non-default value
_MIN_SECRET_LEN = {"candidate_link_secret": 32, "internal_api_key": 16, "session_secret": 32}


def production_posture_problems() -> list[str]:
    """Every dev default the deployment still carries, one entry per env var
    so the boot error names exactly what blocked it. Shared by the API and
    the eval worker; the voice agent mirrors it in agent/interview_agent.py."""
    settings = get_settings()
    problems: list[str] = []
    for field, default in _DEV_SECRET_DEFAULTS.items():
        value = getattr(settings, field)
        if value == default:
            problems.append(f"{field.upper()}: still the dev default")
        elif len(value) < _MIN_SECRET_LEN[field]:
            problems.append(
                f"{field.upper()}: shorter than {_MIN_SECRET_LEN[field]} chars — "
                "empty or weak signing secrets are as bad as dev defaults"
            )
    if settings.dev_default_org:
        problems.append("DEV_DEFAULT_ORG: true grants anonymous callers admin access")
    if not settings.resend_api_key:
        problems.append(
            "RESEND_API_KEY: unset — signup OTPs cannot be delivered, so no one can register"
        )
    if settings.livekit_api_key == "devkey" or settings.livekit_api_secret == "secret":
        problems.append(
            "LIVEKIT_API_KEY/SECRET: dev defaults — anyone can forge room-join tokens"
        )
    if settings.s3_access_key == "minioadmin" or settings.s3_secret_key == "minioadmin":
        problems.append("S3_ACCESS_KEY/S3_SECRET_KEY: minioadmin dev defaults")
    if ":interview@" in settings.database_url or "app_user_dev_pass" in settings.database_url:
        problems.append("DATABASE_URL: carries a dev password")
    if not settings.judge0_auth_token:
        problems.append(
            "JUDGE0_AUTH_TOKEN: unset — a reachable Judge0 without AUTHN is arbitrary "
            "code execution for anyone on its network"
        )
    if "localhost" in settings.app_base_url or "127.0.0.1" in settings.app_base_url:
        problems.append("APP_BASE_URL: still points at localhost")
    if not settings.first_admin_email:
        problems.append(
            "FIRST_ADMIN_EMAIL: unset — whoever registers first on a fresh deploy "
            "would bootstrap as org admin"
        )
    return problems


def validate_production_posture() -> None:
    """Refuse to boot a production deployment that still carries dev defaults.
    In dev, the same problems are warned about so they never surprise anyone
    at deploy time."""
    import logging

    log = logging.getLogger("startup")
    settings = get_settings()
    problems = production_posture_problems()
    if settings.environment == "production":
        if problems:
            checklist = "\n".join(f"  x {p}" for p in problems)
            raise RuntimeError(
                f"refusing to start in production posture — fix these first:\n{checklist}"
            )
        log.info("production posture validated: no dev defaults in use")
    else:
        for p in problems:
            log.warning("dev posture: %s (must be resolved before production)", p)
