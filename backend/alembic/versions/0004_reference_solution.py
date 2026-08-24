"""Add reference_solution to questions (admin-authored; never in any API response)."""

import sqlalchemy as sa

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("questions", sa.Column("reference_solution", sa.Text, nullable=True))


def downgrade() -> None:
    raise NotImplementedError("Migrations are forward-only (CLAUDE.md engineering standards)")
