# DEPLOY.md — taking this stack to production

The compose file is the deployment unit: one VM (4+ cores, 16 GB) runs the
whole platform **at pilot scale (~10–25 concurrent interviews)**. This guide
is the difference between `dev` and a defensible production posture. The API
**refuses to boot** in production posture until the checklist below is
genuinely done, and it prints exactly which variable blocked it — that is by
design. For anything beyond pilot scale, read §8 Capacity planning before
promising a number to a client.

> **Read §7 first if this deployment will face the internet.** A production
> audit left a set of confirmed security findings open by decision; they are
> listed there, not buried.

## 1. Secrets — generate, never reuse dev values

```bash
python -c "import secrets; print('SESSION_SECRET=' + secrets.token_urlsafe(48))"
python -c "import secrets; print('CANDIDATE_LINK_SECRET=' + secrets.token_urlsafe(48))"
python -c "import secrets; print('INTERNAL_API_KEY=' + secrets.token_urlsafe(48))"
python -c "import secrets; print('JUDGE0_AUTH_TOKEN=' + secrets.token_urlsafe(32))"
python -c "import secrets; print('POSTGRES_PASSWORD=' + secrets.token_urlsafe(24))"
python -c "import secrets; print('APP_DB_PASSWORD=' + secrets.token_urlsafe(24))"
python -c "import secrets; print('S3_SECRET_KEY=' + secrets.token_urlsafe(24))"
```

Put them in `.env` on the host (never in the repo). Every row below is
**checked at boot** — production will not start until all of them are real:

| Variable | Production value | Why the boot check rejects the default |
|---|---|---|
| `ENVIRONMENT` | `production` | Aliases (`prod`, `Production`) normalize; an unrecognized value refuses to boot rather than silently falling back to dev posture |
| `SESSION_SECRET` | generated, ≥32 chars | Signs account sessions; short/empty is rejected as well as the dev default |
| `CANDIDATE_LINK_SECRET` | generated, ≥32 chars | Signs candidate interview links |
| `INTERNAL_API_KEY` | generated, ≥16 chars | The agent and eval worker authenticate with it; a known value is full RLS bypass |
| `DEV_DEFAULT_ORG` | `false` | `true` grants anonymous callers default-org admin |
| `RESEND_API_KEY` | real key | Without it, OTPs cannot be delivered, so nobody can register |
| `FIRST_ADMIN_EMAIL` | your admin's email | Closes the fresh-deploy race where whoever registers first bootstraps as org admin |
| `APP_BASE_URL` | `https://your-domain` | Drives CORS and invite links; localhost is rejected |
| `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET` | generated pair | The public `devkey`/`secret` pair lets anyone forge room-join tokens |
| `JUDGE0_AUTH_TOKEN` | generated | An unauthenticated Judge0 reachable on the network is arbitrary code execution |
| `S3_ACCESS_KEY` / `S3_SECRET_KEY` | generated | `minioadmin` guards interview recordings and briefs |
| `POSTGRES_PASSWORD` / `APP_DB_PASSWORD` | generated | Compose feeds both into the connection strings; dev passwords are rejected |
| `ANTHROPIC_API_KEY`, `DEEPGRAM_API_KEY` | live billing keys | Not boot-checked (absence fails loudly at first use) |
| `GOOGLE_CLIENT_ID` + `NEXT_PUBLIC_GOOGLE_CLIENT_ID` | prod OAuth client | Optional; enables Google sign-in |
| `NEXT_PUBLIC_API_URL` / `NEXT_PUBLIC_YWS_URL` | public https/wss URLs | Baked into the frontend **at build time** — rebuild the image to change them |
| `NEXT_PUBLIC_ORG_NAME` / `NEXT_PUBLIC_CONTACT_EMAIL` | your brand + candidate contact | Also build-time |

Everything in `docker-compose.yml` is now parameterized — the file carries
dev fallbacks (`${POSTGRES_PASSWORD:-interview}`) and reads real values from
`.env`. There are no hardcoded credentials left to hunt down.

Operational defaults worth knowing:

| Variable | Default | Note |
|---|---|---|
| `DEMO_ENABLED` | `true` | Self-serve practice interviews. They live in a dedicated demo org, so they never pollute a tenant's pipeline or metrics. Set `false` to hide the feature. |
| `SPECULATIVE_GENERATION` | `false` | Leave it. It cannot help while the agent injects a per-turn engine directive, and enabling it costs one wasted LLM call per turn (ARCHITECTURE.md decision row). |
| `DEEPGRAM_ENDPOINTING_MS` | `500` | Tuned with `utterance_end_ms=1000` against fragmented finals. |
| `RETENTION_DAYS_DEFAULT` | `90` | Applied to new sessions that do not specify their own. |

## 2. Run

```bash
docker compose --profile sandbox --profile agent --profile frontend up -d --build
```

That is: core stack + Judge0 sandbox + containerized voice agent + the
production frontend (`next build` → `next start`). The agent worker runs
`start` (production mode) in its container; local dev keeps using
`interview_agent.py dev` on the host.

