"""Eval worker — consumes evaluate_session jobs, runs T6 pipeline + T7 brief.

Runs as its own container on the backend image:
    python -m app.eval.worker
"""

import asyncio
import json
import logging
import signal
import sys
from types import FrameType

import redis

from app.config import get_settings
from app.db import SessionLocal
from app.eval.brief import generate_brief
from app.eval.pipeline import evaluate_session

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("eval-worker")

_running = True


def _stop(signum: int, frame: FrameType | None) -> None:
    global _running
    _running = False
    log.info("shutdown signal received")


def handle_job(payload: dict[str, object]) -> None:
    session_id = str(payload.get("session_id", ""))
    if not session_id:
        log.error("job missing session_id: %s", payload)
        return
    import uuid as _uuid

    from sqlalchemy import select

    from app.db import set_rls_context
    from app.models import Brief, Evaluation

    sid = _uuid.UUID(session_id)
    # Idempotency for at-least-once delivery: an existing evaluation is
    # REUSED, not recomputed (a redelivered job must not re-bill two LLM
    # passes); a missing brief is the only remaining work in that case.
    db = SessionLocal()
    try:
        set_rls_context(db, bypass=True)
        # operators can force a fresh evaluation: {"session_id":..., "force": true}
        existing = None if payload.get("force") else db.scalar(
            select(Evaluation)
            .where(Evaluation.session_id == sid)
            .order_by(Evaluation.version.desc())
            .limit(1)
        )
        if existing is not None:
            has_brief = (
                db.scalar(
                    select(Brief.id).where(Brief.evaluation_id == existing.id).limit(1)
                )
                is not None
            )
            if has_brief:
                log.info("session %s already evaluated+briefed — skipping", session_id)
                return
            log.info("session %s: reusing evaluation %s, generating brief", session_id, existing.id)
            brief_id = generate_brief(db, existing.id)
            log.info("session %s -> brief %s (reused evaluation)", session_id, brief_id)
            return
    finally:
        db.close()

    log.info("evaluating session %s", session_id)
    evaluation_id = asyncio.run(evaluate_session(session_id))
    db = SessionLocal()
    try:
        # brief generation reads/writes tenant rows: bypass to find the org,
        # then pin it for the writes (invariant #8)
        set_rls_context(db, bypass=True)
        brief_id = generate_brief(db, evaluation_id)
    finally:
        db.close()
    log.info("session %s -> evaluation %s -> brief %s", session_id, evaluation_id, brief_id)


def main() -> None:
    # same refuse-to-boot contract as the API — a worker with dev secrets in
    # production is the same hole through a different door
    from app.config import validate_production_posture

    validate_production_posture()
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    settings = get_settings()
    r = redis.Redis.from_url(settings.redis_url, socket_timeout=10, socket_connect_timeout=5)
    log.info("eval-worker listening on queue %r", settings.eval_queue)

    while _running:
        try:
            item = r.blpop([settings.eval_queue], timeout=5)
        except (redis.ConnectionError, redis.TimeoutError):
            log.warning("redis unavailable, retrying in 3s")
            import time

            time.sleep(3)
            continue
        if item is None:
            continue
        _, raw = item
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            log.error("malformed job payload dropped: %r", raw[:200])
            continue
        try:
            handle_job(payload)
        except Exception as exc:
            # at-least-once with bounded retries + dead-letter: a transient
            # failure (provider outage, DB blip) must not silently lose the
            # evaluation, and a poison job must not retry forever
            attempts = int(payload.get("attempts", 0)) + 1
            if attempts < 3:
                log.exception("evaluation job failed (attempt %d/3) — requeueing", attempts)
                import time as _time

                _time.sleep(2 * attempts)
                r.rpush(
                    settings.eval_queue, json.dumps({**payload, "attempts": attempts})
                )
            else:
                log.exception("evaluation job dead-lettered after %d attempts", attempts)
                r.lpush(
                    f"{settings.eval_queue}:dead",
                    json.dumps({**payload, "attempts": attempts, "error": str(exc)[:500]}),
                )

    log.info("eval-worker stopped")
    sys.exit(0)


if __name__ == "__main__":
    main()
