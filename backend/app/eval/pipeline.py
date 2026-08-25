"""T6 — two-pass evaluation: evidence extraction -> scoring from evidence.

The two-pass split is the halo-effect firewall (§8): the scoring model never
sees the full transcript, only cited evidence. Validation rejects any score
whose citations don't resolve to real event ids; one retry, then the
evaluation is stored flagged `degraded` for human attention — never
fabricated, never silently shipped.
"""

import json
import logging
import re
import uuid
from typing import Any

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.config import get_settings
from app.db import SessionLocal
from app.eval.signals import compute_signals
from app.models import (
    Evaluation,
    InterviewEvent,
    InterviewPlan,
    LLMCall,
    PromptVersion,
    Session,
)
from providers import ContextBlock, LLMRequest, get_provider
from providers.pricing import estimate_cost_usd

log = logging.getLogger("eval-pipeline")

TRANSCRIPT_EVENT_TYPES = ("stt_final", "agent_turn", "hint_issued", "execution_result",
                          "state_transition", "twist_injected", "paste")


class EvidenceItem(BaseModel):
    event_id: int
    quote: str
    why_relevant: str


class CompetencyScore(BaseModel):
    score_1_to_5: int = Field(ge=1, le=5)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_refs: list[int] = Field(min_length=1)
    rationale: str


def _parse_json_object(text: str) -> dict[str, Any]:
    """Tolerant JSON extraction: strips code fences / surrounding prose."""
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object found in model output")
    result: dict[str, Any] = json.loads(cleaned[start : end + 1])
    return result


def _prompt_version(db: DbSession, name: str) -> PromptVersion:
    pv = db.scalar(
        select(PromptVersion)
        .where(PromptVersion.name == name)
        .order_by(PromptVersion.created_at.desc())
        .limit(1)
    )
    if pv is None:
        raise RuntimeError(f"prompt version {name!r} missing — run scripts/sync_prompts.py")
    return pv


def _log_llm_call(
    db: DbSession, session_id: uuid.UUID, org_id: uuid.UUID, pv: PromptVersion, result: Any
) -> None:
    db.add(
        LLMCall(
            org_id=org_id,
            session_id=session_id,
            prompt_version_id=pv.id,
            role="evaluate",
            model=result.model,
            input_tokens=result.input_tokens,
            cached_tokens=result.cache_read_tokens,
            output_tokens=result.output_tokens,
            ttft_ms=result.ttft_ms,
            total_ms=result.total_ms,
            cost_estimate=result.cost_usd
            or estimate_cost_usd(
                result.model, result.input_tokens, result.output_tokens,
                result.cache_read_tokens, result.cache_creation_tokens,
            ),
        )
    )
    db.commit()


