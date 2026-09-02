"""Initial schema — PHASE1_ARCHITECTURE.md §4.

Includes the immutability trigger on interview_events (invariant #1):
UPDATEs are rejected at the database level. DELETE is left open solely
for the retention purge job (T9); application code must never delete.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "role_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text, nullable=False, unique=True),
        sa.Column("competencies", postgresql.JSONB, nullable=False),
        sa.Column("weights", postgresql.JSONB, nullable=False),
        sa.Column("thresholds", postgresql.JSONB, nullable=False),
    )

    op.create_table(
        "interview_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("role_config_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("role_configs.id")),
        sa.Column("plan", postgresql.JSONB, nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
    )

    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("candidate_label", sa.Text, nullable=False),
        sa.Column("role_config_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("role_configs.id")),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("interview_plans.id")),
        sa.Column("status", sa.Text, nullable=False, server_default="created"),
        sa.Column("livekit_room", sa.Text),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("retention_days", sa.Integer, nullable=False, server_default="90"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('created','in_progress','paused','completed','aborted')",
            name="ck_sessions_status",
        ),
    )

    op.create_table(
        "interview_events",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("seq", sa.Integer, nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("type", sa.Text, nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.UniqueConstraint("session_id", "seq", name="uq_events_session_seq"),
    )
    op.create_index("ix_interview_events_session_id", "interview_events", ["session_id"])

    # Invariant #1: append-only. Block UPDATE at the DB level.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION reject_event_update() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'interview_events is append-only (PHASE1_ARCHITECTURE.md invariant #1)';
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_events_no_update
            BEFORE UPDATE ON interview_events
            FOR EACH ROW EXECUTE FUNCTION reject_event_update();
        """
    )

    op.create_table(
        "questions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("statement_md", sa.Text, nullable=False),
        sa.Column("language_targets", postgresql.ARRAY(sa.Text), nullable=False),
        sa.Column("visible_tests", postgresql.JSONB, nullable=False),
        sa.Column("hidden_tests", postgresql.JSONB, nullable=False),
        sa.Column("hints", postgresql.JSONB, nullable=False),
        sa.Column("twist", postgresql.JSONB),
        sa.Column("difficulty", sa.Integer, nullable=False, server_default="1"),
    )

    op.create_table(
        "prompt_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("role", sa.Text, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("model_target", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("notes", sa.Text),
        sa.CheckConstraint("role IN ('conduct','evaluate','brief')", name="ck_prompt_role"),
    )

    op.create_table(
        "llm_calls",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sessions.id")),
        sa.Column("prompt_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("prompt_versions.id"), nullable=False),
        sa.Column("role", sa.Text, nullable=False),
        sa.Column("model", sa.Text, nullable=False),
        sa.Column("input_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cached_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("ttft_ms", sa.Integer),
        sa.Column("total_ms", sa.Integer),
        sa.Column("cost_estimate", sa.Numeric(10, 6)),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_llm_calls_session_id", "llm_calls", ["session_id"])

    op.create_table(
        "evaluations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("model", sa.Text, nullable=False),
        sa.Column("prompt_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("prompt_versions.id"), nullable=False),
        sa.Column("rubric", postgresql.JSONB, nullable=False),
        sa.Column("signals", postgresql.JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("session_id", "version", name="uq_eval_session_version"),
    )
    op.create_index("ix_evaluations_session_id", "evaluations", ["session_id"])

    op.create_table(
        "human_evaluations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("reviewer", sa.Text, nullable=False),
        sa.Column("rubric", postgresql.JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_human_evaluations_session_id", "human_evaluations", ["session_id"])

    op.create_table(
        "briefs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("evaluation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("evaluations.id"), nullable=False),
        sa.Column("html_object_key", sa.Text, nullable=False),
        sa.Column("summary", postgresql.JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_briefs_session_id", "briefs", ["session_id"])


def downgrade() -> None:
    raise NotImplementedError("Migrations are forward-only (CLAUDE.md engineering standards)")
