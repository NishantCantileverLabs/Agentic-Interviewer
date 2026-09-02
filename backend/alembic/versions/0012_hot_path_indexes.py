"""Hot-path indexes (production audit, Phase 3 findings).

Every index here backs a query the audit caught seq-scanning on a growing
table: event append eid-dedup, replay/type filters, candidacy lookups by
session/email, consent-gate checks, review-gate decision lookups, dashboard
ORDER BY created_at, prompt resolution on every logged LLM call.
"""

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

INDEXES = (
    # append-path eid dedup: was a full per-session event scan on every batch
    "CREATE INDEX IF NOT EXISTS ix_events_session_eid "
    "ON interview_events (session_id, (payload->>'eid'))",
    # code_at / turn_latency / execution_result filters
    "CREATE INDEX IF NOT EXISTS ix_events_session_type "
    "ON interview_events (session_id, type)",
    "CREATE INDEX IF NOT EXISTS ix_sessions_candidacy ON sessions (candidacy_id)",
    "CREATE INDEX IF NOT EXISTS ix_sessions_created ON sessions (created_at)",
    "CREATE INDEX IF NOT EXISTS ix_candidacies_email ON candidacies (candidate_email)",
    "CREATE INDEX IF NOT EXISTS ix_candidacies_job_role ON candidacies (job_role_id)",
    "CREATE INDEX IF NOT EXISTS ix_consent_candidacy ON consent_records (candidacy_id)",
    "CREATE INDEX IF NOT EXISTS ix_review_decisions_session "
    "ON review_decisions (session_id)",
    "CREATE INDEX IF NOT EXISTS ix_prompt_versions_name_created "
    "ON prompt_versions (name, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_evaluations_created ON evaluations (created_at)",
    "CREATE INDEX IF NOT EXISTS ix_schedules_candidacy ON schedules (candidacy_id)",
    "CREATE INDEX IF NOT EXISTS ix_llm_calls_session ON llm_calls (session_id)",
)


def upgrade() -> None:
    for stmt in INDEXES:
        op.execute(stmt)


def downgrade() -> None:
    raise NotImplementedError("Migrations are forward-only (CLAUDE.md engineering standards)")
