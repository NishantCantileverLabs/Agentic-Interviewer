# AI Interview Platform — Phase 3 Architecture & Claude Code Instructions

**Version 1.0 | Scope: beyond coding — case/consulting rounds, system design + whiteboard, behavioral, SQL/data rounds, multi-round pipelines**

Phase 3 generalizes the single-round SDE interview into a multi-round, multi-format interview platform. The Phase 1 spine (event log, state machine, dual-model, cache-stable context) and Phase 2 layers (tenancy, consent, integrity, review) are unchanged — Phase 3 adds **round types as plugins** on top of them.

**Phase 3 exit criteria:** an org can compose a pipeline like *Behavioral (20 min) → Case round (35 min) → System design with whiteboard (40 min)* across one or more sittings, and receive a cross-round aggregated brief with consistency analysis.

## Design stances

1. **A round type is data + plugins, not a fork.** One engine, one event log, one evaluation pipeline shape. Adding a round type must never touch the voice path or core engine.
2. **Artifacts are structured, not screenshots.** Whiteboard state, calc scratchpads, and SQL queries flow to models as structured text/JSON. Vision is the fallback, not the default.
3. **Cross-round claims need cross-round evidence.** The aggregation layer may only assert consistency/contradiction with citations into both rounds' event logs.

## Task summary (full detail in the Phase 3 brief; §9 of the source document)

- **T19** Round-type framework refactor: declarative registry (states/tools/prompts/observation/signals per type); coding becomes the first plugin; golden regression + import-linter boundary (invariant #15); dummy round registers without touching core.
- **T20** Calc scratchpad + deterministic math checker: number extraction (spoken forms incl. Indian numbering) ≥95% on fixtures; tolerance compare; confirm-final-only doctrine; scratchpad replay parity.
- **T21** Case round: case packs (clarifications, engine-owned exhibit release, must-touch redirect, math blocks, synthesis forcing move); structure-first completion criteria; case evaluation.
- **T22** Whiteboard: tldraw canvas, delta/snapshot events, `canvas_at(t)` replay, CanvasSerializer scene graph into observation block; vision fallback flag-gated.
- **T23** System design round: requirements-first nudge, estimation via T20, dive-area trigger, mandatory scale+failure criteria; diagram-derived signals.
- **T24** Behavioral round: resume→structured claims (versioned parser, degrade-to-raw), STAR tracking mechanics, resume-grounded probes, deterministic contradiction checks with one-neutral-question queue, I/we ratio signal.
- **T25** SQL/data round: seeded datasets with a data-quality trap task, query process capture, server-side answer re-execution (client never trusted), agent behavior reuse from coding.
- **T26** Multi-round pipelines: sittings, gates (none/auto/review), per-sitting consent/scheduling on Phase 2 machinery.
- **T27** Cross-round aggregation brief: weighted roll-up in code, merged evidence, citation-validated consistency analysis (invariant #17), trajectory + confidence scaling.

**Order: T19 → T20+T22 → T21+T23 → T24+T25 → T26 → T27.**
Gate 5: golden regression byte-identical after T19. Gate 6: per-round-type shadow calibration (≥20 dual-scored sessions each) before client exposure.

## New invariants
15. Round-type plugins may not import from the voice path — mechanically enforced.
16. Numeric correctness (case math, estimation, SQL answers) decided by deterministic code; LLMs discuss, never adjudicate.
17. Cross-round consistency claims require resolvable citations into every referenced session's event log.
18. Canvas/scratchpad/SQL replay parity: `*_at(session_id, t)` tests for every new tool.

## Implementation deviations (recorded per CLAUDE.md working style)
- **T25**: client-side DuckDB-WASM substituted with the existing Judge0-SQLite server execution — strictly server-adjudicated (stronger on invariant #16); client-side execution is a latency optimization deferred. Dataset/tasks schema, trap task, and process signals implemented as specified.
- **Phase 2 T12–T14 (proctoring) and T17 (ATS)**: explicitly skipped at the operator's direction. T18 cloud provisioning (managed infra/IaC apply) requires cloud accounts; the compliance mechanics (erase/export, retention classes, concurrency caps, spend alarms) are implemented.
