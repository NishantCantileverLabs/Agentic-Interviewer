# AI Interview Platform — Phase 2 Architecture & Claude Code Instructions

**Version 1.0 | Scope: proctoring & integrity, recruiter product, ATS integration, real users, production hardening**

Phase 2 turns the Phase 1 core loop into a product real recruiters and real candidates use. It builds strictly on Phase 1's invariants — event-sourced log, versioned prompts, deterministic-signals-in-code — and extends them. Read PHASE1_ARCHITECTURE.md first; nothing here overrides it.

**Phase 2 exit criteria:** a client org can be onboarded, create a role, invite real candidates, run proctored interviews, review flagged sessions in a dashboard, and sync results to their ATS — with consent, retention, and audit obligations met.

---

## 1. Scope

| Track | Deliverables |
|---|---|
| **A. Identity & tenancy** | Orgs, users, roles (admin / recruiter / reviewer), auth, org-scoped data isolation |
| **B. Candidate lifecycle** | Invites, scheduling/self-scheduling, candidate portal, consent flow, notifications |
| **C. Proctoring & integrity** | Webcam signals, typing dynamics, answer-style detection, voice consistency, integrity report |
| **D. Recruiter product** | Pipeline dashboard, session review + replay, comparison views, calibration analytics, review queue |
| **E. ATS integration** | Greenhouse + Lever (Phase 2 targets), webhook sync, brief push-back |
| **F. Production hardening** | Managed infra, security baseline, DPDP/GDPR compliance mechanics, cost & quota controls |

**Explicitly still out:** consulting/case rounds, whiteboard (Phase 3); payments; multi-role generalization (Phase 4).

### Design stances carried into everything below

1. **Integrity signals inform humans; they never auto-reject.** Every signal is evidence-linked, presented neutrally, and reviewable. This is both the ethically defensible position and the legally survivable one (NYC LL144, EU AI Act high-risk classification, India DPDP).
2. **Privacy-proportionate proctoring.** Prefer client-side analysis emitting *events* over shipping raw video to servers. Record video only with explicit separate consent, only when the org enables it.
3. **The event log remains the spine.** Proctoring signals, reviews, ATS sync operations — all are events or event-derived. No side-channel truths.

---

## 2. Architecture delta (what's added to the Phase 1 diagram)

```
                    CANDIDATE BROWSER (additions)
        ┌───────────────────────────────────────────────┐
        │ + Webcam capture (LiveKit video track)         │
        │ + On-device proctoring worker (WebWorker):     │
        │     MediaPipe face landmarks → gaze/pose/      │
        │     presence/multi-face EVENTS (not frames)    │
        │ + Consent UI, portal, scheduling               │
        └──────────────┬────────────────────────────────┘
                       │ proctor events (batched)          sampled frames
                       ▼                                   (opt-in orgs only)
   ┌────────────────────────────┐              ┌─────────────────────────────┐
   │  FastAPI CONTROL PLANE     │              │  PROCTOR WORKER (Python)     │
   │  + org/tenant scoping      │─────────────►│  frame verification model,   │
   │  + consent records         │   queue      │  voice-embedding drift,      │
   │  + ATS sync service        │              │  typing-dynamics analyzer,   │
   │  + review queue API        │              │  integrity aggregation       │
   └──────────┬─────────────────┘              └──────────────┬──────────────┘
              │                                               │
              ▼                                               ▼
        Postgres (+ RLS by org_id)                 integrity_reports (versioned,
        Redis, S3 (+ video egress bucket,          evidence-cited, same pattern
        separate retention policy)                 as evaluations)
              │
              ▼
   ┌────────────────────────────┐         ┌──────────────────────────────┐
   │  RECRUITER DASHBOARD        │         │  ATS CONNECTORS               │
   │  (Next.js, role-gated):     │         │  Greenhouse Harvest API,      │
   │  pipeline, review, replay,  │         │  Lever API; webhook inbound,  │
   │  calibration analytics      │         │  outbox-pattern outbound sync │
   └────────────────────────────┘         └──────────────────────────────┘
```

New processes: `proctor-worker` (queue consumer, CPU/GPU-light models), `ats-sync` (can live inside the API process initially, isolated module + outbox table from day one).

---

## 3. Track A — Identity & multi-tenancy