def build_transcript(events: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for e in events:
        if e["type"] not in TRANSCRIPT_EVENT_TYPES:
            continue
        p = e.get("payload") or {}
        eid = e["id"]
        if e["type"] == "stt_final":
            lines.append(f"[{eid}] CANDIDATE: {p.get('text', '')}")
        elif e["type"] == "agent_turn":
            intent = (p.get("meta") or {}).get("intent", "chat")
            lines.append(f"[{eid}] INTERVIEWER ({intent}): {p.get('text', '')}")
        elif e["type"] == "hint_issued":
            lines.append(f"[{eid}] EVENT: hint issued (level {p.get('level')})")
        elif e["type"] == "execution_result":
            resp = p.get("response", {})
            per = resp.get("per_test", [])
            passed = sum(1 for t in per if t.get("passed"))
            lines.append(
                f"[{eid}] EVENT: code run ({p.get('language')}) -> "
                f"{resp.get('status')}, {passed}/{len(per)} tests passed"
            )
        elif e["type"] == "state_transition":
            lines.append(f"[{eid}] EVENT: round -> {p.get('to')}")
        elif e["type"] == "twist_injected":
            lines.append(f"[{eid}] EVENT: requirement twist introduced")
        elif e["type"] == "paste":
            lines.append(f"[{eid}] EVENT: paste into editor ({p.get('length', 0)} chars)")
    return "\n".join(lines)


def _store_degraded(
    db: DbSession,
    sid: uuid.UUID,
    org_id: uuid.UUID,
    competency_ids: list[str],
    reason: str,
    signals: dict[str, Any] | None = None,
) -> uuid.UUID:
    """Terminal record for a failed evaluation: degraded=True routes it to the
    review queue (T15) so an operator sees it — never a silently dropped job
    or a session stuck in Processing."""
    version = (
        db.scalar(
            select(Evaluation.version)
            .where(Evaluation.session_id == sid)
            .order_by(Evaluation.version.desc())
            .limit(1)
        )
        or 0
    ) + 1
    evaluation = Evaluation(
        id=uuid.uuid4(),
        org_id=org_id,
        session_id=sid,
        version=version,
        model=get_settings().eval_model,
        prompt_version_id=_prompt_version(db, "evaluate/scoring_v1").id,
        rubric={
            "competencies": {cid: {"evidence": []} for cid in competency_ids},
            "degraded": True,
            "degraded_reason": reason,
        },
        signals=signals or {},
    )
    db.add(evaluation)
    db.commit()
    log.error("degraded evaluation v%d stored for %s: %s", version, sid, reason)
    return evaluation.id


async def _call_model(
    db: DbSession,
    session_id: uuid.UUID,
    org_id: uuid.UUID,
    prompt_name: str,
    user_content: str,
) -> str:
    settings = get_settings()
    pv = _prompt_version(db, prompt_name)
    request = LLMRequest(
        model=settings.eval_model,
        system_blocks=[ContextBlock(pv.content, cached=True)],
        messages=[{"role": "user", "content": user_content}],
        max_tokens=4000,
    )
    # provider failover (T9 for the eval path): primary, then the other
    # configured provider — a single provider outage must not drop the job
    order = [settings.llm_provider]
    alt = "openrouter" if settings.llm_provider == "anthropic" else "anthropic"
    alt_key = settings.openrouter_api_key if alt == "openrouter" else settings.anthropic_api_key
    if alt_key:
        order.append(alt)
    last_exc: Exception | None = None
    for name in order:
        try:
            provider = get_provider(name)
            req = request
            if name == "openrouter":
                # OpenRouter needs its slug form of the model id
                req = LLMRequest(
                    model=f"anthropic/{settings.eval_model}",
                    system_blocks=request.system_blocks,
                    messages=request.messages,
                    max_tokens=request.max_tokens,
                )
            result = await provider.complete(req)
            _log_llm_call(db, session_id, org_id, pv, result)
            return result.text
        except Exception as exc:  # noqa: BLE001 - try the next tier
            last_exc = exc
            log.warning("eval provider %s failed for %s: %s", name, prompt_name, exc)
    raise RuntimeError(f"all eval providers failed for {prompt_name}: {last_exc}")


def _validate_evidence(
    raw: dict[str, Any], valid_ids: set[int], competency_ids: list[str]
) -> dict[str, list[EvidenceItem]]:
    out: dict[str, list[EvidenceItem]] = {}
    for cid in competency_ids:
        items = []
        for entry in raw.get(cid, []):
            item = EvidenceItem.model_validate(entry)
            if item.event_id in valid_ids:
                items.append(item)
        out[cid] = items
    return out


def _validate_scores(
    raw: dict[str, Any], evidence: dict[str, list[EvidenceItem]], competency_ids: list[str]
) -> dict[str, CompetencyScore]:
    out: dict[str, CompetencyScore] = {}
    errors: list[str] = []
    for cid in competency_ids:
        if cid not in raw:
            errors.append(f"missing competency {cid}")
            continue
        score = CompetencyScore.model_validate(raw[cid])
        allowed = {i.event_id for i in evidence.get(cid, [])}
        resolvable = [r for r in score.evidence_refs if r in allowed]
        if not resolvable:
            errors.append(f"{cid}: no resolvable evidence refs")
            continue
        score.evidence_refs = resolvable
        out[cid] = score
    if errors:
        raise ValueError("; ".join(errors))
    return out


async def evaluate_session(session_id: str) -> uuid.UUID:
    from app.db import set_rls_context

    sid = uuid.UUID(session_id)
    db = SessionLocal()
    try:
        # Worker path: bypass to locate the session, then pin its org (inv. #8)
        set_rls_context(db, bypass=True)
        session = db.get(Session, sid)
        if session is None:
            raise RuntimeError(f"session {session_id} not found")
        set_rls_context(db, org_id=str(session.org_id), bypass=False)
        plan = db.get(InterviewPlan, session.plan_id) if session.plan_id else None
        competencies: list[dict[str, Any]] = (plan.plan.get("competencies") if plan else None) or []
        competency_ids = [c["id"] for c in competencies]
        if not competency_ids:
            raise RuntimeError("session plan defines no competencies")

        rows = list(
            db.scalars(
                select(InterviewEvent)
                .where(InterviewEvent.session_id == sid)
                .order_by(InterviewEvent.seq)
            )
        )
        events: list[dict[str, Any]] = [
            {"id": r.id, "seq": r.seq, "ts": r.ts, "type": r.type, "payload": r.payload}
            for r in rows
        ]
        if not events:
            # aborted-before-anything sessions still deserve a terminal record:
            # a degraded evaluation routes to the review queue instead of the
            # session sitting in "Processing" forever
            return _store_degraded(
                db, sid, session.org_id, competency_ids,
                reason="session has no events to evaluate (partial/aborted)",
            )
        valid_ids: set[int] = {r.id for r in rows}

        signals = compute_signals(events)
        transcript = build_transcript(events)

        # Pass 1 — evidence
        evidence_input = (
            "Competencies: " + json.dumps(competencies)
            + "\n\nTranscript and events:\n" + transcript
        )
        try:
            evidence_text = await _call_model(
                db, sid, session.org_id, "evaluate/evidence_v1", evidence_input
            )
            evidence = _validate_evidence(
                _parse_json_object(evidence_text), valid_ids, competency_ids
            )
        except Exception as exc:  # noqa: BLE001 - degraded beats dropped
            log.error("evidence pass failed for %s: %s", sid, exc)
            return _store_degraded(
                db, sid, session.org_id, competency_ids,
                reason=f"evidence pass failed: {exc}"[:300], signals=signals,
            )

        # Pass 2 — scoring from evidence only (retry once on validation failure)
        jd_context = (
            "\n\nRole requirements (job description — score against this bar):\n"
            + session.jd_text.strip()[:3000]
            if session.jd_text
            else ""
        )
        scoring_input = (
            "Rubric competencies: " + json.dumps(competencies)
            + jd_context
            + "\n\nProcess signals (computed deterministically, read-only): "
            + json.dumps(signals)
            + "\n\nEvidence per competency:\n"
            + json.dumps({k: [i.model_dump() for i in v] for k, v in evidence.items()}, indent=1)
        )
        degraded = False
        scores: dict[str, CompetencyScore] = {}
        last_error = ""
        for attempt in range(2):
            try:
                extra = (
                    f"\n\nYour previous output was invalid ({last_error}). "
                    "Fix it and output valid JSON."
                    if attempt else ""
                )
                scoring_text = await _call_model(
                    db, sid, session.org_id, "evaluate/scoring_v1", scoring_input + extra
                )
                scores = _validate_scores(
                    _parse_json_object(scoring_text), evidence, competency_ids
                )
                break
            except Exception as exc:  # noqa: BLE001 - validation OR provider
                last_error = str(exc)[:300]
                log.warning("scoring pass attempt %d failed: %s", attempt + 1, last_error)
        else:
            degraded = True

        rubric = {
            "competencies": {
                cid: {
                    **(scores[cid].model_dump() if cid in scores else {}),
                    "evidence": [i.model_dump() for i in evidence.get(cid, [])],
                }
                for cid in competency_ids
            },
            "degraded": degraded,
        }

        version = (
            db.scalar(
                select(Evaluation.version)
                .where(Evaluation.session_id == sid)
                .order_by(Evaluation.version.desc())
                .limit(1)
            )
            or 0
        ) + 1
        evaluation = Evaluation(
            id=uuid.uuid4(),
            org_id=session.org_id,
            session_id=sid,
            version=version,
            model=get_settings().eval_model,
            prompt_version_id=_prompt_version(db, "evaluate/scoring_v1").id,
            rubric=rubric,
            signals=signals,
        )
        db.add(evaluation)
        db.commit()
        log.info(
            "evaluation v%d stored for session %s (degraded=%s)", version, session_id, degraded
        )
        return evaluation.id
    finally:
        db.close()
