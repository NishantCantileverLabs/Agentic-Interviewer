"use client";

import { useEffect, useRef, useState } from "react";
import { postEvents } from "./api";

/** T20 — calc scratchpad: full text posted as scratchpad_delta (2s debounce);
 * replay = last delta at t (parity by construction). */
export default function ScratchpadPanel({ sessionId }: { sessionId: string }) {
  const [text, setText] = useState("");
  const lastSent = useRef("");

  useEffect(() => {
    const t = setInterval(() => {
      if (text !== lastSent.current) {
        lastSent.current = text;
        void postEvents(sessionId, [
          { type: "scratchpad_delta", payload: { text: text.slice(0, 8000) } },
        ]);
      }
    }, 2000);
    return () => clearInterval(t);
  }, [sessionId, text]);

  return (
    <div className="panel scratch-panel">
      <div className="code-toolbar">
        <b style={{ fontSize: 13 }}>🧮 Scratchpad</b>
        <span className="eye-note">visible to the interviewer</span>
      </div>
      <textarea
        className="scratch-area"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={"Work your numbers here…\n\ne.g. 40M households × 8.5 = 340M"}
      />
    </div>
  );
}
