"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Editor, { OnMount } from "@monaco-editor/react";
import * as Y from "yjs";
import { WebsocketProvider } from "y-websocket";
import { MonacoBinding } from "y-monaco";
import { cx } from "../../../../lib/cx";
import { Button } from "../../../../components/ui";
import {
  type ExecuteResponse,
  type QuestionView,
  YWS_URL,
  apiUrl,
  execute,
  postEvents,
} from "../../../interview/api";

const ALL_LANGUAGES = ["python", "javascript", "java", "cpp", "sql"];

interface Delta {
  rangeOffset: number;
  rangeLength: number;
  text: string;
}

/** F4 — the working surface. Same process-capture contract as Phase 1:
 * delta batches (500ms), snapshots (30s + on run), paste length, run clicks —
 * batched off the typing path. Yjs doc is live truth; the event log restores
 * it on rejoin. Hidden tests report pass/fail only, never expectations. */
export function CodeTool({
  sessionId,
  question,
}: {
  sessionId: string;
  question: QuestionView | null;
}) {
  const [language, setLanguage] = useState(question?.language_default ?? "python");
  const languages = question?.language_targets?.length
    ? question.language_targets
    : ALL_LANGUAGES;

  useEffect(() => {
    const targets = question?.language_targets ?? [];
    if (targets.length && !targets.includes(language)) setLanguage(targets[0]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [question?.id]);

  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<ExecuteResponse | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const [statementOpen, setStatementOpen] = useState(true);
  const editorRef = useRef<Parameters<OnMount>[0] | null>(null);
  const deltaBuffer = useRef<Delta[]>([]);

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
      if (!code) return;
      void postEvents(sessionId, [{ type: "editor_snapshot", payload: { code, language } }]);
    }, 30_000);
    return () => {
      clearInterval(flushDeltas);
      clearInterval(snapshot);
    };
  }, [sessionId, language]);

  const onMount: OnMount = useCallback(
    (editor) => {
      editorRef.current = editor;
      const doc = new Y.Doc();
      const provider = new WebsocketProvider(YWS_URL, `interview-${sessionId}`, doc);
      const model = editor.getModel();
      if (model) {
        const ytext = doc.getText("code");
        new MonacoBinding(ytext, model, new Set([editor]), provider.awareness);
        let restored = false;
        const restoreIfEmpty = async () => {
          if (restored || ytext.length > 0) return;
          restored = true;
          try {
            const resp = await fetch(
              apiUrl(
                `/sessions/${sessionId}/code_at?ts=${encodeURIComponent(new Date().toISOString())}`,
              ),
            );
            const data = (await resp.json()) as { code?: string };
            if (data.code && ytext.length === 0) ytext.insert(0, data.code);
          } catch {
            /* fresh session — nothing to restore */
          }
        };
        provider.on("sync", () => void restoreIfEmpty());
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
    if (running) return; // per-session concurrency of 1; no double-fire
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
  }, [running, sessionId, language, question]);

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      {question && (
        <div className="rounded-lg border border-line bg-panel">
          <button
            className="flex w-full items-center justify-between px-4 py-2.5 text-left"
            onClick={() => setStatementOpen((o) => !o)}
            aria-expanded={statementOpen}
          >
            <span className="font-display text-md font-semibold text-ink">
              {question.title}
            </span>
            <span className="text-sm text-muted">{statementOpen ? "Collapse" : "Expand"}</span>
          </button>
          {statementOpen && (
            <div className="border-t border-line px-4 py-3">
              <pre className="whitespace-pre-wrap font-body text-base leading-relaxed text-ink-soft">
                {question.statement_md.replace(/^#+\s.*\n+/, "")}
              </pre>
              <p className="mt-2 font-mono text-xs text-muted">
                {question.visible_tests.cases.length} visible tests ·{" "}
                {question.hidden_test_count} hidden tests on submit
              </p>
            </div>
          )}
        </div>
      )}

      <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg border border-line bg-panel">
        <div className="flex items-center gap-3 border-b border-line px-3 py-2">
          <label className="sr-only" htmlFor="lang">Language</label>
          <select
            id="lang"
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
            className="rounded-md border border-line bg-panel px-2 py-1.5 text-sm text-ink"
          >
            {languages.map((l) => (
              <option key={l} value={l}>
                {l}
              </option>
            ))}
          </select>
          <span className="text-xs text-muted">The interviewer can see your code</span>
          <div className="ml-auto">
            <Button size="sm" onClick={run} loading={running}>
              {running ? "Running" : "Run tests"}
            </Button>
          </div>
        </div>
        <div className="min-h-0 flex-1">
          <Editor
            height="100%"
            theme="vs"
            language={language === "cpp" ? "cpp" : language}
            onMount={onMount}
            options={{
              fontSize: 14,
              fontFamily: "'JetBrains Mono', Consolas, monospace",
              fontLigatures: true,
              minimap: { enabled: false },
              scrollBeyondLastLine: false,
              automaticLayout: true,
              padding: { top: 12 },
              renderLineHighlight: "gutter",
            }}
          />
        </div>
        <div className="max-h-[30%] overflow-y-auto border-t border-line px-3 py-2.5 text-sm">
          {runError && (
            <p role="alert" className="text-rust">
              {runError}
            </p>
          )}
          {result && (
            <div className="flex flex-col gap-2">
              <div className="flex flex-wrap items-center gap-1.5">
                <span
                  className={cx(
                    "rounded-full px-2.5 py-0.5 font-mono text-xs font-semibold",
                    result.status === "accepted"
                      ? "bg-panel text-green ring-1 ring-green/40"
                      : "bg-panel text-amber ring-1 ring-amber/40",
                  )}
                >
                  {result.status}
                </span>
                {result.per_test.map((t) => (
                  <span
                    key={t.id}
                    title={t.hidden ? "Hidden test — result only" : t.stdout || ""}
                    className={cx(
                      "rounded-full px-2 py-0.5 font-mono text-xs",
                      t.passed ? "bg-panel text-green ring-1 ring-green/30" : "bg-panel text-rust ring-1 ring-rust/30",
                    )}
                  >
                    {t.hidden ? "hidden·" : ""}
                    {t.id} {t.passed ? "✓" : "✕"} {t.time_ms}ms
                  </span>
                ))}
              </div>
              {result.stdout && (
                <pre className="overflow-x-auto rounded-md bg-paper p-2 font-mono text-xs text-ink-soft">
                  {result.stdout}
                </pre>
              )}
              {/* failing visible tests: input + expected vs got, side by side —
                  "output doesn't match" must be self-explanatory, not a mystery */}
              {result.per_test
                .filter((t) => !t.hidden && !t.passed)
                .map((t) => {
                  const spec = question?.visible_tests.cases.find((c) => c.id === t.id);
                  return (
                    <div key={t.id} className="rounded-md border border-rust/30 bg-paper p-2">
                      <div className="font-mono text-xs font-semibold text-rust">
                        {t.id} failed{t.status && t.status !== "wrong_answer" ? ` — ${t.status}` : ""}
                      </div>
                      {t.stderr && (
                        <pre className="mt-1 overflow-x-auto font-mono text-xs text-rust">{t.stderr}</pre>
                      )}
                      {spec && (
                        <div className="mt-1.5 grid gap-1.5 sm:grid-cols-3">
                          <div>
                            <div className="font-mono text-xs uppercase tracking-wide text-muted">Input</div>
                            <pre className="mt-0.5 overflow-x-auto whitespace-pre-wrap font-mono text-xs text-ink-soft">{spec.stdin || "(none)"}</pre>
                          </div>
                          <div>
                            <div className="font-mono text-xs uppercase tracking-wide text-muted">Expected output</div>
                            <pre className="mt-0.5 overflow-x-auto whitespace-pre-wrap font-mono text-xs text-green">{spec.expected_output}</pre>
                          </div>
                          <div>
                            <div className="font-mono text-xs uppercase tracking-wide text-muted">Your output</div>
                            <pre className="mt-0.5 overflow-x-auto whitespace-pre-wrap font-mono text-xs text-rust">{t.stdout || "(no output)"}</pre>
                          </div>
                        </div>
                      )}
                      {spec && !t.stderr && (t.stdout ?? "").trim() !== spec.expected_output.trim() && (t.stdout ?? "").includes(spec.expected_output.trim()) && (
                        <p className="mt-1 text-xs text-muted">
                          The expected value is in your output, but with extra text around it —
                          print only the answer (e.g. input() prompts also count as output).
                        </p>
                      )}
                    </div>
                  );
                })}
            </div>
          )}
          {!result && !runError && (
            <p className="text-muted">Run your code against the visible tests any time.</p>
          )}
        </div>
      </div>
    </div>
  );
}
