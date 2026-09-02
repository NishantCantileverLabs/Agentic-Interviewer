"use client";

import { useEffect, useRef, useState } from "react";
import {
  BarVisualizer,
  RoomAudioRenderer,
  VoiceAssistantControlBar,
  useVoiceAssistant,
} from "@livekit/components-react";
import { ReplayEvent, replay } from "./api";

interface TranscriptLine {
  seq: number;
  who: "you" | "interviewer";
  text: string;
}

export default function VoicePanel({ sessionId }: { sessionId: string }) {
  const { state, audioTrack } = useVoiceAssistant();
  const [lines, setLines] = useState<TranscriptLine[]>([]);
  const lastSeq = useRef(-1);
  const feedRef = useRef<HTMLDivElement>(null);

  // Transcript straight from the event log — the audit source of truth.
  useEffect(() => {
    const poll = setInterval(async () => {
      try {
        const events: ReplayEvent[] = await replay(sessionId, lastSeq.current);
        if (!events.length) return;
        lastSeq.current = events[events.length - 1].seq;
        const additions: TranscriptLine[] = [];
        for (const ev of events) {
          if (ev.type === "stt_final" && ev.payload.text) {
            additions.push({ seq: ev.seq, who: "you", text: String(ev.payload.text) });
          } else if (ev.type === "agent_turn" && ev.payload.text) {
            additions.push({ seq: ev.seq, who: "interviewer", text: String(ev.payload.text) });
          }
        }
        if (additions.length) {
          // never render back-to-back identical lines (historical duplicates)
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
        /* polling is best-effort */
      }
    }, 2500);
    return () => clearInterval(poll);
  }, [sessionId]);

  useEffect(() => {
    feedRef.current?.scrollTo({ top: feedRef.current.scrollHeight, behavior: "smooth" });
  }, [lines]);

  return (
    <div className="panel voice-panel">
      <div className="agent-card">
        {/* The orb is the latency-perception anchor: candidates always know
            whether the agent heard them, is thinking, or is speaking. */}
        <div className={`orb-wrap ${state}`}>
          <span className="orb-ring" />
          <span className="orb" />
        </div>
        <BarVisualizer state={state} trackRef={audioTrack} barCount={9} className="viz" />
        <div className="agent-status">
          <span className={`state-dot ${state}`} />
          <span className="agent-state-label">
            {state === "disconnected" ? "connecting…" : state}
          </span>
        </div>
        <VoiceAssistantControlBar />
        <RoomAudioRenderer />
      </div>
      <div className="transcript" ref={feedRef}>
        {lines.length === 0 && (
          <span className="console-hint">Live transcript appears here as you talk.</span>
        )}
        {lines.map((l) => (
          <div key={l.seq} className={`bubble ${l.who}`}>
            <span className="bubble-who">{l.who === "you" ? "You" : "Interviewer"}</span>
            {l.text}
          </div>
        ))}
      </div>
    </div>
  );
}
