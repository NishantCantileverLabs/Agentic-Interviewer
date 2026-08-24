import uuid
from typing import Any, Literal

import redis
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session as DbSession

from app.config import get_settings
from app.events import append_event
from app.execution import (
    LANGUAGE_IDS,
    Judge0Client,
    compose_source,
    evaluate_case,
    load_test_cases,
    map_status,
    shape_response,
)
from app.models import Question, Session
from app.tenancy import OrgContext, ensure_session_access, get_db, get_org_context

router = APIRouter()

_EXEC_LOCK_TTL_S = 60


class ExecuteRequest(BaseModel):
    session_id: uuid.UUID
    language: Literal["python", "javascript", "java", "cpp", "sql"]
    source: str
    stdin: str | None = None
    test_suite_id: uuid.UUID | None = None  # question id


def _redis() -> redis.Redis:
    return redis.Redis.from_url(get_settings().redis_url, socket_timeout=5)


@router.post("/execute")
async def execute(
    body: ExecuteRequest,
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(get_org_context),
) -> dict[str, Any]:
    ensure_session_access(ctx, body.session_id)
    if body.language not in LANGUAGE_IDS:
        raise HTTPException(400, f"unsupported language {body.language!r}")
    exec_session = db.get(Session, body.session_id)
    if exec_session is None:
        raise HTTPException(404, "session not found")

    # Per-session concurrency = 1 (Redis lock; TTL guards against crashed holders)
    r = _redis()
    lock_key = f"exec:lock:{body.session_id}"
    if not r.set(lock_key, "1", nx=True, ex=_EXEC_LOCK_TTL_S):
        raise HTTPException(429, "an execution is already running for this session")

    client = Judge0Client()
    try:
        if body.test_suite_id is None:
            raw = await client.run(body.language, body.source, body.stdin or "")
            status = map_status(
                int((raw.get("status") or {}).get("id", 0)),
                str((raw.get("status") or {}).get("description", "")),
            )
            response = shape_response(
                status, raw.get("stdout") or "", raw.get("stderr") or "", []
            )
        else:
            question = db.get(Question, body.test_suite_id)
            if question is None:
                raise HTTPException(404, "test suite not found")
            cases = load_test_cases(question)
            results = []
            for case in cases:
                source = compose_source(body.language, body.source, case)
                raw = await client.run(body.language, source, case.stdin)
                results.append(evaluate_case(raw, case))
            overall = "accepted" if all(t["passed"] for t in results) else "failed"
            response = shape_response(overall, "", "", results)

        # Full detail (incl. hidden-case results) goes to the event log — the
        # log is internal; only `response` crosses the API boundary.
        append_event(
            db,
            body.session_id,
            exec_session.org_id,
            "execution_result",
            {
                "language": body.language,
                "test_suite_id": str(body.test_suite_id) if body.test_suite_id else None,
                "source_chars": len(body.source),
                "response": response,
            },
        )
        return response
    finally:
        await client.close()
        r.delete(lock_key)
