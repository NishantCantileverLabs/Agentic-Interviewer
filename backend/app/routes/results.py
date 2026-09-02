"""Evaluation + brief retrieval."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from minio import Minio
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.config import get_settings
from app.models import Brief, Evaluation, Session
from app.tenancy import OrgContext, get_db, require_role

router = APIRouter()


@router.get("/sessions/{session_id}/evaluation")
def get_evaluation(
    session_id: uuid.UUID,
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(require_role("reviewer")),
) -> dict[str, Any]:
    # Scores are org-side only — candidates never see them (spec §7 hard rule).
    ev = db.scalar(
        select(Evaluation)
        .where(Evaluation.session_id == session_id)
        .order_by(Evaluation.version.desc())
        .limit(1)
    )
    if ev is None:
        raise HTTPException(404, "no evaluation for this session yet")
    return {
        "id": str(ev.id),
        "version": ev.version,
        "model": ev.model,
        "rubric": ev.rubric,
        "signals": ev.signals,
        "created_at": ev.created_at.isoformat(),
    }


@router.get("/sessions/{session_id}/brief")
def get_brief(
    session_id: uuid.UUID,
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(require_role("reviewer")),
) -> dict[str, Any]:
    brief = db.scalar(
        select(Brief)
        .where(Brief.session_id == session_id)
        .order_by(Brief.created_at.desc())
        .limit(1)
    )
    if brief is None:
        raise HTTPException(404, "no brief for this session yet")
    return {
        "id": str(brief.id),
        "evaluation_id": str(brief.evaluation_id),
        "html_url": f"/sessions/{session_id}/brief.html",
        "summary": brief.summary,
        "created_at": brief.created_at.isoformat(),
    }


@router.get("/sessions/{session_id}/brief.html", response_class=HTMLResponse)
def get_brief_html(
    session_id: uuid.UUID,
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(require_role("reviewer")),
) -> HTMLResponse:
    if db.get(Session, session_id) is None:
        raise HTTPException(404, "session not found")
    brief = db.scalar(
        select(Brief)
        .where(Brief.session_id == session_id)
        .order_by(Brief.created_at.desc())
        .limit(1)
    )
    if brief is None:
        raise HTTPException(404, "no brief for this session yet")
    settings = get_settings()
    client = Minio(
        settings.s3_endpoint.replace("http://", "").replace("https://", ""),
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        secure=settings.s3_endpoint.startswith("https"),
    )
    obj = client.get_object("briefs", brief.html_object_key)
    try:
        return HTMLResponse(obj.read().decode("utf-8"))
    finally:
        obj.close()
        obj.release_conn()
