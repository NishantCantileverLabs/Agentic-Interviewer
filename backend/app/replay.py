"""Point-in-time code reconstruction (PHASE1_ARCHITECTURE.md §7.1).

`code_at(events, t)` folds editor_snapshot + editor_delta_batch events up to
timestamp t: start from the latest snapshot at or before t, then apply delta
batches after it in seq order.

Delta shape (recorded by the frontend from Monaco content-change events, with
changes within one event pre-sorted by descending rangeOffset so sequential
application against the same base document is correct):
    {"deltas": [{"rangeOffset": int, "rangeLength": int, "text": str}, ...]}
"""

from datetime import datetime
from typing import Any


def apply_delta_batch(code: str, batch: dict[str, Any]) -> str:
    for d in batch.get("deltas", []):
        offset = int(d["rangeOffset"])
        length = int(d["rangeLength"])
        code = code[:offset] + str(d.get("text", "")) + code[offset + length :]
    return code


def code_at(events: list[dict[str, Any]], t: datetime) -> dict[str, Any]:
    """events: ordered replay rows (dicts with ts/type/payload/seq)."""

    def ts_of(ev: dict[str, Any]) -> datetime:
        ts = ev["ts"]
        return datetime.fromisoformat(ts) if isinstance(ts, str) else ts

    snapshot_code = ""
    snapshot_seq = -1
    language = None
    for ev in events:
        if ev["type"] == "editor_snapshot" and ts_of(ev) <= t:
            snapshot_code = ev["payload"].get("code", "")
            snapshot_seq = ev["seq"]
            language = ev["payload"].get("language", language)

    code = snapshot_code
    applied = 0
    for ev in events:
        if (
            ev["type"] == "editor_delta_batch"
            and ev["seq"] > snapshot_seq
            and ts_of(ev) <= t
        ):
            code = apply_delta_batch(code, ev["payload"])
            applied += 1
        if ev["type"] == "editor_delta_batch" and language is None:
            language = ev["payload"].get("language")

    return {
        "code": code,
        "language": language,
        "as_of": t.isoformat(),
        "base_snapshot_seq": snapshot_seq if snapshot_seq >= 0 else None,
        "delta_batches_applied": applied,
    }
