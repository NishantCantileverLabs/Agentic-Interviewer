import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from livekit import api as lk_api
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.orm import Session as DbSession

from app.config import get_settings
from app.models import SESSION_STATUSES, InterviewEvent, Session
from app.schemas import EventBatchIn, EventOut, SessionCreate, SessionOut
from app.tenancy import (
    OrgContext,
    ensure_session_access,
    get_db,
    get_org_context,
    log_admin_action,
    mint_candidate_token,
    require_role,
)

router = APIRouter()

# a finished interview never goes back to live
_TERMINAL_SESSION_STATUSES = ("completed", "aborted")

# events that drive engine state / scoring — never written by a browser
_CONTROL_EVENT_TYPES = frozenset({
    "state_transition",
    "hint_issued",
    "twist_injected",
    "execution_result",
    "agent_turn",
    "round_handoff",
    "exhibit_revealed",
    "turn_latency",
    "error",
    "fallback_triggered",
})


@router.post("/sessions", response_model=SessionOut, status_code=201)
def create_session(
    body: SessionCreate,
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(require_role("recruiter", "service")),
) -> Session:
    plan_id = body.plan_id
    if plan_id is None:
        # Backend decides the interview: newest FULL plan in THIS org
        # (RLS-scoped). Pipeline-synthesized round fragments are excluded.
        from sqlalchemy import func

        from app.models import InterviewPlan

        newest = db.scalars(
            select(InterviewPlan)
            .where(
                func.coalesce(InterviewPlan.plan["role_config_id"].astext, "").notin_(
                    ("pipeline", "demo")
                )
            )
            .order_by(InterviewPlan.created_at.desc())
            .limit(1)
        ).first()
        plan_id = newest.id if newest else None
    session = Session(
        id=uuid.uuid4(),
        org_id=ctx.org_id,
        candidate_label=body.candidate_label,
        role_config_id=body.role_config_id,
        plan_id=plan_id,
        retention_days=body.retention_days or get_settings().retention_days_default,
        jd_text=body.jd_text,
        resume_text=body.resume_text,
    )
    db.add(session)
    db.commit()
    return session


@router.get("/sessions/{session_id}", response_model=SessionOut)
def get_session(
    session_id: uuid.UUID,
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(get_org_context),
) -> Session:
    ensure_session_access(ctx, session_id)
    session = db.get(Session, session_id)
    if session is None:
        raise HTTPException(404, "session not found")
    return session


@router.head("/sessions/{session_id}")
def head_session(
    session_id: uuid.UUID,
    ctx: OrgContext = Depends(get_org_context),
) -> None:
    ensure_session_access(ctx, session_id)


@router.post("/sessions/{session_id}/candidate-link")
def create_candidate_link(
    session_id: uuid.UUID,
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(get_org_context),
) -> dict[str, str]:
    """Mint a revocable, single-session candidate link (24h). Re-minting
    revokes the previous token via jti rotation."""
    session = db.get(Session, session_id)
    if session is None:
        raise HTTPException(404, "session not found")
    token, jti = mint_candidate_token(session_id, session.org_id)
    session.candidate_jti = jti
    log_admin_action(db, ctx, "candidate_link_minted", {"session_id": str(session_id)})
    db.commit()
    path = f"/interview?session={session_id}&candidate_token={token}"
    return {"candidate_token": token, "path": path}


