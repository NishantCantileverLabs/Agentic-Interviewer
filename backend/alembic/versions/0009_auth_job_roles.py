"""Accounts + job roles.

users grows first-party credential columns (password/OTP/Google) and an
account_type (staff | candidate). job_roles is the recruiter-facing "role"
a candidate is hired for; it binds a pipeline (multi-round) or plan
(single-round) so assignment drives which interview the candidate gets.
users stays a global identity table (no RLS — org access is via memberships);
job_roles is tenant-owned (org_id + RLS from first migration, invariant #8).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_hash", sa.Text))
    op.add_column(
        "users",
        sa.Column("auth_provider", sa.Text, nullable=False, server_default="password"),
    )
    op.add_column(
        "users",
        sa.Column("account_type", sa.Text, nullable=False, server_default="staff"),
    )
    op.add_column(
        "users",
        sa.Column("email_verified", sa.Boolean, nullable=False, server_default="false"),
    )
    op.add_column("users", sa.Column("otp_hash", sa.Text))
    op.add_column("users", sa.Column("otp_expires_at", sa.DateTime(timezone=True)))
    op.create_check_constraint(
        "ck_users_account_type", "users", "account_type IN ('staff','candidate')"
    )

    op.create_table(
        "job_roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orgs.id"), nullable=False
        ),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("pipeline_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("pipelines.id")),
        sa.Column(
            "plan_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("interview_plans.id")
        ),
        sa.Column("status", sa.Text, nullable=False, server_default="open"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_job_roles_org_id", "job_roles", ["org_id"])
    op.execute("ALTER TABLE job_roles ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE job_roles FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY org_isolation ON job_roles
        USING (org_id = NULLIF(current_setting('app.current_org', true), '')::uuid
               OR current_setting('app.bypass_rls', true) = 'on')
        WITH CHECK (org_id = NULLIF(current_setting('app.current_org', true), '')::uuid
                    OR current_setting('app.bypass_rls', true) = 'on')
        """
    )

    op.add_column(
        "candidacies",
        sa.Column(
            "job_role_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("job_roles.id")
        ),
    )

    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user")
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_user")


def downgrade() -> None:
    raise NotImplementedError("Migrations are forward-only (CLAUDE.md engineering standards)")