- **Model:** `orgs`, `users`, `memberships(user, org, role)` with roles `admin | recruiter | reviewer`. Candidates are **not** users — they remain token-authenticated per session (short-lived signed links), which keeps the candidate funnel friction-free and the user table clean.
- **Auth:** managed provider (Clerk or Auth0) for org users — SSO/SAML lands free later, which enterprise ATS-owning clients will ask for. Keycloak self-hosted is the fallback if data-residency positioning demands it. Candidate links: JWT, 24 h validity, single-session scope, revocable.
- **Isolation:** every tenant-owned table gains `org_id`; Postgres Row-Level Security enforced with `SET app.current_org`, plus application-layer scoping (belt and suspenders). A cross-tenant leak in a hiring product is existential — RLS tests are CI-blocking.
- **Audit:** `admin_actions` append-only table: who changed role configs, thresholds, retention, integrations, and when. Threshold changes especially — they alter hire signals and must be reconstructible.

---

## 4. Track B — Candidate lifecycle

- **Invite flow:** recruiter creates candidacy (or ATS webhook does) → email via Resend/SES with signed link → candidate lands on portal.
- **Self-scheduling:** slot picker against org-configured windows and concurrency caps (max parallel interviews per org — this is your infra cost throttle). Reschedule ≤ 2 times, cutoff 2 h before start. No calendar-provider integration in Phase 2; slots are platform-native.
- **Consent flow (legal load-bearing, not a checkbox):**
  - Screen 1: what happens in the interview, what is recorded (audio always; video only if org enabled), what is analyzed, retention period, right to human review of any automated assessment.
  - Separate explicit consent items: audio processing (required to proceed), video proctoring (required only if org mandates; org may configure "video optional — reduced integrity coverage noted to reviewer").
  - Stored as `consent_records(candidacy_id, item, granted, ts, policy_version)` — policy text itself is versioned. DPDP and GDPR both effectively require being able to show *which text* the person agreed to.
- **Candidate experience additions:** pre-join check now includes camera; a "what to expect" page (reduces no-shows and anxiety-driven false integrity flags); post-interview confirmation screen with the org's contact for questions. No score is ever shown to the candidate by the platform — that's the org's call, outside the product.

---

## 5. Track C — Proctoring & integrity (the sensitive core)

### 5.1 Signal inventory

| Signal | Where computed | Method | Cost profile |
|---|---|---|---|
| Face presence / absence | Client (WebWorker) | MediaPipe face detection @ ~2 fps analysis rate | Free (candidate CPU) |
| Multiple faces | Client | Same pipeline, count > 1 sustained ≥ 3 s | Free |
| Gaze / head-pose deviation | Client | MediaPipe landmarks → yaw/pitch; sustained off-screen ≥ 4 s → event | Free |
| Identity spot-check | Server (proctor worker) | 1 sampled frame / 60 s (opt-in orgs) vs. session-start reference frame, face-embedding distance | Small |
| Voice consistency | Server | Speaker embeddings (speechbrain/pyannote-class model) on rolling audio windows; drift score across session | Small |
| Tab switches / focus loss | Client (Phase 1 beacons) | `visibilitychange` + blur, already captured | Free |
| Paste anomalies | Server, deterministic | Phase 1 events: paste length, burst-typing signature (chars/sec spikes vs. session baseline) | Free |
| Answer-style detection | Eval worker | Evaluation model flags responses pattern-matching LLM-generated style, with cited turns | Existing eval cost |
| Response-latency anomalies | Server, deterministic | Turn-latency distribution shifts (e.g., uniform 8–10 s delays on every hard question) | Free |

**Client-side first** is deliberate: raw video mostly never leaves the browser, cost stays near zero, and the privacy story is defensible ("we analyze on your device and transmit events, not your camera feed" — with the sampled-frame exception clearly consented).

### 5.2 Event & aggregation design

- Client emits `proctor_event` rows into `interview_events` (same append-only spine): `{signal, severity, start_ts, end_ts, meta}`. Batched every 5 s; a network stall never blocks the interview.
- **No live intervention in Phase 2.** The agent does not confront candidates about signals mid-interview — false-positive confrontation is the worst candidate experience in the industry. Signals flow silently to the report.
- **Integrity report (post-session, proctor worker):**
  - Deterministic aggregation into per-signal summaries: count, total duration, session-relative timeline.
  - A composite `integrity_attention_level ∈ {none, low, review_recommended}` computed by **transparent rules** (documented thresholds in org config), *not* by an ML black box and *not* by an LLM. Example default: `review_recommended` if (multi-face ≥ 2 events) or (off-screen gaze > 15 % of coding time) or (any paste > 300 chars with matching burst signature).
  - Every line item links to timestamps; the review UI (Track D) jumps straight to the moment in the replay with synchronized audio + code.
