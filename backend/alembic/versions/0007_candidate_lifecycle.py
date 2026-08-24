"""T11/T15/T18 — candidacies, consent, review queue, compliance mechanics.

All new tenant tables ship with org_id + RLS from birth (invariant #8).
review_decisions and flag_dispositions are append-only (invariant #14).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

NEW_TENANT_TABLES = [
    "candidacies",
    "schedules",
    "consent_records",
    "review_decisions",
    "flag_dispositions",
    "purge_audit",
]


def upgrade() -> None:
    op.create_table(
        "candidacies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orgs.id"), nullable=False),
        sa.Column("role_config_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("role_configs.id")),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("interview_plans.id")),
        sa.Column("candidate_email", sa.Text, nullable=False),
        sa.Column("candidate_name", sa.Text, nullable=False),
        sa.Column("source", sa.Text, nullable=False, server_default="manual"),
        sa.Column("ats_ref", postgresql.JSONB),
        sa.Column("status", sa.Text, nullable=False, server_default="invited"),
        sa.Column("jd_text", sa.Text),
        sa.Column("resume_text", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('invited','scheduled','in_progress','completed','reviewed','synced','withdrawn')",
            name="ck_candidacy_status",
        ),
    )

    op.create_table(
        "schedules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orgs.id"), nullable=False),
        sa.Column("candidacy_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("candidacies.id"), nullable=False),
        sa.Column("slot_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("slot_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reschedule_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("sitting", sa.Integer, nullable=False, server_default="1"),
    )

    op.create_table(
        "policy_versions",
        sa.Column("version", sa.Text, primary_key=True),
        sa.Column("item", sa.Text, primary_key=True),
        sa.Column("text_md", sa.Text, nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "consent_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orgs.id"), nullable=False),
        sa.Column("candidacy_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("candidacies.id"), nullable=False),
        sa.Column("item", sa.Text, nullable=False),
        sa.Column("granted", sa.Boolean, nullable=False),
        sa.Column("policy_version", sa.Text, nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "review_decisions",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orgs.id"), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("reviewer_email", sa.Text, nullable=False),
        sa.Column("inflow", sa.Text, nullable=False),
        sa.Column("decision", sa.Text, nullable=False),
        sa.Column("rationale", sa.Text, nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("inflow IN ('integrity','degraded','borderline')", name="ck_review_inflow"),
        sa.CheckConstraint("decision IN ('confirm','override')", name="ck_review_decision"),
        sa.CheckConstraint("length(trim(rationale)) > 0", name="ck_review_rationale_nonempty"),
    )
    op.execute(
        "CREATE TRIGGER trg_review_decisions_ro BEFORE UPDATE OR DELETE ON review_decisions "
        "FOR EACH ROW EXECUTE FUNCTION reject_event_update()"
    )

    op.create_table(
        "flag_dispositions",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orgs.id"), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("signal", sa.Text, nullable=False),
        sa.Column("disposition", sa.Text, nullable=False),
        sa.Column("reviewer_email", sa.Text, nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "disposition IN ('substantiated','benign','unclear')", name="ck_disposition"
        ),
    )
    op.execute(
        "CREATE TRIGGER trg_flag_dispositions_ro BEFORE UPDATE OR DELETE ON flag_dispositions "
        "FOR EACH ROW EXECUTE FUNCTION reject_event_update()"
    )

    # T18: purge/erase audit trail
    op.create_table(
        "purge_audit",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orgs.id"), nullable=False),
        sa.Column("action", sa.Text, nullable=False),  # retention_purge | erase | export
        sa.Column("subject", sa.Text, nullable=False),  # session/candidacy id
        sa.Column("detail", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("actor", sa.Text, nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.add_column(
        "sessions",
        sa.Column("candidacy_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("candidacies.id")),
    )

    for table in NEW_TENANT_TABLES:
        op.create_index(f"ix_{table}_org_id", table, ["org_id"])
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY org_isolation ON {table}
            USING (org_id = NULLIF(current_setting('app.current_org', true), '')::uuid
                   OR current_setting('app.bypass_rls', true) = 'on')
            WITH CHECK (org_id = NULLIF(current_setting('app.current_org', true), '')::uuid
                        OR current_setting('app.bypass_rls', true) = 'on')
            """
        )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user")
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_user")


def downgrade() -> None:
    raise NotImplementedError("Migrations are forward-only (CLAUDE.md engineering standards)")
