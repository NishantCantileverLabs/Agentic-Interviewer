"""Add sessions.voice — the candidate's interviewer-voice pick (Aura-2 model id).

Chosen in the lobby before joining; the agent reads it at bootstrap. NULL means
the platform default voice.
"""

import sqlalchemy as sa

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("voice", sa.Text, nullable=True))


def downgrade() -> None:
    raise NotImplementedError("Migrations are forward-only (CLAUDE.md engineering standards)")
