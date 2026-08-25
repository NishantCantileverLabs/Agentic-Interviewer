"use client";

import { useParams, useRouter, useSearchParams } from "next/navigation";
import {
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  AuthFrame,
  Button,
  EvidenceChip,
  Tabs,
  useToast,
} from "../../../../components/ui";
import { cx } from "../../../../lib/cx";
import { API } from "../../../../lib/auth";
import {
  type EvaluationView,
  type QueueItem,
  type ReplayEvent,
  codeAt,
  reviewQueue,
  sessionEvaluation,
  sessionReplay,
  submitDecision,
} from "../../../../lib/org";

/** R9. Session view: Brief | Replay | Evaluation, plus the review-mode
 * decision panel (F8). Replay synchronizes transcript, reconstructed code,
 * and the event rail over the event-log timeline. (This deployment records
 * no audio, so the scrubber is time-based rather than waveform-based. The
 * two-click promise from evidence to moment is unchanged.) */
export default function SessionViewPage() {
  return (
    <Suspense>
      <SessionViewInner />
    </Suspense>
  );
}

function SessionViewInner() {
  const { id } = useParams<{ id: string }>();
  const search = useSearchParams();
  const reviewMode = search.get("mode") === "review";
  const [tab, setTab] = useState(reviewMode ? "evaluation" : "brief");
  const [events, setEvents] = useState<ReplayEvent[] | null>(null);
  const [evaluation, setEvaluation] = useState<EvaluationView | null>(null);
  const [evalMissing, setEvalMissing] = useState(false);
  const [playhead, setPlayhead] = useState<number>(0);

  useEffect(() => {
    sessionReplay(id)
      .then((evs) => {
        setEvents(evs);
        if (evs.length) setPlayhead(new Date(evs[0].ts).getTime());
      })
      .catch(() => setEvents([]));
    sessionEvaluation(id)
      .then(setEvaluation)
      .catch(() => setEvalMissing(true));
  }, [id]);

  const seekToSeq = useCallback(
    (seq: number) => {
      const ev = events?.find((e) => e.seq === seq);
      if (ev) {
        setPlayhead(new Date(ev.ts).getTime());
        setTab("replay");
      }
    },
    [events],
  );

  return (
    <div className={cx("mx-auto", reviewMode ? "max-w-[1280px]" : "max-w-[1100px]")}>
      <div className="flex items-center gap-3">
        <h1 className="font-display text-xl font-semibold text-ink">Session</h1>
        <span className="font-mono text-xs text-muted">{id.slice(0, 8)}</span>
        {reviewMode && (
          <span className="rounded-full border border-violet/30 bg-panel px-2.5 py-0.5 text-xs font-medium text-violet">
            review mode
          </span>
        )}
      </div>

      <div className={cx("mt-4 grid gap-5", reviewMode && "lg:grid-cols-[1fr_320px]")}>
        <div className="min-w-0">
          <Tabs
            tabs={[
              { id: "brief", label: "Brief" },
              { id: "replay", label: "Replay" },
              { id: "evaluation", label: "Evaluation" },
            ]}
            active={tab}
            onChange={setTab}
          />

          {tab === "brief" && (
            <div className="mt-4">
              <AuthFrame
                url={`${API}/sessions/${id}/brief.html`}
                title="Decision brief"
                className="h-[72vh] w-full rounded-lg border border-line bg-white"
                pendingText="The brief appears a few minutes after the interview ends."
              />
            </div>
          )}

          {tab === "replay" &&
            (events === null ? (
              <p className="mt-4 text-muted" aria-busy="true">
                Loading the event stream. Long sessions take a few seconds.
              </p>
            ) : events.length === 0 ? (
              <p className="mt-4 text-muted">No events recorded for this session.</p>
            ) : (
              <ReplayPane
                sessionId={id}
                events={events}
                playhead={playhead}
                setPlayhead={setPlayhead}
              />
            ))}

          {tab === "evaluation" && (
            <EvaluationPane
              evaluation={evaluation}
              missing={evalMissing}
              onSeek={seekToSeq}
            />
          )}
        </div>

        {reviewMode && <DecisionPanel sessionId={id} />}
      </div>
    </div>
  );
}

// ── Replay: scrubber + three synchronized panes ─────────────────────