The API container runs `alembic upgrade head` before serving, so schema
migrations apply on deploy (head is **0012**). The **eval worker runs the
same production posture check as the API** — it will refuse to start on dev
secrets too, so give it the same `.env`.

**Sync prompts as a deploy step.** Images do not ship prompt files into the
database, and the runtime resolves the newest DB row per prompt name:

```bash
docker compose exec api python scripts/sync_prompts.py --check
```

`--check` exits non-zero on drift and changes nothing — wire it into CI. Drop
`--check` to actually sync after a prompt edit. (A prompt *revert* used to be
a silent no-op; the sync now compares against the latest row, so rollbacks
take effect.)

## 3. TLS and ingress (not in compose — one reverse proxy on the host)

Terminate TLS in front of three upstreams — e.g. Caddy:

```
your-domain.com          → localhost:3000   (frontend)
api.your-domain.com      → localhost:8000   (API)
lk.your-domain.com       → localhost:7880   (LiveKit ws + turn/udp per LiveKit docs)
```

`y-websocket` (port 1234) must also be reachable as `wss://` for the editor —
**and see §7: it is unauthenticated.**

Compose binds Postgres, Redis, MinIO, and Judge0 to **127.0.0.1 only**. Do not
publish them; the app containers reach them over the compose network.

LiveKit no longer runs with `--dev`: compose passes `--keys` from your `.env`
pair. Its ICE range is pinned to **50000–50060/udp** and those ports are
published — open the same range on the host firewall, or media will fail to
connect while signalling appears healthy. A production LiveKit deployment
wants its own config (external IP, TURN) — see livekit.io/deploy.

## 4. What the boot check enforces vs. what it cannot

`app/config.py::validate_production_posture` fails the boot with a checklist
naming every offending variable — dev secrets, weak/empty signing secrets,
`DEV_DEFAULT_ORG=true`, missing email key, the LiveKit dev pair, MinIO and
Postgres dev credentials, a missing Judge0 token, a localhost `APP_BASE_URL`,
and an unset `FIRST_ADMIN_EMAIL`. The voice agent mirrors it in its own
process.

It **cannot** check: TLS termination, firewall rules, backups (`pg_dump` cron
+ MinIO versioning are on you), whether your LiveKit keys are actually the
ones LiveKit is running with, or anything in §7. Do those from this list, not
from memory.

## 5. Monitoring — what to alert on

| Signal | Where | Why it matters |
|---|---|---|
| Evaluation health | `GET /metrics/eval-health` (reviewer+) | Returns `queue_depth`, `dead_letter`, `stuck_sessions` (completed >10 min ago with no evaluation) and a `healthy` flag. **Alert on any non-zero.** A wedged eval worker is otherwise invisible: candidates look "Processing" forever. The Analytics screen banners this too. |
| Dead-letter queue | Redis list `evaluate_session:dead` | Jobs that failed 3 attempts with backoff. Each entry carries the error. Non-empty means evaluations were lost until someone re-queues them. |
| Voice latency | `GET /metrics/latency`, Analytics screen | Per-session p50/p95 with the segment breakdown (EOU → STT → LLM TTFT → TTS TTFB). Targets p50 ≤ 800 ms / p95 ≤ 1500 ms. |
| Provider fallback | agent logs | TTS falling back Deepgram → ElevenLabs → Cartesia, or the eval pipeline switching providers, means a vendor is degraded. |
| Boot-check failure | container exit | A crash-looping API/worker after a config change is almost always the posture checklist; the log names the variable. |

Structured logs carry `session_id`. There is **no** Sentry/APM wiring yet —
that remains open work.

## 6. Session lifecycle semantics (operational)

Behaviour a support person needs to know:

- A **completed or aborted session is a one-way door**. It cannot be reopened
  by anyone, including staff: room tokens 409, `/execute` 409, and the agent
  refuses dispatch. A candidate who reloads lands on the wrap-up screen.
- A **terminal candidacy** (completed / in_review / reviewed / withdrawn)
  refuses `start-interview`. Re-interviewing means a new candidacy.
- **Candidate links are genuinely revocable.** Re-minting a link rotates its
  jti and the previous link stops working immediately, as does any link for a
  session whose data was erased. If a candidate reports a dead link, they are
  probably holding a superseded one — send the current invite.
- Mid-interview reloads **rejoin** the same session rather than starting a
  second one.

## 7. Open security findings — read before exposing this to the internet

A production audit confirmed these and they were **deferred by decision**, not
fixed. They are release blockers for an internet-facing deployment:

