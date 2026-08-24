# DEPLOY.md — taking this stack to production

The compose file is the deployment unit: one VM (4+ cores, 16 GB) runs the
whole platform **at pilot scale (~10–25 concurrent interviews)**. This guide
is the difference between `dev` and a defensible production posture. The API
**refuses to boot** in production posture until the checklist below is
genuinely done — that is by design. For anything beyond pilot scale, read
§7 Capacity planning before promising a number to a client.

## 1. Secrets — generate, never reuse dev values

```bash
python -c "import secrets; print('SESSION_SECRET=' + secrets.token_urlsafe(48))"
python -c "import secrets; print('CANDIDATE_LINK_SECRET=' + secrets.token_urlsafe(48))"
python -c "import secrets; print('INTERNAL_API_KEY=' + secrets.token_urlsafe(48))"
```

Put them in `.env` on the host (never in the repo). Also required there:

| Variable | Production value |
|---|---|
| `ENVIRONMENT` | `production` — enforces all of this at boot |
| `DEV_DEFAULT_ORG` | `false` |
| `RESEND_API_KEY` | real key — OTPs and invites must be emailed, never displayed |
| `APP_BASE_URL` | `https://your-domain` (drives CORS + invite links) |
| `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET` | generated pair (not devkey/secret) |
| `ANTHROPIC_API_KEY`, `DEEPGRAM_API_KEY` | live billing keys |
| `GOOGLE_CLIENT_ID` + `NEXT_PUBLIC_GOOGLE_CLIENT_ID` | prod OAuth client (optional) |
| `NEXT_PUBLIC_API_URL` / `NEXT_PUBLIC_YWS_URL` | public https/wss URLs (baked into the frontend at build) |

Postgres/MinIO credentials in docker-compose.yml are still dev literals
(`interview/interview`, `minioadmin`) — change them together with their
connection strings when the data outlives one host.

## 2. Run

```bash
docker compose --profile sandbox --profile agent --profile frontend up -d --build
```

That is: core stack + Judge0 sandbox + containerized voice agent + the
production frontend (`next build` → `next start`). The agent worker runs
`start` (production mode) in its container; local dev keeps using
`interview_agent.py dev` on the host.

## 3. TLS and ingress (not in compose — one reverse proxy on the host)

Terminate TLS in front of three upstreams — e.g. Caddy:

```
your-domain.com          → localhost:3000   (frontend)
api.your-domain.com      → localhost:8000   (API)
lk.your-domain.com       → localhost:7880   (LiveKit ws + turn/udp per LiveKit docs)
```

LiveKit in production wants its own config (keys, external IP, TURN) — see
livekit.io/deploy; the dev `--dev` flag in compose is for localhost only.
`y-websocket` (port 1234) must also be reachable as `wss://` for the editor.

## 4. What the boot check enforces vs. what it cannot

`app/main.py::validate_production_posture` hard-fails on dev secrets,
`DEV_DEFAULT_ORG=true`, or missing email. It **cannot** check: TLS, database
credentials, backups (`pg_dump` cron + MinIO versioning are on you), or the
LiveKit key pair. Do those from this list, not from memory.

## 5. Pre-launch gates (product, not infra)

- Latency: certify p50 ≤ 800 ms / p95 ≤ 1500 ms on the production host.
- Calibration: ≥ 20 human-scored sessions per round type before AI scores
  influence decisions (the analytics screen enforces the display floor).
- The three-device candidate pass (low-end Android, Safari/Mac, Chrome/Windows)
  on a genuinely bad network.
- Compliance you cannot code away: independent bias audit where required
  (e.g. NYC LL144), accessibility review, counsel-reviewed consent texts.

## 6. Known not-included

ATS integrations, camera proctoring, audio recording (LiveKit egress), email
reminders/no-show flows, multi-node scale-out. Each has a documented seam;
none is silently faked.

## 7. Capacity planning — what 300–400 concurrent interviews takes

The single-VM compose deployment handles roughly **10–25 simultaneous
interviews** (the agent worker is the constraint: each live session is a
process running STT, VAD, turn detection, TTS, and the engine — budget
~0.3–0.5 CPU core and ~200–300 MB each). 300–400 concurrent is a different
deployment shape, not a bigger VM:

| Component | At 300–400 concurrent | What changes |
|---|---|---|
| **Agent workers** | ~120–200 cores, 60–120 GB RAM total | A fleet of 10–25 worker VMs (or pods) all registering as "interviewer". **Mandatory code change: restore a real `load_fnc`** — it is pinned to 0 for single-worker correctness, which breaks load balancing the moment a second worker exists (agent/interview_agent.py, flagged in ARCHITECTURE.md). |
| **LiveKit** | 600–800 audio participants | The `--dev` container is out. Either LiveKit Cloud, or self-hosted distributed LiveKit (Redis-backed, proper keys, TURN, real UDP range). One sized node can carry the audio; HA needs the distributed setup. |
| **Anthropic API** | ~20–30 req/s to the conduct model, ~5–7 M input tokens/min (mostly cache reads) | Default rate-limit tiers will throttle far below this — negotiate custom limits before the pilot that needs them. Eval (Opus) is asynchronous and queue-buffered, so it needs throughput, not latency. |
| **Deepgram** | 300–400 concurrent STT streams + TTS | Pay-as-you-go project concurrency caps sit well below this — needs an enterprise concurrency commitment for both Nova-3 streaming and Aura. |
| **API + Postgres** | Steady event-append load (batched writes from ~800 writers), bursts of reads | 2–4 API replicas behind a load balancer, pgbouncer in front of a managed Postgres. The per-session advisory lock serializes only within a session, so appends scale with session count. |
| **y-websocket** | 300–400 editor rooms | The bare `npx y-websocket` process is a dev tool: no persistence, no HA. Move to a Redis-backed y-websocket deployment or sticky-routed replicas. |
| **Judge0 / eval workers** | Bursty | Both stateless — scale worker counts; already queue-shaped. |
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
