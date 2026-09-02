"""T11 — candidacies, invites, scheduling, consent (the legal load-bearing flow).

Consent gate (invariant #12) is enforced by consent_missing() in this module,
called from the session status transition (routes/sessions.py) and the
start-interview path — API-level, not UI-level.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session as DbSession

from app.config import get_settings
from app.models import AdminAction, Org, Session
from app.models_phase23 import (
    CONSENT_ITEMS,
    REQUIRED_CONSENT_ITEMS,
    Candidacy,
    ConsentRecord,
    PolicyVersion,
    Schedule,
)
from app.notify import invite_email_html, send_email
from app.tenancy import (
    OrgContext,
    get_db,
    get_org_context,
    log_admin_action,
    mint_candidate_token,
    require_role,
)

router = APIRouter()

# candidacy states that must never start another interview
_TERMINAL_CANDIDACY_STATUSES = ("completed", "in_review", "reviewed", "withdrawn")

DEFAULT_POLICIES = {
    "audio_processing": (
        "Your interview audio is processed in real time to conduct the conversation "
        "and transcribed for evaluation. A second AI model scores the transcript "
        "against the role's rubric; every score cites specific moments. You have "
        "the right to human review of any automated assessment."
    ),
    "video_proctoring": (
        "If enabled by the hiring organization, your camera is analyzed on your own "
        "device for presence signals; continuous video is not transmitted. This "
        "organization has video proctoring disabled — no video is captured."
    ),
    "data_retention": (
        "Interview records (transcript, code, audio) are retained for the period "
        "shown (default 90 days) and then purged. You may request export or "
        "erasure of your data via the hiring organization at any time."
    ),
}


def ensure_policies(db: DbSession) -> str:
    """Seed the current policy version texts (idempotent). Returns version."""
    version = get_settings().consent_policy_version
    for item, text_md in DEFAULT_POLICIES.items():
        exists = db.get(PolicyVersion, {"version": version, "item": item})
        if exists is None:
            db.add(PolicyVersion(version=version, item=item, text_md=text_md))
    db.commit()
    return version


# ── candidacies & invites ────────────────────────────────────────────


class CandidacyIn(BaseModel):
    candidate_email: str
    candidate_name: str
    plan_id: uuid.UUID | None = None
    role_config_id: uuid.UUID | None = None
    job_role_id: uuid.UUID | None = None
    jd_text: str | None = None
    resume_text: str | None = None


@router.post("/candidacies", status_code=201)
def create_candidacy(
    body: CandidacyIn,
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(require_role("recruiter")),
) -> dict[str, Any]:
    cand = Candidacy(id=uuid.uuid4(), org_id=ctx.org_id, **body.model_dump())
    db.add(cand)
    log_admin_action(
        db, ctx, "candidacy_created",
        {"candidacy_id": str(cand.id), "email": body.candidate_email},
    )
    db.commit()

    org = db.get(Org, ctx.org_id)
    link = f"{get_settings().app_base_url}/i/{cand.id}"
    sent = send_email(
        body.candidate_email,
        f"Interview invitation — {org.name if org else 'our team'}",
        invite_email_html(body.candidate_name, org.name if org else "the team", link),
    )
    return {"id": str(cand.id), "invite_link": link, "email_sent": sent}


@router.get("/candidacies")
def list_candidacies(
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(require_role("reviewer")),
) -> list[dict[str, Any]]:
    from app.models import Brief
    from app.models_phase23 import JobRole

    rows = db.scalars(
        select(Candidacy).order_by(Candidacy.created_at.desc()).limit(200)
    ).all()
    role_names = {
        r.id: r.name for r in db.scalars(select(JobRole))
    }
    slots = {
        s.candidacy_id: s.slot_start
        for s in db.scalars(select(Schedule).order_by(Schedule.slot_start))
    }
    # which candidacies have a decision brief (distinguishes "processing"
    # from "brief ready" in the §7 chip without a per-row roundtrip)
    _cand_ids_for_briefs = [c.id for c in rows]
    briefed = {
        row[0]
        for row in db.execute(
            select(Session.candidacy_id)
            .join(Brief, Brief.session_id == Session.id)
            .where(Session.candidacy_id.in_(_cand_ids_for_briefs))
            .distinct()
        ).all()
    } if _cand_ids_for_briefs else set()
    # latest session per candidacy (session-view link for R5/R6). Two columns
    # for the listed candidacies only — loading every full Session ORM row
    # (incl. jd_text/resume_text) unbounded was the audit finding.
    cand_ids = [c.id for c in rows]
    latest_session: dict[uuid.UUID, str] = {}
    if cand_ids:
        for cid, sid in db.execute(
            select(Session.candidacy_id, Session.id)
            .where(Session.candidacy_id.in_(cand_ids))
            .order_by(Session.created_at)
        ).all():
            latest_session[cid] = str(sid)
    return [
        {
            "id": str(c.id),
            "candidate_name": c.candidate_name,
            "candidate_email": c.candidate_email,
            "status": c.status,
            "source": c.source,
            "job_role_id": str(c.job_role_id) if c.job_role_id else None,
            "role_name": role_names.get(c.job_role_id) if c.job_role_id else None,
            "slot_start": slots[c.id].isoformat() if c.id in slots else None,
            "has_brief": c.id in briefed,
            "latest_session_id": latest_session.get(c.id),
            "created_at": c.created_at.isoformat(),
        }
        for c in rows
    ]


@router.get("/candidacies/{candidacy_id}")
def get_candidacy(
    candidacy_id: uuid.UUID, db: DbSession = Depends(get_db)
) -> dict[str, Any]:
    """Candidate-portal view: safe subset, no org internals. Public by
    candidacy id (the invite link IS the credential for scheduling/consent;
    the interview itself still requires the session candidate token)."""
    c = _get_candidacy_public(db, candidacy_id)
    schedule = db.scalar(
        select(Schedule).where(Schedule.candidacy_id == candidacy_id).order_by(Schedule.slot_start.desc()).limit(1)
    )
    version = ensure_policies(db)
    policies = {
        p.item: p.text_md
        for p in db.scalars(select(PolicyVersion).where(PolicyVersion.version == version))
    }
    consents = db.scalars(
        # ordered so the dict comprehension below is latest-wins per item
        select(ConsentRecord)
        .where(ConsentRecord.candidacy_id == candidacy_id)
        .order_by(ConsentRecord.ts)
    )
    from app.models_phase23 import JobRole

    role = db.get(JobRole, c.job_role_id) if c.job_role_id else None
    return {
        "id": str(c.id),
        "candidate_name": c.candidate_name,
        "role_name": role.name if role else None,
        "source": c.source,
        "status": c.status,
        "schedule": (
            {
                "slot_start": schedule.slot_start.isoformat(),
                "slot_end": schedule.slot_end.isoformat(),
                "reschedule_count": schedule.reschedule_count,
            }
            if schedule
            else None
        ),
        "policy_version": version,
        "policies": policies,
        "required_items": list(REQUIRED_CONSENT_ITEMS),
        "consents": {r.item: r.granted for r in consents},
    }


def _get_candidacy_public(db: DbSession, candidacy_id: uuid.UUID) -> Candidacy:
    # Candidate portal has no org header: resolve via bypass, scoped to the id
    from app.db import set_rls_context

    set_rls_context(db, bypass=True)
    c = db.get(Candidacy, candidacy_id)
    if c is None:
        raise HTTPException(404, "candidacy not found")
    set_rls_context(db, org_id=str(c.org_id))
    return c


# ── scheduling ───────────────────────────────────────────────────────


class ScheduleIn(BaseModel):
    slot_start: datetime


@router.post("/candidacies/{candidacy_id}/schedule")
def schedule_slot(
    candidacy_id: uuid.UUID,
    body: ScheduleIn,
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(get_org_context),
) -> dict[str, Any]:
    settings = get_settings()
    # Staff scheduling on the candidate's behalf never burns the candidate's
    # reschedule quota or hits the cutoff — those limits exist for candidates.
    is_staff = ctx.role in ("recruiter", "admin")
    c = _get_candidacy_public(db, candidacy_id)
    if c.status == "withdrawn":
        raise HTTPException(409, "candidacy withdrawn")
    if body.slot_start < datetime.now(UTC):
        raise HTTPException(422, "slot is in the past")

    slot_end = body.slot_start + timedelta(minutes=60)

    # Org concurrency cap (the infra cost throttle). Serialized per org:
    # count-then-insert under concurrency would let two bookings both pass
    # a full window's check.
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:k))"),
        {"k": f"schedule:{c.org_id}"},
    )
    org = db.get(Org, c.org_id)
    org_settings = (org.settings if org else None) or {}
    cap = int(
        org_settings.get(
            "max_concurrent_sessions", settings.org_max_concurrent_sessions_default
        )
    )
    overlapping = db.scalar(
        select(func.count(Schedule.id)).where(
            Schedule.slot_start < slot_end, Schedule.slot_end > body.slot_start
        )
    )
    if (overlapping or 0) >= cap:
        raise HTTPException(409, f"no capacity in that window (org cap {cap}) — pick another slot")

    existing = db.scalar(
        select(Schedule).where(Schedule.candidacy_id == candidacy_id).limit(1)
    )
    if existing:
        if not is_staff:
            if existing.reschedule_count >= settings.reschedule_max:
                raise HTTPException(409, f"reschedule limit ({settings.reschedule_max}) reached")
            if existing.slot_start - datetime.now(UTC) < timedelta(
                hours=settings.reschedule_cutoff_h
            ):
                raise HTTPException(
                    409, f"reschedule cutoff is {settings.reschedule_cutoff_h}h before the slot"
                )
        existing.slot_start = body.slot_start
        existing.slot_end = slot_end
        if not is_staff:
            existing.reschedule_count += 1
    else:
        db.add(
            Schedule(
                id=uuid.uuid4(),
                org_id=c.org_id,
                candidacy_id=candidacy_id,
                slot_start=body.slot_start,
                slot_end=slot_end,
            )
        )
    c.status = "scheduled"
    db.commit()
    return {"scheduled": body.slot_start.isoformat()}


# ── consent (invariant #12: gate enforced at the API layer) ──────────


class ConsentIn(BaseModel):
    items: dict[str, bool]  # item -> granted


@router.post("/candidacies/{candidacy_id}/consent")
def record_consent(
    candidacy_id: uuid.UUID, body: ConsentIn, db: DbSession = Depends(get_db)
) -> dict[str, Any]:
    c = _get_candidacy_public(db, candidacy_id)
    version = ensure_policies(db)
    for item, granted in body.items.items():
        if item not in CONSENT_ITEMS:
            raise HTTPException(422, f"unknown consent item {item!r}")
        db.add(
            ConsentRecord(
                id=uuid.uuid4(),
                org_id=c.org_id,
                candidacy_id=candidacy_id,
                item=item,
                granted=granted,
                policy_version=version,
            )
        )
    db.commit()
    missing = consent_missing(db, candidacy_id)
    return {"recorded": list(body.items), "missing_required": missing}


def consent_missing(db: DbSession, candidacy_id: uuid.UUID) -> list[str]:
    """Required items not granted under the CURRENT policy version.

    Latest record wins per item: a candidate who granted and later withdrew
    (granted=False) counts as NOT granted — anything else makes revocation
    a no-op."""
    version = get_settings().consent_policy_version
    rows = db.execute(
        select(ConsentRecord.item, ConsentRecord.granted)
        .where(
            ConsentRecord.candidacy_id == candidacy_id,
            ConsentRecord.policy_version == version,
        )
        .order_by(ConsentRecord.ts)
    ).all()
    latest: dict[str, bool] = {}
    for item, granted in rows:
        latest[item] = granted
    return [i for i in REQUIRED_CONSENT_ITEMS if not latest.get(i, False)]


@router.post("/candidacies/{candidacy_id}/decline")
def decline_candidacy(
    candidacy_id: uuid.UUID, db: DbSession = Depends(get_db)
) -> dict[str, Any]:
    """Candidate-side decline/cancel (C3 'I do not wish to proceed', C5 cancel).
    Logged; the candidacy becomes withdrawn and the flow shows the polite end."""
    c = _get_candidacy_public(db, candidacy_id)
    if c.status in ("completed", "in_review", "reviewed"):
        raise HTTPException(409, "the interview is already completed")
    c.status = "withdrawn"
    db.add(
        AdminAction(
            org_id=c.org_id, user_email=f"candidate:{candidacy_id}",
            action="candidacy_declined", payload={"candidacy_id": str(candidacy_id)},
        )
    )
    db.commit()
    return {"status": "withdrawn"}


@router.get("/candidacies/{candidacy_id}/timeline")
def candidacy_timeline(
    candidacy_id: uuid.UUID,
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(require_role("reviewer")),
) -> dict[str, Any]:
    """Org-side detail (R6): the lifecycle made human-readable, plus sessions."""
    c = db.get(Candidacy, candidacy_id)
    if c is None:
        raise HTTPException(404, "candidacy not found")
    from app.models import Brief
    from app.models import Session as Sess
    from app.models_phase23 import JobRole

    events: list[dict[str, Any]] = [
        {"at": c.created_at.isoformat(), "label": "Invited", "detail": c.source}
    ]
    for r in db.scalars(
        select(ConsentRecord)
        .where(ConsentRecord.candidacy_id == candidacy_id)
        .order_by(ConsentRecord.ts)
    ):
        events.append(
            {
                "at": r.ts.isoformat(),
                "label": f"Consent {'granted' if r.granted else 'refused'}: {r.item}",
                "detail": f"policy {r.policy_version}",
            }
        )
    for s in db.scalars(select(Schedule).where(Schedule.candidacy_id == candidacy_id)):
        events.append(
            {
                "at": s.slot_start.isoformat(),
                "label": "Scheduled",
                "detail": f"reschedules: {s.reschedule_count}",
            }
        )
    sessions = []
    for sess in db.scalars(
        select(Sess).where(Sess.candidacy_id == candidacy_id).order_by(Sess.created_at)
    ):
        events.append(
            {
                "at": sess.created_at.isoformat(),
                "label": f"Interview started ({sess.round_type or 'full'})",
                "detail": str(sess.id)[:8],
            }
        )
        has_brief = (
            db.scalar(select(Brief).where(Brief.session_id == sess.id).limit(1)) is not None
        )
        sessions.append(
            {
                "id": str(sess.id),
                "status": sess.status,
                "round_type": sess.round_type,
                "created_at": sess.created_at.isoformat(),
                "has_brief": has_brief,
            }
        )
    role = db.get(JobRole, c.job_role_id) if c.job_role_id else None
    events.sort(key=lambda e: str(e["at"]))
    return {
        "id": str(c.id),
        "candidate_name": c.candidate_name,
        "candidate_email": c.candidate_email,
        "status": c.status,
        "role_name": role.name if role else None,
        "events": events,
        "sessions": sessions,
    }


@router.post("/candidacies/{candidacy_id}/start-interview")
def start_interview(
    candidacy_id: uuid.UUID, db: DbSession = Depends(get_db)
) -> dict[str, Any]:
    """Consent-gated session creation for the candidate portal: creates the
    round-1 session (or pipeline round session) + candidate link."""
    c = _get_candidacy_public(db, candidacy_id)
    missing = consent_missing(db, candidacy_id)
    if missing:
        raise HTTPException(
            403, f"required consent not granted under current policy: {missing}"
        )

    if c.status in _TERMINAL_CANDIDACY_STATUSES:
        # a finished candidacy does not spawn fresh interviews: the invite
        # link is the only credential here, so without this check anyone
        # holding it could re-open interviewing after completion
        raise HTTPException(
            409, f"this interview is already {c.status} and cannot be restarted"
        )
    # Serialize concurrent starts for this candidacy (double-click, portal
    # retry): the check-then-create below is only idempotent under a lock.
    # Advisory xact lock releases automatically at commit/rollback.
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
        {"key": f"start-interview:{c.id}"},
    )
    # Idempotent: an in-flight session (any round) means "rejoin", not "start
    # another". Re-mint the candidate link (jti rotation revokes the old one)
    # and hand back the same room — a reload or dropped tab never dead-ends.
    # NOTE "in_progress", not "active": the agent sets in_progress, and the
    # old filter's phantom status meant a reload mid-interview spawned a
    # SECOND session instead of rejoining.
    live = db.scalars(
        select(Session)
        .where(
            Session.candidacy_id == c.id,
            Session.status.in_(("created", "in_progress", "paused")),
        )
        .order_by(Session.created_at.desc())
        .limit(1)
    ).first()
    if live is not None:
        token, jti = mint_candidate_token(live.id, c.org_id)
        live.candidate_jti = jti
        db.commit()
        return {
            "session_id": str(live.id),
            "candidate_token": token,
            "interview_path": f"/interview?session={live.id}&candidate_token={token}",
            "rejoined": True,
        }

    from app.models import InterviewPlan
    from app.models_phase23 import CandidacyProgress, JobRole

    # Role-driven interview selection: an assigned job role decides what the
    # candidate gets — its pipeline (multi-round) or its plan (single round).
    role = db.get(JobRole, c.job_role_id) if c.job_role_id else None
    if role and role.pipeline_id and c.plan_id is None:
        from app.routes.pipelines import _advance

        if db.get(CandidacyProgress, c.id) is None:
            db.add(
                CandidacyProgress(
                    candidacy_id=c.id, org_id=c.org_id, pipeline_id=role.pipeline_id,
                    current_round=0, round_sessions={}, gate_state="advancing",
                )
            )
            db.commit()
        ctx = OrgContext(org_id=c.org_id, role="service", user_email=f"portal:{c.id}")
        result = _advance(db, ctx, c.id)
        if "interview_path" not in result:
            raise HTTPException(409, f"pipeline cannot start a round now: {result}")
        c.status = "in_progress"
        db.commit()
        return {
            "session_id": result["session_id"],
            "interview_path": result["interview_path"],
        }

    plan_id = c.plan_id or (role.plan_id if role else None)
    if plan_id is None:
        # Fallback: newest FULL plan. Pipeline-synthesized single-round plans
        # (role_config_id == "pipeline") are round fragments, not interviews —
        # picking one gave candidates a talk-only session with no editor.
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
        org_id=c.org_id,
        candidacy_id=c.id,
        candidate_label=c.candidate_name,
        plan_id=plan_id,
        jd_text=c.jd_text,
        resume_text=c.resume_text,
    )
    db.add(session)
    if c.resume_text:
        from app.models_phase23 import Resume
        from app.rounds.resume_parser import PARSER_VERSION, parse_resume

        db.add(
            Resume(
                id=uuid.uuid4(),
                org_id=c.org_id,
                candidacy_id=c.id,
                raw_text=c.resume_text,
                parsed_claims=parse_resume(c.resume_text),
                parser_version=PARSER_VERSION,
            )
        )
    token, jti = mint_candidate_token(session.id, c.org_id)
    session.candidate_jti = jti
    c.status = "in_progress"
    db.commit()
    return {
        "session_id": str(session.id),
        "candidate_token": token,
        "interview_path": f"/interview?session={session.id}&candidate_token={token}",
    }