| Sev | Finding |
|---|---|
| **P0** | Pool-poisoned RLS bypass: `auth._identity_db()` commits with the bypass GUC on and returns the connection to the pool; `/orgs/current/admin-actions` reuses it. Reproduced live — 74 rows across 5 orgs. |
| **P0** | `POST /sessions/{id}/candidate-link` has no gate — any candidate token can mint a link for another session in the same org. |
| **P1** | `GET /sessions/{id}/token` (which starts the live room) performs no consent check. |
| **P1** | `design_questions` / `sql_datasets` have no `org_id` and no RLS despite being tenant-written (violates invariant #8). |
| **P1** | No login brute-force protection; `/auth/register` is an unauthenticated email-send amplifier. |
| **P1** | `y-websocket` is unauthenticated: anyone who learns a session id can join that editor's CRDT room. Currently mitigated only by the id being an unguessable UUID. |
| **P1** | `next@14.2.x` carries unpatched high-severity advisories; the fix is a major upgrade. |
| **P2** | `memberships` lacks RLS; containers run as root; dependency pins are floor-only with no lock file; the cross-tenant suite covers only Phase-1 tables. |

Full detail with file:line and proposed fixes is in `AUDIT_REPORT.md`.

## 8. Pre-launch gates (product, not infra)

- Latency: certify p50 ≤ 800 ms / p95 ≤ 1500 ms on the production host. **Not
  yet met** — the last measured run was p50 ≈ 1.85 s on a busy dev machine,
  with LLM time-to-first-token dominating.
- Calibration: ≥ 20 human-scored sessions per round type before AI scores
  influence decisions (the analytics screen enforces the display floor, and
  calibration does not transfer across round types).
- The three-device candidate pass (low-end Android, Safari/Mac, Chrome/Windows)
  on a genuinely bad network.
- Compliance you cannot code away: independent bias audit where required
  (e.g. NYC LL144), accessibility review, counsel-reviewed consent texts.

Verification suites, all expected green (run from `backend/`):

```bash
python scripts/test_tenancy.py && python scripts/smoke.py && python scripts/smoke_exec.py
```

plus `python tests/e2e/mock_session.py`, `python tests/e2e/phase23_flow.py` from
the repo root, and the unit suite in-container (host Python may fight the
app's pins):

```bash
docker compose exec api python -m pytest tests -q
```

## 9. Known not-included

ATS integrations, camera proctoring, audio recording (LiveKit egress), email
reminders/no-show flows, Sentry/APM, Playwright device tests, and multi-node
scale-out. Each has a documented seam; none is silently faked. The `/worker`
directory is retired (evaluation runs as `app.eval.worker` on the backend
image) and can be deleted.

## 10. Capacity planning — what 300–400 concurrent interviews takes

The single-VM compose deployment handles roughly **10–25 simultaneous
interviews** (the agent worker is the constraint: each live session is a
process running STT, VAD, turn detection, TTS, and the engine — budget
~0.3–0.5 CPU core and ~200–300 MB each). 300–400 concurrent is a different
deployment shape, not a bigger VM:

| Component | At 300–400 concurrent | What changes |
|---|---|---|
| **Agent workers** | ~120–200 cores, 60–120 GB RAM total | A fleet of 10–25 worker VMs (or pods) all registering as "interviewer". **Mandatory code change: restore a real `load_fnc`** — it is pinned to 0 for single-worker correctness, which breaks load balancing the moment a second worker exists (agent/interview_agent.py, flagged in ARCHITECTURE.md). |
| **LiveKit** | 600–800 audio participants | The single container is out. Either LiveKit Cloud, or self-hosted distributed LiveKit (Redis-backed, proper keys, TURN, real UDP range). One sized node can carry the audio; HA needs the distributed setup. |
| **Anthropic API** | ~20–30 req/s to the conduct model, ~5–7 M input tokens/min (mostly cache reads) | Default rate-limit tiers will throttle far below this — negotiate custom limits before the pilot that needs them. Eval (Opus) is asynchronous and queue-buffered, so it needs throughput, not latency. |
| **Deepgram** | 300–400 concurrent STT streams + TTS | Pay-as-you-go project concurrency caps sit well below this — needs an enterprise concurrency commitment for both Nova-3 streaming and Aura. |
| **API + Postgres** | Steady event-append load (batched writes from ~800 writers), bursts of reads | 2–4 API replicas behind a load balancer, pgbouncer in front of a managed Postgres. The per-session advisory lock serializes only within a session, so appends scale with session count. Migration 0012 added the hot-path indexes this depends on. |
| **y-websocket** | 300–400 editor rooms | The bare `npx y-websocket` process is a dev tool: no persistence, no HA, **no auth**. Move to a Redis-backed y-websocket deployment or sticky-routed replicas, behind authentication. |
| **Judge0 / eval workers** | Bursty | Both stateless — scale worker counts; already queue-shaped, now with retry + dead-letter. |
| **Admission control** | — | Per-org caps exist (`max_concurrent_sessions`); add a global capacity gate so scheduling can never book more slots than the fleet can hold. |

Also required before selling that number: a **synthetic load harness** (scripted
sessions driving real audio through the full pipeline — nothing else will
surface the true per-session footprint), per-component metrics + alerting,
and a re-run of the latency gate (p50 ≤ 800 ms / p95 ≤ 1500 ms) **under load**,
not on an idle box.

Provider spend at full tilt: ~$1/interview ≈ **$300–800/hour** at 300–400
concurrent — linear, no scale surprises. The engineering work above is
weeks, not months; none of it changes application code except `load_fnc`
and the admission gate.
