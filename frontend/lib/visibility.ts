/**
 * §7 status-driven UI rules — the single source of truth for "what does each
 * surface show for this status". Screens NEVER compute visibility from ad-hoc
 * props; they read it here (FRONTEND.md rule 1). Adding a status means editing
 * this file, not individual screens.
 */

export type CandidacyStatus =
  | "invited"
  | "scheduled"
  | "in_progress"
  | "processing" // completed, evaluation running
  | "brief_ready" // completed, brief ready
  | "in_review"
  | "reviewed"
  | "synced"
  | "withdrawn";

export const ALL_STATUSES: CandidacyStatus[] = [
  "invited",
  "scheduled",
  "in_progress",
  "processing",
  "brief_ready",
  "in_review",
  "reviewed",
  "synced",
  "withdrawn",
];

export type StatusTone =
  | "slate"
  | "info"
  | "accent"
  | "amber"
  | "green"
  | "violet"
  | "rust";

/** Chip presentation: hue + label + glyph, so status is never color-alone. */
export interface StatusMeta {
  label: string;
  tone: StatusTone;
  glyph: string;
  live?: boolean; // pulsing dot (in_progress)
}

export const STATUS_META: Record<CandidacyStatus, StatusMeta> = {
  invited: { label: "Invited", tone: "slate", glyph: "○" },
  scheduled: { label: "Scheduled", tone: "info", glyph: "◷" },
  in_progress: { label: "Live now", tone: "accent", glyph: "●", live: true },
  processing: { label: "Processing", tone: "amber", glyph: "◐" },
  brief_ready: { label: "Brief ready", tone: "green", glyph: "✓" },
  in_review: { label: "In review", tone: "violet", glyph: "◎" },
  reviewed: { label: "Reviewed", tone: "green", glyph: "✓" },
  synced: { label: "Synced", tone: "slate", glyph: "↗" },
  withdrawn: { label: "Withdrawn", tone: "slate", glyph: "⊘" },
};

/** R6 action-bar visibility, per §7. Each action is shown/hidden; when the whole
 * bar is locked, `lockReason` names why (FRONTEND.md rule 2 — never a silent
 * lock). */
export interface ActionVisibility {
  remind: boolean;
  reschedule: boolean;
  withdraw: boolean;
  sync: boolean; // Sync to ATS
  sendToReview: boolean;
  locked: boolean;
  lockReason?: string;
}

/** Candidate-side: which screen the invite link resolves to for this status. */
export type CandidateSurface = "landing" | "room" | "completion" | "declined";

export interface Visibility {
  chip: StatusMeta;
  actions: ActionVisibility;
  candidateSurface: CandidateSurface;
  reviewActive: boolean; // is there a live review-queue item?
}

const NO_ACTIONS: ActionVisibility = {
  remind: false,
  reschedule: false,
  withdraw: false,
  sync: false,
  sendToReview: false,
  locked: false,
};

const MATRIX: Record<CandidacyStatus, Omit<Visibility, "chip">> = {
  invited: {
    actions: { ...NO_ACTIONS, remind: true, withdraw: true },
    candidateSurface: "landing",
    reviewActive: false,
  },
  scheduled: {
    actions: { ...NO_ACTIONS, remind: true, reschedule: true, withdraw: true },
    candidateSurface: "landing",
    reviewActive: false,
  },
  in_progress: {
    actions: { ...NO_ACTIONS, locked: true, lockReason: "Interview in progress" },
    candidateSurface: "room",
    reviewActive: false,
  },
  processing: {
    actions: { ...NO_ACTIONS, locked: true, lockReason: "Evaluation in progress" },
    candidateSurface: "completion",
    reviewActive: false,
  },
  brief_ready: {
    actions: { ...NO_ACTIONS, sync: true, sendToReview: true },
    candidateSurface: "completion",
    reviewActive: true,
  },
  in_review: {
    actions: { ...NO_ACTIONS, locked: true, lockReason: "Locked until a decision is recorded" },
    candidateSurface: "completion",
    reviewActive: true,
  },
  reviewed: {
    actions: { ...NO_ACTIONS, sync: true },
    candidateSurface: "completion",
    reviewActive: false,
  },
  synced: {
    actions: { ...NO_ACTIONS },
    candidateSurface: "completion",
    reviewActive: false,
  },
  withdrawn: {
    actions: { ...NO_ACTIONS },
    candidateSurface: "declined",
    reviewActive: false,
  },
};

/**
 * The one helper every screen uses to decide what to show for a status.
 * Pure and deterministic (named `useVisibility` per FRONTEND.md, but it needs
 * no React state — safe to call anywhere).
 */
export function useVisibility(status: CandidacyStatus): Visibility {
  const row = MATRIX[status];
  return { chip: STATUS_META[status], ...row };
}