@router.post("/sessions/{session_id}/events", status_code=201)
def append_events(
    session_id: uuid.UUID,
    body: EventBatchIn,
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(get_org_context),
) -> dict[str, int]:
    ensure_session_access(ctx, session_id)
    """Batched append to the event log.

    seq is server-assigned under a per-session advisory lock: multiple writers
    (agent worker, browser beacons, server-side appends) interleave safely and
    the log stays strictly ordered. Batch order is preserved.
    """
    session = db.get(Session, session_id)
    if session is None:
        raise HTTPException(404, "session not found")
    if not body.events:
        return {"appended": 0}
    if ctx.role == "candidate":
        # The browser reports what the CANDIDATE did (typing, pastes, runs,
        # tab visibility). Control events drive engine state and the closure
        # guards that read it, so they are service/staff only: appending a
        # state_transition was enough to move rebuilt state off ENDED and
        # resurrect a finished interview.
        illegal = {e.type for e in body.events} & _CONTROL_EVENT_TYPES
        if illegal:
            raise HTTPException(
                403, f"these event types are not writable by a candidate: {sorted(illegal)}"
            )

    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": str(session_id)})

    # Idempotent retries: writers stamp a client id (payload.eid). A flush
    # that timed out AFTER the server persisted gets retried by the sink —
    # skipping already-stored eids keeps the append-only log duplicate-free.
    incoming_eids = [
        str(e.payload["eid"]) for e in body.events if isinstance(e.payload.get("eid"), str)
    ]
    seen: set[str] = set()
    if incoming_eids:
        seen = set(
            db.scalars(
                select(InterviewEvent.payload["eid"].astext).where(
                    InterviewEvent.session_id == session_id,
                    InterviewEvent.payload["eid"].astext.in_(incoming_eids),
                )
            )
        )

    last_seq = db.scalar(
        select(InterviewEvent.seq)
        .where(InterviewEvent.session_id == session_id)
        .order_by(InterviewEvent.seq.desc())
        .limit(1)
    )
    seq = (last_seq if last_seq is not None else -1) + 1
    appended = 0
    for e in body.events:
        eid = e.payload.get("eid")
        if isinstance(eid, str) and eid in seen:
            continue
        row = InterviewEvent(
            session_id=session_id,
            org_id=session.org_id,
            seq=seq,
            type=e.type,
            payload=e.payload,
        )
        if e.ts is not None:
            row.ts = e.ts
        db.add(row)
        seq += 1
        appended += 1
    db.commit()
    return {"appended": appended}


@router.get("/sessions/{session_id}/plan")
def get_session_plan(
    session_id: uuid.UUID,
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(get_org_context),
) -> dict[str, object]:
    """The interview plan driving this session (agent worker bootstrap)."""
    from app.models import InterviewPlan

    ensure_session_access(ctx, session_id)
    session = db.get(Session, session_id)
    if session is None:
        raise HTTPException(404, "session not found")
    if session.plan_id is None:
        raise HTTPException(409, "session has no interview plan attached")
    plan = db.get(InterviewPlan, session.plan_id)
    if plan is None:
        raise HTTPException(500, "session references a missing plan")
    return {"id": str(plan.id), "plan": plan.plan}


class SessionStatusIn(BaseModel):
    status: str


# Aura-2 voices offered in the lobby picker. Whitelist — an arbitrary string
# would be passed to Deepgram as a model name.
INTERVIEWER_VOICES: dict[str, str] = {
    "aura-2-thalia-en": "Thalia — clear, confident (default)",
    "aura-2-andromeda-en": "Andromeda — calm, warm",
    "aura-2-orion-en": "Orion — approachable, deeper",
    "aura-2-arcas-en": "Arcas — natural, smooth",
}


class SessionVoiceIn(BaseModel):
    voice: str


@router.patch("/sessions/{session_id}/voice", response_model=SessionOut)
def set_session_voice(
    session_id: uuid.UUID,
    body: SessionVoiceIn,
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(get_org_context),
) -> Session:
    """Candidate's interviewer-voice pick, set from the lobby before the agent
    joins. Candidate tokens for this session pass ensure_session_access."""
    ensure_session_access(ctx, session_id)
    session = db.get(Session, session_id)
    if session is None:
        raise HTTPException(404, "session not found")
    if body.voice not in INTERVIEWER_VOICES:
        raise HTTPException(422, f"unknown voice {body.voice!r}")
    session.voice = body.voice
    db.commit()
    return session


