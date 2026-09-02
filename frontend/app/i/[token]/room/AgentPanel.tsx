"use client";

import { useEffect, useRef, useState } from "react";
import { useVoiceAssistant } from "@livekit/components-react";
import { cx } from "../../../../lib/cx";
import { type ReplayEvent, replay } from "../../../interview/api";

export type OrbState = "listening" | "thinking" | "speaking" | "paused";

const STATE_LABEL: Record<OrbState, string> = {
  listening: "Listening",
  thinking: "Thinking",
  speaking: "Speaking",
  paused: "Reconnecting",
};

interface CaptionLine {
  seq: number;
  who: "you" | "interviewer";
  text: string;
}

/** F3 — the agent panel: state orb + live captions. The orb is the latency
 * affordance (a two-second pause must read as intentional); captions are an
 * accessibility feature, streamed from the event log — the audit source of
 * truth — not a debug view. */
export function AgentPanel({
  sessionId,
  captionsOn,
  fullWidth,
}: {
  sessionId: string;
  captionsOn: boolean;
  fullWidth?: boolean;
}) {
  const { state } = useVoiceAssistant();
  const orb: OrbState =
    state === "listening"
      ? "listening"
      : state === "thinking"
        ? "thinking"
        : state === "speaking"
          ? "speaking"
          : "paused";

  const [lines, setLines] = useState<CaptionLine[]>([]);
  const lastSeq = useRef(-1);
  const feedRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const poll = setInterval(async () => {
      try {
        const events: ReplayEvent[] = await replay(sessionId, lastSeq.current);
        if (!events.length) return;
        lastSeq.current = events[events.length - 1].seq;
        const additions: CaptionLine[] = [];
        for (const ev of events) {
          if (ev.type === "stt_final" && ev.payload.text) {
            additions.push({ seq: ev.seq, who: "you", text: String(ev.payload.text) });
          } else if (ev.type === "agent_turn" && ev.payload.text) {
            additions.push({ seq: ev.seq, who: "interviewer", text: String(ev.payload.text) });
          }
        }
        if (additions.length) {
          // defensive: never render back-to-back identical lines even if the
          // log carries historical duplicates
          setLines((prev) => {
            const next = [...prev];
            for (const a of additions) {
              const last = next[next.length - 1];
              if (!last || last.who !== a.who || last.text !== a.text) next.push(a);
            }
            return next;
          });
        }
      } catch {
        /* captions polling is best-effort */
      }
    }, 2000);
    return () => clearInterval(poll);
  }, [sessionId]);

  useEffect(() => {
    feedRef.current?.scrollTo({ top: feedRef.current.scrollHeight });
  }, [lines, captionsOn]);

  return (
    <div
      className={cx(
        "flex min-h-0 flex-col rounded-lg border border-line bg-panel",
        fullWidth ? "flex-1" : "w-full",
      )}
    >
      <div className="flex flex-col items-center gap-2 border-b border-line px-4 pb-3 pt-5">
        <div className="relative h-10 w-10" aria-hidden>
          {orb === "listening" && (
            <span className="absolute -inset-1 rounded-full border-2 border-accent/50 animate-orb-ring motion-reduce:hidden" />
          )}
          <span
            className={cx(
              "absolute inset-0 rounded-full transition-transform duration-200",
              orb === "listening" && "bg-accent",
              orb === "speaking" && "scale-110 bg-accent",
              orb === "thinking" && "scale-90 bg-accent/60 animate-live-pulse",
              orb === "paused" && "bg-line",
            )}
          />
        </div>
        {/* screen readers hear every state change (FRONTEND.md rule 7);
            internal phase names never render on the candidate surface */}
        <div aria-live="polite" className="text-sm font-medium text-ink-soft">
          {STATE_LABEL[orb]}
        </div>
      </div>

      {captionsOn && (
        <div
          ref={feedRef}
          className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto p-3"
          role="log"
          aria-label="Live captions"
        >
          {lines.length === 0 && (
            <p className="text-sm text-muted">Captions appear here as you talk.</p>
          )}
          {lines.map((l) => (
            <div
              key={l.seq}
              className={cx(
                "max-w-[94%] rounded-md px-3 py-2 text-sm leading-relaxed",
                l.who === "interviewer"
                  ? "self-start border border-line bg-paper text-ink"
                  : "self-end bg-accent-tint text-ink",
              )}
            >
              <span className="mb-0.5 block font-mono text-xs uppercase text-muted">
                {l.who === "you" ? "You" : "Interviewer"}
              </span>
              {l.text}
            </div>
          ))}
        </div>
      )}
      {!captionsOn && (
        <div className="flex-1 p-3 text-center text-sm text-muted">Captions are off.</div>
      )}
    </div>
  );
}
