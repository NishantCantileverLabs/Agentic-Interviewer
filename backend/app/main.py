import logging

import redis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import get_settings
from app.db import engine
from app.routes.admin import router as admin_router
from app.routes.auth import router as auth_router
from app.routes.compliance import router as compliance_router
from app.routes.documents import router as documents_router
from app.routes.execute import router as execute_router
from app.routes.job_roles import router as job_roles_router
from app.routes.lifecycle import router as lifecycle_router
from app.routes.llm_calls import router as llm_calls_router
from app.routes.members import router as members_router
from app.routes.metrics import router as metrics_router
from app.routes.orgs import router as orgs_router
from app.routes.pipelines import router as pipelines_router
from app.routes.results import router as results_router
from app.routes.review import router as review_router
from app.routes.rounds import router as rounds_router
from app.routes.sessions import router as sessions_router

log = logging.getLogger("startup")

_DEV_SECRET_DEFAULTS = {
    "candidate_link_secret": "dev-candidate-secret-change-me",
    "internal_api_key": "dev-internal-key",
    "session_secret": "dev-session-secret-change-me",
}


def validate_production_posture() -> None:
    """Refuse to boot a production deployment that still carries dev defaults.
    In dev, the same problems are warned about so they never surprise anyone
    at deploy time."""
    settings = get_settings()
    problems: list[str] = []
    for field, default in _DEV_SECRET_DEFAULTS.items():
        if getattr(settings, field) == default:
            problems.append(f"{field} is still the dev default")
    if settings.dev_default_org:
        problems.append("DEV_DEFAULT_ORG=true grants anonymous callers admin access")
    if not settings.resend_api_key:
        problems.append("RESEND_API_KEY unset — signup OTPs are returned in API responses")

    if settings.environment == "production":
        if problems:
            raise RuntimeError(
                "refusing to start in production posture: " + "; ".join(problems)
            )
        log.info("production posture validated: no dev defaults in use")
    else:
        for p in problems:
            log.warning("dev posture: %s (must be resolved before production)", p)


validate_production_posture()

app = FastAPI(title="AI Interview Platform — Control Plane", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    # comma-separated origins via APP_BASE_URL + CORS_EXTRA_ORIGINS
    allow_origins=get_settings().cors_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(sessions_router)
app.include_router(execute_router)
app.include_router(admin_router)
app.include_router(llm_calls_router)
app.include_router(results_router)
app.include_router(metrics_router)
app.include_router(documents_router)
app.include_router(orgs_router)
app.include_router(lifecycle_router)
app.include_router(review_router)
app.include_router(compliance_router)
app.include_router(rounds_router)
app.include_router(pipelines_router)
app.include_router(auth_router)
app.include_router(job_roles_router)
app.include_router(members_router)


@app.get("/health")
def health() -> dict[str, str]:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    r = redis.Redis.from_url(get_settings().redis_url, socket_connect_timeout=2)
    r.ping()
    return {"status": "ok"}
