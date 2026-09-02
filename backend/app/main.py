import redis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import get_settings, validate_production_posture
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

validate_production_posture()

_IS_PROD = get_settings().environment == "production"
app = FastAPI(
    title="AI Interview Platform — Control Plane",
    version="0.1.0",
    # interactive API docs are a dev tool; production keeps the schema private
    docs_url=None if _IS_PROD else "/docs",
    redoc_url=None if _IS_PROD else "/redoc",
    openapi_url=None if _IS_PROD else "/openapi.json",
)
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
