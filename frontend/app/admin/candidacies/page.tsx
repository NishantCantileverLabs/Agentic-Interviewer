"use client";

import { useCallback, useEffect, useState } from "react";
import Nav from "../../components/Nav";
import StatusChip from "../../components/StatusChip";
import { API, authFetch } from "../../lib/auth";
import "../admin.css";

interface CandidacyRow {
  id: string;
  candidate_name: string;
  candidate_email: string;
  status: string;
  job_role_id: string | null;
  role_name: string | null;
  slot_start: string | null;
  created_at: string;
}

interface RoleRow { id: string; name: string }

export default function CandidaciesPage() {
  const [rows, setRows] = useState<CandidacyRow[]>([]);
  const [roles, setRoles] = useState<RoleRow[]>([]);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("");
  const [slotDraft, setSlotDraft] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(async () => {
    const [c, r] = await Promise.all([
      authFetch(`${API}/candidacies`),
      authFetch(`${API}/job-roles`),
    ]);
    if (c.ok) setRows(await c.json());
    if (r.ok) setRoles(await r.json());
  }, []);
  useEffect(() => { void load(); }, [load]);

  const invite = async () => {
    setMsg(null);
    const r = await authFetch(`${API}/candidacies`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        candidate_name: name,
        candidate_email: email,
        ...(inviteRole ? { job_role_id: inviteRole } : {}),
      }),
    });
    if (!r.ok) return setMsg(await r.text());
    const data = await r.json();
    setMsg(`Invited. Portal link: ${data.invite_link} (email ${data.email_sent ? "sent" : "logged, no RESEND_API_KEY"})`);
    setName(""); setEmail("");
    void load();
  };

  const assignRole = async (cid: string, roleId: string) => {
    if (!roleId) return;
    const r = await authFetch(`${API}/candidacies/${cid}/assign-role`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ job_role_id: roleId }),
    });
    setMsg(r.ok ? "Role assigned." : await r.text());
    void load();
  };

  const schedule = async (cid: string) => {
    const slot = slotDraft[cid];
    if (!slot) return;
    const r = await authFetch(`${API}/candidacies/${cid}/schedule`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ slot_start: new Date(slot).toISOString() }),
    });
    setMsg(r.ok ? "Interview scheduled. The candidate sees it on their home page." : await r.text());
    void load();
  };

  return (
    <>
      <Nav />
      <main className="admin">
        <h1>Candidates</h1>
        <p className="page-sub">
          Invite candidates, assign them a role (which decides their interview), and
          schedule their slot. Candidates see the scheduled interview on their own home
          page the moment you save it.
        </p>

        <div className="card">
          <div className="score-row" style={{ margin: 0 }}>
            <input className="notes" style={{ maxWidth: 200 }} placeholder="Candidate name"
              value={name} onChange={(e) => setName(e.target.value)} />
            <input className="notes" style={{ maxWidth: 240 }} placeholder="email@company.com"
              value={email} onChange={(e) => setEmail(e.target.value)} />
            <select className="notes" style={{ maxWidth: 200 }} value={inviteRole}
              onChange={(e) => setInviteRole(e.target.value)}>
              <option value="">No role (default interview)</option>
              {roles.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
            </select>
            <button className="mini primary" onClick={invite} disabled={!name || !email}>
              + Invite candidate
            </button>
          </div>
          {msg && (
            <p style={{ color: "var(--muted)", fontSize: 13, wordBreak: "break-all", marginBottom: 0 }}>
              {msg}
            </p>
          )}
        </div>

        <table>
          <thead>
            <tr>
              <th>Candidate</th><th>Role</th><th>Status</th>
              <th>Schedule</th><th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr><td colSpan={5} style={{ color: "var(--faint)" }}>
                No candidates yet. Send your first invite above.
              </td></tr>
            )}
            {rows.map((c) => (
              <tr key={c.id}>
                <td>
                  {c.candidate_name}
                  <br />
                  <small style={{ color: "var(--faint)" }}>{c.candidate_email}</small>
                </td>
                <td>
                  {c.role_name ?? (
                    <select className="notes" style={{ maxWidth: 160, padding: "5px 9px" }}
                      defaultValue="" onChange={(e) => assignRole(c.id, e.target.value)}>
                      <option value="">assign role…</option>
                      {roles.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
                    </select>
                  )}
                </td>
                <td><StatusChip status={c.status} /></td>
                <td>
                  {c.slot_start ? (
                    <span style={{ fontSize: 13 }}>
                      📅 {new Date(c.slot_start).toLocaleString(undefined, {
                        month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
                      })}
                    </span>
                  ) : ["completed", "withdrawn", "in_progress"].includes(c.status) ? (
                    <span style={{ color: "var(--faint)", fontSize: 13 }}>-</span>
                  ) : (
                    <span style={{ display: "flex", gap: 6, alignItems: "center" }}>
                      <input type="datetime-local" className="notes"
                        style={{ maxWidth: 180, padding: "5px 9px", fontSize: 12 }}
                        value={slotDraft[c.id] ?? ""}
                        onChange={(e) => setSlotDraft((s) => ({ ...s, [c.id]: e.target.value }))} />
                      <button className="mini" onClick={() => schedule(c.id)}
                        disabled={!slotDraft[c.id]}>
                        set
                      </button>
                    </span>
                  )}
                </td>
                <td>
                  <a href={`/candidate/${c.id}`} target="_blank" rel="noreferrer">portal ↗</a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </main>
    </>
  );
}
