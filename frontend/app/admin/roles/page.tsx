"use client";

import { useCallback, useEffect, useState } from "react";
import Nav from "../../components/Nav";
import { API, authFetch } from "../../lib/auth";
import "../admin.css";

interface PipelineRow { id: string; name: string; rounds: { round_type: string }[] }
interface PlanRow { id: string; created_at?: string }
interface RoleRow {
  id: string;
  name: string;
  description: string | null;
  status: string;
  pipeline_name: string | null;
  plan_id: string | null;
  candidates: number;
  created_at: string;
}

/** Roles: what interviews are created FOR. A role binds a pipeline
 * (multi-round) or a plan (single interview); assigning candidates to the
 * role decides which interview they get. */
export default function RolesPage() {
  const [roles, setRoles] = useState<RoleRow[]>([]);
  const [pipelines, setPipelines] = useState<PipelineRow[]>([]);
  const [plans, setPlans] = useState<PlanRow[]>([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [interview, setInterview] = useState(""); // "pipe:<id>" | "plan:<id>" | ""
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(async () => {
    const [r, p, pl] = await Promise.all([
      authFetch(`${API}/job-roles`),
      authFetch(`${API}/pipelines`),
      authFetch(`${API}/plans`),
    ]);
    if (r.ok) setRoles(await r.json());
    if (p.ok) setPipelines(await p.json());
    if (pl.ok) setPlans(await pl.json());
  }, []);
  useEffect(() => { void load(); }, [load]);

  const create = async () => {
    setMsg(null);
    const body: Record<string, unknown> = { name, description: description || null };
    if (interview.startsWith("pipe:")) body.pipeline_id = interview.slice(5);
    if (interview.startsWith("plan:")) body.plan_id = interview.slice(5);
    const r = await authFetch(`${API}/job-roles`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) return setMsg(await r.text());
    setName(""); setDescription(""); setInterview("");
    setMsg("Role created.");
    void load();
  };

  return (
    <>
      <Nav />
      <main className="admin">
        <h1>Roles</h1>
        <p className="page-sub">
          Create a role, attach the interview it runs (a multi-round pipeline or a single
          plan), then assign candidates to it from the Candidates page. Candidates
          automatically get the interview their role defines.
        </p>

        <div className="card">
          <h2 style={{ marginTop: 0 }}>New role</h2>
          <div className="score-row" style={{ margin: 0 }}>
            <input className="notes" style={{ maxWidth: 220 }} placeholder="Role name (e.g. Backend SDE II)"
              value={name} onChange={(e) => setName(e.target.value)} />
            <select className="notes" style={{ maxWidth: 300 }} value={interview}
              onChange={(e) => setInterview(e.target.value)}>
              <option value="">Interview: latest plan (default)</option>
              {pipelines.map((p) => (
                <option key={p.id} value={`pipe:${p.id}`}>
                  Pipeline · {p.name} ({p.rounds.map((r) => r.round_type).join(" → ")})
                </option>
              ))}
              {plans.map((p) => (
                <option key={p.id} value={`plan:${p.id}`}>
                  Plan · {p.id.slice(0, 8)}
                </option>
              ))}
            </select>
            <button className="mini primary" onClick={create} disabled={!name}>
              + Create role
            </button>
          </div>
          <input className="notes" style={{ marginTop: 10 }} placeholder="Description (optional)"
            value={description} onChange={(e) => setDescription(e.target.value)} />
          {msg && <p style={{ color: "var(--muted)", fontSize: 13, marginBottom: 0 }}>{msg}</p>}
        </div>

        <table>
          <thead>
            <tr><th>Role</th><th>Interview</th><th>Candidates</th><th>Status</th><th>Created</th></tr>
          </thead>
          <tbody>
            {roles.length === 0 && (
              <tr><td colSpan={5} style={{ color: "var(--faint)" }}>
                No roles yet. Create the first one above.
              </td></tr>
            )}
            {roles.map((r) => (
              <tr key={r.id}>
                <td>
                  {r.name}
                  {r.description && (
                    <><br /><small style={{ color: "var(--faint)" }}>{r.description}</small></>
                  )}
                </td>
                <td>
                  {r.pipeline_name
                    ? `Pipeline · ${r.pipeline_name}`
                    : r.plan_id
                      ? `Plan · ${r.plan_id.slice(0, 8)}`
                      : "Latest plan"}
                </td>
                <td>{r.candidates}</td>
                <td><span className="chip green">{r.status}</span></td>
                <td>{new Date(r.created_at).toLocaleDateString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </main>
    </>
  );
}
