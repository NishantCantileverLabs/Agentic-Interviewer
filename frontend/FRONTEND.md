# FRONTEND.md — AI Interview Platform

Screen specs live in PLATFORM_WORKFLOW_SCREENS.md (screens C1–C10, R1–R9, A1–A5).
Status→UI rules in its §7 are authoritative: if a screen and §7 disagree, §7 wins.

## Two products, one codebase
- **Candidate surface** (/i/[token]): no account, no navigation chrome, one primary
  action per screen. Calm, plain, reassuring. Assume the person is nervous and on
  an unfamiliar device.
- **Org surface** (/dashboard etc.): dense, information-first, keyboard-friendly.
  Assume a recruiter with 40 candidacies and 10 minutes.
Never share a layout shell between the two. Shared: tokens, primitives, API client.

## Binding rules
1. Status drives visibility. Never compute "can I show this" from ad-hoc props —
   read candidacy/session status through a single `useVisibility(status)` helper
   derived from §7. New statuses update that helper, not individual screens.
2. Every locked or hidden action states why. A disabled button always carries a
   tooltip naming the reason ("Available after review").
3. No score, signal, or rubric detail ever renders on the candidate surface.
   Enforce with a lint rule: candidate route files may not import from
   `features/evaluation/*` or `features/integrity/*`.
4. Integrity language is observational, never accusatory. The banned-terms lint
   (cheat, dishonest, suspicious, caught) covers frontend copy too.
5. Evidence chips are links. Any score or flag shown in a session view must seek
   the replay to its source moment — the two-click promise. No dead evidence.
6. Every empty state is an invitation to act, and every error says what happened
   and what to do next. No bare spinners on screens that can take >2s: show what
   is loading and roughly how long.
7. Accessibility floor, non-negotiable: keyboard-reachable everything, visible
   focus rings, labelled controls, prefers-reduced-motion respected, live regions
   for agent state changes and captions. The interview room must be usable by a
   candidate who cannot hear well — captions are a first-class feature, not a
   toggle nobody tested.
8. Copy rules: active voice, sentence case, an action keeps its name through the
   flow (button "Send invite" → toast "Invite sent"). Name things by what the
   person controls, never by how the system works ("Reschedule", not "Update
   slot record"). No exclamation marks in the candidate flow.

## Technical
- Next.js 14 App Router, TypeScript strict, server components by default; client
  components only where interaction demands it (room, editor, scrubber, pickers).
- Data: typed API client generated from the backend's OpenAPI schema. No hand-written
  response types, no `any` at boundaries.
- State: server state via the query layer; local UI state via hooks. No global store
  unless the interview room genuinely needs one (it does not — see F4).
- Tokens only. No hard-coded colors, spacing, or font sizes in components.
- Every screen ships with: loading state, empty state, error state, and a Playwright
  path test. A screen without those three states is not done.
