"""Add JD + resume text to sessions (setup-time inputs, auditable)."""

import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("jd_text", sa.Text, nullable=True))
    op.add_column("sessions", sa.Column("resume_text", sa.Text, nullable=True))


def downgrade() -> None:
    raise NotImplementedError("Migrations are forward-only (CLAUDE.md engineering standards)")
