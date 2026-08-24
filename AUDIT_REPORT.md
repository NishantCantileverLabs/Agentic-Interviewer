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

## Latency (Phase 4)

| Segment | Before | After |
|---------|--------|-------|
| _(measured in Phase 4)_ | | |

Baseline from live demo (2026-08-24, busy dev machine): p50 1853 ms, p95 7330 ms.

## Screens changed

_(populated in Phase 6)_

## Deferred

_(mirrored in frontend/DEVIATIONS.md)_

## Go / No-Go checklist

- [ ] All verification suites green (smoke, smoke_exec, test_tenancy, both e2e, full pytest)
- [ ] Zero open P0/P1
- [ ] Latency targets met on 3 consecutive test sessions
- [ ] Cross-tenant tests pass
- [ ] Production boot check verified firing for every dev default
