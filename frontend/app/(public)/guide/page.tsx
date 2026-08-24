"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ButtonLink } from "../../../components/ui";
import { API, authFetch, getToken } from "../../../lib/auth";

/** Platform guide — the client-facing overview. Live figures load when a
 * logged-in viewer opens it; anonymous viewers see the engineering budgets. */

interface LatencySession {
  turns: number;
  p50_ms: number;
  p95_ms: number;
  stage_p50_ms: { llm_ttft: number | null };
}

interface Live {
  p50: number | null;
  p95: number | null;
  ttft: number | null;
  sessions: number | null;
}

const STEPS = [
  { n: "01", label: "Create a role", body: "Attach the interview it runs — one session or a multi-round pipeline." },
  { n: "02", label: "Invite", body: "Candidates schedule, consent, and join from one link." },
  { n: "03", label: "AI interviews", body: "Voice conversation with live coding, SQL, case, and design rounds." },
  { n: "04", label: "Evidence, then people", body: "Cited scores; borderline results go to your review queue." },
];

const FEATURES = [
  ["Live voice interviewer", "Real-time speech with fallbacks — candidates always know they've been heard."],
  ["Real working tools", "Collaborative editor with sandboxed tests, exhibits, scratchpad, whiteboard."],
  ["Numbers checked by code", "SQL re-executed, math verified — never graded by a model."],
  ["Cited evaluations", "Every score links to the exact moment behind it."],
  ["Full replay", "Transcript, code, and events — any moment reconstructed."],
  ["Human review", "Overrides need written rationale; nothing auto-rejects."],
  ["Calibration first", "AI scores stay in shadow mode until they match your reviewers."],
  ["Privacy built in", "Tenant isolation, enforced consent, one-call export or erase."],
];

export default function GuidePage() {
  const [live, setLive] = useState<Live>({ p50: null, p95: null, ttft: null, sessions: null });

  useEffect(() => {
    if (!getToken()) return; // anonymous viewers see budgets only
    authFetch(`${API}/metrics/latency`)
      .then(async (r: Response) => {
        if (!r.ok) return;
        const data = (await r.json()) as { sessions: LatencySession[] };
        const rows = data.sessions.filter((s) => s.turns >= 3);
        const med = (xs: number[]) =>
          xs.length ? [...xs].sort((a, b) => a - b)[Math.floor(xs.length / 2)] : null;
        setLive((l) => ({
          ...l,
          p50: med(rows.map((s) => s.p50_ms)),
          p95: med(rows.map((s) => s.p95_ms)),
          ttft: med(rows.map((s) => s.stage_p50_ms.llm_ttft).filter((v): v is number => v != null)),
        }));
      })
      .catch(() => undefined);
    authFetch(`${API}/sessions`)
      .then(async (r: Response) => {
        if (!r.ok) return;
        const rows = (await r.json()) as unknown[];
        setLive((l) => ({ ...l, sessions: rows.length }));
      })
      .catch(() => undefined);
  }, []);

  const s = (v: number | null) => (v == null ? null : `${(v / 1000).toFixed(2)}s`);

  return (
    <div className="min-h-screen bg-paper text-ink">
      <header className="sticky top-0 z-40 border-b border-line bg-paper/95 backdrop-blur">
        <nav className="mx-auto flex h-14 max-w-[1080px] items-center gap-6 px-5">
          <Link href="/" className="flex items-center gap-2.5 font-display text-md font-semibold">
            <span aria-hidden className="h-5 w-5 rounded-sm bg-accent" />
            AI Interview
          </Link>
          <span className="text-base text-muted">Platform guide</span>
          <div className="ml-auto">
            <ButtonLink href="/login" variant="secondary" size="sm">
              Log in
            </ButtonLink>
          </div>
        </nav>
      </header>

      <main className="mx-auto max-w-[1080px] px-5 pb-14">
        <section className="pt-12">
          <h1 className="max-w-[640px] font-display text-2xl font-semibold leading-tight">
            Structured interviews with a voice AI — reviewed by people, backed by evidence.
          </h1>
        </section>

        {/* stat band */}
        <section className="mt-8 grid gap-px overflow-hidden rounded-lg border border-line bg-line sm:grid-cols-2 lg:grid-cols-4">
          <Stat big="≤ 0.8s" label="voice response, median" cap={live.p50 ? `measured here: ${s(live.p50)}` : "engineering budget"} />
          <Stat big="≤ 1.5s" label="voice response, p95" cap={live.p95 ? `measured here: ${s(live.p95)}` : "engineering budget"} />
          <Stat big={s(live.ttft) ?? "2"} label={live.ttft ? "AI first token, median" : "AI models per interview"} cap={live.ttft ? "live" : "conductor + evaluator"} />
          <Stat big={live.sessions != null ? String(live.sessions) : "10"} label={live.sessions != null ? "interviews on this deployment" : "round types"} cap={live.sessions != null ? "live" : "coding · SQL · case · design …"} />
        </section>

        {/* how it works */}
        <section className="mt-12">
          <h2 className="font-display text-lg font-semibold">How it works</h2>
          <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {STEPS.map((st) => (
              <div key={st.n} className="rounded-lg border border-line bg-panel p-4">
                <div className="font-mono text-xs text-accent">{st.n}</div>
                <div className="mt-1 font-display text-md font-semibold">{st.label}</div>
                <p className="mt-1 text-sm leading-relaxed text-muted">{st.body}</p>
              </div>
            ))}
          </div>
        </section>

        {/* features */}
        <section className="mt-12">
          <h2 className="font-display text-lg font-semibold">What&apos;s inside</h2>
          <div className="mt-4 grid gap-px overflow-hidden rounded-lg border border-line bg-line sm:grid-cols-2">
            {FEATURES.map(([k, v]) => (
              <div key={k} className="bg-panel p-4">
                <div className="text-base font-semibold text-ink">{k}</div>
                <p className="mt-0.5 text-sm text-muted">{v}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="mt-12 flex flex-wrap items-center gap-3">
          <ButtonLink href="/login">Open the console</ButtonLink>
          <Link href="/" className="text-base text-muted underline-offset-4 hover:text-ink hover:underline">
            Back to overview
          </Link>
        </section>
      </main>
    </div>
  );
}

function Stat({ big, label, cap }: { big: string; label: string; cap: string }) {
  return (
    <div className="bg-panel p-5">
      <div className="font-display text-2xl font-semibold tabular-nums text-ink">{big}</div>
      <div className="mt-1 text-sm font-medium text-ink-soft">{label}</div>
      <div className="mt-0.5 font-mono text-xs text-muted">{cap}</div>
    </div>
  );
}
