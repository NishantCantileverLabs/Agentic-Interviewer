import { cx } from "../../lib/cx";

export interface TimelineEvent {
  id: string;
  label: string;
  /** monospace timestamp, e.g. "14:02:11" or an ISO string */
  at: string;
  detail?: string;
  tone?: "default" | "accent" | "muted";
}

/** The event-rail signature (DESIGN.md): a ruled vertical track with monospace
 * timestamps. Used for the candidacy lifecycle timeline (R6). */
export function Timeline({ events }: { events: TimelineEvent[] }) {
  return (
    <ol className="relative ml-2 flex flex-col gap-4 border-l border-line pl-5">
      {events.map((e) => (
        <li key={e.id} className="relative">
          <span
            aria-hidden
            className={cx(
              "absolute -left-[27px] top-1 h-2.5 w-2.5 rounded-full border-2 border-panel",
              e.tone === "accent" ? "bg-accent" : e.tone === "muted" ? "bg-line" : "bg-ink",
            )}
          />
          <div className="flex items-baseline gap-3">
            <time className="font-mono text-xs text-muted">{e.at}</time>
            <span className="text-base font-medium text-ink">{e.label}</span>
          </div>
          {e.detail && <p className="mt-0.5 text-sm text-muted">{e.detail}</p>}
        </li>
      ))}
    </ol>
  );
}
