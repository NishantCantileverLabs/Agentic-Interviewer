import Link from "next/link";
import { cx } from "../../lib/cx";

export interface KpiCardProps {
  label: string;
  value: React.ReactNode;
  unit?: string;
  /** when set, the whole card links there (dashboard funnel counts) */
  href?: string;
  tone?: "default" | "attention";
}

export function KpiCard({ label, value, unit, href, tone = "default" }: KpiCardProps) {
  const body = (
    <div
      className={cx(
        "rounded-lg border bg-panel p-4 transition-colors",
        tone === "attention" ? "border-amber/40" : "border-line",
        href && "hover:border-accent",
      )}
    >
      <div className="font-display text-2xl font-semibold tabular-nums text-ink">
        {value}
        {unit && <span className="ml-1 text-md font-medium text-muted">{unit}</span>}
      </div>
      <div className="mt-1 text-sm text-muted">{label}</div>
    </div>
  );
  return href ? (
    <Link href={href} className="block">
      {body}
    </Link>
  ) : (
    body
  );
}
