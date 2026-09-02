# AUDIT_REPORT.md — Final Production Audit

Release-engineering pass, started 2026-08-24. Method: per phase, parallel
audit agents find defects, an adversarial verifier confirms or refutes each
against the real code, confirmed findings are fixed and the fix noted here.
Deferred items go to frontend/DEVIATIONS.md with reasons.

Severity: **P0** security hole / data loss in prod · **P1** prod outage or
major misbehavior · **P2** degraded but survivable · **P3** polish.

## Findings

| ID | Sev | Area | Location | Finding | Status |
|----|-----|------|----------|---------|--------|
| P0-01 | P0 | boot guard | backend/app/config.py | Production boot accepted LiveKit devkey/secret — anyone could forge room-join tokens; compose additionally ran livekit-server `--dev` (hardcoded keypair) | **Fixed**: posture check added; compose uses `--keys` from env |
| P0-02 | P1 | boot guard | backend/app/config.py:11 | `environment` was a free string — "prod", "Production ", or a typo silently fail-opened every production gate (header-stub auth, dev_otp, boot refusal) | **Fixed**: validator normalizes aliases, unknown values refuse to boot |
| P0-03 | P1 | boot guard | backend/app/config.py | MinIO minioadmin, Postgres dev passwords, empty/short signing secrets, localhost APP_BASE_URL all passed production boot | **Fixed**: all in the checklist; min-length 32/16 on signing secrets; error names each variable |
| P0-04 | P1 | sandbox | backend/app/execution.py | Judge0 had no authentication anywhere (no token setting, no header, LAN-exposed port on a privileged container) | **Fixed**: JUDGE0_AUTH_TOKEN setting + X-Auth-Token client header + judge0 AUTHN env + loopback port bind; required by posture check |
| P0-05 | P1 | route gate | backend/app/routes/orgs.py | GET/POST /orgs had no auth — anonymous tenant-registry enumeration and org creation | **Fixed**: service-key only; anonymous-403 asserted in test_tenancy.py |
| P0-06 | P1 | boot guard | agent/event_sink.py, app/eval/worker.py | Only the API process ran the posture check; agent silently fell back to dev-internal-key in production | **Fixed**: eval worker calls validate_production_posture; agent mirrors it (_validate_agent_posture) |
| P0-07 | P1 | compose | docker-compose.yml | api service received no LIVEKIT_* env (containerized API always minted dev-key tokens); literal passwords everywhere; DB/Redis/MinIO/Judge0 ports LAN-exposed | **Fixed**: full env pass-through, ${VAR:-dev} parameterization, loopback binds for internal services |
| P0-08 | P2 | auth | backend/app/routes/auth.py | Fresh-deploy race: first registrant bootstraps as org admin, in production too | **Fixed**: production requires FIRST_ADMIN_EMAIL match (checked pre-OTP and at membership grant) |
| P0-09 | P2 | demo | backend/app/routes/auth.py | /auth/demo wrote candidacies into DEFAULT_ORG_ID — in production that is a real tenant's org (data pollution, wrong org name shown) | **Fixed**: dedicated demo org (id …d0e0) owns demo plan + question (RLS-clean); DEMO_ENABLED toggle |
| P0-10 | P2 | config drift | .env.example | 9 documented vars read by nothing (SILENCE_MAXHOLD_*, SPECULATIVE_GENERATION, RETENTION_DAYS_DEFAULT, 5 Phase-3 vars); NEXT_PUBLIC_API_URL/YWS_URL/MIGRATIONS_DATABASE_URL read but undocumented; TURN_DETECTOR values wrong | **Fixed**: SPECULATIVE_GENERATION + RETENTION_DAYS_DEFAULT wired for real; dead vars removed; missing vars added; docs corrected |
| P0-11 | P2 | build | frontend/Dockerfile | Google/brand NEXT_PUBLIC_* vars not accepted as build args — prod image silently loses Google sign-in and branding | **Fixed**: 3 new ARG/ENV pairs + compose pass-through |
| P0-12 | P3 | boot guard | backend/app/main.py | /docs, /redoc, /openapi.json served unauthenticated in production | **Fixed**: gated off in production |
| P0-13 | P3 | dead code | worker/ | Retired directory (eval runs as app/eval/worker) still present with stale config reads | **Deferred**: deletion blocked by tool permissions — marked RETIRED in README; safe to `git rm -r worker` |

