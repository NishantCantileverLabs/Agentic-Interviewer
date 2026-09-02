"use client";

import { useCallback, useEffect, useRef } from "react";
import { Tldraw, type Editor } from "tldraw";
import "tldraw/tldraw.css";
import { postEvents } from "./api";

/** T22 — whiteboard: tldraw canvas with structured serialization. Shapes are
 * serialized client-side into a typed scene graph and posted as
 * canvas_snapshot events (30s + 3s-debounced on change) — the model reads
 * structure, never screenshots. */
export default function CanvasPanel({ sessionId }: { sessionId: string }) {
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
          label: ((props.text ?? props.richText ?? "") as object).toString
            ? extractText(props)
            : "",
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
    <div className="panel canvas-panel">
      <div className="code-toolbar">
        <b style={{ fontSize: 13 }}>🖊 Whiteboard</b>
        <span className="eye-note">the interviewer sees your diagram as structure, not pixels</span>
      </div>
      <div className="canvas-wrap">
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
  // tldraw v3 rich text: walk for text leaves
  try {
    const rich = JSON.stringify(props.richText ?? "");
    const matches = rich.match(/"text":"([^"]*)"/g) ?? [];
    return matches.map((m) => m.slice(8, -1)).join(" ");
  } catch {
    return "";
  }
}
