"use client";

/** §7 status-driven chip colors — the single mapping used by every list. */
const STYLES: Record<string, { cls: string; label?: string }> = {
  // candidacy lifecycle
  invited: { cls: "grey", label: "Invited" },
  scheduled: { cls: "blue", label: "Scheduled" },
  consented: { cls: "blue", label: "Consented" },
  in_progress: { cls: "live", label: "Live now" },
  active: { cls: "live", label: "Live now" },
  completed: { cls: "green", label: "Completed" },
  in_review: { cls: "purple", label: "In review" },
  reviewed: { cls: "green", label: "Reviewed ✓" },
  synced: { cls: "grey", label: "Synced ↗" },
  withdrawn: { cls: "grey", label: "Withdrawn" },
  // session states
  created: { cls: "grey", label: "Created" },
  processing: { cls: "amber", label: "Processing" },
  degraded: { cls: "red", label: "Degraded" },
  failed: { cls: "red", label: "Failed" },
};

export default function StatusChip({ status }: { status: string }) {
  const s = STYLES[status] ?? { cls: "grey" };
  return <span className={`chip ${s.cls}`}>{s.label ?? status.replace(/_/g, " ")}</span>;
}
