# DESIGN.md — AI Interview Platform

The design direction, decided once and followed exactly. Tokens in
`tailwind.config.ts` and `app/styles/tokens.css` must match this file; if they
drift, this file wins and the config is corrected.

## What this product is

A high-stakes assessment instrument. Two audiences need opposite things from the
same system: a **candidate**, nervous and on an unfamiliar device, needs calm and
legibility; a **recruiter** with 40 candidacies and ten minutes needs density and
scanability. One token system serves both; the two shells apply it differently.

## Direction: instrument, not app

The reference vocabulary is **measurement and record-keeping** — an audio console,
a flight recorder, a lab notebook. Ruled tracks, monospace timestamps, event
rails, waveforms. Precise and quiet, never decorative. The interview itself is a
record being made; the review surface is that record being read back.

Explicitly **not**: SaaS gradient decoration (the previous aurora-glass look was
exactly this and is retired for these routes), cream-and-terracotta editorial,
near-black-with-acid-accent, or hairline-rule broadsheet. Light-first and
considered. **No dark mode** — a half-done dark theme is worse than none, and a
light instrument panel reads calmer under stress.

## Color — 6 named tokens

| Token | Hex | Role |
|---|---|---|
| `ink` | `#181b1f` | Primary text, strongest marks |
| `paper` | `#f7f6f2` | Base ground (warm neutral — candidate calm) |
| `panel` | `#ffffff` | Raised surfaces: cards, inputs, the room canvas |
| `line` | `#d9d6cd` | Rules, borders, event-rail ticks (the signature material) |
| `muted` | `#6a7078` | Secondary text, timestamps, captions |
| `accent` | `#0b6b70` | The one accent: primary actions + agent state. Nothing else. |

Derived tints (generated in config, not hand-picked in components):
`ink` softens to `#3a4048` for body prose; `accent` has a `-tint` `#e5f0f0` wash
and a `-strong` `#085055` for hover. `paper` and `panel` are the only two grounds.

### Status palette — hue **and** label/icon, never color alone

Every status renders as a chip: a colored dot **plus** a text label **plus** a
glyph. A colorblind recruiter reads the label and shape, not the hue.

| Status | Hue | Hex | Glyph |
|---|---|---|---|
| invited / withdrawn | slate | `#697079` | ○ / ⊘ |
| scheduled | blue | `#2f5fa6` | ◷ |
| in_progress (live) | accent, pulsing | `#0b6b70` | ● |
| processing | amber | `#9a6b0c` | ◐ |
| brief ready / reviewed | green | `#2f7350` | ✓ |
| in_review | violet | `#6b4a9c` | ◎ |
| degraded / error | rust | `#a93f2c` | ▲ |

These seven cover the nine §7 statuses (invited+withdrawn share slate but differ
by glyph and label; reviewed reuses green). Status hues are **reserved** — never
reused as a decorative or series color.

## Type — three faces, each with one job

- **Display — Space Grotesk.** Headings and large data (KPI numbers, countdowns).
  Technical, measured; used with restraint, never for body copy.
- **Body — Inter.** All prose, labels, buttons, table text.
- **Mono — JetBrains Mono.** Code, data values, timestamps, event-rail ticks, IDs.
  Anything the system recorded rather than a human wrote.

Loaded from Google Fonts (allowed). Every face has a real fallback stack.

Scale (rem, 16px base): `xs .75` · `sm .8125` · `base .875` · `md 1` · `lg 1.25`
· `xl 1.5` · `2xl 2` · `3xl 2.75`. Body runs at `base`/`md`; the candidate
surface never goes below `base` (legibility under stress).

## Spacing & radius

Spacing scale (px): `1=4 · 2=8 · 3=12 · 4=16 · 5=24 · 6=32 · 8=48 · 10=64`.
Radius: `sm=4 · md=6 · lg=10 · xl=14`. Modest by intent — an instrument has
precise corners, not pill-round everything. Buttons `md`, cards `lg`, chips full.

## Signature element: the event rail

A ruled horizontal or vertical track in `line`, marked with monospace timestamps
and small tick glyphs. It is literally the replay's event rail and the candidacy
timeline, and it recurs as motif: section dividers are ruled, not shadowed; the
candidate progress indicator is a ticked rail, not dots. Elevation is done with
`line` borders and at most one soft shadow (`0 1px 2px rgba(24,27,31,.06)`), never
glow. The agent orb is the room's second signature — the single place the accent
animates.

## Motion

Sparing and functional. Agent-state transitions ≤120ms. The live-pulse and orb
animations are the only continuous motion, and both are removed under
`prefers-reduced-motion`. No decorative transitions.
