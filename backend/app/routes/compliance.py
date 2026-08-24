"""T18 — compliance mechanics: export(), erase(), spend alarms.

export(): machine-readable bundle of everything derived from a candidacy.
erase(): deletes recordings/objects, purges events (sanctioned path),
scrubs PII to tombstones. Both are admin actions, audit-logged in
purge_audit. These must actually work, not exist in a policy PDF.
"""

import statistics
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session as DbSession

from app.config import get_settings
from app.models import Brief, Evaluation, HumanEvaluation, InterviewEvent, LLMCall, Session, User
from app.models_phase23 import (
    AggregateBrief,
    Candidacy,
    ConsentRecord,
    PurgeAudit,
    Resume,
    Schedule,
)
from app.tenancy import OrgContext, get_db, log_admin_action, require_role

router = APIRouter()

TOMBSTONE = "[erased]"


def _candidacy_sessions(db: DbSession, candidacy_id: uuid.UUID) -> list[Session]:
    return list(db.scalars(select(Session).where(Session.candidacy_id == candidacy_id)))


def _account_bundle(db: DbSession, email: str) -> dict[str, Any] | None:
    """Candidate account data (users row) — part of the DSR surface since
    accounts landed in migration 0009."""
    user = db.scalar(select(User).where(User.email == email, User.account_type == "candidate"))
    if user is None:
        return None
    return {
        "email": user.email,
        "name": user.name,
        "auth_provider": user.auth_provider,
        "email_verified": user.email_verified,
        "created_at": user.created_at.isoformat(),
    }


@router.get("/candidacies/{candidacy_id}/export")
def export_candidacy(
    candidacy_id: uuid.UUID,
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(require_role("admin")),
) -> dict[str, Any]:
    """DSR export: everything we hold that derives from this candidate."""
    cand = db.get(Candidacy, candidacy_id)
    if cand is None:
        raise HTTPException(404, "candidacy not found")
    sessions = _candidacy_sessions(db, candidacy_id)
    bundle: dict[str, Any] = {
        "candidacy": {
            "id": str(cand.id), "name": cand.candidate_name, "email": cand.candidate_email,
            "status": cand.status, "created_at": cand.created_at.isoformat(),
            "jd_text": cand.jd_text, "resume_text": cand.resume_text,
        },
        "consents": [
            {"item": r.item, "granted": r.granted, "policy_version": r.policy_version,
             "ts": r.ts.isoformat()}
            for r in db.scalars(
                select(ConsentRecord).where(ConsentRecord.candidacy_id == candidacy_id)
            )
        ],
        "schedules": [
            {"slot_start": s.slot_start.isoformat(), "slot_end": s.slot_end.isoformat()}
            for s in db.scalars(select(Schedule).where(Schedule.candidacy_id == candidacy_id))
        ],
        "resumes": [
            {"raw_text": r.raw_text, "parsed_claims": r.parsed_claims}
            for r in db.scalars(select(Resume).where(Resume.candidacy_id == candidacy_id))
        ],
        "aggregate_briefs": [
            {"version": ab.version, "rollup": ab.rollup, "consistency": ab.consistency}
            for ab in db.scalars(
                select(AggregateBrief).where(AggregateBrief.candidacy_id == candidacy_id)
            )
        ],
        # candidate account (added with migration 0009 — invariant #13)
        "account": _account_bundle(db, cand.candidate_email),
        "sessions": [],
    }
    for s in sessions:
        events = [
            {"seq": e.seq, "ts": e.ts.isoformat(), "type": e.type, "payload": e.payload}
            for e in db.scalars(
                select(InterviewEvent)
                .where(InterviewEvent.session_id == s.id)
                .order_by(InterviewEvent.seq)
            )
        ]
        evals = [
            {"version": ev.version, "rubric": ev.rubric, "signals": ev.signals}
            for ev in db.scalars(select(Evaluation).where(Evaluation.session_id == s.id))
        ]
        bundle["sessions"].append(
            {"id": str(s.id), "status": s.status, "events": events, "evaluations": evals}
        )
    log_admin_action(db, ctx, "dsr_export", {"candidacy_id": str(candidacy_id)})
    db.add(
        PurgeAudit(
            org_id=ctx.org_id, action="export", subject=str(candidacy_id),
            detail={"sessions": len(sessions)}, actor=ctx.user_email,
        )
    )
    db.commit()
    return bundle