const MARKED_TYPES: Record<string, string> = {
  run_clicked: "run",
  paste: "paste",
  state_transition: "phase",
  exhibit_revealed: "exhibit",
  sql_executed: "sql",
  round_handoff: "round",
};

function ReplayPane({
  sessionId,
  events,
  playhead,
  setPlayhead,
}: {
  sessionId: string;
  events: ReplayEvent[];
  playhead: number;
  setPlayhead: (t: number) => void;
}) {
  const t0 = new Date(events[0].ts).getTime();
  const tEnd = new Date(events[events.length - 1].ts).getTime();
  const span = Math.max(1, tEnd - t0);

  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [code, setCode] = useState<string>("");
  const codeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const transcriptRef = useRef<HTMLDivElement>(null);

  const transcript = useMemo(
    () =>
      events.filter(
        (e) =>
          (e.type === "stt_final" || e.type === "agent_turn") &&
          typeof e.payload.text === "string" &&
          (e.payload.text as string).length > 0,
      ),
    [events],
  );
  const markers = useMemo(
    () => events.filter((e) => e.type in MARKED_TYPES),
    [events],
  );

  // playback clock
  useEffect(() => {
    if (!playing) return;
    const tick = setInterval(() => {
      const next = playhead + 500 * speed;
      if (next >= tEnd) {
        setPlayhead(tEnd);
        setPlaying(false);
      } else setPlayhead(next);
    }, 500);
    return () => clearInterval(tick);
  }, [playing, playhead, speed, tEnd, setPlayhead]);

  // keyboard: space play/pause, arrows scrub ±5s
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (target.tagName === "INPUT" || target.tagName === "TEXTAREA") return;
      if (e.code === "Space") {
        e.preventDefault();
        setPlaying((p) => !p);
      } else if (e.code === "ArrowRight") {
        setPlayhead(Math.min(tEnd, playhead + 5000));
      } else if (e.code === "ArrowLeft") {
        setPlayhead(Math.max(t0, playhead - 5000));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [playhead, t0, tEnd, setPlayhead]);

  // reconstructed code at the playhead (debounced; backwards seeks re-fetch)
  useEffect(() => {
    if (codeTimer.current) clearTimeout(codeTimer.current);
    codeTimer.current = setTimeout(() => {
      codeAt(sessionId, new Date(playhead).toISOString())
        .then((r) => setCode(r.code ?? ""))
        .catch(() => undefined);
    }, 300);
  }, [playhead, sessionId]);

  // keep the current transcript line in view
  const currentIdx = useMemo(() => {
    let idx = -1;
    for (let i = 0; i < transcript.length; i++) {
      if (new Date(transcript[i].ts).getTime() <= playhead) idx = i;
      else break;
    }
    return idx;
  }, [transcript, playhead]);

  useEffect(() => {
    const el = transcriptRef.current?.querySelector<HTMLElement>(
      `[data-idx="${currentIdx}"]`,
    );
    el?.scrollIntoView({ block: "nearest" });
  }, [currentIdx]);

  const fmtClock = (t: number) => {
    const s = Math.max(0, Math.round((t - t0) / 1000));
    return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
  };

  return (
    <div className="mt-4 flex flex-col gap-3">
      {/* scrubber + event rail (the signature element, live) */}
      <div className="rounded-lg border border-line bg-panel p-3">
        <div className="flex items-center gap-3">
          <Button size="sm" variant="secondary" onClick={() => setPlaying((p) => !p)}>
            {playing ? "Pause" : "Play"}
          </Button>
          <select
            aria-label="Playback speed"
            value={speed}
            onChange={(e) => setSpeed(Number(e.target.value))}
            className="rounded-md border border-line bg-panel px-2 py-1 font-mono text-xs"
          >
            {[1, 2, 4, 8].map((s) => (
              <option key={s} value={s}>
                {s}×
              </option>
            ))}
          </select>
          <span className="ml-auto font-mono text-sm tabular-nums text-muted">
            {fmtClock(playhead)} / {fmtClock(tEnd)}
          </span>
        </div>
        <div className="relative mt-3">
          <input
            type="range"
            aria-label="Replay position"
            min={t0}
            max={tEnd}
            value={playhead}
            onChange={(e) => setPlayhead(Number(e.target.value))}
            className="w-full accent-accent"
          />
          <div className="relative mt-1 h-5">
            {markers.map((m) => {
              const left = ((new Date(m.ts).getTime() - t0) / span) * 100;
              return (
                <button
                  key={m.seq}
                  title={`${MARKED_TYPES[m.type]} · ${fmtClock(new Date(m.ts).getTime())}`}
                  aria-label={`Jump to ${MARKED_TYPES[m.type]} at ${fmtClock(new Date(m.ts).getTime())}`}
                  onClick={() => setPlayhead(new Date(m.ts).getTime())}
                  style={{ left: `${left}%` }}
                  className="absolute top-0 h-4 w-1 -translate-x-1/2 rounded-sm bg-accent/70 hover:bg-accent"
                />
              );
            })}
            <div className="absolute inset-x-0 top-4 border-t border-line" />
          </div>
          <p className="mt-1 font-mono text-xs text-muted">
            space to play · arrows to scrub
          </p>
        </div>
      </div>

      {/* synchronized panes */}
      <div className="grid min-h-0 grid-cols-1 gap-3 lg:grid-cols-2">
        <div
          ref={transcriptRef}
          className="h-[46vh] overflow-y-auto rounded-lg border border-line bg-panel p-3"
          role="log"
          aria-label="Transcript"
        >
          {transcript.map((e, i) => {
            const who = e.type === "stt_final" ? "Candidate" : "Interviewer";
            const active = i === currentIdx;
            return (
              <button
                key={e.seq}
                data-idx={i}
                onClick={() => setPlayhead(new Date(e.ts).getTime())}
                className={cx(
                  "block w-full rounded-md px-2 py-1.5 text-left text-sm leading-relaxed",
                  active ? "bg-accent-tint" : "hover:bg-paper",
                  new Date(e.ts).getTime() > playhead && "opacity-45",
                )}
              >
                <span className="mr-2 font-mono text-xs text-muted">
                  {fmtClock(new Date(e.ts).getTime())} {who}
                </span>
                <span className="text-ink">{String(e.payload.text)}</span>
              </button>
            );
          })}
          {transcript.length === 0 && (
            <p className="text-sm text-muted">No spoken turns in this session.</p>
          )}
        </div>

        <div className="h-[46vh] overflow-auto rounded-lg border border-line bg-panel">
          <div className="border-b border-line px-3 py-2 font-mono text-xs text-muted">
            code at {fmtClock(playhead)}
          </div>
          <pre className="p-3 font-mono text-xs leading-relaxed text-ink">
            {code || "(no code at this point)"}
          </pre>
        </div>
      </div>
    </div>
  );
}

