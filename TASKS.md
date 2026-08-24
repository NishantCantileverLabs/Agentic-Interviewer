# AI Interviewer Platform — Task List

> **Phase 2 (T10–T18)** is specified in [PHASE2_ARCHITECTURE.md](PHASE2_ARCHITECTURE.md) §10:
> T10 tenancy/auth → T11 candidate lifecycle → {T12 client proctoring, T15 dashboard, T17 ATS}
> → T13 server integrity → T14 integrity report → T16 calibration → T18 hardening.
> Gate 3 before real candidates; Gate 4 before integrity signals reach clients.

Project: AI-driven technical interview platform (voice + collaborative coding + async evaluation).
Status: Saved 2026-08-23. Awaiting go-ahead on which task to start.

---

## TASK 0 — Project scaffold & architecture record

**Objective:** Set up the monorepo and dev environment so all subsequent tasks land in a consistent structure.

**Requirements:**
- Monorepo: `/backend` (FastAPI, Python 3.11+), `/frontend` (Next.js 14 + TypeScript), `/worker` (async evaluation jobs), `/infra` (docker-compose)
- docker-compose dev stack: Postgres 16, Redis, MinIO (S3-compatible, for recordings), backend, worker
- Alembic migrations from day one; core tables: `sessions`, `interview_events` (append-only event log — every STT partial, LLM turn, editor event, hint lands here), `evaluations`, `prompt_versions`
- LLM provider abstraction layer (`providers/base.py`) with Anthropic implementation — same multi-provider pattern as the Workbench
- Write `ARCHITECTURE.md` recording decisions: event-sourced session log as source of truth, dual-model conduct/evaluate split, streaming-first design

**Acceptance:** `docker compose up` gives a healthy stack; a smoke test writes and reads an `interview_events` row.

---

## TASK 1 — Voice loop spike (P0, highest risk)

**Objective:** Prove the streaming voice pipeline hits latency targets before building anything on top of it.

**Requirements:**
- LiveKit (self-hosted or cloud) room; candidate joins from browser with mic
- Pipeline: Deepgram streaming STT (interim results on) → conversation LLM (streaming) → ElevenLabs streaming TTS → LiveKit audio out. Pipeline stages must overlap: start TTS on first LLM sentence, don't wait for full completion
- Barge-in: candidate speech during agent audio cancels TTS playback and truncates the pending LLM generation
- Silence handling: distinguish thinking pause (no filler) from turn end — endpointing threshold ~1.2s, configurable; agent must tolerate 10s+ thinking silence during hard questions without interjecting
- Latency instrumentation: log timestamps at every stage boundary; emit p50/p95 end-of-candidate-speech → first-audio-out
- Throwaway UI is fine; this is a spike

**Acceptance:** p50 < 800ms, p95 < 1500ms measured over 20 exchanges; barge-in works; a 10s silence does not trigger an agent turn.

**Note:** If latency targets fail with this stack, evaluate Pipecat or a speech-to-speech model before proceeding — do not build Task 2 on a failed spike.

---

## TASK 2 — Interview engine state machine

**Objective:** The orchestrator that runs a structured interview, with the LLM controlling behavior only within states.

**Requirements:**
- States: `INTRO → WARMUP → TECHNICAL_DEEPDIVE → CODING → WRAPUP → ENDED`; transitions driven by the engine (time budgets + completion criteria), never by the LLM freestyling
- Interview plan schema (JSON, stored per session): role config, competencies with weights, question bank refs, time budget per state, probe budget per competency (default 3)
- Per-state system prompts, versioned in `prompt_versions` and referenced by ID in every LLM call — this is the audit trail
- Probe budget enforcement: engine tracks probes-used per competency; when exhausted, injects a move-on directive into the next prompt
- Full session state persisted after every turn (crash-recoverable: a killed process can resume mid-interview from the event log)
- Conversation context management: rolling transcript window + running structured summary of covered competencies

**Acceptance:** A scripted mock candidate (text mode, no voice needed) completes a full state traversal; transcript shows probing within budget and clean state transitions; every LLM call in the log carries a prompt version ID.

---

## TASK 3 — Collaborative code editor with process capture

**Objective:** Monaco + Yjs editor where every keystroke is captured — process data is a first-class evaluation signal.