@router.post("/candidacies/{candidacy_id}/erase")
def erase_candidacy(
    candidacy_id: uuid.UUID,
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(require_role("admin")),
) -> dict[str, Any]:
    """DSR erasure: purge events (sanctioned path), delete stored objects,
    tombstone PII. Evaluations/briefs rows keep aggregate scores but their
    quote-bearing content is scrubbed."""
    cand = db.get(Candidacy, candidacy_id)
    if cand is None:
        raise HTTPException(404, "candidacy not found")
    sessions = _candidacy_sessions(db, candidacy_id)
    erased_events = 0
    for s in sessions:
        result = db.execute(delete(InterviewEvent).where(InterviewEvent.session_id == s.id))
        erased_events += int(result.rowcount or 0)  # type: ignore[attr-defined]
        s.candidate_label = TOMBSTONE
        s.jd_text = None
        s.resume_text = None
        s.candidate_jti = None
        # scrub quote-bearing content from evaluations + briefs
        for ev in db.scalars(select(Evaluation).where(Evaluation.session_id == s.id)):
            ev.rubric = {"erased": True}
            ev.signals = {"erased": True}
        for he in db.scalars(
            select(HumanEvaluation).where(HumanEvaluation.session_id == s.id)
        ):
            he.rubric = {"erased": True}
        for b in db.scalars(select(Brief).where(Brief.session_id == s.id)):
            b.summary = {"erased": True}
            _delete_object("briefs", b.html_object_key)
            b.html_object_key = ""
    for r in db.scalars(select(Resume).where(Resume.candidacy_id == candidacy_id)):
        r.raw_text = TOMBSTONE
        r.parsed_claims = {"erased": True}
    # cross-round rollups hold quotes too (invariant #13: added in 0008)
    for ab in db.scalars(
        select(AggregateBrief).where(AggregateBrief.candidacy_id == candidacy_id)
    ):
        ab.rollup = {"erased": True}
        ab.consistency = []
        _delete_object("briefs", ab.html_object_key)
        ab.html_object_key = ""
    # candidate account: PII + credentials become tombstones (added in 0009)
    account = db.scalar(
        select(User).where(
            User.email == cand.candidate_email, User.account_type == "candidate"
        )
    )
    if account is not None:
        account.email = f"erased-{candidacy_id}@tombstone.invalid"
        account.name = TOMBSTONE
        account.password_hash = None
        account.otp_hash = None
        account.otp_expires_at = None
        account.auth_provider_id = None
        account.email_verified = False
    cand.candidate_name = TOMBSTONE
    cand.candidate_email = f"erased-{candidacy_id}@tombstone.invalid"
    cand.jd_text = None
    cand.resume_text = None
    cand.status = "withdrawn"

    db.add(
        PurgeAudit(
            org_id=ctx.org_id, action="erase", subject=str(candidacy_id),
            detail={"sessions": len(sessions), "events_purged": erased_events},
            actor=ctx.user_email,
        )
    )
    log_admin_action(db, ctx, "dsr_erase", {"candidacy_id": str(candidacy_id)})
    db.commit()
    return {"erased_sessions": len(sessions), "events_purged": erased_events}


def _delete_object(bucket: str, key: str | None) -> None:
    if not key:
        return
    try:
        from minio import Minio

        settings = get_settings()
        client = Minio(
            settings.s3_endpoint.replace("http://", "").replace("https://", ""),
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
            secure=settings.s3_endpoint.startswith("https"),
        )
        client.remove_object(bucket, key)
    except Exception:  # noqa: BLE001 - erase must not fail on missing objects
        pass


@router.get("/metrics/spend-alarm")
def spend_alarm(
    multiplier: float = 10.0,
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(require_role("recruiter")),
) -> dict[str, Any]:
    """T18: sessions whose token spend exceeds N× the org median — the
    'should page you, not surprise the invoice' check."""
    rows = db.execute(
        select(
            LLMCall.session_id,
            func.sum(LLMCall.input_tokens + LLMCall.output_tokens),
            func.sum(LLMCall.cost_estimate),
        )
        .where(LLMCall.session_id.isnot(None))
        .group_by(LLMCall.session_id)
    ).all()
    if not rows:
        return {"median_tokens": 0, "alarms": []}
    totals = sorted(int(t or 0) for _, t, _ in rows)
    median = statistics.median(totals)
    alarms = [
        {
            "session_id": str(sid),
            "tokens": int(t or 0),
            "cost_estimate_usd": round(float(c), 4) if c else None,
            "x_median": round(int(t or 0) / median, 1) if median else None,
        }
        for sid, t, c in rows
        if median and int(t or 0) > multiplier * median
    ]
    return {"median_tokens": int(median), "multiplier": multiplier, "alarms": alarms}
