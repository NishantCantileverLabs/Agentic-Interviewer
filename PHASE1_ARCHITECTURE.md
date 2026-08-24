# AI Interview Platform — Phase 1 Architecture & Claude Code Instructions

**Version 1.0 | Optimization targets: minimum voice latency, maximum interview quality**

This document is the single source of truth for the Phase 1 build. Section 10 (`CLAUDE.md`) is meant to be copied verbatim into the repo root so Claude Code follows these rules on every task.

---

## 1. System Overview

Phase 1 delivers: one role type (SDE), a live voice AI interviewer, a live collaborative coding round with sandboxed execution, async dual-model evaluation, a dual-audience decision brief, and shadow-mode validation.

```
                        ┌─────────────────────────────────────────────┐
                        │              CANDIDATE BROWSER               │
                        │  Next.js app: LiveKit client (audio)         │
                        │  + Monaco editor (Yjs)  + test-run panel     │
                        └───────┬───────────────────────┬─────────────┘
                                │ WebRTC (audio)        │ WebSocket (CRDT)
                                ▼                       ▼
                    ┌───────────────────┐    ┌────────────────────┐
                    │   LiveKit Cloud    │    │  y-websocket server │
                    │  (SFU + egress)    │    │  (editor sync)      │
                    └────────┬──────────┘    └─────────┬──────────┘
                             │ agent joins room         │ editor deltas
                             ▼                          ▼
      ┌──────────────────────────────────────────────────────────────┐
      │              AGENT WORKER (Python, LiveKit Agents)            │
      │                                                              │
      │   Deepgram STT ──► Interview Engine ──► Cartesia/11Labs TTS  │
      │   (streaming,      (state machine +     (streaming,          │
      │    interim         Claude Haiku/Sonnet   sentence-chunked)   │
      │    results)        conduct model,                            │
      │                    prompt-cached)                            │
      │                          │                                   │
      │                          ▼                                   │
      │                 code-observation loop                        │
      │                 (polls editor snapshots,                     │
      │                  injects diffs into context)                 │
      └──────────┬───────────────────────────────────────────────────┘
                 │ events (append-only)
                 ▼
   ┌───────────────────────────┐         ┌──────────────────────────┐
   │   FastAPI CONTROL PLANE    │────────►│   Postgres 16            │
   │  session mgmt, exec proxy, │         │  event log, sessions,    │
   │  replay, briefs, admin     │         │  evaluations, prompts    │
   └──────┬──────────┬─────────┘         └──────────────────────────┘
          │          │
          │          └────────────► Redis (queues, rate limits, presence)
          ▼
   ┌──────────────┐    on session end     ┌───────────────────────────┐
   │   Judge0      │                      │  EVAL WORKER (Python)      │
   │  (sandboxed   │                      │  Claude Opus-class,        │
   │   execution,  │                      │  two-pass evidence→score,  │
   │   Docker)     │                      │  brief generation (HTML)   │
   └──────────────┘                       └───────────────────────────┘
   MinIO/S3: audio recordings (LiveKit egress), brief HTML artifacts
```

**Five processes** in dev docker-compose: `frontend`, `api` (FastAPI), `agent` (LiveKit Agents worker), `eval-worker`, `y-websocket`, plus infra containers (`postgres`, `redis`, `minio`, `judge0`). LiveKit Cloud is external in Phase 1.

### Core architectural decisions (locked)

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | **Event-sourced session log** (`interview_events`, append-only) is the source of truth. Everything — transcripts, editor deltas, hints, executions, state transitions — is an event. | Replay, audit, crash recovery, and evaluation all read one stream. |
| D2 | **Dual-model split**: fast conduct model (Haiku-class) live; strong evaluation model (Opus-class) async. Conduct model never produces scores. | Latency where it matters, quality where it matters, no anchoring/sycophancy leakage into scores. |
| D3 | **State machine owns the interview**; the LLM only controls behavior *within* a state. Transitions are code, driven by time budgets and completion criteria. | Predictable interviews, enforceable structure, auditability. |
| D4 | **Streaming + pipelining everywhere**: STT interims → LLM token stream → sentence-chunked TTS. No stage waits for the previous stage to finish. | This is where the latency budget is won. |
| D5 | **Prompt caching on every conduct call**: system prompt + interview plan + transcript prefix are cache-stable; only the newest turns are uncached. | Cuts time-to-first-token and cost dramatically on 50–80 calls/interview. |
| D6 | **Deterministic signals in Python, judgment in the LLM.** Hint counts, paste sizes, solve times, latency stats are computed by code; only content quality is scored by the model. | Reproducibility; the audit layer must be re-derivable. |
| D7 | **Every LLM call carries a `prompt_version_id`.** No inline prompt edits ever ship without a new version row. | The audit trail is a compliance requirement, not a nice-to-have. |

