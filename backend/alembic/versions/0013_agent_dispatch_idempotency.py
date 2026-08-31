"""Agent dispatch idempotency — double-voice fix.

Every GET /sessions/{id}/token used to carry
RoomConfiguration(agents=[interviewer]), so a reconnect or a StrictMode
double-mount dispatched a SECOND agent into the same LiveKit room.
This column records the first dispatch timestamp so only the first token
ever requests a dispatch; reconnects rejoin the existing room/agent.
"""

import sqlalchemy as sa

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("agent_dispatched_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    raise NotImplementedError("Migrations are forward-only (CLAUDE.md engineering standards)")
