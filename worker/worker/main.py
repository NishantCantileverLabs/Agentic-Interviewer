"""Eval worker — consumes `evaluate_session` jobs from Redis.

T0: queue consumption loop only. The evaluation pipeline itself
(deterministic signals -> evidence extraction -> scoring) lands in T6.
"""

import json
import logging
import os
import signal
import sys
import time
from types import FrameType

import redis

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("eval-worker")

QUEUE = os.environ.get("EVAL_QUEUE", "evaluate_session")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

_running = True


def _stop(signum: int, frame: FrameType | None) -> None:
    global _running
    _running = False
    log.info("shutdown signal received")


def handle_job(payload: dict[str, object]) -> None:
    # T6 wires the real evaluation pipeline here.
    log.info("received evaluate_session job: %s", payload)


def main() -> None:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    # socket_timeout must exceed the blpop timeout or reads raise TimeoutError
    r = redis.Redis.from_url(REDIS_URL, socket_timeout=10, socket_connect_timeout=5)
    log.info("eval-worker listening on queue %r", QUEUE)

    while _running:
        try:
            item = r.blpop([QUEUE], timeout=5)
        except (redis.ConnectionError, redis.TimeoutError):
            log.warning("redis unavailable, retrying in 3s")
            time.sleep(3)
            continue
        if item is None:
            continue
        _, raw = item
        try:
            handle_job(json.loads(raw))
        except json.JSONDecodeError:
            log.error("malformed job payload dropped: %r", raw[:200])

    log.info("eval-worker stopped")
    sys.exit(0)


if __name__ == "__main__":
    main()
