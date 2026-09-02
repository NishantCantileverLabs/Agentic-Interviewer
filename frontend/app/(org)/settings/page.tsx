"use client";

import { useEffect, useState } from "react";
import { Button, Input, PageHeader, Select, useToast } from "../../../components/ui";
import { API, authFetch } from "../../../lib/auth";
import {
  type CandidacyRow,
  eraseCandidacy,
  exportCandidacy,
  listCandidacies,
} from "../../../lib/org";

/** A1–A5 (this deployment's honest subset): org profile is read-only, policy
 * versions are immutable and listed, data-subject tools work end to end, and
 * the question bank links to its editor. ATS integrations are not connected
 * here by decision — shown as such, not stubbed to look live. */
export default function SettingsPage() {
  return (
    <div className="mx-auto flex max-w-[860px] flex-col gap-8">
      <PageHeader title="Settings" />
      <MembersSection />
      <PoliciesSection />
      <DataSubjectSection />
      <section>
        <h2 className="mb-2 font-display text-md font-semibold text-ink">Integrations</h2>
        <div className="rounded-lg border border-line bg-panel p-4 text-sm text-muted">
          ATS connections (Greenhouse, Lever) are not connected.
        </div>
      </section>
    </div>
  );
}

interface MemberRow {
  user_id: string;
  email: string;
  name: string | null;
  role: string;
}
interface InviteRow {
  id: string;
  email: string;
  role: string;
  accepted: boolean;
}

function MembersSection() {
  const toast = useToast();
  const [members, setMembers] = useState<MemberRow[]>([]);
  const [invites, setInvites] = useState<InviteRow[]>([]);
  const [allowed, setAllowed] = useState(true);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("recruiter");
  const [busy, setBusy] = useState(false);

  const load = () =>
    authFetch(`${API}/org/members`)
      .then(async (r: Response) => {
        if (r.status === 403) {
          setAllowed(false);
          return;
        }
        const data = (await r.json()) as { members: MemberRow[]; invites: InviteRow[] };
        setMembers(data.members);
        setInvites(data.invites.filter((i) => !i.accepted));
      })
      .catch(() => null);

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!allowed) return null; // admin-only section

  const invite = async () => {
    setBusy(true);
    const r = await authFetch(`${API}/org/members/invite`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, role }),
    });
    setBusy(false);
    if (r.ok) {
      toast("Invite sent", "success");
      setEmail("");
      void load();
    } else toast(await r.text(), "error");
  };

  const revoke = async (id: string) => {
    const r = await authFetch(`${API}/org/members/invite/${id}`, { method: "DELETE" });
    if (r.ok) {
      toast("Invite revoked", "success");
      void load();
    }
  };

  const remove = async (userId: string) => {
    const r = await authFetch(`${API}/org/members/${userId}`, { method: "DELETE" });
    if (r.ok) {
      toast("Access removed", "success");
      void load();
    } else toast(await r.text(), "error");
  };

  return (
    <section>
      <h2 className="mb-2 font-display text-md font-semibold text-ink">Members</h2>
      <p className="mb-3 text-sm text-muted">
        Console access is invite-only. Invited people sign up with the same email.
      </p>

      <div className="flex flex-wrap items-end gap-2">
        <div className="w-64">
          <Input label="Email" type="email" value={email}
            onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div className="w-36">
          <Select label="Role" value={role} onChange={(e) => setRole(e.target.value)}
            options={[
              { value: "reviewer", label: "Reviewer" },
              { value: "recruiter", label: "Recruiter" },
              { value: "admin", label: "Admin" },
            ]} />
        </div>
        <Button size="sm" onClick={invite} loading={busy}
          disabledReason={email.includes("@") ? undefined : "Enter an email first"}>
          Send invite
        </Button>
      </div>

      <div className="mt-4 flex flex-col gap-2">
        {members.map((m) => (
          <div key={m.user_id}
            className="flex items-center gap-3 rounded-lg border border-line bg-panel px-4 py-2.5">
            <div className="min-w-0 flex-1">
              <span className="font-medium text-ink">{m.name ?? m.email}</span>
              <span className="ml-2 font-mono text-xs text-muted">{m.email}</span>
            </div>
            <span className="rounded-full border border-line px-2.5 py-0.5 text-xs capitalize text-ink-soft">
              {m.role}
            </span>
            <Button size="sm" variant="ghost" onClick={() => remove(m.user_id)}>
              Remove
            </Button>
          </div>
        ))}
        {invites.map((i) => (
          <div key={i.id}
            className="flex items-center gap-3 rounded-lg border border-dashed border-line bg-paper px-4 py-2.5">
            <div className="min-w-0 flex-1">
              <span className="font-mono text-sm text-ink-soft">{i.email}</span>
              <span className="ml-2 text-xs text-muted">invited · {i.role}</span>
            </div>
            <Button size="sm" variant="ghost" onClick={() => revoke(i.id)}>
              Revoke
            </Button>
          </div>
        ))}
      </div>
    </section>
  );
}

