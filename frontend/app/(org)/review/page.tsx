"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { Button, PageHeader, Tabs } from "../../../components/ui";
import { type QueueItem, reviewQueue } from "../../../lib/org";

const INFLOWS = ["integrity", "borderline", "degraded"] as const;

function waitingSince(iso: string): string {
  const h = Math.floor((Date.now() - new Date(iso).getTime()) / 3_600_000);
  if (h < 1) return "under an hour";
  if (h < 24) return `${h}h`;
  return `${Math.floor(h / 24)}d ${h % 24}h`;
}

/** R7 — Review queue: three inflow tabs, oldest first (SLA honesty). */
export default function ReviewQueuePage() {
  const router = useRouter();
  const [items, setItems] = useState<QueueItem[] | null>(null);
  const [tab, setTab] = useState<string>("borderline");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    reviewQueue()
      .then((q) => {
        setItems(q);
        const first = INFLOWS.find((i) => q.some((x) => x.inflow === i));
        if (first) setTab(first);
      })
      .catch((e) => setError(String(e.message ?? e)));
  }, []);

  const byInflow = useMemo(() => {
    const map: Record<string, QueueItem[]> = { integrity: [], borderline: [], degraded: [] };
    for (const it of items ?? []) map[it.inflow]?.push(it);
    for (const k of Object.keys(map))
      map[k].sort((a, b) => a.created_at.localeCompare(b.created_at)); // oldest first
    return map;
  }, [items]);

  const current = byInflow[tab] ?? [];

  return (
    <div className="mx-auto max-w-[900px]">
      <PageHeader title="Review queue" subtitle="Oldest first." />

      {error && (
        <p role="alert" className="mt-4 text-sm text-rust">
          Could not load the queue: {error}
        </p>
      )}

      <div className="mt-4">
        <Tabs
          tabs={INFLOWS.map((i) => ({
            id: i,
            label: i[0].toUpperCase() + i.slice(1),
            count: byInflow[i].length,
          }))}
          active={tab}
          onChange={setTab}
        />
      </div>

      {items === null ? (
        <p className="mt-4 text-muted" aria-busy="true">Loading the queue…</p>
      ) : current.length === 0 ? (
        <div className="mt-4 rounded-lg border border-green/30 bg-panel p-6 text-center">
          <p className="font-medium text-green">All caught up</p>
          <p className="mt-1 text-sm text-muted">Nothing waiting in this inflow.</p>
        </div>
      ) : (
        <ul className="mt-4 flex flex-col gap-2">
          {current.map((it) => (
            <li
              key={it.session_id}
              className="flex items-center justify-between gap-4 rounded-lg border border-line bg-panel px-4 py-3"
            >
              <div className="min-w-0">
                <div className="font-medium text-ink">{it.candidate_label}</div>
                <p className="mt-0.5 truncate text-sm text-muted">{it.reason}</p>
                {it.signal && (
                  <p className="mt-0.5 font-mono text-xs text-muted">signal: {it.signal}</p>
                )}
              </div>
              <div className="flex shrink-0 items-center gap-3">
                <span className="font-mono text-xs text-muted">
                  waiting {waitingSince(it.created_at)}
                </span>
                <Button
                  size="sm"
                  onClick={() => router.push(`/sessions/${it.session_id}?mode=review`)}
                >
                  Open
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