**Requirements:**
- Monaco in the Next.js app, Yjs CRDT sync via y-websocket (backend hosts the websocket server)
- Language support Phase 1: Python, JavaScript, Java, C++ (syntax highlighting only; no LSP yet)
- Event capture to `interview_events`: batched editor deltas (500ms flush), cursor position, selection, paste events (with paste length — large pastes are an integrity signal), test-run clicks
- Periodic full snapshots (every 30s + on run) so any point-in-time code state is reconstructible
- Copy-paste and tab-visibility (`visibilitychange`) event logging — log only, no blocking, no candidate-facing warnings in Phase 1
- Replay endpoint: given session ID, return the ordered event stream (feeds Task 5's live observation and Task 8's review UI)

**Acceptance:** Two browser tabs stay in sync; killing and rejoining preserves state; replay endpoint reconstructs the exact code at an arbitrary timestamp; a 200-char paste appears in the event log with its length.

---

## TASK 4 — Sandboxed code execution service (P0)

**Objective:** Safe, fast execution of candidate code with visible and hidden test cases.

**Requirements:**
- Recommended: self-hosted Judge0 (Docker) for Phase 1 — swap for Firecracker-based later; wrap it behind our own `POST /execute` so the backend never exposes Judge0 directly
- API contract: `{language, source, stdin?, test_suite_id?}` → `{status, stdout, stderr, per_test: [{id, passed, time_ms, hidden}]}`; hidden tests return pass/fail only, never expected output
- Limits: 5s CPU, 256MB memory, no network egress, output truncated at 64KB
- Test suite schema per question: visible examples (shown in UI) + hidden cases (run on submit); stored in Postgres
- Every execution logged to `interview_events` with full result
- Queue with per-session rate limit (max 1 concurrent execution per candidate)

**Acceptance:** Correct/incorrect/TLE/OOM/infinite-loop submissions all return proper statuses in <8s wall time; a network call from candidate code fails; hidden test expected outputs never appear in any API response.

---

## TASK 5 — Coding round agent behaviors

**Objective:** The AI interviewer behaviors that replicate a real live coding round. Depends on Tasks 1–4.

**Requirements:**
- Live observation loop: every 15s (or on run/significant edit), compute a diff of the candidate's code vs. last observed state and inject into the conversation model's context as a structured observation block — the agent can comment on code as it's written
- Comment policy in prompt: interject only when (a) candidate asks, (b) candidate is silent and stuck >60s, (c) a clarifying question adds value; never narrate every edit
- Graduated hint system: three levels (nudge → direction → partial approach) stored per question; engine controls escalation, each hint issuance logged with level and timestamp
- Requirement-change injection: each question defines an optional `twist` (e.g., "now handle streaming input") triggered by the engine when the base solution passes visible tests with ≥40% of the time budget remaining
- Post-solution phase: agent must ask complexity + "how would you test this" before state exit (enforced as state-completion criteria, not just prompted)
- Think-aloud prompting: if candidate codes silently >90s, one gentle "walk me through your thinking" — max twice per round

**Acceptance:** End-to-end mock session (voice + editor): agent comments on a deliberately wrong approach without giving the answer, hints escalate correctly on request, twist fires when conditions met, complexity discussion happens before wrap.

---

## TASK 6 — Async evaluation pipeline

**Objective:** The second model scores the session against the rubric, with cited evidence — fully decoupled from the live interview.

**Requirements:**
- Worker consumes an `evaluate_session` job (Redis queue) on session end
- Inputs: full transcript, editor event summary (time-to-first-line, edit/delete patterns, hints used with levels, test-run cadence, paste events), execution results
- Rubric scoring: per competency, output `{score_1_to_5, confidence, evidence: [{event_id, quote, rationale}]}` — every score must cite specific transcript/event moments; scores without evidence are rejected by schema validation and retried
- Evaluation model: Opus-class, separate prompt version lineage from the conduct model
- Two-pass design: pass 1 extracts evidence per competency, pass 2 scores from the evidence — reduces halo effect from reading the full transcript while scoring
- Process signals computed deterministically in Python (not by the LLM): hint count, paste anomalies, solve time percentile — LLM scores content, code computes behavior
- Idempotent: re-running evaluation on the same session creates a new versioned evaluation row, never overwrites

