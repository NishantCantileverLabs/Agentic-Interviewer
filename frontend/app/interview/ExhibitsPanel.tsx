"use client";

import { useEffect, useRef, useState } from "react";
import { replay } from "./api";

interface Exhibit {
  exhibit_id: string;
  title: string;
  content_md: string;
}

/** T21 — exhibits appear only when the ENGINE releases them (exhibit_revealed
 * events); the candidate cannot request them from the UI. */
export default function ExhibitsPanel({ sessionId }: { sessionId: string }) {
  const [exhibits, setExhibits] = useState<Exhibit[]>([]);
  const lastSeq = useRef(-1);

  useEffect(() => {
    const t = setInterval(async () => {
      try {
        const events = await replay(sessionId, lastSeq.current);
        if (!events.length) return;
        lastSeq.current = events[events.length - 1].seq;
        const revealed = events
          .filter((e) => e.type === "exhibit_revealed")
          .map((e) => e.payload as unknown as Exhibit);
        if (revealed.length) setExhibits((prev) => [...prev, ...revealed]);
      } catch {
        /* best-effort */
      }
    }, 4000);
    return () => clearInterval(t);
  }, [sessionId]);

  return (
    <div className="panel exhibits-panel">
      <div className="code-toolbar"><b style={{ fontSize: 13 }}>📊 Exhibits</b></div>
      <div className="exhibits-body">
        {exhibits.length === 0 && (
          <span className="console-hint">
            Exhibits appear here when the interviewer shares them.
          </span>
        )}
        {exhibits.map((ex) => (
          <div key={ex.exhibit_id} className="exhibit-card">
            <b>{ex.title}</b>
            <pre className="statement-body">{ex.content_md}</pre>
          </div>
        ))}
      </div>
    </div>
  );
}
