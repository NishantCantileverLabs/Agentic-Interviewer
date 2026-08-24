"""Server-side event append helper.

seq is allocated under a per-session Postgres advisory lock (same scheme as
POST /events), so agent batches, browser beacons, and server-side appends
interleave without conflicts. Append-only semantics are unchanged.
"""

import uuid
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session as DbSession

from app.models import InterviewEvent


def append_event(
    db: DbSession,
    session_id: uuid.UUID,
    org_id: uuid.UUID,
    type_: str,
    payload: dict[str, Any],
) -> InterviewEvent:
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": str(session_id)})
    last_seq = db.scalar(
        select(InterviewEvent.seq)
        .where(InterviewEvent.session_id == session_id)
        .order_by(InterviewEvent.seq.desc())
        .limit(1)
    )
    row = InterviewEvent(
        session_id=session_id,
        org_id=org_id,
        seq=(last_seq if last_seq is not None else -1) + 1,
        type=type_,
        payload=payload,
    )
    db.add(row)
    db.commit()
    return row
