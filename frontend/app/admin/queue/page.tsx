"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import Nav from "../../components/Nav";
import { API, authFetch } from "../../lib/auth";
import "../admin.css";

interface QueueItem {
  session_id: string;
  candidate_label: string;
  inflow: string;
  reason: string;
  signal?: string;
}

/** T15 — review queue: degraded + borderline inflows; confirm/override with
 * mandatory rationale (API rejects rationale-less overrides). */
export default function QueuePage() {
  const [items, setItems] = useState<QueueItem[]>([]);
  const [rationale, setRationale] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(async () => {
    const r = await authFetch(`${API}/review-queue`);
    if (r.ok) setItems(await r.json());
  }, []);
  useEffect(() => { void load(); }, [load]);

  const decide = async (item: QueueItem, decision: "confirm" | "override") => {
    setMsg(null);
    const r = await authFetch(`${API}/sessions/${item.session_id}/review-decision`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        inflow: item.inflow, decision,
        rationale: rationale[item.session_id] ?? "",
      }),
    });
    setMsg(r.ok ? "Decision recorded." : `Rejected: ${await r.text()}`);
    void load();
  };

  return (
    <>
      <Nav />
      <main className="admin">
        <h1>Review queue</h1>
        <p className="page-sub">
          Inflows: degraded evaluations and borderline hire signals, oldest first. Overrides
          require a written rationale. The API enforces it.
        </p>
        {items.length === 0 && (
          <div className="card" style={{ color: "var(--muted)" }}>The queue is clear. 🎉</div>
        )}
        {items.map((it) => (
          <div key={it.session_id} className="queue-card">
            <b>{it.candidate_label}</b>{" "}
            <span className={`badge ${it.inflow === "degraded" ? "bad" : "warn"}`}>{it.inflow}</span>
            {it.signal && <span className="badge ok" style={{ marginLeft: 6 }}>{it.signal}</span>}
            <p style={{ color: "#8b949e", margin: "6px 0" }}>{it.reason}</p>
            <p>
              <Link href={`/admin/review/${it.session_id}`}>replay & score</Link>
              {" · "}
              <Link href={`/admin/brief/${it.session_id}`}>brief</Link>
            </p>
            <input className="notes" placeholder="rationale (required for override)"
              value={rationale[it.session_id] ?? ""}
              onChange={(e) => setRationale((s) => ({ ...s, [it.session_id]: e.target.value }))} />
            <div style={{ marginTop: 10, display: "flex", gap: 8 }}>
              <button className="mini primary" onClick={() => decide(it, "confirm")}>
                Confirm AI result
              </button>
              <button className="mini" onClick={() => decide(it, "override")}>
                Override (rationale required)
              </button>
            </div>
          </div>
        ))}
        {msg && <p style={{ color: "#8b949e" }}>{msg}</p>}
      </main>
    </>
  );
}