**Acceptance:** A completed mock session produces a full evaluation with every score carrying ≥1 evidence citation resolving to a real event ID; deterministic signals match manual calculation; re-run produces v2 without touching v1.

---

## TASK 7 — Decision brief generation

**Objective:** Dual-audience output — recruiter brief + technical audit layer. Same pattern as the Workbench decision brief.

**Requirements:**
- Recruiter layer (plain language): overall signal (strong hire / hire / no hire / strong no-hire — mapped from weighted rubric, thresholds in role config, not decided by the LLM), top 3 strengths and top 3 risks each with one evidence quote, notable moments timeline, explicit uncertainty statement (e.g., "coding assessed on one problem; breadth not established")
- Audit layer: full rubric table with all evidence citations linking to transcript timestamps, model + prompt versions used (conduct and evaluate), all process signals, all integrity events (pastes, tab switches) presented neutrally as "for reviewer attention" — never as accusations
- Rendered as self-contained offline HTML (same delivery pattern as the HMIS dashboards) + JSON API
- Hard rule in generation prompt and post-validation: every claim in the recruiter layer must trace to an audit-layer citation

**Acceptance:** Brief renders offline from a single HTML file; every recruiter-layer claim has a resolvable citation; the hire signal changes correctly when role-config weights are edited and the brief is regenerated.

---

## TASK 8 — Shadow mode & validation harness

**Objective:** The credibility layer — prove AI scores correlate with human scores before anyone trusts this.

**Requirements:**
- Human scoring UI: reviewer watches session replay (audio + synchronized editor replay from Task 3) and scores the same rubric, blind to AI scores until submission
- Storage: `human_evaluations` table, same schema as AI evaluations
- Calibration report (offline HTML, auto-generated): per-competency Spearman correlation AI vs. human, mean absolute difference, disagreement cases (|Δ| ≥ 2) listed with links to session moments, pass/fail agreement rate at the configured threshold
- Honest-uncertainty rule: with n < 20 sessions, the report must display "insufficient data for reliable calibration" prominently — no correlation headline on 5 data points
- Disagreement review queue: sessions with large deltas flagged for a second human review

**Acceptance:** After 3 mock sessions scored by both, report generates with correct math (verified by hand) and displays the insufficient-data warning.

---

## TASK 9 — Session recording & observability

**Objective:** Everything reconstructible; every LLM call inspectable.

**Requirements:**
- LiveKit egress → audio recording to MinIO/S3, linked to session; retention policy field on session (default 90 days) with a purge job
- LLM call logging: every call (conduct + evaluate) logged with prompt version, input token summary, latency, cost estimate — Langfuse if quick to integrate, else a homegrown `llm_calls` table (don't over-invest in Phase 1)
- Latency dashboard: simple internal page charting the Task 1 stage-boundary metrics across sessions — voice latency regressions must be visible immediately
- Structured error taxonomy: STT dropout, TTS failure, LLM timeout, sandbox failure — each with a defined mid-interview fallback behavior (e.g., LLM timeout → canned "give me a moment" + retry)

**Acceptance:** For any completed session: audio playable, full event log queryable, every LLM call traceable to its prompt version; killing Deepgram mid-session triggers the defined fallback rather than a dead-air crash.

---

## Dependency graph & sequencing

```
T0 ──┬── T1 (voice spike)      ── P0, start immediately
     ├── T3 (editor)           ── parallel with T1
     ├── T4 (sandbox)          ── P0, parallel with T1
     │
     ├── T2 (state machine)    ── after T0, parallel track
     │
T1+T2+T3+T4 ── T5 (coding agent behaviors)
T2+T5      ── T6 (evaluation)
T6         ── T7 (decision brief)
T3+T6+T7   ── T8 (shadow mode)
T1..T5     ── T9 (observability — start early, finish last)
```

**Suggested order of execution:** T0 → {T1, T4} → {T2, T3} → T5 → T6 → T7 → T9 → T8.

## Open decisions (shape the T0 scaffold)

1. **LiveKit Cloud vs. self-hosted** — Cloud is faster to spike (recommended for T1); self-hosting matters later for data-residency pitches (relevant for government recruitment, given data-sovereignty positioning).
2. **Judge0 vs. E2B for T4** — Judge0 self-hosted is free and sufficient for structured test-case rounds; E2B better for agent-driven exploratory sandboxes later. Judge0 recommended for Phase 1.