---

## 2. Latency: budget, techniques, and measurement

**Target: p50 ≤ 800 ms, p95 ≤ 1500 ms** from *end of candidate speech* to *first agent audio out*. This is the go/no-go gate for the whole project (Task 1).

### 2.1 The latency budget (where every millisecond goes)

| Stage | Budget (p50) | How it's achieved |
|---|---|---|
| End-of-turn detection | 250–450 ms | Deepgram endpointing (~300 ms setting) fused with LiveKit's semantic turn-detector model; interim transcripts already in hand before the endpoint fires |
| Conduct LLM time-to-first-token | 200–350 ms | Haiku-class model + prompt caching (cache hit = most of the context is pre-processed) + streaming API + warm HTTPS connection pool |
| First sentence completion | overlapped | TTS starts at the first sentence boundary, not at generation end |
| TTS time-to-first-byte | 90–200 ms | Cartesia Sonic (~90 ms TTFB) or ElevenLabs Flash model; persistent WebSocket opened at session start |
| Audio transport + playout buffer | 80–150 ms | WebRTC via LiveKit SFU; agent worker deployed in the same cloud region as LiveKit project + STT/TTS endpoints |
| **Total** | **~650–1150 ms** | p50 target met with headroom |

### 2.2 Latency techniques (implement in this order)

1. **LiveKit Agents framework (Python)** as the voice pipeline substrate. It ships production turn-taking, barge-in, and streaming plugins for Deepgram/Cartesia/ElevenLabs. Do not hand-roll WebRTC or the STT↔LLM↔TTS plumbing — the framework's pipelining is the product of exactly the tuning we'd otherwise spend weeks on.
2. **Streaming STT with interim results.** The engine sees the candidate's sentence *while it is being spoken*. By endpoint time, the full user turn is already assembled — zero transcription wait after speech ends.
3. **Semantic end-of-turn detection, not fixed silence.** Fixed silence thresholds force a brutal trade-off (fast = interrupts thinking; tolerant = sluggish). Fuse: (a) Deepgram endpointing as the fast path, (b) LiveKit turn-detector model to *hold back* the agent when the transcript looks unfinished ("So my approach would be…" + pause ≠ turn end), (c) state-aware overrides — in CODING and after hard questions, extend max hold to 10 s+ so thinking silence is never punished.
4. **Prompt caching (Anthropic cache_control).** Structure every conduct call as: `[system prompt — cached] [interview plan — cached] [transcript prefix — cached, extended each turn] [last N turns + observation block — uncached]`. Cache hits slash both TTFT and cost. The context layout in §6.3 is designed around cache-boundary stability — do not reorder blocks per-call.
5. **Sentence-boundary TTS flushing.** Stream LLM tokens; on each sentence terminator, flush that sentence to the TTS WebSocket. The candidate hears sentence 1 while sentence 3 is still being generated.
6. **Connection warming.** At session start (before the candidate finishes the mic check): open and hold Deepgram WS, TTS WS, and issue one tiny warm-up conduct call to populate the prompt cache and TLS/connection pools.
7. **Barge-in as cancellation.** Candidate speech during agent audio → immediately stop playout, cancel the in-flight LLM stream and TTS synthesis, log a `barge_in` event, and treat buffered interims as the start of the new turn.
8. **Short-turn prompting.** The conduct system prompt enforces spoken-style brevity (1–3 sentences per turn, one question at a time). Shorter outputs = faster full-response latency *and* better interviews — monologuing interviewers are bad interviewers.
9. **Region pinning.** Deploy the agent worker in the same region as the LiveKit project; choose Deepgram/Cartesia endpoints accordingly. Cross-region hops silently add 100–200 ms.
10. **(Optional, flag-gated) Speculative generation.** On a high-confidence interim final, start generating the reply before the endpoint fires; cancel and regenerate if the final transcript differs materially. Ship only if p95 misses target after 1–9 — it adds complexity and token cost.

