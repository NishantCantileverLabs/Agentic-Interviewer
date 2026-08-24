from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

engine = create_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """UNSCOPED session — RLS denies tenant rows until context is set.
    Request handlers must use app.tenancy.get_db instead; this remains for
    non-tenant paths (health) and worker code that sets context explicitly."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def set_rls_context(db: Session, org_id: str | None = None, bypass: bool = False) -> None:
    """Worker-path RLS context (invariant #8: workers set org explicitly)."""
    from sqlalchemy import text

    db.execute(
        text("SELECT set_config('app.current_org', :o, false)"),
        {"o": org_id or ""},
    )
    db.execute(
        text("SELECT set_config('app.bypass_rls', :b, false)"),
        {"b": "on" if bypass else "off"},
    )
