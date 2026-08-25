"""Async, batched event posting to the control plane.

Latency discipline (CLAUDE.md): the voice path never blocks on the control
plane. Events are queued in memory and flushed by a background task; a lagging
or down API costs nothing but delayed durability.
"""

import asyncio
import logging
import os
import uuid
from typing import Any

import httpx

log = logging.getLogger("event-sink")

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
FLUSH_INTERVAL_S = 2.0
# T10: the agent is a trusted service — authenticates with the internal key
_HEADERS = {"X-Internal-Key": os.environ.get("INTERNAL_API_KEY", "dev-internal-key")}


class EventSink:
    def __init__(self, session_id: str) -> None:
        self._session_id = session_id
        self._queue: list[dict[str, Any]] = []
        self._lock = asyncio.Lock()
        # generous timeout: a slow control plane must produce late durability,
        # not spurious retry churn (retries are idempotent via eid regardless)
        self._client = httpx.AsyncClient(base_url=BACKEND_URL, timeout=30, headers=_HEADERS)
        self._task: asyncio.Task[None] | None = None
        self._closed = False

    def emit(self, type_: str, payload: dict[str, Any]) -> None:
        """Synchronous, non-blocking enqueue — safe to call from the voice path.
        seq is server-assigned; batch order is preserved server-side.
        Each event carries a client id ("eid") so a retried flush — e.g. a
        timeout AFTER the server persisted the batch — can never duplicate
        events in the log (the server skips eids it has already stored)."""
        if self._closed:
            log.debug("event %s dropped: sink already closed", type_)
            return
        self._queue.append({"type": type_, "payload": {**payload, "eid": uuid.uuid4().hex}})

    async def start(self) -> None:
        self._task = asyncio.create_task(self._flush_loop())

    async def _flush_loop(self) -> None:
        while True:
            await asyncio.sleep(FLUSH_INTERVAL_S)
            await self.flush()

    async def flush(self) -> None:
        async with self._lock:
            if not self._queue:
                return
            batch, self._queue = self._queue, []
        try:
            resp = await self._client.post(
                f"/sessions/{self._session_id}/events", json={"events": batch}
            )
            resp.raise_for_status()
        except (TypeError, ValueError) as exc:
            # poison batch (non-JSON-serializable payload): re-queueing would
            # block every later event forever — drop it and say so loudly
            log.error("dropping %d unserializable events: %s", len(batch), exc)
        except Exception as exc:  # noqa: BLE001 - never crash the voice path
            log.warning("event flush failed (%s); re-queueing %d events", exc, len(batch))
            async with self._lock:
                self._queue = batch + self._queue

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._task:
            self._task.cancel()
        await self.flush()
        await self._client.aclose()


async def create_backend_session(candidate_label: str) -> str | None:
    """Create a session row so spike events land in the real event log."""
    try:
        async with httpx.AsyncClient(base_url=BACKEND_URL, timeout=10, headers=_HEADERS) as client:
            resp = await client.post("/sessions", json={"candidate_label": candidate_label})
            resp.raise_for_status()
            return str(resp.json()["id"])
    except httpx.HTTPError as exc:
        log.warning("backend unavailable (%s) — spike runs without durable events", exc)
        return None


class BackendClient:
    """Read/side-channel API calls for the engine-driven agent. Never in the
    hot voice path — used by background tasks (bootstrap, observation loop)."""

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(base_url=BACKEND_URL, timeout=10, headers=_HEADERS)

    async def get_json(self, path: str) -> Any | None:
        try:
            resp = await self._client.get(path)
            resp.raise_for_status()
            return resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            # ValueError: a 200 with a non-JSON body (proxy error page) must
            # degrade like any other failed fetch, not kill the caller's loop
            log.warning("GET %s failed: %s", path, exc)
            return None

    async def replay(self, session_id: str, after_seq: int = -1) -> list[dict[str, Any]]:
        return await self.get_json(f"/sessions/{session_id}/replay?after_seq={after_seq}") or []

    async def set_status(self, session_id: str, status: str) -> None:
        try:
            await self._client.patch(f"/sessions/{session_id}/status", json={"status": status})
        except httpx.HTTPError as exc:
            log.warning("status update failed: %s", exc)

    async def log_llm_call(self, payload: dict[str, Any]) -> None:
        try:
            resp = await self._client.post("/llm-calls", json=payload)
            if resp.status_code >= 300:
                # a 422 here means an unsynced prompt name — invariant #2's
                # audit row was rejected, which must not pass silently
                log.warning(
                    "llm-call log rejected (%s): %s", resp.status_code, resp.text[:200]
                )
        except httpx.HTTPError as exc:
            log.warning("llm-call log failed: %s", exc)

    async def close(self) -> None:
        await self._client.aclose()