@router.patch("/sessions/{session_id}/status", response_model=SessionOut)
def set_session_status(
    session_id: uuid.UUID,
    body: SessionStatusIn,
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(get_org_context),
) -> Session:
    ensure_session_access(ctx, session_id)
    session = db.get(Session, session_id)
    if session is None:
        raise HTTPException(404, "session not found")
    if body.status not in SESSION_STATUSES:
        raise HTTPException(422, f"invalid status {body.status!r}")
    if session.status in _TERMINAL_SESSION_STATUSES and body.status != session.status:
        # completed/aborted is a one-way door. Without this, every other
        # closure guard (room token, /execute, agent dispatch) was bypassable
        # by simply flipping the session back to in_progress first.
        raise HTTPException(
            409, f"this interview is {session.status} and cannot be reopened"
        )
    if body.status == "in_progress" and session.candidacy_id is not None:
        # Invariant #12: consent gate is API-enforced, not UI-enforced
        from app.routes.lifecycle import consent_missing

        missing = consent_missing(db, session.candidacy_id)
        if missing:
            raise HTTPException(
                403, f"cannot start: required consent missing under current policy: {missing}"
            )
    was_completed = session.status == "completed"
    session.status = body.status
    now = datetime.now(UTC)
    if body.status == "in_progress" and session.started_at is None:
        session.started_at = now
    if body.status in ("completed", "aborted") and session.ended_at is None:
        session.ended_at = now
    if body.status == "completed" and session.candidacy_id is not None:
        # close the candidacy for plan-based interviews (practice included) —
        # only the pipeline orchestrator managed this before, so single-round
        # candidacies stayed "in_progress" forever and the portal kept
        # offering re-entry into a finished interview
        from app.models_phase23 import Candidacy, CandidacyProgress

        if db.get(CandidacyProgress, session.candidacy_id) is None:
            cand = db.get(Candidacy, session.candidacy_id)
            if cand is not None and cand.status not in ("withdrawn", "reviewed"):
                cand.status = "completed"
    db.commit()

    if body.status == "completed" and not was_completed:
        # Session end triggers async evaluation (T6). Fire-and-forget: a Redis
        # hiccup must not fail the status change; re-runs are idempotent anyway.
        import json as _json

        import redis as _redis

        try:
            r = _redis.Redis.from_url(get_settings().redis_url, socket_timeout=3)
            r.lpush(get_settings().eval_queue, _json.dumps({"session_id": str(session_id)}))
        except _redis.RedisError:
            # LOUD failure: this session will sit unevaluated until someone
            # re-enqueues it — a silent pass here is how sessions get stuck
            # in "Processing" forever
            import logging

            logging.getLogger("sessions").error(
                "EVAL ENQUEUE FAILED for session %s — redis unavailable; "
                "re-enqueue manually or restart the worker", session_id
            )
    return session


@router.get("/sessions/{session_id}/token")
def issue_room_token(
    session_id: uuid.UUID,
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(get_org_context),
) -> dict[str, str]:
    """LiveKit access token for the candidate to join this session's room."""
    ensure_session_access(ctx, session_id)
    session = db.get(Session, session_id)
    if session is None:
        raise HTTPException(404, "session not found")
    if session.status in ("completed", "aborted"):
        # a finished interview is closed: no room re-entry, no agent
        # re-dispatch, no resumed context. The portal routes to /next.
        raise HTTPException(409, "this interview has ended")

    room = session.livekit_room or f"interview-{session_id}"
    if session.livekit_room != room:
        session.livekit_room = room
        db.commit()

    settings = get_settings()
    token = (
        lk_api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity(f"candidate-{session_id}")
        .with_name(session.candidate_label)
        .with_grants(lk_api.VideoGrants(room_join=True, room=room))
        # Explicit agent dispatch: the room requests the named interviewer
        # worker on creation (deterministic; replaces automatic dispatch).
        .with_room_config(
            lk_api.RoomConfiguration(
                agents=[lk_api.RoomAgentDispatch(agent_name="interviewer")]
            )
        )
        .to_jwt()
    )
    return {"token": token, "url": settings.livekit_public_url or settings.livekit_url, "room": room}


@router.get("/sessions/{session_id}/replay", response_model=list[EventOut])
def replay(
    session_id: uuid.UUID,
    after_seq: int = -1,
    limit: int = 5000,
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(get_org_context),
) -> list[InterviewEvent]:
    """Ordered event stream for a session (feeds T5 observation + T8 review).
    `after_seq` supports incremental polling (only events with seq > after_seq);
    `limit` caps the page — callers page by passing the last seq they saw.
    A long interview's full log is tens of MB of jsonb, so an unbounded read
    was a memory/latency hazard on every poll."""
    ensure_session_access(ctx, session_id)
    if db.get(Session, session_id) is None:
        raise HTTPException(404, "session not found")
    return list(
        db.scalars(
            select(InterviewEvent)
            .where(InterviewEvent.session_id == session_id, InterviewEvent.seq > after_seq)
            .order_by(InterviewEvent.seq)
            .limit(max(1, min(limit, 20000)))
        )
    )


@router.get("/sessions/{session_id}/code_at")
def code_at_endpoint(
    session_id: uuid.UUID,
    ts: datetime,
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(get_org_context),
) -> dict[str, object]:
    """Exact editor content at an arbitrary timestamp (T3 replay guarantee)."""
    from app.replay import code_at

    ensure_session_access(ctx, session_id)
    if db.get(Session, session_id) is None:
        raise HTTPException(404, "session not found")
    rows = db.scalars(
        select(InterviewEvent)
        .where(
            InterviewEvent.session_id == session_id,
            InterviewEvent.type.in_(["editor_snapshot", "editor_delta_batch"]),
        )
        .order_by(InterviewEvent.seq)
    )
    events = [{"seq": r.seq, "ts": r.ts, "type": r.type, "payload": r.payload} for r in rows]
    return code_at(events, ts)