- **Language discipline (enforced in templates + review UI copy):** signals are described as observations ("candidate off-camera 3:12–3:41"), never as accusations ("candidate cheated"). The brief's recruiter layer shows only the attention level + "see integrity report"; details live in the audit layer.

### 5.3 Calibration & fairness obligations

- Maintain a false-positive review loop: reviewers mark each flag `substantiated | benign | unclear`; monthly report of per-signal precision. Signals with poor precision get thresholds raised or get demoted to audit-only.
- Environmental fairness: poor lighting, shared rooms, and low-end webcams correlate with socioeconomics. Face-presence and gaze thresholds must be forgiving by default, and "camera quality insufficient for signal X" must be reported as *coverage absence*, never as a flag.

---

## 6. Track D — Recruiter product

- **Pipeline dashboard:** per-role funnel (invited → scheduled → completed → reviewed → synced), filterable, with hire-signal distribution and time-to-complete stats.
- **Session view:** decision brief inline + full replay (audio scrubber synchronized with code reconstruction and transcript — built on Phase 1's `code_at(t)` and event stream) + integrity report tab.
- **Review queue:** three inflows — `integrity: review_recommended`, `evaluation: degraded` (uncited scores from Phase 1's validator), and `borderline` (hire signal within a configurable band of the threshold). Reviewer actions: confirm / override with mandatory written rationale → `review_decisions` append-only table. Overrides feed calibration.
- **Comparison view:** side-by-side candidates on the same role — rubric radar, evidence quotes, process signals. Strictly same-role comparison; cross-role comparison is statistically meaningless and the UI should refuse it rather than mislead.
- **Calibration analytics (org-facing honesty layer):** AI-vs-human agreement from shadow mode, pass-rate drift over time (a silently drifting pass rate is how these systems rot), per-competency score distributions, reviewer-override rates. Same "insufficient data below n=20" rule as Phase 1 — no confident dashboards on five sessions.

---

## 7. Track E — ATS integration

- **Targets:** Greenhouse (Harvest API + webhooks) and Lever first — deepest market coverage. Workday deferred (enterprise sales cycle problem, not an engineering one).
- **Inbound:** ATS webhook (candidate moved to "AI Interview" stage) → create candidacy → send invite. Webhook signatures verified; idempotency keyed on ATS candidate + stage-change ID.
- **Outbound (outbox pattern, non-negotiable):** domain events (`interview_completed`, `brief_ready`, `review_decided`) written to an `ats_outbox` table in the same transaction as the triggering change; a sync worker drains it with retries + exponential backoff + dead-letter visibility in the admin UI. Direct API-call-on-event is how integrations silently lose data.
- **Payload to ATS:** stage transition + a link to the brief in our dashboard + a compact summary (signal, competency scores). **Do not push full transcripts or integrity details into the ATS** — least-privilege data sharing; the ATS is a system of record for process, ours for evidence.
- **Mapping UI:** org admin maps ATS stages ↔ platform states, ATS jobs ↔ role configs. Store mappings versioned; a remap must not retro-break in-flight candidacies.

---

## 8. Track F — Production hardening

- **Infra migration:** docker-compose → managed: Postgres (RDS/Cloud SQL), Redis (ElastiCache), S3 proper, container platform (ECS/Cloud Run/K8s — pick the one you'll actually operate; ECS/Cloud Run recommended over K8s for a small team). Agent workers on instances pinned to the LiveKit region; autoscale on active-session count with pre-warmed headroom of 2 (cold agent start mid-schedule = candidate waiting).
- **Judge0 isolation upgrade:** move execution hosts to dedicated instances with no route to internal services; this is the one workload that runs adversarial code.
- **Security baseline:** secrets manager (no .env in prod), TLS everywhere, signed URLs for recordings (short TTL), rate limiting on all public endpoints, dependency scanning in CI, quarterly access review of admin roles.
- **Compliance mechanics (build, don't document-only):**
  - Retention enforcement: per-org, per-artifact-class retention (events vs. audio vs. video may differ); nightly purge job with a purge audit log.
  - Data-subject requests: `export(candidacy_id)` (machine-readable bundle) and `erase(candidacy_id)` (crypto-shred recordings, tombstone events) implemented as admin actions — DPDP and GDPR both require these to actually work, not exist in a policy PDF.
  - Automated-decision disclosure text + human-review right surfaced in the consent flow (already in Track B) and honored via the review queue.
- **Cost & quota controls:** per-org concurrency caps, per-session token budget alarms, daily spend dashboard extending Phase 1's `llm_calls` cost logging. An interview that somehow burns 50× median tokens should page you, not surprise the invoice.

---

## 9. Data model additions

```sql
orgs(id, name, settings jsonb, created_at)
users(id, auth_provider_id, email, name)
memberships(user_id, org_id, role enum(admin|recruiter|reviewer))
admin_actions(id, org_id, user_id, action, payload jsonb, ts)          -- append-only
candidacies(id, org_id, role_config_id, candidate_email, candidate_name,
            source enum(manual|greenhouse|lever), ats_ref jsonb,
            status enum(invited|scheduled|in_progress|completed|reviewed|synced|withdrawn))
schedules(id, candidacy_id, slot_start, slot_end, reschedule_count int)
consent_records(id, candidacy_id, item, granted bool, ts, policy_version text)
policy_versions(version pk, item, text_md, effective_from)
-- sessions gains: org_id, candidacy_id, video_recorded bool
integrity_reports(id, session_id, version int,
                  signals jsonb,          -- per-signal: count, duration, timeline refs
                  attention_level enum(none|low|review_recommended),
                  rule_config_snapshot jsonb,   -- thresholds used, frozen at compute time
                  created_at)             -- versioned like evaluations, never overwritten
proctor_frame_checks(id, session_id, ts, embedding_distance numeric, verdict text)
voice_consistency(id, session_id, window_start, window_end, drift_score numeric)
review_decisions(id, session_id, reviewer_id, inflow enum(integrity|degraded|borderline),
                 decision enum(confirm|override), rationale text not null, ts)  -- append-only
flag_dispositions(id, session_id, signal, disposition enum(substantiated|benign|unclear),
                  reviewer_id, ts)        -- feeds monthly precision report
ats_connections(id, org_id, provider enum(greenhouse|lever), credentials_ref,
                stage_mappings jsonb, mapping_version int)
ats_outbox(id, org_id, event_type, payload jsonb, status enum(pending|sent|dead),
           attempts int, next_retry_at, created_at)
```

**New invariants (added to CI):**
8. All tenant-owned queries run under RLS; a cross-org access test suite is CI-blocking.
9. `integrity_reports.attention_level` is derivable from `signals` + `rule_config_snapshot` by a pure function — re-running the rules on the snapshot must reproduce the level.
10. `review_decisions.rationale` is non-empty on every override.
11. Outbound ATS effects exist only via `ats_outbox` (no direct API calls from request handlers).
12. Consent gate: a session cannot transition to `in_progress` without required consent items granted under the current policy version.

---

## 10. Claude Code task breakdown (T10–T18)

Ordered by dependency and risk. Same discipline as Phase 1: acceptance criteria are the definition of done.

**TASK 10 — Multi-tenancy & auth foundation** *(everything depends on this; do first, do carefully)*
- Orgs/users/memberships/admin_actions; Clerk (or Auth0) integration; org context middleware; Postgres RLS on all tenant tables + `SET app.current_org` plumbing; migration back-filling `org_id` onto Phase 1 tables (single "default org" for existing data); candidate JWT links (24 h, single-session, revocable).
- *Acceptance:* cross-tenant test suite proves org A cannot read org B's sessions/events/briefs via any endpoint; role gates hold (reviewer cannot edit role configs); admin actions logged.

**TASK 11 — Candidate lifecycle: invites, scheduling, consent**
- Candidacy model + manual creation UI; Resend/SES invite emails; slot picker with org windows + concurrency caps + reschedule rules; consent screens with versioned policy text; consent gate invariant #12; "what to expect" page; camera added to pre-join check.
- *Acceptance:* full happy path manual-invite → schedule → consent → interview start in staging; starting without required consent is impossible at the API layer (not just UI); consent record stores the exact policy version shown.

**TASK 12 — Client-side proctoring signals**
- WebWorker with MediaPipe: face presence, multi-face, gaze/head-pose events at ~2 fps analysis; severity/duration thresholds from org config; batched `proctor_event` emission (5 s) with offline buffering; zero impact on interview A/V performance budget.
- *Acceptance:* scripted scenarios produce correct events with correct durations; brief glances produce nothing; a 30 s network stall loses no events; CPU overhead ≤ 15 % on a mid-range laptop.

**TASK 13 — Server-side integrity: frame checks, voice consistency, typing dynamics**
- Proctor worker: sampled-frame identity check vs. session-start reference (opt-in orgs), face-embedding distance; voice-embedding drift on rolling windows; deterministic typing-burst analyzer over Phase 1 editor events; response-latency anomaly stats.
- *Acceptance:* fixture sessions score correctly; all deterministic analyzers reproduce identical outputs on re-run; frame checks never run for non-consented sessions (test).

**TASK 14 — Integrity report & aggregation rules**
- Rule engine computing `attention_level` from documented org-configurable thresholds; `rule_config_snapshot` frozen per report; report versioning; neutral-language templates; timeline with event deep-links; "coverage absence" reporting; brief integration (recruiter layer shows level only).
- *Acceptance:* invariant #9 test (recompute from snapshot = same level); threshold change produces v2 report leaving v1 intact; templates contain no accusatory language (banned-terms lint in CI).

**TASK 15 — Recruiter dashboard & review queue**
- Pipeline funnel, session view (brief + synchronized replay + integrity tab), review queue with three inflows, confirm/override with mandatory rationale, comparison view (same-role only), flag disposition capture.
- *Acceptance:* reviewer can go from queue → flagged moment in replay in ≤ 2 clicks; override without rationale rejected at API; dispositions persist and export.

**TASK 16 — Calibration analytics**
- AI-vs-human agreement views, pass-rate drift chart with alerting, override-rate and per-signal precision monthly rollups; n<20 insufficient-data rule everywhere.
- *Acceptance:* metrics verified by hand against fixtures; drift alert fires on a synthetic drifted dataset; small-n screens show the warning.

**TASK 17 — ATS integration (Greenhouse first, Lever second)**
- Connection setup UI (credentials via secrets ref); stage/job mapping UI (versioned); inbound webhooks (signature-verified, idempotent); `ats_outbox` + sync worker with retries/backoff/dead-letter; outbound payloads (no transcripts, no integrity detail).
- *Acceptance:* sandbox round-trip works; kill the sync worker mid-flight → no lost or duplicated updates after restart; invariant #11 enforced.

**TASK 18 — Production hardening & compliance mechanics**
- Managed-infra deployment (IaC), secrets manager, signed short-TTL recording URLs, per-artifact-class retention purge with audit log, `export()`/`erase()` admin actions, per-org concurrency caps, spend dashboard + token-budget alarms, agent autoscaling with warm headroom.
- *Acceptance:* staging → prod deploy from IaC alone; erase() leaves no retrievable recording; token-budget alarm fires at 10× median; load test at concurrency cap shows zero cold-start waits.

---

## 11. Dependency graph & sequencing

```
T10 tenancy/auth ──┬── T11 candidate lifecycle ──► T12 client proctoring ──► T13 server integrity ──► T14 integrity report
                   │
                   ├── T15 dashboard/review  (needs T10; integrity tab lands after T14)
                   ├── T16 calibration       (after T15)
                   ├── T17 ATS              (after T11)
                   └── T18 hardening        (starts early — IaC alongside T10; finishes last)
```

**Order of execution: T10 → T11 → {T12, T15, T17 in parallel} → T13 → T14 → T16 → T18 (final gate).**

**Gate 3 (before first real external candidate):** consent flow live with versioned policy text, RLS suite green, retention purge tested, erase() tested, integrity language lint green, review queue operational.

**Gate 4 (before integrity signals are shown to any client):** per-signal precision reviewed on ≥ 30 internally-run sessions with staged scenarios; any signal below agreed precision demoted to audit-only.

---

## 12. CLAUDE.md additions — see CLAUDE.md §Phase 2 (appended verbatim)

## 13. Configuration additions — see .env.example

## 14. Honest hard parts of Phase 2, in order

1. **Integrity signal precision** — the arms race is permanent, and false positives cost more than false negatives. Gate 4 exists for this reason.
2. **Multi-tenancy retrofit** — T10 touches every Phase 1 table and query. A rushed RLS rollout is worse than none because it creates false confidence.
3. **ATS long tail** — the APIs are easy; the edge cases (candidates moved backwards, stages renamed mid-flight, duplicate webhooks) are the work.
4. **Compliance as code** — erase(), retention, consent versioning are the difference between "can sell to a serious client" and "cannot pass their vendor security review."
