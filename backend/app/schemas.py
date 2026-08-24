import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, field_validator

from app.models import EVENT_TYPES


class SessionCreate(BaseModel):
    candidate_label: str
    role_config_id: uuid.UUID | None = None
    plan_id: uuid.UUID | None = None
    retention_days: int = 90
    jd_text: str | None = None
    resume_text: str | None = None


class SessionOut(BaseModel):
    id: uuid.UUID
    candidate_label: str
    status: str
    livekit_room: str | None
    retention_days: int
    jd_text: str | None = None
    resume_text: str | None = None
    voice: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class EventIn(BaseModel):
    # seq is server-assigned (multi-writer safety); a client-supplied value is ignored
    seq: int | None = None
    type: str
    payload: dict[str, Any] = {}
    ts: datetime | None = None

    @field_validator("type")
    @classmethod
    def type_in_vocabulary(cls, v: str) -> str:
        if v not in EVENT_TYPES:
            raise ValueError(
                f"unknown event type {v!r}; the vocabulary is closed "
                "(extend via migration + ARCHITECTURE.md note)"
            )
        return v


class EventBatchIn(BaseModel):
    events: list[EventIn]


class EventOut(BaseModel):
    id: int
    session_id: uuid.UUID
    seq: int
    ts: datetime
    type: str
    payload: dict[str, Any]

    model_config = {"from_attributes": True}
