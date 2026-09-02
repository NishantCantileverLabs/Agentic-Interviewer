"""Phase 2/3 models (T11 lifecycle, T15 review, T18 audit, Phase 3 rounds).

Kept in a separate module for readability; same declarative Base.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base

CANDIDACY_STATUSES = (
    "invited", "scheduled", "in_progress", "completed", "reviewed", "synced", "withdrawn",
)
CONSENT_ITEMS = ("audio_processing", "video_proctoring", "data_retention")
REQUIRED_CONSENT_ITEMS = ("audio_processing", "data_retention")


class Candidacy(Base):
    __tablename__ = "candidacies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id"), index=True)
    role_config_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("role_configs.id"))
    plan_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("interview_plans.id"))
    candidate_email: Mapped[str] = mapped_column(Text)
    candidate_name: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text, default="manual")
    ats_ref: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(Text, default="invited")
    jd_text: Mapped[str | None] = mapped_column(Text)
    resume_text: Mapped[str | None] = mapped_column(Text)
    job_role_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("job_roles.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StaffInvite(Base):
    """Allow-list for org-side signups: staff accounts are invite-only (the
    first account in an empty org bootstraps as admin)."""

    __tablename__ = "staff_invites"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id"), index=True)
    email: Mapped[str] = mapped_column(Text, index=True)
    role: Mapped[str] = mapped_column(Text, default="recruiter")
    invited_by: Mapped[str] = mapped_column(Text)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class JobRole(Base):
    """A hiring role: what recruiters create interviews *for*. Binds either a
    pipeline (multi-round) or a plan (single interview); assigning a candidate
    to the role decides which interview they get."""

    __tablename__ = "job_roles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id"), index=True)
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    pipeline_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("pipelines.id"))
    plan_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("interview_plans.id"))
    status: Mapped[str] = mapped_column(Text, default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Schedule(Base):
    __tablename__ = "schedules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id"), index=True)
    candidacy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidacies.id"))
    slot_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    slot_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reschedule_count: Mapped[int] = mapped_column(Integer, default=0)
    sitting: Mapped[int] = mapped_column(Integer, default=1)


class PolicyVersion(Base):
    __tablename__ = "policy_versions"

    version: Mapped[str] = mapped_column(Text, primary_key=True)
    item: Mapped[str] = mapped_column(Text, primary_key=True)
    text_md: Mapped[str] = mapped_column(Text)
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ConsentRecord(Base):
    __tablename__ = "consent_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id"), index=True)
    candidacy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidacies.id"))
    item: Mapped[str] = mapped_column(Text)
    granted: Mapped[bool] = mapped_column(Boolean)
    policy_version: Mapped[str] = mapped_column(Text)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReviewDecision(Base):
    __tablename__ = "review_decisions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id"), index=True)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id"))
    reviewer_email: Mapped[str] = mapped_column(Text)
    inflow: Mapped[str] = mapped_column(Text)  # integrity | degraded | borderline
    decision: Mapped[str] = mapped_column(Text)  # confirm | override
    rationale: Mapped[str] = mapped_column(Text)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FlagDisposition(Base):
    __tablename__ = "flag_dispositions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id"), index=True)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id"))
    signal: Mapped[str] = mapped_column(Text)
    disposition: Mapped[str] = mapped_column(Text)
    reviewer_email: Mapped[str] = mapped_column(Text)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PurgeAudit(Base):
    __tablename__ = "purge_audit"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id"), index=True)
    action: Mapped[str] = mapped_column(Text)  # retention_purge | erase | export
    subject: Mapped[str] = mapped_column(Text)
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    actor: Mapped[str] = mapped_column(Text)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ── Phase 3 ──────────────────────────────────────────────────────────


class CasePack(Base):
    __tablename__ = "case_packs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id"), index=True)
    title: Mapped[str] = mapped_column(Text)
    pack: Mapped[dict[str, Any]] = mapped_column(JSONB)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DesignQuestion(Base):
    __tablename__ = "design_questions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(Text)
    requirement_sheet: Mapped[dict[str, Any]] = mapped_column(JSONB)
    reference_components: Mapped[dict[str, Any]] = mapped_column(JSONB)
    dive_areas: Mapped[dict[str, Any]] = mapped_column(JSONB)
    estimation_blocks: Mapped[dict[str, Any]] = mapped_column(JSONB, default=list)
    version: Mapped[int] = mapped_column(Integer, default=1)


class SqlDataset(Base):
    __tablename__ = "sql_datasets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(Text)
    schema_ddl: Mapped[str] = mapped_column(Text)
    tasks: Mapped[dict[str, Any]] = mapped_column(JSONB)
    version: Mapped[int] = mapped_column(Integer, default=1)


class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id"), index=True)
    candidacy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidacies.id"))
    raw_text: Mapped[str] = mapped_column(Text)
    parsed_claims: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    parser_version: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Pipeline(Base):
    __tablename__ = "pipelines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id"), index=True)
    name: Mapped[str] = mapped_column(Text)
    role_config_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("role_configs.id"))
    rounds: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CandidacyProgress(Base):
    __tablename__ = "candidacy_progress"

    candidacy_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidacies.id"), primary_key=True
    )
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id"), index=True)
    pipeline_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pipelines.id"))
    current_round: Mapped[int] = mapped_column(Integer, default=0)
    round_sessions: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    gate_state: Mapped[str] = mapped_column(Text, default="advancing")


class AggregateBrief(Base):
    __tablename__ = "aggregate_briefs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id"), index=True)
    candidacy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidacies.id"))
    version: Mapped[int] = mapped_column(Integer, default=1)
    rollup: Mapped[dict[str, Any]] = mapped_column(JSONB)
    consistency: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    html_object_key: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