// ── Evaluation (audit layer) ────────────────────────────────────────

function EvaluationPane({
  evaluation,
  missing,
  onSeek,
}: {
  evaluation: EvaluationView | null;
  missing: boolean;
  onSeek: (seq: number) => void;
}) {
  if (missing) {
    return (
      <p className="mt-4 text-muted">
        No evaluation yet. It runs automatically when the interview completes.
        If this session finished a while ago, the evaluation may have failed:
        check eval health in Analytics, then re-run it.
      </p>
    );
  }
  if (!evaluation) {
    return <p className="mt-4 text-muted" aria-busy="true">Loading the evaluation…</p>;
  }
  const comps = Object.entries(evaluation.rubric.competencies ?? {});
  return (
    <div className="mt-4 flex flex-col gap-3">
      <p className="font-mono text-xs text-muted">
        model {evaluation.model} · v{evaluation.version} ·{" "}
        {new Date(evaluation.created_at).toLocaleString()}
        {evaluation.rubric.degraded && (
          <span className="ml-2 text-rust">
            degraded: scores need human review
            {evaluation.rubric.degraded_reason
              ? ` (${String(evaluation.rubric.degraded_reason)})`
              : ""}
          </span>
        )}
      </p>
      {comps.length === 0 && <p className="text-muted">The rubric holds no competencies.</p>}
      {comps.map(([name, c]) => (
        <div key={name} className="rounded-lg border border-line bg-panel p-4">
          <div className="flex items-baseline gap-3">
            <span className="font-medium capitalize text-ink">{name.replace(/_/g, " ")}</span>
            <span className="font-display text-lg font-semibold text-ink">
              {typeof c.score_1_to_5 === "number" ? `${c.score_1_to_5}/5` : "unscored"}
            </span>
            {c.confidence && (
              <span className="font-mono text-xs text-muted">confidence {c.confidence}</span>
            )}
          </div>
          {c.rationale && <p className="mt-1.5 text-sm text-ink-soft">{c.rationale}</p>}
          <div className="mt-2 flex flex-wrap gap-1.5">
            {(c.evidence ?? []).map((ev, i) =>
              typeof ev.seq === "number" ? (
                <EvidenceChip
                  key={i}
                  label={ev.quote ?? `event ${ev.seq}`}
                  onSeek={() => onSeek(ev.seq!)}
                />
              ) : (
                <EvidenceChip key={i} label="" missing />
              ),
            )}
            {typeof c.score_1_to_5 === "number" && (c.evidence ?? []).length === 0 && (
              <EvidenceChip label="" missing />
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

// ── F8: decision panel (review mode) ────────────────────────────────

const MIN_RATIONALE = 20;

function DecisionPanel({ sessionId }: { sessionId: string }) {
  const router = useRouter();
  const toast = useToast();
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [rationale, setRationale] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirmKind, setConfirmKind] = useState<"confirm" | "override" | null>(null);

  useEffect(() => {
    reviewQueue().then(setQueue).catch(() => setQueue([]));
  }, []);

  const item = queue.find((q) => q.session_id === sessionId);

  const submit = async (decision: "confirm" | "override") => {
    if (!item) return;
    setBusy(true);
    try {
      await submitDecision(sessionId, { inflow: item.inflow, decision, rationale });
      toast("Decision recorded", "success");
      // advance to the next queue item rather than dumping back to the list
      const rest = queue.filter((q) => q.session_id !== sessionId);
      if (rest.length) router.push(`/sessions/${rest[0].session_id}?mode=review`);
      else router.push("/review");
    } catch (e) {
      toast(e instanceof Error ? e.message : String(e), "error");
      setBusy(false);
      setConfirmKind(null);
    }
  };

  return (
    <aside className="lg:sticky lg:top-4 lg:self-start">
      <div className="rounded-lg border border-violet/30 bg-panel p-4">
        <h2 className="font-display text-md font-semibold text-ink">Decision</h2>
        {item ? (
          <>
            <p className="mt-2 text-sm text-ink-soft">
              <span className="font-mono text-xs uppercase text-violet">{item.inflow}</span>:{" "}
              {item.reason}
            </p>
            {item.signal && (
              <p className="mt-1 font-mono text-xs text-muted">AI signal: {item.signal}</p>
            )}
          </>
        ) : (
          <p className="mt-2 text-sm text-muted">
            This session is not in the queue (already decided, or not flagged).
          </p>
        )}

        <label className="mt-4 block text-sm font-medium text-ink-soft" htmlFor="rationale">
          Rationale{" "}
          <span className="font-normal text-muted">
            (required to override · at least {MIN_RATIONALE} characters)
          </span>
        </label>
        <textarea
          id="rationale"
          value={rationale}
          onChange={(e) => setRationale(e.target.value)}
          rows={4}
          className="mt-1 w-full rounded-md border border-line bg-panel p-2 text-sm text-ink"
          placeholder="What did you see in the replay that the signal missed?"
        />

        <div className="mt-3 flex flex-col gap-2">
          <Button
            onClick={() => setConfirmKind("confirm")}
            loading={busy && confirmKind === "confirm"}
            disabledReason={item ? undefined : "No open queue item for this session"}
          >
            Confirm signal
          </Button>
          <Button
            variant="secondary"
            onClick={() => setConfirmKind("override")}
            loading={busy && confirmKind === "override"}
            disabledReason={
              !item
                ? "No open queue item for this session"
                : rationale.trim().length < MIN_RATIONALE
                  ? `An override needs a written rationale (${rationale.trim().length}/${MIN_RATIONALE})`
                  : undefined
            }
          >
            Override
          </Button>
        </div>

        {confirmKind && !busy && (
          <div className="mt-3 rounded-md border border-line bg-paper p-3 text-sm">
            <p className="text-ink-soft">This decision is permanent.</p>
            <div className="mt-2 flex gap-2">
              <Button size="sm" onClick={() => void submit(confirmKind)}>
                Record {confirmKind}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setConfirmKind(null)}>
                Go back
              </Button>
            </div>
          </div>
        )}
      </div>
    </aside>
  );
}
