import { describe, expect, it } from "vitest";
import {
  ALL_STATUSES,
  type CandidacyStatus,
  STATUS_META,
  useVisibility,
} from "./visibility";

/** One assertion per §7 row — the matrix is load-bearing, so it is pinned. */
const EXPECTED: Record<
  CandidacyStatus,
  {
    label: string;
    tone: string;
    surface: string;
    locked: boolean;
    remind: boolean;
    reschedule: boolean;
    withdraw: boolean;
    sync: boolean;
    sendToReview: boolean;
    reviewActive: boolean;
  }
> = {
  invited: { label: "Invited", tone: "slate", surface: "landing", locked: false, remind: true, reschedule: false, withdraw: true, sync: false, sendToReview: false, reviewActive: false },
  scheduled: { label: "Scheduled", tone: "info", surface: "landing", locked: false, remind: true, reschedule: true, withdraw: true, sync: false, sendToReview: false, reviewActive: false },
  in_progress: { label: "Live now", tone: "accent", surface: "room", locked: true, remind: false, reschedule: false, withdraw: false, sync: false, sendToReview: false, reviewActive: false },
  processing: { label: "Processing", tone: "amber", surface: "completion", locked: true, remind: false, reschedule: false, withdraw: false, sync: false, sendToReview: false, reviewActive: false },
  brief_ready: { label: "Brief ready", tone: "green", surface: "completion", locked: false, remind: false, reschedule: false, withdraw: false, sync: true, sendToReview: true, reviewActive: true },
  in_review: { label: "In review", tone: "violet", surface: "completion", locked: true, remind: false, reschedule: false, withdraw: false, sync: false, sendToReview: false, reviewActive: true },
  reviewed: { label: "Reviewed", tone: "green", surface: "completion", locked: false, remind: false, reschedule: false, withdraw: false, sync: true, sendToReview: false, reviewActive: false },
  synced: { label: "Synced", tone: "slate", surface: "completion", locked: false, remind: false, reschedule: false, withdraw: false, sync: false, sendToReview: false, reviewActive: false },
  withdrawn: { label: "Withdrawn", tone: "slate", surface: "declined", locked: false, remind: false, reschedule: false, withdraw: false, sync: false, sendToReview: false, reviewActive: false },
};

describe("useVisibility — every §7 row", () => {
  for (const status of ALL_STATUSES) {
    it(status, () => {
      const v = useVisibility(status);
      const e = EXPECTED[status];
      expect(v.chip.label).toBe(e.label);
      expect(v.chip.tone).toBe(e.tone);
      expect(v.candidateSurface).toBe(e.surface);
      expect(v.actions.locked).toBe(e.locked);
      expect(v.actions.remind).toBe(e.remind);
      expect(v.actions.reschedule).toBe(e.reschedule);
      expect(v.actions.withdraw).toBe(e.withdraw);
      expect(v.actions.sync).toBe(e.sync);
      expect(v.actions.sendToReview).toBe(e.sendToReview);
      expect(v.reviewActive).toBe(e.reviewActive);
    });
  }

  it("a locked bar always names a reason (FRONTEND.md rule 2)", () => {
    for (const status of ALL_STATUSES) {
      const { actions } = useVisibility(status);
      if (actions.locked) expect(actions.lockReason && actions.lockReason.length > 0).toBe(true);
    }
  });

  it("every status has chip metadata with a glyph", () => {
    for (const status of ALL_STATUSES) {
      expect(STATUS_META[status].glyph.length).toBeGreaterThan(0);
    }
  });
});
