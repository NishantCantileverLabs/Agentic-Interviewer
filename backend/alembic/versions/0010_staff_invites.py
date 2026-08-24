"""Invite-only staff accounts.

staff_invites is the allow-list for org-side signups: registering as staff
succeeds only when a matching invite exists (or when the org has no members
yet — the first account becomes the owning admin). Tenant-owned: org_id +
RLS from first migration (invariant #8).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "staff_invites",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orgs.id"), nullable=False
        ),
        sa.Column("email", sa.Text, nullable=False),
        sa.Column("role", sa.Text, nullable=False, server_default="recruiter"),
        sa.Column("invited_by", sa.Text, nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("role IN ('reviewer','recruiter','admin')", name="ck_invite_role"),
        sa.UniqueConstraint("org_id", "email", name="uq_staff_invite_org_email"),
    )
    op.create_index("ix_staff_invites_org_id", "staff_invites", ["org_id"])
    op.create_index("ix_staff_invites_email", "staff_invites", ["email"])
    op.execute("ALTER TABLE staff_invites ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE staff_invites FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY org_isolation ON staff_invites
        USING (org_id = NULLIF(current_setting('app.current_org', true), '')::uuid
               OR current_setting('app.bypass_rls', true) = 'on')
        WITH CHECK (org_id = NULLIF(current_setting('app.current_org', true), '')::uuid
                    OR current_setting('app.bypass_rls', true) = 'on')
        """
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user")


def downgrade() -> None:
    raise NotImplementedError("Migrations are forward-only (CLAUDE.md engineering standards)")
