"use client";

import { cx } from "../../lib/cx";

export interface EvidenceChipProps {
  /** short quote or signal label */
  label: string;
  /** monospace source moment, e.g. "12:41" */
  at?: string;
  /** the two-click promise: seek the replay to this moment. When absent, the
   * chip renders as a flagged "evidence missing" marker instead of hiding. */
  onSeek?: () => void;
  missing?: boolean;
}

export function EvidenceChip({ label, at, onSeek, missing }: EvidenceChipProps) {
  if (missing) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-rust/40 bg-panel px-2.5 py-0.5 text-xs text-rust">
        <span aria-hidden>▲</span>
        evidence missing — flagged
      </span>
    );
  }
  return (
    <button
      onClick={onSeek}
      disabled={!onSeek}
      className={cx(
        "inline-flex items-center gap-1.5 rounded-full border border-line bg-panel px-2.5 py-0.5 text-xs text-ink",
        onSeek ? "hover:border-accent hover:text-accent" : "cursor-default",
      )}
    >
      <span className="max-w-56 truncate">{label}</span>
      {at && <span className="font-mono text-muted">{at}</span>}
    </button>
  );
}
