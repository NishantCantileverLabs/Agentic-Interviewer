"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Button, Input, KpiCard, Modal, PageHeader, Select, useToast } from "../../../components/ui";
import {
  type HiringStats,
  type JobRoleRow,
  type QueueItem,
  type SessionRow,
  hiringStats,
  inviteCandidate,
  listJobRoles,
  listSessions,
  reviewQueue,
} from "../../../lib/org";

const WEEK_MS = 7 * 24 * 3600 * 1000;

/** R1 — Dashboard: KPI row, per-role funnel cards (counts link into the
 * filtered list), attention list, global invite. */
export default function DashboardPage() {
  const [sessions, setSessions] = useState<SessionRow[] | null>(null);
  const [stats, setStats] = useState<HiringStats | null>(null);
  const [queue, setQueue] = useState<QueueItem[] | null>(null);
  const [roles, setRoles] = useState<JobRoleRow[]>([]);
  const [inviteOpen, setInviteOpen] = useState(false);

  useEffect(() => {
    listSessions().then(setSessions).catch(() => setSessions([]));
    hiringStats().then(setStats).catch(() => null);
    reviewQueue().then(setQueue).catch(() => setQueue([]));
    listJobRoles().then(setRoles).catch(() => null);
  }, []);

  const thisWeek =
    sessions?.filter((s) => Date.now() - new Date(s.created_at).getTime() < WEEK_MS) ?? [];
  const completed = sessions?.filter((s) => s.status === "completed") ?? [];
  const completionRate =
    sessions && sessions.length > 0
      ? Math.round((completed.length / sessions.length) * 100)
      : null;
  const briefsReady = sessions?.filter((s) => s.briefs > 0).length ?? 0;

  return (
    <div className="mx-auto max-w-[1100px]">
      <PageHeader
        title="Dashboard"
        actions={<Button onClick={() => setInviteOpen(true)}>Invite candidates</Button>}
      />

      <div className="mt-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <KpiCard label="interview sessions this week" value={sessions ? thisWeek.length : "—"} />
        <KpiCard
          label="session completion rate (all-time)"
          value={completionRate ?? "—"}
          unit={completionRate === null ? undefined : "%"}
        />
        <KpiCard
          label="awaiting review"
          value={queue ? queue.length : "—"}
          href="/review"
          tone={queue && queue.length > 0 ? "attention" : "default"}
        />
        <KpiCard label="candidates interviewed" value={stats?.interviewed ?? "—"} />
      </div>

      {/* attention list */}
      <section className="mt-6">
        <h2 className="mb-2 font-display text-md font-semibold text-ink">Needs attention</h2>
        <div className="flex flex-col gap-2">
          {queue && queue.length > 0 && (
            <Link
              href="/review"
              className="flex items-center justify-between rounded-lg border border-amber/40 bg-panel px-4 py-3 hover:border-amber"
            >
              <span className="text-base text-ink">
                Needs review <b>({queue.length})</b> — oldest first
              </span>
              <span aria-hidden className="text-muted">→</span>
            </Link>
          )}
          {briefsReady > 0 && (
            <Link
              href="/candidates"
              className="flex items-center justify-between rounded-lg border border-line bg-panel px-4 py-3 hover:border-accent"
            >
              <span className="text-base text-ink">
                Briefs ready <b>({briefsReady})</b>
              </span>
              <span aria-hidden className="text-muted">→</span>
            </Link>
          )}
          {(!queue || queue.length === 0) && briefsReady === 0 && (
            <div className="rounded-lg border border-line bg-panel px-4 py-3 text-muted">
              Nothing waiting on you — invite candidates or check the funnel below.
            </div>
          )}
        </div>
      </section>

      {/* per-role funnels */}
      <section className="mt-6">
        <h2 className="mb-2 font-display text-md font-semibold text-ink">Roles</h2>
        {stats && stats.by_role.length === 0 && (
          <div className="rounded-lg border border-line bg-panel p-5 text-muted">
            No roles yet — create one under Roles, then invite candidates into it.
          </div>
        )}
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {stats?.by_role.map((r) => (
            <div key={r.role_id} className="rounded-lg border border-line bg-panel p-4">
              <div className="font-medium text-ink">{r.role_name}</div>
              <div className="mt-3 flex items-center gap-2 font-mono text-sm">
                <FunnelStage label="invited" count={r.invited} href={`/candidates?role=${r.role_id}`} />
                <span aria-hidden className="text-line">—</span>
                <FunnelStage
                  label="interviewed"
                  count={r.interviewed}
                  href={`/candidates?role=${r.role_id}&status=completed`}
                />
              </div>
            </div>
          ))}
        </div>
      </section>

      <InviteModal
        open={inviteOpen}
        onClose={() => setInviteOpen(false)}
        roles={roles}
      />
    </div>
  );
}

function FunnelStage({ label, count, href }: { label: string; count: number; href: string }) {
  return (
    <Link href={href} className="rounded-md px-2 py-1 hover:bg-accent-tint">
      <span className="text-lg font-semibold text-ink">{count}</span>{" "}
      <span className="text-muted">{label}</span>
    </Link>
  );
}

function InviteModal({
  open,
  onClose,
  roles,
}: {
  open: boolean;
  onClose: () => void;
  roles: JobRoleRow[];
}) {
  const toast = useToast();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [roleId, setRoleId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const send = async () => {
    setBusy(true);
    setError(null);
    try {
      await inviteCandidate({
        candidate_name: name,
        candidate_email: email,
        ...(roleId ? { job_role_id: roleId } : {}),
      });
      toast("Invite sent", "success");
      setName("");
      setEmail("");
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Invite candidates"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            onClick={send}
            loading={busy}
            disabledReason={name && email ? undefined : "Name and email are needed first"}
          >
            Send invite
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <Input label="Candidate name" value={name} onChange={(e) => setName(e.target.value)} />
        <Input
          label="Email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <Select
          label="Role"
          value={roleId}
          onChange={(e) => setRoleId(e.target.value)}
          options={[
            { value: "", label: "No role (default interview)" },
            ...roles.map((r) => ({ value: r.id, label: r.name })),
          ]}
          hint="The role decides which interview the candidate gets"
        />
        {error && (
          <p role="alert" className="text-sm text-rust">
            {error}
          </p>
        )}
      </div>
    </Modal>
  );
}
