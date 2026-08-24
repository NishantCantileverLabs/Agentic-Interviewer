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
    log.info("evaluating session %s", session_id)
    evaluation_id = asyncio.run(evaluate_session(session_id))
    from app.db import set_rls_context

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
            handle_job(json.loads(raw))
        except json.JSONDecodeError:
            log.error("malformed job payload dropped: %r", raw[:200])
        except Exception:
            log.exception("evaluation job failed")

    log.info("eval-worker stopped")
    sys.exit(0)


if __name__ == "__main__":
    main()
