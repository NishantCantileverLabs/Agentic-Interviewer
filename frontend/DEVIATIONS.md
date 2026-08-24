# DEVIATIONS.md — F0–F9 build vs. spec

Honest deltas between PLATFORM_WORKFLOW_SCREENS.md / the F-task acceptance
criteria and what shipped, with reasons. Anything not listed here was built as
specified.

| Area | Spec | Shipped | Why |
|---|---|---|---|
| Replay scrubber (F7) | Audio waveform scrubber | Time-based scrubber over the event-log timeline; same three synced panes, same two-click promise | No audio exists: LiveKit egress/recording was deferred by decision. The waveform slots in when recording ships. |
| Invite token (F1) | Signed `/i/[token]` | Token = candidacy id (unguessable UUIDv4); room access still requires the session-scoped JWT | Matches the backend's existing credential model; a signed wrapper is additive later. |
| Slot inventory (C4) | Slots from the API with concurrency applied | Client-generated 7-day/half-hour grid; the API's concurrency cap rejects overbooked picks on confirm | No slot-inventory endpoint exists; the cap is still enforced server-side at booking time. |
| Storybook (F0) | Storybook or /dev/primitives | `/dev/primitives` | Spec-sanctioned option; far lighter on the dev machine. |
| Playwright tests | Per-screen path tests | Not yet installed (browser download deferred); vitest unit tests + manual browser passes done | 8 GB dev machine at capacity; add Playwright before the three-device gate. |
| Token lint (F0) | ESLint rule | `npm run check:tokens` standalone script (has already caught real violations) | Same enforcement, no custom-plugin machinery. |
| OpenAPI-generated client | Generated types | Hand-written typed clients (`lib/portal.ts`, `lib/org.ts`), no `any` at boundaries | Single-repo backend under our control; codegen is a drop-in later. |
| Beacons (F3) | visibility/focus, offline-buffered | Shipped (`tab_visibility` events, 5s-flush queue that holds through offline windows) | — (as spec'd; noted because integrity *analysis* of them is deferred with proctoring T12–14) |
| Integrity surfaces | Integrity tab + inflow | Hidden entirely (never empty-rendered) | Proctoring (T12–14) deferred by decision; §7 says integrity renders only when signals exist. |
| ATS actions (§7 sync) | [Sync to ATS] ≥ reviewed | Button renders with a disabled-reason tooltip ("not connected in this deployment") | ATS (T17) deferred by decision; the outbox seam exists server-side. |
| Reviewer soft-lock (F8) | Claimed item locked to reviewer | Not implemented; decisions are append-only and idempotent-guarded server-side | Needs a claims table; single-reviewer deployments don't hit it. Flagged for the multi-reviewer milestone. |
| A1/A2/A3/A5 admin | Full admin screens | A4 data-subject tools + policy versions shipped in Settings; question bank links to the existing editor; members/org-profile/ATS read-only or marked not-connected | Matches what the backend actually supports today; no fake-live UI. |
| Round n of m (C8 top bar) | Round counter | Round *type* chip; counter needs plan-position plumbing | The engine knows its round; exposing index/total is a small backend add. |
| Emails (§6) | Reminder/no-show/brief-ready emails | Only the invite email exists (dev-logged without RESEND_API_KEY) | Scheduling emails needs a job scheduler; deferred with the notification layer. |
| Lobby (C7) — addition | Waiting-room copy only | Interviewer-voice picker (4 Aura-2 voices, radio cards; PATCHed to the session before entering; pipeline rounds inherit round 1's pick) | Post-spec addition from live-demo feedback (2026-08-24); server whitelists the voice ids. |
| Footer controls (F3) | — | Static bar at the bottom of the voice column, not a floating overlay | The spec'd fixed pill overlapped captions/editor text on small viewports (live-demo finding). |
| Run panel (F3) — addition | Pass/fail chips | Failing visible tests show input / expected / actual side-by-side + an extra-output hint | "Tests fail silently" read as "compiler broken" in live demo; hidden-test expectations still never render. |
| Practice interview — addition | Not in spec | `/portal` → Start practice (POST /auth/demo, 3/account); 3-step flow skips scheduling | Self-serve product trial for any candidate account (2026-08-24). |

Legacy surfaces (`/interview`, `/admin`, `/portal`, `/candidate`) remain live
and untouched during the migration; the new candidate flow (`/i`) and org
surface (`/dashboard` etc.) run alongside them on the new token system.

## Production-hardening pass (2026-08-24, closing the audit)

Closed: anonymous access to every private read and to session artifacts
(single choke point in `ensure_session_access`, pinned by
`backend/tests/test_authz.py`); dev header-auth stub and on-screen OTPs are
dead in `ENVIRONMENT=production`; production boot refuses dev-default secrets
(`app/main.py::validate_production_posture`, verified); staff scheduling no
longer burns candidate quotas; `next build` passes for all routes;
production Dockerfiles for frontend and agent; compose has restart policies,
pinned LiveKit, env passthrough. Full runbook: ../DEPLOY.md. Still open by
choice or dependency: Playwright device gate, audio recording, ATS,
proctoring, email scheduler, cloud infra itself.
