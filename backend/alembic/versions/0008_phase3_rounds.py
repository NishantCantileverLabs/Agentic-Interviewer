"""Phase 3 — round-type content, pipelines, aggregation.

Extends the closed event vocabulary (ARCHITECTURE.md registry updated):
exhibit_revealed, canvas_delta_batch, canvas_snapshot, scratchpad_delta,
sql_executed, round_handoff.

case_packs / pipelines / resumes / aggregate_briefs are tenant tables (RLS);
design_questions and sql_datasets are platform-global content libraries
(like prompt_versions).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

NEW_TENANT_TABLES = ["case_packs", "resumes", "pipelines", "candidacy_progress", "aggregate_briefs"]


def upgrade() -> None:
    op.create_table(
        "case_packs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orgs.id"), nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("pack", postgresql.JSONB, nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "design_questions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("requirement_sheet", postgresql.JSONB, nullable=False),
        sa.Column("reference_components", postgresql.JSONB, nullable=False),
        sa.Column("dive_areas", postgresql.JSONB, nullable=False),
        sa.Column("estimation_blocks", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
    )

    op.create_table(
        "sql_datasets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("schema_ddl", sa.Text, nullable=False),
        sa.Column("tasks", postgresql.JSONB, nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
    )

    op.create_table(
        "resumes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orgs.id"), nullable=False),
        sa.Column("candidacy_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("candidacies.id"), nullable=False),
        sa.Column("raw_text", sa.Text, nullable=False),
        sa.Column("parsed_claims", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("parser_version", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "pipelines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orgs.id"), nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("role_config_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("role_configs.id")),
        sa.Column("rounds", postgresql.JSONB, nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "candidacy_progress",
        sa.Column("candidacy_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("candidacies.id"), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orgs.id"), nullable=False),
        sa.Column("pipeline_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("pipelines.id"), nullable=False),
        sa.Column("current_round", sa.Integer, nullable=False, server_default="0"),
        sa.Column("round_sessions", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("gate_state", sa.Text, nullable=False, server_default="advancing"),
        sa.CheckConstraint(
            "gate_state IN ('advancing','awaiting_review','ended','completed')",
            name="ck_gate_state",
        ),
    )

    op.create_table(
        "aggregate_briefs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orgs.id"), nullable=False),
        sa.Column("candidacy_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("candidacies.id"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("rollup", postgresql.JSONB, nullable=False),
        sa.Column("consistency", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("html_object_key", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.add_column("sessions", sa.Column("round_type", sa.Text))
    op.add_column("sessions", sa.Column("pipeline_round_index", sa.Integer))

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
