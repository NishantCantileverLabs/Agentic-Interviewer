"use client";

import { useEffect, useState } from "react";
import { cx } from "../../../lib/cx";
import { PageHeader } from "../../../components/ui";
import {
  type CalibrationReport,
  type LatencyReport,
  calibration,
  latencyReport,
} from "../../../lib/org";

const MIN_N = 20;

/** The house rule, made structural: every chart renders through this guard.
 * Below n=20 the chart area is replaced by the notice — no exceptions. */
function InsufficientData({
  n,
  children,
  label,
}: {
  n: number;
  label: string;
  children: React.ReactNode;
}) {
  if (n < MIN_N) {
    return (
      <div className="flex h-40 flex-col items-center justify-center rounded-lg border border-line bg-panel text-center">
        <p className="font-medium text-ink">Not enough data yet</p>
        <p className="mt-1 text-sm text-muted">
          {label} unlocks at {MIN_N} samples · currently {n}
        </p>
      </div>
    );
  }
  return <>{children}</>;
}

/** R8 — Analytics: calibration + latency, every figure carrying its n. */
export default function AnalyticsPage() {
  const [cal, setCal] = useState<CalibrationReport | null>(null);
  const [lat, setLat] = useState<LatencyReport | null>(null);

  useEffect(() => {
    calibration().then(setCal).catch(() => setCal({ n: 0 }));
    latencyReport().then(setLat).catch(() => null);
  }, []);

  return (
    <div className="mx-auto max-w-[1000px]">
      <PageHeader title="Analytics" />

      <section className="mt-6">
        <h2 className="mb-2 font-display text-md font-semibold text-ink">
          Calibration — AI vs human agreement{" "}
          <span className="font-mono text-xs font-normal text-muted">
            n={cal?.n ?? "…"}
          </span>
        </h2>
        <InsufficientData n={cal?.n ?? 0} label="Calibration">
          <div className="flex flex-col gap-2 rounded-lg border border-line bg-panel p-4">
            {Object.entries(cal?.competencies ?? {}).map(([name, c]) => (
              <div key={name} className="flex items-center gap-3">
                <span className="w-44 truncate text-sm capitalize text-ink">
                  {name.replace(/_/g, " ")}
                </span>
                <div className="h-3 flex-1 overflow-hidden rounded-full bg-paper">
                  <div
                    className="h-full bg-accent"
                    style={{ width: `${Math.round((c.agreement_within_1 ?? 0) * 100)}%` }}
                  />
                </div>
                <span className="w-24 text-right font-mono text-xs text-muted">
                  {Math.round((c.agreement_within_1 ?? 0) * 100)}% · n={c.n}
                </span>
              </div>
            ))}
          </div>
        </InsufficientData>
      </section>

      <section className="mt-6">
        <h2 className="mb-2 font-display text-md font-semibold text-ink">
          Voice latency{" "}
          <span className="font-mono text-xs font-normal text-muted">
            targets p50 ≤ {lat?.targets.p50_ms ?? 800}ms · p95 ≤ {lat?.targets.p95_ms ?? 1500}ms
          </span>
        </h2>
        <div className="flex flex-col gap-1.5 rounded-lg border border-line bg-panel p-4">
          {(lat?.sessions ?? [])
            .filter((s) => s.turns >= 3)
            .slice(0, 10)
            .map((s) => {
              const over = s.p95_ms > (lat?.targets.p95_ms ?? 1500);
              return (
                <div key={s.session_id} className="flex items-center gap-3 text-sm">
                  <span className="w-40 truncate text-ink">{s.candidate_label}</span>
                  <span className="font-mono text-xs text-muted">{s.turns} turns</span>
                  <span className="ml-auto font-mono text-xs tabular-nums text-ink-soft">
                    p50 {s.p50_ms}ms
                  </span>
                  <span
                    className={cx(
                      "font-mono text-xs tabular-nums",
                      over ? "text-rust" : "text-green",
                    )}
                  >
                    p95 {s.p95_ms}ms {over ? "▲" : "✓"}
                  </span>
                </div>
              );
            })}
          {(lat?.sessions ?? []).filter((s) => s.turns >= 3).length === 0 && (
            <p className="text-sm text-muted">
              No measured sessions yet — latency rows appear after live interviews.
            </p>
          )}
        </div>
      </section>

      <section className="mt-6">
        <h2 className="mb-2 font-display text-md font-semibold text-ink">
          Overrides &amp; signal precision
        </h2>
        <InsufficientData n={0} label="Override analysis">
          <span />
        </InsufficientData>
      </section>
    </div>
  );
}