## Phase log

### Phase 0 — Boot & config sanity — DONE
- Audit: 3 finders + adversarial verify (28 raw → 26 confirmed, 2 refuted).
- All fixes verified live: full backend suite (122 passed) in-container; boot
  guard fires with per-variable checklist under ENVIRONMENT=production;
  `ENVIRONMENT="Prod "` normalizes to production; `porduction` refuses boot.
- Every `environment != "production"` branch audited: dev_otp, X-Org-Id stub,
  and /docs are the only dev-only surfaces, all gated on the now-validated
  canonical value.


### Phase 1 & 3 — non-security fixes — DONE

Audits: Phase 1 (45 confirmed: 3×P0, 17×P1, 16×P2, 9×P3) and Phase 3
(68 confirmed: 9×P1, 37×P2, 22×P3), both adversarially verified.
**Security/auth-gate findings were deliberately deferred by the user** (see
Deferred). Everything else was fixed across four commits:

| ID | Sev | Area | Fix |
|----|-----|------|-----|
| A-01 | P1 | agent | transition/observation loops now supervised — a crash logs and restarts instead of silently freezing the interview forever (no transitions, no ENDED, no eval) |
| A-02 | P1 | agent | bootstrap retries 3× then refuses the job; a backend blip no longer makes the agent conduct DEFAULT_PLAN against a real session and append a false round-1 transition to the append-only log |
| A-03 | P2 | agent | llm_calls tasks tracked (were GC-able before completion); non-2xx responses logged (a 422 for an unsynced prompt was silently dropping invariant-#2 audit rows) |
| A-04 | P2 | agent | EventSink: unserializable batch dropped loudly instead of head-requeued forever (one poison event blocked ALL later events); closed-sink guard; JSONDecodeError-safe get_json |
| A-05 | P3 | agent | difflib diff skipped above 20k chars (quadratic cost on the live-audio event loop); fallback model attribution in llm_calls |
| B-01 | P1 | lifecycle | start-interview rejoin filtered on status `active`, which does not exist — **every** mid-interview reload spawned a second session. Fixed to created/in_progress/paused + advisory lock |
| B-02 | P1 | consent | `consent_missing` counted any historical granted=True, so withdrawal was a no-op. Now latest-record-wins per item |
| B-03 | P1 | pipelines | `_advance` read-modify-write serialized (double-click created two sessions for one round); start-pipeline check-then-insert locked |
| B-04 | P2 | review | duplicate decision submit returns the existing row (idempotent) without breaking append-only |
| B-05 | P2 | lifecycle/auth | org schedule cap and demo 3-cap were count-then-insert races — both serialized |
| B-06 | P2 | pipelines | aggregate-brief `version = max+1` race serialized |
| C-01 | P1 | eval | any provider failure dropped the job silently. Now: provider failover (anthropic↔openrouter), then a **degraded** evaluation routed to the review queue |
| C-02 | P2 | eval | empty/partial transcripts evaluate as degraded instead of raising |
| C-03 | P2 | worker | 3 retries with backoff → dead-letter queue (was at-most-once, silently lost) |
| C-04 | P2 | worker | redelivered jobs reuse the existing evaluation (no double LLM billing); brief-only recovery when evaluation succeeded but brief failed; `force` flag for operator re-runs |
| C-05 | P2 | sessions | eval enqueue failure now logs loudly (was a bare `pass`) |
| C-06 | P1 | compliance | GDPR erase swallowed every MinIO error, blanked the DB pointer, and reported success — briefs with candidate quotes survived untraceably. Now: only "already gone" counts as success, keys retained + recorded in purge audit, 502 asks for retry |
| D-01 | P1 | prompts | a prompt **revert** was a silent no-op (sync compared against any historical row, runtime picks newest). Now latest-row comparison + `--check` drift gate |
| D-02 | P2 | prompts | consistency pass used an inlined prompt and logged no llm_calls row (double invariant-#2 violation) — moved to `evaluate/consistency_v1`, now logged |
| D-03 | P3 | migrations | alembic env.py escapes `%` in DB URLs (a password with `%` crashed migrations) |
| E-01 | P2 | db | migration 0012: 12 hot-path indexes. The event-append eid-dedup was scanning every event of the session on every batch |
| E-02 | P2 | queries | N+1 eliminated in my_interviews, list_sessions, latency_metrics, review-queue, list_candidacies |
| E-03 | P2 | queries | unbounded reads bounded: replay paging, `?limit=` caps, COUNT(*) instead of len(rows), execute source/stdin caps |
| E-04 | P2 | hot path | pooled Judge0 + Redis clients (were per-request); PDF parse and MinIO upload moved off the event loop; uploads stream-capped before buffering |
| F-01 | P2 | observability | `/metrics/eval-health` + Analytics banner: stuck sessions, dead-letter, queue depth. A failed eval was indistinguishable from "still processing" — the live check immediately found **8 stuck sessions** on this deployment |

Verification after each batch: 122 backend pytest (in-container), cross-tenant
suite, smoke, smoke_exec, both e2e flows, 22 agent engine tests, ruff clean
across backend+agent, tsc clean. One regression caught and fixed during
verification (cached Judge0 client closed per-request → 500s on /execute).

## Latency (Phase 4)

| Segment | Before | After |
|---------|--------|-------|
| _(measured in Phase 4)_ | | |

Baseline from live demo (2026-08-24, busy dev machine): p50 1853 ms, p95 7330 ms.

## Screens changed

_(populated in Phase 6)_

## Deferred

**Security / auth-gate findings — deferred by user decision (2026-08-25).**
The Phase 1 audit confirmed these; they are NOT fixed and remain release
blockers for an internet-facing deployment:

- **P0** pool-poisoned `bypass_rls`: `auth._identity_db()` commits with the
  RLS bypass GUC on and returns the connection to the pool;
  `/orgs/current/admin-actions` reuses it. Reproduced live — 74 rows across
  5 orgs. Fix: reset the GUC on pool checkin, or route that read through
  `tenancy.get_db`.
- **P0** candidate-token revocation is a no-op (jti rotation never enforced).
- **P0** `POST /sessions/{id}/candidate-link` has no gate — any candidate
  token can mint a link for another session in the org.
- **P1** `GET /sessions/{id}/token` (starts the live room) performs no
  consent check.
- **P1** `design_questions` / `sql_datasets` have no `org_id`/RLS despite
  being tenant-written (invariant #8).
- **P1** no login brute-force protection; `/auth/register` is an
  unauthenticated email-send amplifier.
- **P1** frontend `next@14.2.x` has unpatched high-severity advisories
  (fix requires a major upgrade).
- Various P2/P3: memberships lacks RLS, containers run as root, floating
  dependency pins, y-websocket unauthenticated, cross-tenant suite covers
  only Phase-1 tables.

**Blocked by tooling:** deleting the retired `worker/` directory
(`git rm -r worker` refused by the permission classifier). Marked RETIRED in
README; safe to delete manually.

**Not started:** Phase 2 (persona flow-walking), Phase 4 (latency work —
baseline captured: LLM TTFT 1.0–1.3 s dominates, EOU ~0.45 s, TTS ~0.32 s),
Phase 5 (robustness scenarios), Phase 6 (UI/UX polish), Phase 7 (editor
surfaces), Phase 8 (observability beyond eval-health; load test), Phase 9
(feature specs).

## Go / No-Go checklist

- [ ] All verification suites green (smoke, smoke_exec, test_tenancy, both e2e, full pytest)
- [ ] Zero open P0/P1
- [ ] Latency targets met on 3 consecutive test sessions
- [ ] Cross-tenant tests pass
- [ ] Production boot check verified firing for every dev default