### 2.3 Measurement (non-negotiable, from day one)

Every turn logs a `turn_latency` event with monotonic timestamps at: `speech_end_detected`, `llm_request_sent`, `llm_first_token`, `first_sentence_complete`, `tts_first_byte`, `first_audio_out`. The internal dashboard (Task 9) charts p50/p95 per stage per session. **A latency regression must be visible the day it ships, not discovered in a demo.**

---

## 3. Component architecture

### 3.1 Frontend (`/frontend`) — Next.js 14, TypeScript

- **Routes:** `/interview/[token]` (candidate room), `/admin/sessions`, `/admin/replay/[id]`, `/admin/review/[id]` (shadow scoring), `/admin/latency`.
- **Candidate room layout:** left = agent presence indicator (speaking/listening/thinking states — candidates need to know the agent heard them), right = Monaco editor + language picker + Run panel (visible tests only) + output console. Question statement panel above the editor.
- **Pre-join system check:** mic permission, echo test, measured RTT to LiveKit, browser support. Blocks entry on hard failures. This single screen removes the majority of live-session support pain.
- **Audio via LiveKit client SDK** — no custom WebRTC. Editor via Monaco + `y-monaco` + `y-websocket` provider.
- **Instrumentation beacons:** `visibilitychange` (tab switches), paste events with length, focus/blur — POSTed to the event API, logged silently, never blocking and never surfaced to the candidate in Phase 1.

### 3.2 Agent worker (`/agent`) — Python, LiveKit Agents

The heart of the system. One process, one asyncio loop per active session.

- **Pipeline:** LiveKit `AgentSession` with Deepgram STT plugin (interims + endpointing on), custom LLM node wrapping the Interview Engine, TTS plugin (Cartesia Sonic primary; ElevenLabs Flash behind a config switch for A/B).
- **Interview Engine embedded** (see §6): state machine, plan interpreter, probe budgets, context builder with cache-stable layout.
- **Code observation loop:** asyncio task per CODING state; every 15 s (or on a `run_clicked` event) fetches the latest editor snapshot from the API, diffs against last observed, and injects a structured observation block into the next conduct call (see §7.2).
- **Event emission:** every STT final, agent turn, state transition, hint, barge-in, and latency record is POSTed (batched) to the control plane's event endpoint. The agent holds no durable state — **a crashed agent process re-attaches to the room and rebuilds engine state entirely from the event log.**
- **Failure fallbacks (wired, not aspirational):** STT dropout → auto-reconnect with a spoken "sorry, could you repeat that?"; LLM timeout (>4 s TTFT) → canned bridge line ("give me a moment to think about that") + one retry; TTS failure → provider failover (Cartesia → ElevenLabs); LiveKit disconnect → session pause state + candidate-facing reconnect banner.

### 3.3 Control plane (`/backend`) — FastAPI

- **Endpoints:** session CRUD + token issuance; `POST /events` (batched append, validates monotonic sequence per session); `GET /sessions/{id}/replay` (ordered event stream with time-travel code reconstruction); `POST /execute` (Judge0 proxy — the only path to Judge0, enforces per-session concurrency=1 and rate limits via Redis); interview-plan CRUD; question bank CRUD; brief retrieval; shadow-review submission.
- **Never in the voice path.** The control plane is not latency-critical; the agent talks to STT/LLM/TTS directly. Event posting is async/batched and can lag by seconds without harming the interview.

### 3.4 Execution service — Judge0 (self-hosted, Docker)

