# AI Interview Platform

Live voice AI technical interviewer: LiveKit voice loop, collaborative Monaco/Yjs coding
round with sandboxed execution, async dual-model evaluation, evidence-cited decision briefs,
shadow-mode validation, multi-tenant RBAC, and one product UI (single design system) across
the landing page, login, candidate flow (`/i/[token]`, where invite links point), candidate
home (`/portal`), and org console (`/dashboard` … `/questions` … `/settings`). The old
`/admin` and `/interview` pages remain as unlinked dev tools.

Any candidate account can take a self-serve **practice interview** from `/portal`
(POST `/auth/demo`, 3 per account, no recruiter needed). Before entering the room,
candidates pick the **interviewer voice** in the lobby (4 Deepgram Aura-2 options,
stored per session, kept across pipeline rounds).
Capacity planning and production runbook: [DEPLOY.md](DEPLOY.md).

- **Design:** [PHASE1_ARCHITECTURE.md](PHASE1_ARCHITECTURE.md) (+ Phase 2/3 docs)
- **Decisions:** [ARCHITECTURE.md](ARCHITECTURE.md) · **Screens:** frontend/FRONTEND.md + DESIGN.md
- **Task specs:** [TASKS.md](TASKS.md) · **Agent rules:** [CLAUDE.md](CLAUDE.md)
- **Workflow guide:** [WORKFLOW.md](WORKFLOW.md) · **Known deltas:** frontend/DEVIATIONS.md

## Auth model (enforced API-wide)

`DEV_DEFAULT_ORG=false`: every org read/write needs a login (`/login`, session
JWT re-validated against memberships per request); candidates act through
invite links + session-scoped tokens. Dev conveniences — the `X-Org-Id` header
stub used by scripts, and on-screen signup OTPs — work only while
`ENVIRONMENT` is not `production`. Setting `ENVIRONMENT=production` makes the
API **refuse to boot** with any dev-default secret still in place.

## Quick start (Docker)

```bash
# Start core services — API, Postgres, Redis, MinIO, LiveKit, eval worker, y-websocket
docker compose up -d --build

# Full stack — add Judge0 sandbox, containerized voice agent, production frontend
docker compose --profile sandbox --profile agent --profile frontend up -d --build
```

Then open http://localhost:3000 — candidate side and admin console both hang off it.

First-time setup: `cp .env.example .env` and fill keys (ANTHROPIC_API_KEY or
OPENROUTER_API_KEY, and DEEPGRAM_API_KEY — one key covers STT and the default
Aura TTS; ELEVENLABS_API_KEY / CARTESIA_API_KEY are optional fallback voices).
The provided `.env` has working dev defaults for everything else.

Stop everything: `docker compose down`.

API at http://localhost:8000 (docs at /docs), MinIO console at http://localhost:9001.

### Dev quickstart (host + containers)

```bash
# Terminal 1 — infra + api + eval worker (+ Judge0 sandbox + LiveKit + y-websocket)
docker compose --profile sandbox up -d --build

# Terminal 2 — voice agent (local venv; console mode also works: ... console)
cd agent && .venv/Scripts/python interview_agent.py dev

# Terminal 3 — frontend
cd frontend && npm run dev
```

Create venvs with `python -m venv .venv && .venv/Scripts/pip install -e .` in
`backend/` (add `[dev]` for tests) and `agent/`, and `npm install` in `frontend/`.
Seed dev content: `backend/.venv/Scripts/python backend/scripts/seed.py`,
`seed_rounds.py`, `seed_phase3.py`, and `sync_prompts.py`.

Verification suites (run from `backend/`):
`scripts/smoke.py` · `scripts/smoke_exec.py` · `scripts/test_tenancy.py` ·
`../tests/e2e/mock_session.py` · `../tests/e2e/phase23_flow.py` · `pytest tests`
(if the host Python env fights the app's pins, run the pytest suite inside the
api container: `docker cp backend/tests <api>:/srv/tests`, `pip install pytest`,
`python -m pytest tests` — same DB, real RLS).

## Layout

```
/backend    FastAPI control plane, alembic, providers/ (LLM abstraction)
/agent      LiveKit Agents voice worker (T1+)
/worker     RETIRED — eval runs as backend app/eval/worker (safe to delete)
/frontend   Next.js 14 app
/infra      judge0, seed scripts
/prompts    versioned prompt files (file = source, DB = runtime record)
/tests/e2e  scripted mock-candidate harness
```

## Docker

All services are containerized with `docker-compose.yml` at the repo root.

| File | Purpose |
|------|---------|
| `backend/Dockerfile` | Python 3.12 API + eval worker |
| `frontend/Dockerfile` | Next.js multi-stage build (build → production) |
| `agent/Dockerfile` | LiveKit Agents voice worker |
| `backend/.dockerignore` | Excludes tests/venv from backend build context |
| `frontend/.dockerignore` | Excludes node_modules/.next from frontend build context |
| `.env` | Environment variables (dev defaults, works out of the box) |
| `.env.example` | Full reference of all available variables |

The API container runs Alembic migrations + prompt sync on startup. Migrations
apply automatically; prompts from `/prompts` are mounted read-only and synced
into the database at boot.

Profiles:
- (none) — core stack: API, Postgres, Redis, MinIO, LiveKit, eval worker, y-websocket
- `sandbox` — Judge0 code execution (requires `privileged: true`)
- `agent` — containerized voice worker (needs DEEPGRAM_API_KEY)
- `frontend` — production Next.js build (NEXT_PUBLIC_* args baked at build time)

Run `docker compose --profile sandbox --profile agent --profile frontend up -d --build`
for the full stack. See [DEPLOY.md](DEPLOY.md) for production posture and TLS setup.
