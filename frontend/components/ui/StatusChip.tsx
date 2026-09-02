import { cx } from "../../lib/cx";
import { type CandidacyStatus, STATUS_META, type StatusTone } from "../../lib/visibility";

/** Status is never color-alone: dot (hue) + label + glyph together. */
const TONE: Record<StatusTone, { text: string; dot: string; bg: string; border: string }> = {
  slate: { text: "text-slate", dot: "bg-slate", bg: "bg-paper", border: "border-line" },
  info: { text: "text-info", dot: "bg-info", bg: "bg-panel", border: "border-info/30" },
  accent: { text: "text-accent", dot: "bg-accent", bg: "bg-accent-tint", border: "border-accent/30" },
  amber: { text: "text-amber", dot: "bg-amber", bg: "bg-panel", border: "border-amber/30" },
  green: { text: "text-green", dot: "bg-green", bg: "bg-panel", border: "border-green/30" },
  violet: { text: "text-violet", dot: "bg-violet", bg: "bg-panel", border: "border-violet/30" },
  rust: { text: "text-rust", dot: "bg-rust", bg: "bg-panel", border: "border-rust/30" },
};

export function StatusChip({ status }: { status: CandidacyStatus }) {
  const meta = STATUS_META[status];
  const t = TONE[meta.tone];
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium",
        t.text,
        t.bg,
        t.border,
      )}
    >
      <span
        aria-hidden
        className={cx("h-1.5 w-1.5 rounded-full", t.dot, meta.live && "animate-live-pulse")}
      />
      {meta.label}
      <span aria-hidden className="opacity-70">
        {meta.glyph}
      </span>
    </span>
  );
}
