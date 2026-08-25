import uuid
from functools import lru_cache
from typing import Any, Literal

import redis
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
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


MAX_SOURCE_CHARS = 200_000  # ~200KB: far above any interview answer
MAX_STDIN_CHARS = 100_000


class ExecuteRequest(BaseModel):
    session_id: uuid.UUID
    language: Literal["python", "javascript", "java", "cpp", "sql"]
    # bounded: unbounded bodies were forwarded straight to Judge0
    source: str = Field(max_length=MAX_SOURCE_CHARS)
    stdin: str | None = Field(default=None, max_length=MAX_STDIN_CHARS)
    test_suite_id: uuid.UUID | None = None  # question id


@lru_cache(maxsize=1)
def _redis() -> redis.Redis:
    # one pooled client per process (was a fresh client per request on the
    # live-interview code-run path)
    return redis.Redis.from_url(get_settings().redis_url, socket_timeout=5)


@lru_cache(maxsize=1)
def _judge0() -> Judge0Client:
    """One client (and one connection pool) for the process: a fresh
    AsyncClient per /execute meant a new TLS/TCP handshake on the code-run
    hot path during live interviews."""
    return Judge0Client()


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

    client = _judge0()
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
        # the Judge0 client is process-cached (connection reuse) — closing it
        # here would break every subsequent request
        r.delete(lock_key)
