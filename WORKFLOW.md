# Standard Hiring Workflows

> **Surfaces update (F0–F9 build):** the product now ships two dedicated
> surfaces — the candidate flow at **`/i/[token]`** (landing → consent →
> schedule → system check → lobby with interviewer-voice pick → room → done;
> practice interviews skip the schedule step) and the org console at
> **`/dashboard`** (Roles, Candidates, Review queue, Sessions with replay,
> Analytics, Compare, Settings). The `/admin` and `/portal` routes below
> remain as the legacy console during migration; both use the same login
> and the same API gates.

How to run the platform day-to-day, mapped to real routes. The UI follows the
Copilot-style design language (aurora glass); the candidate side follows the
"one screen, one decision" rule.

## Personas & surfaces

| Persona | Entry | Surface |
|---|---|---|
| Recruiter / Admin | `/login` → `/admin` | Left rail: Dashboard · Roles · Candidates · New interview · Question bank · Review queue · Calibration · Latency |
| Reviewer | `/login` → `/admin/queue` | Review queue → per-session replay & blind scoring |
| Candidate | `/login` → `/portal` (or invite link `/candidate/[id]`) | Home lists their scheduled interviews; Start opens the guided wizard: welcome → consent → schedule → room → done |

## Accounts & role-based access

- Sign up at `/login` with **email + password + emailed OTP**, or **Google**
  (set `GOOGLE_CLIENT_ID` + `NEXT_PUBLIC_GOOGLE_CLIENT_ID`; the button appears
  automatically). With no email provider configured (dev), the OTP is shown
  on-screen as `dev_otp`.
- Account types: **candidate** → `/portal`; **recruiter (staff)** → `/admin`.
  Staff signup is **invite-only** (Settings → Members creates `staff_invites`
  rows; uninvited staff registration 403s before OTP). The first account in an
  empty org bootstraps as admin.
- Session JWTs ride `Authorization: Bearer` on every console call; the
  backend's `require_role` gates enforce reviewer < recruiter < admin, and
  candidate tokens get 403 on all staff APIs.
- This deployment runs `DEV_DEFAULT_ORG=false`: login is mandatory API-wide
  (candidate invite-link endpoints keep working — they authenticate by
  candidacy id + consent gate). The `X-Org-Id` header stub used by dev scripts
  works only while `ENVIRONMENT` is not `production`.

## Role-driven interviews (the standard flow)

1. `/admin/roles` — create a role (e.g. "Backend SDE II") and attach the
   interview it runs: a multi-round **pipeline** or a single **plan**.
2. `/admin/candidacies` — invite the candidate *into the role* (or assign the
   role later from the table), and optionally **schedule the slot yourself**.
3. The candidate logs in at `/portal`, sees "Backend SDE II · 📅 slot", and
   presses **Start** — consent gate first, then the exact interview their
   role defines (pipeline round 1 or the plan).
4. Dashboard → **By role** table tracks invited vs interviewed per role;
   the "candidates interviewed" KPI counts distinct candidates with a
   completed session (`/metrics/hiring`, computed in SQL).

## Workflow 1 — Managed pipeline (recommended for real hiring)

The full lifecycle with consent gates, review gates, and an auditable trail.

1. **Author content once** — `/admin/questions`: statement, visible + hidden
   tests, hint ladder, twist, reference solution (hidden tests are validated
   against it; expected outputs never leave the backend).
2. **Invite** — `/admin/candidacies` → *+ Invite candidate*. The portal link is
   emailed (or shown, in dev) to the candidate.
3. **Candidate self-serve** — the wizard walks them through what-to-expect,
   versioned consent (API-enforced — starting without it returns 403), an
   optional slot pick (≤2 reschedules), then the interview room.
4. **Run a pipeline** — `/admin/candidacies` → *▶ pipeline* (e.g. "SDE full
   loop"): each round becomes its own session; gates between rounds are
   `none` / `auto` (threshold in code) / `review` (blocks until a human
   confirms in the queue).
5. **Evaluation happens on completion** — dual-model, evidence-cited; the
   brief appears in Dashboard → *brief* within ~2 minutes.
6. **Review** — `/admin/queue` receives degraded + borderline sessions
   automatically. Confirm the AI result, or override **with a written
   rationale** (the API rejects rationale-less overrides). Decisions are
   append-only.
7. **Decide** — per-candidate aggregate brief (`/aggregate-brief`) rolls up
   rounds with citation-validated cross-round claims.

## Workflow 2 — Quick single interview (demos, referrals, one-offs)

1. `/admin/setup`: name the candidate, paste/upload JD + resume, compose
   rounds (intro → warmup → coding/SQL/discussion → wrapup), pick questions.
2. Copy the generated room link, send it to the candidate.
3. Track it on the Dashboard; review/brief as above.

## Workflow 2b — Practice interview (candidate self-serve)

Any candidate account can try the product without an invite: `/portal` →
**Start practice** (POST `/auth/demo`). It creates a demo candidacy
(`source="demo"`, capped at 3 per account, an in-flight one is resumed) with a
short fixed plan (intro → warmup → coding → wrapup) and a 3-step flow that
skips scheduling: what to expect → consent → system check → lobby → room.
Practice sessions never appear in role pipelines, and demo plans are excluded
from every "newest plan" fallback.

## Workflow 3 — Calibration loop (before trusting the AI at scale)

1. Run interviews normally; AI evaluations accumulate in shadow mode.
2. Reviewers blind-score sessions at `/admin/review/[id]` (AI scores hidden
   until submitted).
3. `/admin/calibration` shows AI↔human agreement per competency — charts render
   only at n≥20 (house rule: below that, "insufficient data", no exceptions).
4. Watch `/admin/latency` for the voice-path p50 ≤ 800 ms / p95 ≤ 1500 ms targets.

## Status chips (§7 of the screen spec)

`Invited` grey → `Scheduled` blue → `Live now` pulsing cyan → `Processing`
amber → `Completed/Brief ready` green → `In review` purple → `Reviewed ✓`
green → `Synced ↗` grey. The candidate side never leaks status beyond its own
flow.

## Deliberately deferred (per scope decisions)

ATS sync (Greenhouse/Lever), proctoring/integrity video, org SSO login,
JD→rubric generation, and the system-check screen's camera probe (browser,
microphone-level, and network-RTT checks are implemented; camera reports
"not required by this organization").
The spec for all of these lives in the screen-flow document; the backend seams
(ats_outbox, consent items, Clerk hook in `tenancy.py`) already exist.
