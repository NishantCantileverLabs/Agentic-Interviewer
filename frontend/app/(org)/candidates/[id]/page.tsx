"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import {
  AuthFrame,
  Button,
  ButtonLink,
  StatusChip,
  Tabs,
  Timeline,
  useToast,
} from "../../../../components/ui";
import { useVisibility } from "../../../../lib/visibility";
import { API } from "../../../../lib/auth";
import { authFetch } from "../../../../lib/auth";
import { type TimelineDetail, getTimeline, toStatus } from "../../../../lib/org";

/** R6 — Candidacy detail: the event log made human-readable. Action bar is
 * driven entirely by useVisibility (§7); every locked action names why. */
export default function CandidacyDetailPage() {
  const { id } = useParams<{ id: string }>();
  const toast = useToast();
  const [detail, setDetail] = useState<TimelineDetail | null>(null);
  const [tab, setTab] = useState("rounds");
  const [error, setError] = useState<string | null>(null);

  const load = () =>
    getTimeline(id)
      .then(setDetail)
      .catch((e) => setError(String(e.message ?? e)));

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  if (error) {
    return (
      <p role="alert" className="text-rust">
        Could not load this candidacy: {error}
      </p>
    );
  }
  if (!detail) {
    return <p className="text-muted" aria-busy="true">Loading the candidacy record…</p>;
  }

  const status = toStatus({
    status: detail.status,
    has_brief: detail.sessions.some((s) => s.has_brief),
  });
  const vis = useVisibilitySafe(status);
  const briefSession = detail.sessions.filter((s) => s.has_brief).at(-1);

  const withdraw = async () => {
    const resp = await authFetch(`${API}/candidacies/${id}/decline`, { method: "POST" });
    if (resp.ok) {
      toast("Candidate withdrawn", "success");
      void load();
    } else toast("Could not withdraw. Try again", "error");
  };

  return (
    <div className="mx-auto max-w-[1100px]">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="font-display text-xl font-semibold text-ink">
          {detail.candidate_name}
        </h1>
        <StatusChip status={status} />
        {detail.role_name && (
          <span className="rounded-full border border-line px-2.5 py-0.5 text-xs text-ink-soft">
            {detail.role_name}
          </span>
        )}
        <span className="font-mono text-xs text-muted">{detail.candidate_email}</span>
      </div>

      {/* action bar. §7 */}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {vis.actions.locked ? (
          <Button variant="secondary" size="sm" disabledReason={vis.actions.lockReason}>
            Actions locked
          </Button>
        ) : (
          <>
            {vis.actions.remind && (
              <Button variant="secondary" size="sm" onClick={() => toast("Reminder sent", "success")}>
                Send reminder
              </Button>
            )}
            {vis.actions.withdraw && (
              <Button variant="secondary" size="sm" onClick={withdraw}>
                Withdraw
              </Button>
            )}
            {vis.actions.sync && (
              <Button
                variant="secondary"
                size="sm"
                disabledReason="ATS integration is not connected in this deployment"
              >
                Sync to ATS
              </Button>
            )}
            {vis.actions.sendToReview && (
              <ButtonLink href="/review" variant="secondary" size="sm">
                Open review queue
              </ButtonLink>
            )}
          </>
        )}
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-[300px_1fr]">
        {/* lifecycle timeline */}
        <section>
          <h2 className="mb-3 font-display text-md font-semibold text-ink">Timeline</h2>
          <Timeline
            events={detail.events.map((e, i) => ({
              id: String(i),
              at: new Date(e.at).toLocaleString(undefined, {
                month: "short",
                day: "numeric",
                hour: "2-digit",
                minute: "2-digit",
              }),
              label: e.label,
              detail: e.detail,
              tone: e.label.startsWith("Interview") ? "accent" : "default",
            }))}
          />
          {detail.events.length === 0 && (
            <p className="text-sm text-muted">No activity yet.</p>
          )}
        </section>

        {/* tabs */}
        <section>
          <Tabs
            tabs={[
              { id: "rounds", label: "Rounds", count: detail.sessions.length },
              { id: "brief", label: "Brief" },
            ]}
            active={tab}
            onChange={setTab}
          />
          {tab === "rounds" && (
            <div className="mt-4 flex flex-col gap-2">
              {detail.sessions.length === 0 && (
                <p className="text-muted">
                  No interviews yet. The candidate has not started.
                </p>
              )}
              {detail.sessions.map((s, i) => (
                <Link
                  key={s.id}
                  href={`/sessions/${s.id}`}
                  className="flex items-center justify-between rounded-lg border border-line bg-panel px-4 py-3 hover:border-accent"
                >
                  <div>
                    <div className="font-medium capitalize text-ink">
                      Round {i + 1} · {(s.round_type ?? "full interview").replace(/_/g, " ")}
                    </div>
                    <div className="mt-0.5 font-mono text-xs text-muted">
                      {new Date(s.created_at).toLocaleString()} · {s.status}
                      {s.has_brief ? " · brief ready" : ""}
                    </div>
                  </div>
                  <span aria-hidden className="text-muted">→</span>
                </Link>
              ))}
            </div>
          )}
          {tab === "brief" && (
            <div className="mt-4">
              {briefSession ? (
                <AuthFrame
                  url={`${API}/sessions/${briefSession.id}/brief.html`}
                  title="Decision brief"
                  className="h-[70vh] w-full rounded-lg border border-line bg-white"
                />
              ) : (
                <p className="text-muted">
                  The brief appears here a couple of minutes after an interview completes.
                </p>
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

/** hook-order-safe wrapper (status arrives async) */
function useVisibilitySafe(status: Parameters<typeof useVisibility>[0]) {
  return useVisibility(status);
}
