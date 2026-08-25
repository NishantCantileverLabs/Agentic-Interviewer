"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Nav from "../components/Nav";
import StatusChip from "../components/StatusChip";
import { API, authFetch } from "../lib/auth";
import "./admin.css";

interface SessionRow {
  id: string;
  candidate_label: string;
  status: string;
  created_at: string;
  ai_evaluations: number;
  human_evaluations: number;
  briefs: number;
}

interface HiringStats {
  total_candidates: number;
  scheduled: number;
  interviewed: number;
  by_role: { role_id: string; role_name: string; invited: number; interviewed: number }[];
  unassigned: { invited: number; interviewed: number };
}

const WEEK_MS = 7 * 24 * 3600 * 1000;

export default function AdminDashboard() {
  const [sessions, setSessions] = useState<SessionRow[]>([]);
  const [queueCount, setQueueCount] = useState<number | null>(null);
  const [stats, setStats] = useState<HiringStats | null>(null);

  useEffect(() => {
    authFetch(`${API}/sessions`).then(async (r) => setSessions(await r.json())).catch(() => {});
    authFetch(`${API}/review-queue`)
      .then(async (r) => (r.ok ? setQueueCount(((await r.json()) as unknown[]).length) : null))
      .catch(() => {});
    authFetch(`${API}/metrics/hiring`)
      .then(async (r) => (r.ok ? setStats(await r.json()) : null))
      .catch(() => {});
  }, []);

  const thisWeek = sessions.filter(
    (s) => Date.now() - new Date(s.created_at).getTime() < WEEK_MS,
  );
  const completed = sessions.filter((s) => s.status === "completed");
  const completionRate = sessions.length
    ? Math.round((completed.length / sessions.length) * 100)
    : null;
  const briefsReady = sessions.filter((s) => s.briefs > 0).length;

  return (
    <>
      <Nav />
      <main className="admin">
        <h1>Dashboard</h1>
        <p className="page-sub">
          Your hiring funnel at a glance. Every number links to the screen where you act on it.
        </p>

        <div className="kpi-row">
          <div className="kpi">
            <div className="kpi-num">{thisWeek.length}</div>
            <div className="kpi-label">interviews this week</div>
          </div>
          <div className="kpi">
            <div className="kpi-num">
              {completionRate === null ? "-" : completionRate}
              {completionRate !== null && <span className="unit">%</span>}
            </div>
            <div className="kpi-label">completion rate</div>
          </div>
          <div className={"kpi" + ((queueCount ?? 0) > 0 ? " alert" : "")}>
            <Link href="/admin/queue">
              <div className="kpi-num">{queueCount ?? "-"}</div>
              <div className="kpi-label">awaiting review →</div>
            </Link>
          </div>
          <div className="kpi">
            <div className="kpi-num">{briefsReady}</div>
            <div className="kpi-label">briefs ready</div>
          </div>
          <div className="kpi">
            <div className="kpi-num">{stats?.interviewed ?? "-"}</div>
            <div className="kpi-label">candidates interviewed</div>
          </div>
        </div>

        {stats && stats.by_role.length > 0 && (
          <>
            <h2>By role</h2>
            <table>
              <thead>
                <tr><th>Role</th><th>Invited</th><th>Interviewed</th><th>Progress</th></tr>
              </thead>
              <tbody>
                {stats.by_role.map((r) => (
                  <tr key={r.role_id}>
                    <td>{r.role_name}</td>
                    <td>{r.invited}</td>
                    <td>{r.interviewed}</td>
                    <td style={{ color: "var(--muted)" }}>
                      {r.invited > 0 ? `${Math.round((r.interviewed / r.invited) * 100)}%` : "-"}
                    </td>
                  </tr>
                ))}
                {stats.unassigned.invited > 0 && (
                  <tr>
                    <td style={{ color: "var(--faint)" }}>No role assigned</td>
                    <td>{stats.unassigned.invited}</td>
                    <td>{stats.unassigned.interviewed}</td>
                    <td />
                  </tr>
                )}
              </tbody>
            </table>
          </>
        )}

        <h2>Sessions</h2>
        <table>
          <thead>
            <tr>
              <th>Candidate</th><th>Status</th><th>Started</th>
              <th>AI eval</th><th>Human eval</th><th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {sessions.length === 0 && (
              <tr><td colSpan={6} style={{ color: "var(--faint)" }}>
                No sessions yet. Start one from <Link href="/admin/setup">New interview</Link>.
              </td></tr>
            )}
            {sessions.map((s) => (
              <tr key={s.id}>
                <td>
                  {s.candidate_label}
                  <br />
                  <small style={{ color: "var(--faint)" }}>{s.id.slice(0, 8)}</small>
                </td>
                <td><StatusChip status={s.status} /></td>
                <td>{new Date(s.created_at).toLocaleString()}</td>
                <td>{s.ai_evaluations > 0 ? `✓ v${s.ai_evaluations}` : "-"}</td>
                <td>{s.human_evaluations > 0 ? "✓" : "-"}</td>
                <td>
                  <Link href={`/admin/review/${s.id}`}>review</Link>
                  {s.briefs > 0 && (
                    <>
                      {" · "}
                      <Link href={`/admin/brief/${s.id}`}>brief</Link>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </main>
    </>
  );
}