- Wrapped entirely by `POST /execute`. Contract: `{language, source, stdin?, test_suite_id?}` → `{status, stdout, stderr, per_test: [{id, passed, time_ms, hidden}]}`. Hidden tests return pass/fail only — expected outputs never leave the backend, enforced by a response-shape test in CI.
- Limits: 5 s CPU, 256 MB, no network egress, 64 KB output truncation. Languages: Python, JavaScript, Java, C++.

### 3.5 Eval worker (`/worker`) — Python + Redis queue

- Consumes `evaluate_session` on session end. Two-pass evaluation (evidence extraction → scoring from evidence only), deterministic signal computation, decision-brief HTML generation. Detailed in §8.

### 3.6 Storage

- **Postgres 16** — all durable state. **Redis** — queues, rate limits, agent presence/heartbeats. **MinIO/S3** — LiveKit egress audio recordings + rendered brief HTML, with a `retention_days` field per session (default 90) and a nightly purge job.

---

## 4. Data model (Postgres, Alembic-managed)

```sql
sessions(
  id uuid pk, candidate_label text, role_config_id fk, plan_id fk,
  status enum(created|in_progress|paused|completed|aborted),
  livekit_room text, started_at, ended_at, retention_days int default 90
)
interview_events(            -- APPEND-ONLY. Never updated, never deleted (except retention purge).
  id bigserial pk, session_id fk, seq int,        -- (session_id, seq) unique, monotonic
  ts timestamptz, type text, payload jsonb
)
-- event types (closed vocabulary, extend via migration + ARCHITECTURE.md note):
--  stt_final, agent_turn, state_transition, hint_issued, twist_injected,
--  editor_delta_batch, editor_snapshot, paste, tab_visibility, run_clicked,
--  execution_result, barge_in, turn_latency, error, fallback_triggered
interview_plans(id, role_config_id, plan jsonb, version int)
role_configs(id, name, competencies jsonb, weights jsonb, thresholds jsonb)
questions(id, title, statement_md, language_targets text[], visible_tests jsonb,
          hidden_tests jsonb, hints jsonb,     -- exactly 3 levels: nudge|direction|partial
          twist jsonb, difficulty int)
prompt_versions(id, name, role enum(conduct|evaluate|brief), content text,
                model_target text, created_at, notes text)
llm_calls(id, session_id, prompt_version_id fk, role, model, input_tokens,
          cached_tokens, output_tokens, ttft_ms, total_ms, cost_estimate numeric, ts)
evaluations(id, session_id, version int, model, prompt_version_id fk,
            rubric jsonb,      -- per-competency: {score, confidence, evidence:[{event_id, quote, rationale}]}
            signals jsonb,     -- deterministic: hints_used, paste_events, time_to_first_line, ...
            created_at)        -- re-runs create version+1, never overwrite
human_evaluations(id, session_id, reviewer, rubric jsonb, created_at)  -- same rubric schema
briefs(id, session_id, evaluation_id fk, html_object_key text, summary jsonb, created_at)
```

**Invariants (enforced in code + tests):**
1. `interview_events` rows are immutable.
2. Every `llm_calls` row references a real `prompt_versions` row.
3. Every evidence citation in `evaluations.rubric` resolves to a real `interview_events.id` in the same session (schema-validated at write time; violations reject the evaluation and trigger a retry).
4. Hidden-test expected outputs appear in no API response body (CI contract test).

---

## 5. Voice pipeline — detailed sequence (one turn)

```
Candidate speaking ──► Deepgram interims stream into engine buffer
Candidate stops    ──► Deepgram endpoint fires (~300ms)
                        └─ LiveKit turn-detector agrees turn is complete
                           (else HOLD: wait up to state-specific max, e.g. 10s in CODING)
                   ──► Engine builds context (cache-stable layout, §6.3)
                   ──► Conduct LLM streaming call        [TTFT ~200–350ms on cache hit]
                   ──► Sentence 1 boundary detected ──► flush to TTS WebSocket
                   ──► TTS first audio bytes             [~90–200ms]
                   ──► LiveKit playout to candidate      [first_audio_out logged]
                   ──► Remaining sentences pipeline through while candidate listens
Any candidate speech during playout ──► BARGE-IN:
    stop playout → cancel LLM stream + TTS → log barge_in → new turn begins
```

