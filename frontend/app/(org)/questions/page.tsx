"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Button,
  Input,
  PageHeader,
  Select,
  Table,
  useToast,
} from "../../../components/ui";
import { cx } from "../../../lib/cx";
import { API, authFetch } from "../../../lib/auth";

interface QuestionRow {
  id: string;
  title: string;
  language_targets: string[];
  difficulty: number;
  hidden_test_count: number;
  hint_levels: number;
  has_twist: boolean;
}

interface TestCase {
  id: string;
  stdin: string;
  expected_output: string;
  setup_sql: string;
}

const LANGS = ["python", "javascript", "java", "cpp", "sql"];

const emptyCase = (prefix: string, n: number): TestCase => ({
  id: `${prefix}${n}`,
  stdin: "",
  expected_output: "",
  setup_sql: "",
});

const AREA =
  "w-full rounded-md border border-line bg-panel p-2.5 font-mono text-sm text-ink " +
  "placeholder:text-muted focus-visible:border-accent";

function CaseEditor({
  label,
  hint,
  cases,
  setCases,
  prefix,
  showSql,
}: {
  label: string;
  hint?: string;
  cases: TestCase[];
  setCases: (c: TestCase[]) => void;
  prefix: string;
  showSql: boolean;
}) {
  const update = (i: number, patch: Partial<TestCase>) =>
    setCases(cases.map((c, j) => (j === i ? { ...c, ...patch } : c)));
  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <span className="text-sm font-medium text-ink-soft">{label}</span>
          {hint && <span className="ml-2 text-xs text-muted">{hint}</span>}
        </div>
        <Button
          size="sm"
          variant="secondary"
          onClick={() => setCases([...cases, emptyCase(prefix, cases.length + 1)])}
        >
          Add case
        </Button>
      </div>
      <div className="mt-2 flex flex-col gap-2">
        {cases.map((c, i) => (
          <div
            key={i}
            className={cx(
              "grid items-start gap-2",
              showSql ? "grid-cols-[40px_1fr_1fr_1fr_36px]" : "grid-cols-[40px_1fr_1fr_36px]",
            )}
          >
            <span className="pt-2.5 font-mono text-xs text-muted">{c.id}</span>
            {showSql && (
              <textarea
                className={AREA}
                rows={3}
                aria-label={`${c.id} setup SQL`}
                placeholder="setup SQL"
                value={c.setup_sql}
                onChange={(e) => update(i, { setup_sql: e.target.value })}
              />
            )}
            <textarea
              className={AREA}
              rows={3}
              aria-label={`${c.id} stdin`}
              placeholder="stdin"
              value={c.stdin}
              onChange={(e) => update(i, { stdin: e.target.value })}
            />
            <textarea
              className={AREA}
              rows={3}
              aria-label={`${c.id} expected output`}
              placeholder="expected output"
              value={c.expected_output}
              onChange={(e) => update(i, { expected_output: e.target.value })}
            />
            <button
              aria-label={`Remove ${c.id}`}
              className="mt-1 rounded-md p-2 text-muted hover:bg-paper hover:text-rust"
              onClick={() => setCases(cases.filter((_, j) => j !== i))}
            >
              ✕
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function QuestionsPage() {
  const toast = useToast();
  const [existing, setExisting] = useState<QuestionRow[]>([]);
  const [title, setTitle] = useState("");
  const [statement, setStatement] = useState("");
  const [languages, setLanguages] = useState<string[]>(["python"]);
  const [difficulty, setDifficulty] = useState(2);
  const [solution, setSolution] = useState("");
  const [visible, setVisible] = useState<TestCase[]>([emptyCase("v", 1)]);
  const [hidden, setHidden] = useState<TestCase[]>([emptyCase("h", 1)]);
  const [hints, setHints] = useState(["", "", ""]);
  const [twist, setTwist] = useState("");

  const isSql = languages.length === 1 && languages[0] === "sql";

  const refresh = useCallback(
    () =>
      authFetch(`${API}/questions`).then(async (r: Response) =>
        setExisting((await r.json()) as QuestionRow[]),
      ),
    [],
  );
  useEffect(() => {
    void refresh();
  }, [refresh]);

  const toCases = (cs: TestCase[]) => ({
    cases: cs
      .filter((c) => c.expected_output.trim() || c.stdin.trim() || c.setup_sql.trim())
      .map((c) => ({
        id: c.id,
        stdin: c.stdin,
        expected_output: c.expected_output,
        ...(c.setup_sql.trim() ? { setup_sql: c.setup_sql } : {}),
      })),
  });

  const save = async () => {
    if (!title.trim() || !statement.trim()) {
      toast("Title and statement are required", "error");
      return;
    }
    if (hints.some((h) => !h.trim())) {
      toast("All three hint levels are required", "error");
      return;
    }
    const body = {
      title,
      statement_md: statement,
      language_targets: languages,
      visible_tests: toCases(visible),
      hidden_tests: toCases(hidden),
      hints: { levels: hints },
      twist: twist.trim() ? { prompt: twist } : null,
      difficulty,
      reference_solution: solution.trim() || null,
    };
    const resp = await authFetch(`${API}/questions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!resp.ok) {
      toast(await resp.text(), "error");
      return;
    }
    toast("Question added", "success");
    setTitle("");
    setStatement("");
    setSolution("");
    setTwist("");
    setVisible([emptyCase("v", 1)]);
    setHidden([emptyCase("h", 1)]);
    setHints(["", "", ""]);
    void refresh();
  };

  return (
    <div className="mx-auto max-w-[900px]">
      <PageHeader title="Question bank" />

      <Table<QuestionRow>
        columns={[
          { key: "title", header: "Title", sortValue: (q) => q.title.toLowerCase(), render: (q) => q.title },
          {
            key: "langs",
            header: "Languages",
            render: (q) => (
              <span className="font-mono text-sm text-ink-soft">
                {q.language_targets.join(", ")}
              </span>
            ),
          },
          { key: "diff", header: "Difficulty", sortValue: (q) => q.difficulty, render: (q) => q.difficulty },
          { key: "hidden", header: "Hidden tests", render: (q) => q.hidden_test_count },
          { key: "twist", header: "Twist", render: (q) => (q.has_twist ? "✓" : "—") },
        ]}
        rows={existing}
        rowKey={(q) => q.id}
        empty={<span>No questions yet — add the first one below.</span>}
      />

      <section className="mt-8 flex flex-col gap-4 rounded-lg border border-line bg-panel p-5">
        <h2 className="font-display text-md font-semibold text-ink">New question</h2>

        <div className="grid gap-3 sm:grid-cols-[1fr_120px]">
          <Input label="Title" value={title} onChange={(e) => setTitle(e.target.value)} />
          <Select
            label="Difficulty"
            value={String(difficulty)}
            onChange={(e) => setDifficulty(Number(e.target.value))}
            options={[1, 2, 3, 4, 5].map((n) => ({ value: String(n), label: String(n) }))}
          />
        </div>

        <fieldset>
          <legend className="mb-1.5 text-sm font-medium text-ink-soft">Languages</legend>
          <div className="flex flex-wrap gap-2">
            {LANGS.map((l) => (
              <button
                key={l}
                type="button"
                aria-pressed={languages.includes(l)}
                onClick={() =>
                  setLanguages((ls) =>
                    ls.includes(l) ? ls.filter((x) => x !== l) : [...ls, l],
                  )
                }
                className={cx(
                  "h-9 rounded-md border px-3 font-mono text-sm transition-colors",
                  languages.includes(l)
                    ? "border-accent bg-accent-tint text-accent"
                    : "border-line bg-panel text-ink-soft hover:border-accent",
                )}
              >
                {l}
              </button>
            ))}
          </div>
        </fieldset>

        <div>
          <label className="mb-1 block text-sm font-medium text-ink-soft" htmlFor="statement">
            Problem statement
          </label>
          <textarea
            id="statement"
            className={AREA}
            rows={6}
            value={statement}
            onChange={(e) => setStatement(e.target.value)}
            placeholder="Markdown. Tests compare stdout exactly."
          />
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium text-ink-soft" htmlFor="solution">
            Reference solution <span className="font-normal text-muted">(never shown to candidates)</span>
          </label>
          <textarea
            id="solution"
            className={AREA}
            rows={5}
            value={solution}
            onChange={(e) => setSolution(e.target.value)}
          />
        </div>

        <CaseEditor
          label="Visible tests"
          hint="candidates can run these"
          cases={visible}
          setCases={setVisible}
          prefix="v"
          showSql={isSql}
        />
        <CaseEditor
          label="Hidden tests"
          hint="pass/fail only on submit"
          cases={hidden}
          setCases={setHidden}
          prefix="h"
          showSql={isSql}
        />

        <div>
          <span className="text-sm font-medium text-ink-soft">Hints</span>
          <div className="mt-2 flex flex-col gap-2">
            {["Level 1 — nudge", "Level 2 — direction", "Level 3 — partial approach"].map(
              (lbl, i) => (
                <Input
                  key={i}
                  label={lbl}
                  value={hints[i]}
                  onChange={(e) =>
                    setHints((h) => h.map((x, j) => (j === i ? e.target.value : x)))
                  }
                />
              ),
            )}
          </div>
        </div>

        <Input
          label="Twist"
          hint="optional mid-round requirement change"
          value={twist}
          onChange={(e) => setTwist(e.target.value)}
        />

        <div>
          <Button onClick={save}>Add question</Button>
        </div>
      </section>
    </div>
  );
}
