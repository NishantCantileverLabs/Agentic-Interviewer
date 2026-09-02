# CLAUDE.md — AI Interview Platform (Phase 1)

You are building a production voice AI interviewer. Read PHASE1_ARCHITECTURE.md
before any task. These rules are binding on every change.

## Non-negotiable invariants

1. `interview_events` is append-only and the single source of truth. Never add
   code that updates or deletes event rows (retention purge job is the sole
   exception). New event types require a migration + a note in ARCHITECTURE.md.
2. Every LLM call goes through `providers/` and logs to `llm_calls` with a real
   `prompt_version_id`. Never inline a prompt string in application code —
   prompts live in /prompts and are versioned.
3. The conduct model NEVER: decides state transitions, produces scores, reveals
   solutions or hidden-test expectations, or exceeds the spoken-brevity rules.
   The evaluation model NEVER runs in the live voice path.
4. Deterministic signals (hints, pastes, timings, latency stats) are computed in
   Python with unit tests — never by an LLM.
5. Hidden-test expected outputs must never appear in any API response. The CI
   contract test for this must stay green.
6. Engine state must remain a pure function of the event log:
   `rebuild(session_id)` tests must pass after any engine change.
7. Cache-stable context layout (ARCHITECTURE §6.3): never reorder blocks A–C,
   never rewrite block C retroactively. Anything per-turn goes in block D.

## Latency discipline

- The voice path (agent worker) may not gain synchronous calls to the control
  plane, Postgres, or Judge0. Event posting is batched/async only.
- Any change touching the agent pipeline must preserve the `turn_latency`
  instrumentation points and must be checked against the latency dashboard
  before merge. Targets: p50 ≤ 800 ms, p95 ≤ 1500 ms.
- Streaming everywhere: no code path may buffer a full LLM response before TTS.

## Engineering standards

- Python 3.11+, type hints everywhere, ruff + mypy clean. TypeScript strict.
- Alembic for every schema change; migrations are forward-only.
- Tests required per task: unit tests for engine logic and signal computation,
  contract tests for API shapes, the e2e mock-candidate script for anything
  touching the interview flow. A task is not done until its acceptance criteria
  from the task file pass.
- Fallback paths (STT dropout, LLM timeout, TTS failover) are features, not
  afterthoughts — they get tests too (fault injection in the e2e harness).
- Secrets only via environment; .env.example stays current.

## Phase 2 additions — binding

8. Tenancy: every new tenant-owned table gets org_id + RLS from its first
   migration. The cross-tenant test suite is CI-blocking. No query bypasses
   org scoping, including admin and worker paths (workers set org context
   explicitly per job).
9. Integrity signals never auto-reject and never trigger in-interview
   confrontation. attention_level is computed by the documented rule engine
   only — never by an LLM, never by an unexplainable model. Report language
   is observational; the banned-terms lint must stay green.
10. Proctoring privacy: raw frames leave the client only for consented,
    org-enabled sampled identity checks. No code path may buffer or transmit
    continuous video outside LiveKit's consented recording. Signal analysis
    that can run client-side runs client-side.
11. Consent gates are API-enforced (invariant #12), not UI-enforced. Any new
    data-collecting feature adds a consent item + policy version before it
    ships, not after.
12. ATS side effects exist only via ats_outbox (no direct calls in request
    handlers). Inbound webhooks are signature-verified and idempotent.
13. erase()/export() must remain correct as the schema grows: every migration
    adding candidate-derived data updates both, with tests, in the same PR.
14. Reviewer overrides require rationale; review_decisions and
    flag_dispositions are append-only.

## Phase 3 additions — binding

15. Round types are plugins: no plugin imports from the voice path, no core
    engine change ships inside a round-type PR. The import-linter rule and the
    golden-transcript suite are CI-blocking.
16. Numbers are adjudicated by code (math checker, SQL re-execution, component
    coverage). LLMs discuss numbers; they never decide correctness.
17. Every new candidate-facing tool (canvas, scratchpad, SQL console) ships
    with: event logging, *_at(t) replay parity tests, and inclusion in
    erase()/export() — in the same PR (extends Phase 2 rule 13).
18. Cross-round assertions require citations into every referenced session,
    schema-validated. No uncited consistency claims, ever.
19. Each round type passes its own shadow-mode gate before client exposure.
    Calibration does not transfer across formats.

## Working style

- One task file at a time, in the stated order. If a task reveals a conflict
  with the architecture doc, stop and surface it — do not silently diverge.
- Prefer boring technology and the framework's built-in path (LiveKit Agents
  plugins) over custom plumbing. Custom code is a liability in the voice path.
- When uncertain about a provider API detail, check current docs rather than
  assuming — STT/TTS/LLM APIs change frequently.