Silence policy by state: WARMUP/INTRO max-hold 4 s; TECHNICAL_DEEPDIVE 8 s; CODING 12 s + think-aloud nudge only after 90 s of silent coding (max 2 per round). The agent never fills silence with filler words — a canned bridge line is used **only** on an LLM-timeout fallback, never as conversational padding.

---

## 6. Interview Engine (the brain)

### 6.1 State machine

```
INTRO ──► WARMUP ──► TECHNICAL_DEEPDIVE ──► CODING ──► WRAPUP ──► ENDED
                                              │
                                              └── (twist sub-phase, engine-triggered)
```

- Transitions fire on **engine-evaluated criteria only**: time budget spent, completion criteria met (e.g., WRAPUP requires complexity-discussion + testing-question events present), or hard session timeout. The LLM is *informed* of transitions via prompt updates; it never decides them.
- Each state binds: a versioned system prompt, a max turn length, a silence max-hold, allowed tools (code observation only in CODING), and completion criteria.
- Full engine state is derivable from the event log at any time: `rebuild(session_id) -> EngineState` is a pure function and has its own test suite. This is what makes crash-recovery and the replay/review UIs trivial.

### 6.2 Interview plan (per session, JSON)

```json
{
  "role_config_id": "sde_backend_v1",
  "time_budget_min": {"INTRO": 2, "WARMUP": 5, "TECHNICAL_DEEPDIVE": 12, "CODING": 22, "WRAPUP": 4},
  "competencies": [
    {"id": "problem_solving", "weight": 0.3, "probe_budget": 3},
    {"id": "coding_proficiency", "weight": 0.3, "probe_budget": 3},
    {"id": "cs_fundamentals", "weight": 0.2, "probe_budget": 2},
    {"id": "communication", "weight": 0.2, "probe_budget": 2}
  ],
  "question_refs": {"deepdive_pool": ["q_api_design_1"], "coding": "q_two_pointer_3"},
  "language_default": "python"
}
```

Probe budgets are enforced by the engine: it counts follow-up probes per competency (the conduct model tags each turn intent in a structured header, see §6.4) and, at budget exhaustion, injects a move-on directive into the next context build.

### 6.3 Context layout (cache-stable — this exact order, always)

```
[BLOCK A — cached] Conduct system prompt (versioned): persona, brevity rules,
                   probing doctrine, hint policy, never-reveal-solutions rule,
                   spoken-style constraints (no markdown, no lists, contractions ok)
[BLOCK B — cached] Interview plan + current question statement + rubric summary
[BLOCK C — cached, grows monotonically] Transcript prefix: all turns older than
                   the last 6, plus rolling structured summary of covered
                   competencies and probe counts
[BLOCK D — fresh]  Last 6 turns verbatim + current state directive
                   ("You are in CODING. Probe budget remaining: {...}") +
                   latest code observation block (if CODING) + candidate turn
```

Blocks A–C carry `cache_control` breakpoints. Because C only ever *appends*, cache hits stay high for the whole interview. Never reorder, never rewrite C retroactively — a summary update appends a new summary block rather than editing the old one.

### 6.4 Conduct-model output contract

The conduct model streams plain spoken text for TTS, preceded by a single machine-readable header line the engine strips before synthesis:

```
@meta{"intent":"probe","competency":"problem_solving","hint_level":null}
That makes sense. What would happen to your approach if the input didn't fit in memory?
```

The header feeds probe accounting, hint logging, and state-completion tracking. Malformed header → engine logs a warning, treats intent as "chat", and continues (never block the voice path on parsing).

### 6.5 Conduct system prompt — doctrine it must encode

- 1–3 sentences per turn, exactly one question at a time, spoken register (it will be heard, not read).
- Probe 2–3 levels deep on claims: quantify ("how did you measure that?"), verify ("what was the baseline?"), stress ("when would that break?").
- Acknowledge before pivoting; never interrogate-machine-gun style.
- Hints only via engine authorization (the directive block says which level is unlocked); never volunteer the solution; never confirm correctness during CODING beyond what test results show.
- No meta-references to being an AI, to the rubric, to scoring, or to "moving to the next state" — transitions are voiced naturally ("Let's switch gears and write some code").
- Tolerance rules: silence is thinking, not absence; partial answers get a chance to be completed before probing.

