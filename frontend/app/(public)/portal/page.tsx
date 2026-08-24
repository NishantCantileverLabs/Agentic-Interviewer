"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Button, ButtonLink, StatusChip } from "../../../components/ui";
import { API, authFetch, logout, useUser } from "../../../lib/auth";
import { toStatus } from "../../../lib/org";

interface MyInterview {
  candidacy_id: string;
  org_name: string;
  source: string;
  role_name: string | null;
  status: string;
  slot_start: string | null;
  session_status: string | null;
  portal_path: string;
}

/** Candidate home: the interviews addressed to this account's email. One
 * press takes them into the guided /i flow. Calm, no scores, no org chrome. */
export default function CandidateHome() {
  const { user, loading } = useUser();
  const [rows, setRows] = useState<MyInterview[] | null>(null);
  const [demoBusy, setDemoBusy] = useState(false);
  const [demoError, setDemoError] = useState<string | null>(null);

  const startDemo = async () => {
    setDemoBusy(true);
    setDemoError(null);
    const r = await authFetch(`${API}/auth/demo`, { method: "POST" });
    if (r.ok) {
      const data = (await r.json()) as { portal_path: string };
      window.location.assign(data.portal_path);
    } else {
      setDemoError(
        r.status === 409
          ? "You've used all your practice interviews."
          : "Could not start a practice interview — try again.",
      );
      setDemoBusy(false);
    }
  };

  useEffect(() => {
    if (loading) return;
    if (!user) {
      window.location.assign("/login");
      return;
    }
    if (user.account_type !== "candidate") {
      window.location.assign("/dashboard");
      return;
    }
    authFetch(`${API}/auth/me/interviews`)
      .then(async (r: Response) => setRows(r.ok ? ((await r.json()) as MyInterview[]) : []))
      .catch(() => setRows([]));
  }, [user, loading]);

  if (loading || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-paper text-muted">
        Loading your interviews…
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-paper">
      <header className="border-b border-line bg-panel">
        <div className="mx-auto flex h-14 max-w-[720px] items-center gap-3 px-5">
          <Link href="/" className="flex items-center gap-2.5 font-display text-md font-semibold text-ink">
            <span aria-hidden className="h-5 w-5 rounded-sm bg-accent" />
            AI Interview
          </Link>
          <div className="ml-auto flex items-center gap-3">
            <span className="hidden font-mono text-xs text-muted sm:block">{user.email}</span>
            <Button size="sm" variant="ghost" onClick={logout}>
              Log out
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[720px] px-5 py-8">
        <h1 className="font-display text-xl font-semibold text-ink">
          Hi {user.name?.split(" ")[0] ?? "there"}
        </h1>
        <p className="mt-1 text-base text-muted">
          Your interviews appear here as recruiters invite you.
        </p>

        <div className="mt-6 flex flex-col gap-3">
          {rows === null && (
            <div className="rounded-lg border border-line bg-panel p-5 text-muted" aria-busy="true">
              Checking for interviews addressed to {user.email}…
            </div>
          )}
          {rows !== null && rows.length === 0 && (
            <div className="rounded-lg border border-line bg-panel p-6 text-center">
              <p className="font-medium text-ink">No interviews yet</p>
              <p className="mt-1 text-sm text-muted">
                Invitations sent to <b>{user.email}</b> will appear here.
              </p>
            </div>
          )}
          {rows?.map((r) => {
            const done = ["completed", "in_review", "reviewed"].includes(r.status);
            const slot = r.slot_start ? new Date(r.slot_start) : null;
            return (
              <div
                key={r.candidacy_id}
                className="flex flex-wrap items-center gap-4 rounded-lg border border-line bg-panel p-4"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-display text-md font-semibold text-ink">
                      {r.role_name ?? (r.source === "demo" ? "Practice interview" : "Interview")}
                    </span>
                    <StatusChip status={toStatus({ status: r.status })} />
                  </div>
                  <div className="mt-1 text-sm text-muted">
                    {r.org_name}
                    {slot && (
                      <>
                        {" · "}
                        <span className="font-mono">
                          {slot.toLocaleString(undefined, {
                            weekday: "short",
                            month: "short",
                            day: "numeric",
                            hour: "2-digit",
                            minute: "2-digit",
                          })}
                        </span>
                      </>
                    )}
                  </div>
                </div>
                <div className="shrink-0">
                  {done ? (
                    <span className="text-sm text-muted">
                      Done — the team will be in touch
                    </span>
                  ) : r.status === "withdrawn" ? (
                    <span className="text-sm text-muted">Withdrawn</span>
                  ) : (
                    <ButtonLink href={`/i/${r.candidacy_id}`}>
                      {r.status === "in_progress" ? "Rejoin" : "Start"}
                    </ButtonLink>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        <div className="mt-8 rounded-lg border border-dashed border-line bg-panel p-4">
          <div className="flex flex-wrap items-center gap-4">
            <div className="min-w-0 flex-1">
              <div className="font-display text-md font-semibold text-ink">
                Try a practice interview
              </div>
              <p className="mt-0.5 text-sm text-muted">
                Ten minutes with the AI interviewer — no stakes, nothing shared.
              </p>
            </div>
            <Button variant="secondary" onClick={startDemo} loading={demoBusy}>
              Start practice
            </Button>
          </div>
          {demoError && (
            <p role="alert" className="mt-2 text-sm text-rust">
              {demoError}
            </p>
          )}
        </div>

        <p className="mt-8 text-sm text-muted">
          Questions? Contact the team that invited you.
        </p>
      </main>
    </div>
  );
}
