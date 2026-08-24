"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Editor, { OnMount } from "@monaco-editor/react";
import * as Y from "yjs";
import { WebsocketProvider } from "y-websocket";
import { MonacoBinding } from "y-monaco";
import {
  ExecuteResponse,
  QuestionView,
  YWS_URL,
  apiUrl,
  execute,
  postEvents,
} from "./api";

const ALL_LANGUAGES = ["python", "javascript", "java", "cpp", "sql"];
const MONACO_LANG: Record<string, string> = {
  python: "python",
  javascript: "javascript",
  java: "java",
  cpp: "cpp",
  sql: "sql",
};

interface Delta {
  rangeOffset: number;
  rangeLength: number;
  text: string;
}

export default function CodePanel({
  sessionId,
  question,
}: {
  sessionId: string;
  question: QuestionView | null;
}) {
  const [language, setLanguage] = useState(question?.language_default ?? "python");
  const languages = question?.language_targets?.length ? question.language_targets : ALL_LANGUAGES;

  // Round switch (question changed): adopt the new round's language set
  useEffect(() => {
    const targets = question?.language_targets ?? [];
    if (targets.length && !targets.includes(language)) setLanguage(targets[0]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [question?.id]);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<ExecuteResponse | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const editorRef = useRef<Parameters<OnMount>[0] | null>(null);
  const deltaBuffer = useRef<Delta[]>([]);

  // ── process capture: batched deltas (500ms), snapshots (30s), paste, tab-vis
  useEffect(() => {
    const flushDeltas = setInterval(() => {
      if (deltaBuffer.current.length) {
        const deltas = deltaBuffer.current;
        deltaBuffer.current = [];
        void postEvents(sessionId, [
          { type: "editor_delta_batch", payload: { deltas, language } },
        ]);
      }
    }, 500);
    const snapshot = setInterval(() => {
      const code = editorRef.current?.getValue() ?? "";
      // An empty editor adds nothing as a reconstruction base (deltas already
      // record deletions) and would bury the last meaningful snapshot.
      if (!code) return;
      void postEvents(sessionId, [{ type: "editor_snapshot", payload: { code, language } }]);
    }, 30_000);
    const onVisibility = () =>
      void postEvents(sessionId, [
        { type: "tab_visibility", payload: { visible: !document.hidden } },
      ]);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      clearInterval(flushDeltas);
      clearInterval(snapshot);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [sessionId, language]);

  const onMount: OnMount = useCallback(
    (editor) => {
      editorRef.current = editor;
      // Yjs CRDT sync — the shared doc is the live truth (§7.1)
      const doc = new Y.Doc();
      const provider = new WebsocketProvider(YWS_URL, `interview-${sessionId}`, doc);
      const model = editor.getModel();
      if (model) {
        const ytext = doc.getText("code");
        new MonacoBinding(ytext, model, new Set([editor]), provider.awareness);
        // The y-websocket doc is in-memory only; the event log is durable.
        // On (re)join with an empty shared doc, restore the last snapshot.
        // Event name differs across y-websocket versions ("sync"/"synced"),
        // so a timed fallback guards the restore either way.
        let restored = false;
        const restoreIfEmpty = async () => {
          if (restored || ytext.length > 0) return;
          restored = true;
          try {
            const resp = await fetch(
              apiUrl(`/sessions/${sessionId}/code_at?ts=${encodeURIComponent(
                new Date().toISOString(),
              )}`),
            );
            const data = (await resp.json()) as { code?: string };
            if (data.code && ytext.length === 0) ytext.insert(0, data.code);
          } catch {
            /* fresh session — nothing to restore */
          }
        };
        provider.on("sync", () => void restoreIfEmpty());
        // y-websocket v1 servers emit "synced" instead of "sync"; the event
        // name isn't in the v2 client's type union, hence the cast.
        provider.on("synced" as "sync", () => void restoreIfEmpty());
        setTimeout(() => void restoreIfEmpty(), 2500);
        model.onDidChangeContent((ev) => {
          const sorted = [...ev.changes].sort((a, b) => b.rangeOffset - a.rangeOffset);
          deltaBuffer.current.push(
            ...sorted.map((c) => ({
              rangeOffset: c.rangeOffset,
              rangeLength: c.rangeLength,
              text: c.text,
            })),
          );
        });
      }
      editor.onDidPaste((ev) => {
        const length = editor.getModel()?.getValueLengthInRange(ev.range) ?? 0;
        void postEvents(sessionId, [{ type: "paste", payload: { length } }]);
      });
    },
    [sessionId],
  );

  const run = useCallback(async () => {
    const source = editorRef.current?.getValue() ?? "";
    if (!source.trim()) return;
    setRunning(true);
    setRunError(null);
    void postEvents(sessionId, [
      { type: "run_clicked", payload: { language } },
      { type: "editor_snapshot", payload: { code: source, language } },
    ]);
    try {
      setResult(await execute(sessionId, language, source, question?.id));
    } catch (e) {
      setRunError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  }, [sessionId, language, question]);

  return (
    <div className="panel code-panel">
      <div className="code-toolbar">
        <select
          value={language}
          onChange={(e) => setLanguage(e.target.value)}
          className="lang-select"
        >
          {languages.map((l) => (
            <option key={l} value={l}>
              {l}
            </option>
          ))}
        </select>
        <span className="eye-note" title="The interviewer's code observation refreshes every ~15 seconds">
          👁 the interviewer can see your code
        </span>
        <button className="run-btn" onClick={run} disabled={running}>
          {running ? "Running…" : "▶ Run tests"}
        </button>
      </div>
      <div className="editor-wrap">
        <Editor
          height="100%"
          theme="vs-dark"
          language={MONACO_LANG[language]}
          onMount={onMount}
          options={{
            fontSize: 14,
            fontFamily: "'JetBrains Mono', Consolas, monospace",
            fontLigatures: true,
            minimap: { enabled: false },
            scrollBeyondLastLine: false,
            automaticLayout: true,
            padding: { top: 14 },
            smoothScrolling: true,
            cursorBlinking: "smooth",
            cursorSmoothCaretAnimation: "on",
            bracketPairColorization: { enabled: true },
            renderLineHighlight: "gutter",
          }}
        />
      </div>
      <div className="console">
        {runError && <div className="test-chip fail">{runError}</div>}
        {result && (
          <>
            <div className="console-row">
              <span className={`status-badge ${result.status === "accepted" ? "ok" : "warn"}`}>
                {result.status}
              </span>
              {result.per_test.map((t) => (
                <span
                  key={t.id}
                  className={`test-chip ${t.passed ? "pass" : "fail"}`}
                  title={t.hidden ? "hidden test" : t.stdout || ""}
                >
                  {t.hidden ? "🔒" : ""} {t.id} {t.passed ? "✓" : "✗"} {t.time_ms}ms
                </span>
              ))}
            </div>
            {result.stdout && <pre className="console-out">{result.stdout}</pre>}
            {result.per_test
              .filter((t) => !t.hidden && !t.passed && (t.stdout || t.stderr))
              .map((t) => (
                <pre key={t.id} className="console-out">
                  [{t.id}] {t.stderr || t.stdout}
                </pre>
              ))}
          </>
        )}
        {!result && !runError && (
          <span className="console-hint">
            Run your code against the visible tests. Hidden tests run on submit and report
            pass/fail only.
          </span>
        )}
      </div>
    </div>
  );
}