---

## 7. Coding round integration

### 7.1 Editor + process capture

- Monaco + Yjs (`y-monaco`, `y-websocket`). Backend-hosted y-websocket server; the Yjs doc is the live truth, Postgres events are the durable record.
- Captured to `interview_events`: editor delta batches (500 ms flush), cursor/selection samples, paste events **with length**, `run_clicked`, full snapshots every 30 s and on every run.
- Replay guarantee: `code_at(session_id, t)` reconstructs exact editor content at any timestamp from snapshots + deltas — the foundation for the shadow-review UI and any future integrity analysis.

### 7.2 Code observation block (injected into BLOCK D during CODING)

```
@code_observation
elapsed_in_state: 07:42 / 22:00
last_run: 05:10 ago → 2/4 visible tests passed (t3 failed: expected 7 got 6)
diff_since_last_observation: |
  + for i in range(len(nums)):
  +     for j in range(i+1, len(nums)):   # O(n^2) nested loop introduced
activity: steady typing; 1 large deletion (refactor) at 06:55; no pastes
hints_used: 1 (nudge, 04:30)
```

Diffs are truncated to a token budget (largest hunks first). The observation block lives in the uncached tail, so it never breaks the prompt cache.

### 7.3 Agent behaviors (enforced, not hoped-for)

- **Comment policy** (in prompt + engine gating): interject on code only when (a) asked, (b) candidate silent-and-stuck > 60 s with failing tests, (c) a genuinely clarifying question adds value. Never narrate every edit.
- **Graduated hints:** 3 authored levels per question. Escalation is engine-controlled: level N+1 unlocks only after level N was issued ≥ 90 s prior *and* tests still fail. Each issuance is a `hint_issued` event with level + timestamp.
- **Twist injection:** engine fires the question's `twist` when visible tests pass with ≥ 40 % of the CODING budget remaining. The directive block tells the model to introduce it conversationally.
- **Mandatory post-solution phase:** WRAPUP is unreachable until `complexity_discussed` and `testing_question_asked` completion events exist (detected from the @meta intents). The engine keeps steering until they do or time expires.

---

## 8. Evaluation pipeline (async, quality-first)

- **Trigger:** session `completed` → `evaluate_session` job on Redis.
- **Pass 0 — deterministic signals (pure Python):** time-to-first-line, edit/delete ratio, run cadence, hints used (count × level), paste anomalies (any paste > 120 chars flagged), per-turn response-latency distribution, twist-adaptation time. Unit-tested against fixture event streams; the LLM never computes these.
- **Pass 1 — evidence extraction (Opus-class):** for each competency, extract candidate moments as `{event_id, quote, why_relevant}` from the transcript + code timeline. No scores in this pass.
- **Pass 2 — scoring from evidence only:** the model sees the rubric + extracted evidence (not the full transcript) and outputs `{score_1_to_5, confidence, evidence_refs, rationale}` per competency. The two-pass split is the halo-effect firewall.
- **Validation:** JSON-schema check + citation resolution against real event IDs. Any score lacking resolvable evidence → reject, retry once, else mark evaluation `degraded` for human attention. Never fabricate, never ship uncited scores.
- **Hire signal:** computed **in code** from weighted rubric vs. role-config thresholds. The LLM writes prose; it does not decide hire/no-hire.
- **Decision brief:** self-contained offline HTML (recruiter layer: signal, top-3 strengths/risks each with one cited quote, moments timeline, explicit uncertainty statement; audit layer: full rubric with citations linking to transcript timestamps, model + prompt versions, all deterministic signals, integrity events presented neutrally "for reviewer attention"). Every recruiter-layer claim must trace to an audit-layer citation — post-validated, not just prompted.

---

## 9. Repository layout