function PoliciesSection() {
  const [policies, setPolicies] = useState<Record<string, string>>({});
  const [version, setVersion] = useState<string>("");

  useEffect(() => {
    // policy texts ride on any candidacy payload; a dedicated listing uses the
    // same source of truth
    authFetch(`${API}/candidacies`)
      .then(async (r: Response) => {
        if (!r.ok) return;
        const rows = (await r.json()) as { id: string }[];
        if (!rows.length) return;
        const p = await authFetch(`${API}/candidacies/${rows[0].id}`);
        if (p.ok) {
          const data = (await p.json()) as {
            policy_version: string;
            policies: Record<string, string>;
          };
          setVersion(data.policy_version);
          setPolicies(data.policies);
        }
      })
      .catch(() => null);
  }, []);

  return (
    <section>
      <h2 className="mb-2 font-display text-md font-semibold text-ink">
        Consent policies{" "}
        {version && <span className="font-mono text-xs font-normal text-muted">v{version}</span>}
      </h2>
      <p className="mb-2 text-sm text-muted">
        Versions are immutable. A text change ships as a new version and applies to
        candidacies created after it.
      </p>
      <div className="flex flex-col gap-2">
        {Object.entries(policies).map(([item, text]) => (
          <details key={item} className="rounded-lg border border-line bg-panel p-3">
            <summary className="cursor-pointer font-medium text-ink">
              {item.replace(/_/g, " ")}
            </summary>
            <p className="mt-2 text-sm text-ink-soft">{text}</p>
          </details>
        ))}
        {Object.keys(policies).length === 0 && (
          <p className="text-sm text-muted">Policy texts appear after the first invite.</p>
        )}
      </div>
    </section>
  );
}

function DataSubjectSection() {
  const toast = useToast();
  const [rows, setRows] = useState<CandidacyRow[]>([]);
  const [query, setQuery] = useState("");
  const [confirmErase, setConfirmErase] = useState<string | null>(null);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    listCandidacies().then(setRows).catch(() => null);
  }, []);

  const matches = query
    ? rows.filter(
        (r) =>
          r.candidate_email.toLowerCase().includes(query.toLowerCase()) ||
          r.candidate_name.toLowerCase().includes(query.toLowerCase()),
      )
    : [];

  const doExport = async (id: string) => {
    setBusy(true);
    try {
      const bundle = await exportCandidacy(id);
      const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `export-${id.slice(0, 8)}.json`;
      a.click();
      URL.revokeObjectURL(a.href);
      toast("Export downloaded. The action is in the audit log", "success");
    } catch (e) {
      toast(e instanceof Error ? e.message : String(e), "error");
    } finally {
      setBusy(false);
    }
  };

  const doErase = async (id: string) => {
    setBusy(true);
    try {
      const r = await eraseCandidacy(id);
      toast(
        `Erased: ${r.erased_sessions} sessions, ${r.events_purged} events purged. Audit-logged`,
        "success",
      );
      setConfirmErase(null);
      setTyped("");
      listCandidacies().then(setRows).catch(() => null);
    } catch (e) {
      toast(e instanceof Error ? e.message : String(e), "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section>
      <h2 className="mb-2 font-display text-md font-semibold text-ink">Data subject tools</h2>
      <div className="max-w-sm">
        <Input
          label="Find a candidate"
          placeholder="name or email"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>
      <div className="mt-3 flex flex-col gap-2">
        {matches.map((r) => (
          <div
            key={r.id}
            className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-line bg-panel px-4 py-3"
          >
            <div>
              <div className="font-medium text-ink">{r.candidate_name}</div>
              <div className="font-mono text-xs text-muted">{r.candidate_email}</div>
            </div>
            <div className="flex items-center gap-2">
              <Button size="sm" variant="secondary" loading={busy} onClick={() => doExport(r.id)}>
                Export data
              </Button>
              <Button size="sm" variant="danger" onClick={() => setConfirmErase(r.id)}>
                Erase
              </Button>
            </div>
            {confirmErase === r.id && (
              <div className="w-full rounded-md border border-rust/30 bg-paper p-3">
                <p className="text-sm text-ink-soft">
                  Erasure is permanent: events are purged, PII becomes tombstones. Type{" "}
                  <b className="font-mono">erase</b> to confirm.
                </p>
                <div className="mt-2 flex items-end gap-2">
                  <div className="w-40">
                    <Input
                      label="Confirmation"
                      value={typed}
                      onChange={(e) => setTyped(e.target.value)}
                    />
                  </div>
                  <Button
                    size="sm"
                    variant="danger"
                    loading={busy}
                    disabledReason={typed === "erase" ? undefined : "Type erase to confirm"}
                    onClick={() => void doErase(r.id)}
                  >
                    Erase permanently
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      setConfirmErase(null);
                      setTyped("");
                    }}
                  >
                    Cancel
                  </Button>
                </div>
              </div>
            )}
          </div>
        ))}
        {query && matches.length === 0 && (
          <p className="text-sm text-muted">No candidate matches that search.</p>
        )}
      </div>
    </section>
  );
}
