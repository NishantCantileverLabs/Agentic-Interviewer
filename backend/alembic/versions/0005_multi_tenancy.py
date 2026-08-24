"""T10 — multi-tenancy foundation.

- orgs / users / memberships / admin_actions (admin_actions append-only)
- org_id on every tenant-owned table, backfilled to the default org
- Postgres Row-Level Security (ENABLE + FORCE) with a deny-by-default policy:
  unset app.current_org means zero rows. Workers/maintenance set
  app.bypass_rls='on' explicitly.
- prompt_versions stays platform-global (shared prompt library) by design.
- interview_events backfill requires temporarily disabling the append-only
  trigger (schema migration — the sole sanctioned context).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

DEFAULT_ORG = "00000000-0000-0000-0000-000000000001"

TENANT_TABLES = [
    "sessions",
    "interview_plans",
    "role_configs",
    "questions",
    "interview_events",
    "llm_calls",
    "evaluations",
    "human_evaluations",
    "briefs",
]


def upgrade() -> None:
    op.create_table(
        "orgs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text, nullable=False, unique=True),
        sa.Column("settings", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("auth_provider_id", sa.Text),
        sa.Column("email", sa.Text, nullable=False, unique=True),
        sa.Column("name", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "memberships",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orgs.id"), primary_key=True),
        sa.Column("role", sa.Text, nullable=False),
        sa.CheckConstraint("role IN ('admin','recruiter','reviewer')", name="ck_membership_role"),
    )
    op.create_table(
        "admin_actions",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orgs.id"), nullable=False),
        sa.Column("user_email", sa.Text, nullable=False),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.execute(
        """
        CREATE TRIGGER trg_admin_actions_no_update
            BEFORE UPDATE OR DELETE ON admin_actions
            FOR EACH ROW EXECUTE FUNCTION reject_event_update();
        """
    )

    op.execute(f"INSERT INTO orgs (id, name) VALUES ('{DEFAULT_ORG}', 'default')")

    # candidate link revocation anchor
    op.add_column("sessions", sa.Column("candidate_jti", sa.Text, nullable=True))

    # append-only trigger blocks UPDATE — schema migration is the sanctioned
    # exception; disable, backfill, re-enable
    op.execute("ALTER TABLE interview_events DISABLE TRIGGER trg_events_no_update")

    for table in TENANT_TABLES:
        op.add_column(table, sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orgs.id")))
        op.execute(f"UPDATE {table} SET org_id = '{DEFAULT_ORG}'")
        op.alter_column(table, "org_id", nullable=False)
        op.create_index(f"ix_{table}_org_id", table, ["org_id"])

    op.execute("ALTER TABLE interview_events ENABLE TRIGGER trg_events_no_update")

    # RLS: deny-by-default (unset app.current_org -> zero rows); explicit
    # bypass channel for workers/maintenance. FORCE applies it to the owner too.
    for table in TENANT_TABLES + ["admin_actions"]:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY org_isolation ON {table}
            USING (
                org_id = NULLIF(current_setting('app.current_org', true), '')::uuid
                OR current_setting('app.bypass_rls', true) = 'on'
            )
            WITH CHECK (
                org_id = NULLIF(current_setting('app.current_org', true), '')::uuid
                OR current_setting('app.bypass_rls', true) = 'on'
            )
            """
        )


def downgrade() -> None:
    raise NotImplementedError("Migrations are forward-only (CLAUDE.md engineering standards)")