```
/                     CLAUDE.md, ARCHITECTURE.md, docker-compose.yml, .env.example
/backend              FastAPI app, alembic/, providers/ (LLM abstraction), tests/
/agent                LiveKit Agents worker: engine/ (state machine, context builder,
                      plan), pipeline/ (stt, tts, llm nodes, latency), observation/
/worker               eval pipeline: signals.py, evidence.py, scoring.py, brief/
/frontend             Next.js app
/infra                judge0/, y-websocket/, minio bootstrap, seed scripts
/prompts              versioned prompt files, mirrored into prompt_versions by a
                      sync script (file = source, DB = runtime record)
/tests/e2e            scripted mock-candidate harness (text + synthetic audio)
```

---

## 10. CLAUDE.md — copy this verbatim into the repo root

(See `CLAUDE.md` at the repo root — extracted from this section.)

---

## 11. Build order & gates

Task specs T0–T9 (from the Phase 1 breakdown, see `TASKS.md`) execute in this order, with two hard gates:

```
T0 scaffold
   ├── T1 voice spike ──────── GATE 1: p50 ≤ 800ms, p95 ≤ 1500ms, barge-in,
   ├── T4 sandbox              10s-silence tolerance. FAIL → try Cartesia⇄11Labs
   │                           swap, region re-pin, speculative generation;
   │                           still failing → evaluate Pipecat / S2S models
   │                           BEFORE building T2/T5.
   ├── T2 engine (parallel)
   └── T3 editor (parallel)
T1+T2+T3+T4 ──► T5 coding-round behaviors
T5 ──► T6 evaluation ──► T7 brief
T9 observability (starts with T1's instrumentation, finishes last)
T8 shadow mode ──────────── GATE 2: no external claims about interview quality
                            until ≥20 dual-scored sessions and the calibration
                            report exists. n<20 shows "insufficient data".
```

## 12. Configuration (.env.example)

```
# LLM
ANTHROPIC_API_KEY=
CONDUCT_MODEL=            # Haiku-class; resolve current model string at T0
EVAL_MODEL=               # Opus-class; resolve current model string at T0
PROMPT_CACHE_ENABLED=true
# Voice
LIVEKIT_URL= LIVEKIT_API_KEY= LIVEKIT_API_SECRET=
DEEPGRAM_API_KEY=
DEEPGRAM_ENDPOINTING_MS=300
TTS_PRIMARY=cartesia      # cartesia | elevenlabs (A/B in T1)
CARTESIA_API_KEY= ELEVENLABS_API_KEY=
# Turn-taking
TURN_DETECTOR=semantic    # semantic | vad_only
SILENCE_MAXHOLD_INTRO_S=4  SILENCE_MAXHOLD_DEEPDIVE_S=8  SILENCE_MAXHOLD_CODING_S=12
SPECULATIVE_GENERATION=false
# Infra
DATABASE_URL= REDIS_URL= S3_ENDPOINT= S3_BUCKET=recordings
JUDGE0_URL=http://judge0:2358
EXEC_CPU_LIMIT_S=5 EXEC_MEM_MB=256
# Eval
EVAL_QUEUE=evaluate_session
RETENTION_DAYS_DEFAULT=90
```

Model strings, plugin names, and provider pricing shift frequently — Task 0 includes verifying current values against live docs before locking them into config. Do not carry model IDs from this document into code without checking.

---

## 13. What "best-in-class interview" means here (quality checklist)

The latency work makes it *feel* human; these make it *interview* like a strong human:

- [ ] Probes claims 2–3 levels deep with quantify/verify/stress questions (probe budgets visible in transcripts)
- [ ] One question at a time, 1–3 sentences, spoken register — no monologues
- [ ] Tolerates thinking silence; never punishes a pause with an interruption
- [ ] Watches code live and comments sparingly and usefully — like a good panelist, not a linter
- [ ] Hints escalate gradually and cost the candidate transparently in the audit trail
- [ ] Adapts mid-problem (twist) when the candidate is ahead of schedule
- [ ] Always closes coding with complexity + testing discussion
- [ ] Every score in the brief carries resolvable evidence; uncertainty is stated, never smoothed over
- [ ] Shadow-mode calibration before anyone is asked to trust a number
