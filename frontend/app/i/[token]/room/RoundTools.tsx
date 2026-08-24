"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Tldraw, type Editor } from "tldraw";
import "tldraw/tldraw.css";
import { postEvents, replay } from "../../../interview/api";

/** F4 round tools for the new room — same capture contracts as Phase 3:
 * exhibits render only on engine release (exhibit_revealed), scratchpad posts
 * scratchpad_delta (2s debounce), canvas posts structured canvas_snapshot
 * (30s + 3s-debounced). Replay parity is preserved by construction. */

interface Exhibit {
  exhibit_id: string;
  title: string;
  content_md: string;
}

export function ExhibitsTool({ sessionId }: { sessionId: string }) {
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
        if (revealed.length) {
          setExhibits((prev) => {
            const seen = new Set(prev.map((x) => x.exhibit_id));
            return [...prev, ...revealed.filter((x) => !seen.has(x.exhibit_id))];
          });
        }
      } catch {
        /* best-effort */
      }
    }, 4000);
    return () => clearInterval(t);
  }, [sessionId]);

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg border border-line bg-panel">
      <div className="border-b border-line px-4 py-2.5 font-display text-md font-semibold text-ink">
        Exhibits
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-3">
        {exhibits.length === 0 && (
          <p className="text-sm text-muted">
            Exhibits appear here when the interviewer shares them.
          </p>
        )}
        {exhibits.map((ex) => (
          <div key={ex.exhibit_id} className="mb-3 rounded-md border border-line bg-paper p-3">
            <div className="font-medium text-ink">{ex.title}</div>
            <pre className="mt-1.5 whitespace-pre-wrap font-mono text-xs leading-relaxed text-ink-soft">
              {ex.content_md}
            </pre>
          </div>
        ))}
      </div>
    </div>
  );
}

export function ScratchpadTool({ sessionId }: { sessionId: string }) {
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
    <div className="flex max-h-[38%] min-h-[160px] flex-col overflow-hidden rounded-lg border border-line bg-panel">
      <div className="flex items-center gap-2 border-b border-line px-4 py-2.5">
        <span className="font-display text-md font-semibold text-ink">Scratchpad</span>
        <span className="text-xs text-muted">visible to the interviewer</span>
      </div>
      <label className="sr-only" htmlFor="scratchpad">Scratchpad</label>
      <textarea
        id="scratchpad"
        className="min-h-0 flex-1 resize-none bg-panel p-3 font-mono text-sm text-ink outline-none placeholder:text-muted"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={"Work your numbers here…\n\ne.g. 40M households × 8.5 = 340M"}
      />
    </div>
  );
}

export function CanvasTool({ sessionId }: { sessionId: string }) {
  const editorRef = useRef<Editor | null>(null);
  const lastSerialized = useRef("");
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  const serialize = useCallback((): Record<string, unknown>[] => {
    const editor = editorRef.current;
    if (!editor) return [];
    const shapes = editor.getCurrentPageShapes();
    const out: Record<string, unknown>[] = [];
    for (const s of shapes) {
      const props = s.props as Record<string, unknown>;
      if (s.type === "arrow") {
        const bindings = editor
          .getBindingsFromShape(s.id, "arrow")
          .map((b) => b as unknown as { toId: string; props: { terminal: string } });
        const start = bindings.find((b) => b.props.terminal === "start")?.toId;
        const end = bindings.find((b) => b.props.terminal === "end")?.toId;
        out.push({
          id: s.id, kind: "arrow", from: start ?? null, to: end ?? null,
          label: (props.text as string) ?? "",
        });
      } else if (s.type === "geo" || s.type === "text" || s.type === "note") {
        out.push({
          id: s.id,
          kind: s.type === "geo" ? ((props.geo as string) ?? "box") : s.type,
          label: extractText(props),
          x: Math.round(s.x), y: Math.round(s.y),
        });
      }
    }
    return out;
  }, []);

  const snapshot = useCallback(() => {
    const shapes = serialize();
    const key = JSON.stringify(shapes);
    if (key === lastSerialized.current) return;
    lastSerialized.current = key;
    void postEvents(sessionId, [{ type: "canvas_snapshot", payload: { shapes } }]);
  }, [serialize, sessionId]);

  useEffect(() => {
    const t = setInterval(snapshot, 30_000);
    return () => clearInterval(t);
  }, [snapshot]);

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg border border-line bg-panel">
      <div className="flex items-center gap-2 border-b border-line px-4 py-2.5">
        <span className="font-display text-md font-semibold text-ink">Whiteboard</span>
        <span className="text-xs text-muted">visible to the interviewer</span>
      </div>
      <div className="relative min-h-[320px] flex-1">
        <Tldraw
          onMount={(editor) => {
            editorRef.current = editor;
            editor.store.listen(
              () => {
                if (debounce.current) clearTimeout(debounce.current);
                debounce.current = setTimeout(snapshot, 3000);
              },
              { scope: "document", source: "user" },
            );
          }}
        />
      </div>
    </div>
  );
}

function extractText(props: Record<string, unknown>): string {
  const t = props.text;
  if (typeof t === "string") return t;
  try {
    const rich = JSON.stringify(props.richText ?? "");
    const matches = rich.match(/"text":"([^"]*)"/g) ?? [];
    return matches.map((m) => m.slice(8, -1)).join(" ");
  } catch {
    return "";
  }
}
