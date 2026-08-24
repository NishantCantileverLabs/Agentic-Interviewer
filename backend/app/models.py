"""SQLAlchemy models mirroring PHASE1_ARCHITECTURE.md §4.

`interview_events` is append-only (invariant #1): a DB trigger blocks UPDATEs,
and the only sanctioned DELETE path is the retention purge job.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


SESSION_STATUSES = ("created", "in_progress", "paused", "completed", "aborted")

# Closed vocabulary (PHASE1_ARCHITECTURE.md §4). Extending it requires a
# migration + an ARCHITECTURE.md note.
EVENT_TYPES = (
    "stt_final",
    "agent_turn",
    "state_transition",
    "hint_issued",
    "twist_injected",
    "editor_delta_batch",
    "editor_snapshot",
    "paste",
    "tab_visibility",
    "run_clicked",
    "execution_result",
    "barge_in",
    "turn_latency",
    "error",
    "fallback_triggered",
    # Phase 3 (migration 0008): new tool + pipeline events
    "exhibit_revealed",
    "canvas_delta_batch",
    "canvas_snapshot",
    "scratchpad_delta",
    "sql_executed",
    "round_handoff",
)

PROMPT_ROLES = ("conduct", "evaluate", "brief")


class Org(Base):
    __tablename__ = "orgs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, unique=True)
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    auth_provider_id: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str | None] = mapped_column(Text)
    password_hash: Mapped[str | None] = mapped_column(Text)
    auth_provider: Mapped[str] = mapped_column(Text, default="password")  # password | google
    account_type: Mapped[str] = mapped_column(Text, default="staff")  # staff | candidate
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    otp_hash: Mapped[str | None] = mapped_column(Text)
    otp_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Membership(Base):
    __tablename__ = "memberships"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id"), primary_key=True)
    role: Mapped[str] = mapped_column(Text)  # admin | recruiter | reviewer


class AdminAction(Base):
    __tablename__ = "admin_actions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id"))
    user_email: Mapped[str] = mapped_column(Text)
    action: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id"), index=True)
    candidate_jti: Mapped[str | None] = mapped_column(Text)
    candidate_label: Mapped[str] = mapped_column(Text)
    role_config_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("role_configs.id"))
    plan_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("interview_plans.id"))
    status: Mapped[str] = mapped_column(Text, default="created")
    livekit_room: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retention_days: Mapped[int] = mapped_column(Integer, default=90)
    jd_text: Mapped[str | None] = mapped_column(Text)
    resume_text: Mapped[str | None] = mapped_column(Text)
    candidacy_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("candidacies.id"))
    round_type: Mapped[str | None] = mapped_column(Text)
    pipeline_round_index: Mapped[int | None] = mapped_column(Integer)
    # candidate's TTS voice pick (Aura-2 model id); NULL = platform default
    voice: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class InterviewEvent(Base):
    __tablename__ = "interview_events"
    __table_args__ = (UniqueConstraint("session_id", "seq", name="uq_events_session_seq"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id"), index=True)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    type: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class InterviewPlan(Base):
    __tablename__ = "interview_plans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id"), index=True)
    role_config_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("role_configs.id"))
    plan: Mapped[dict[str, Any]] = mapped_column(JSONB)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class RoleConfig(Base):
    __tablename__ = "role_configs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id"), index=True)
    name: Mapped[str] = mapped_column(Text, unique=True)
    competencies: Mapped[dict[str, Any]] = mapped_column(JSONB)
    weights: Mapped[dict[str, Any]] = mapped_column(JSONB)
    thresholds: Mapped[dict[str, Any]] = mapped_column(JSONB)


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id"), index=True)
    title: Mapped[str] = mapped_column(Text)
    statement_md: Mapped[str] = mapped_column(Text)
    language_targets: Mapped[list[str]] = mapped_column(ARRAY(Text))
    visible_tests: Mapped[dict[str, Any]] = mapped_column(JSONB)
    hidden_tests: Mapped[dict[str, Any]] = mapped_column(JSONB)
    hints: Mapped[dict[str, Any]] = mapped_column(JSONB)  # exactly 3 levels
    twist: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    difficulty: Mapped[int] = mapped_column(Integer, default=1)
    # Admin-authored reference solution: stored for review context only —
    # never returned by any API response (same discipline as hidden tests).
    reference_solution: Mapped[str | None] = mapped_column(Text)


class PromptVersion(Base):
    __tablename__ = "prompt_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text)  # conduct | evaluate | brief
    content: Mapped[str] = mapped_column(Text)
    model_target: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    notes: Mapped[str | None] = mapped_column(Text)


class LLMCall(Base):
    __tablename__ = "llm_calls"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id"), index=True)
    session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sessions.id"), index=True)
    prompt_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("prompt_versions.id"))
    role: Mapped[str] = mapped_column(Text)  # conduct | evaluate | brief
    model: Mapped[str] = mapped_column(Text)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cached_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    ttft_ms: Mapped[int | None] = mapped_column(Integer)
    total_ms: Mapped[int | None] = mapped_column(Integer)
    cost_estimate: Mapped[float | None] = mapped_column(Numeric(10, 6))
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Evaluation(Base):
    __tablename__ = "evaluations"
    __table_args__ = (UniqueConstraint("session_id", "version", name="uq_eval_session_version"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id"), index=True)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)  # re-runs create version+1
    model: Mapped[str] = mapped_column(Text)
    prompt_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("prompt_versions.id"))
    rubric: Mapped[dict[str, Any]] = mapped_column(JSONB)
    signals: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class HumanEvaluation(Base):
    __tablename__ = "human_evaluations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id"), index=True)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id"), index=True)
    reviewer: Mapped[str] = mapped_column(Text)
    rubric: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Brief(Base):
    __tablename__ = "briefs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id"), index=True)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id"), index=True)
    evaluation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evaluations.id"))
    html_object_key: Mapped[str] = mapped_column(Text)
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
