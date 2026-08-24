"use client";

import { useCallback, useEffect, useState } from "react";
import Nav from "../../components/Nav";
import "../admin.css";

import { API, authFetch } from "../../lib/auth";

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

function CaseEditor({
  label,
  cases,
  setCases,
  prefix,
  showSql,
  note,
}: {
  label: string;
  cases: TestCase[];
  setCases: (c: TestCase[]) => void;
  prefix: string;
  showSql: boolean;
  note: string;
}) {
  const update = (i: number, patch: Partial<TestCase>) =>
    setCases(cases.map((c, j) => (j === i ? { ...c, ...patch } : c)));
  return (
    <div style={{ marginBottom: 16 }}>
      <div className="doc-head">
        <b>{label}</b>
        <button
          className="mini"
          onClick={() => setCases([...cases, emptyCase(prefix, cases.length + 1)])}
        >
          + case
        </button>
      </div>
      <p style={{ color: "#8b949e", fontSize: 12, margin: "4px 0" }}>{note}</p>
      {cases.map((c, i) => (
        <div key={i} className="case-row">
          <span className="case-id">{c.id}</span>
          {showSql && (
            <textarea
              className="notes"
              placeholder="setup SQL (schema + data for this case)"
              value={c.setup_sql}
              onChange={(e) => update(i, { setup_sql: e.target.value })}
            />
          )}
          <textarea
            className="notes"
            placeholder="stdin"
            value={c.stdin}
            onChange={(e) => update(i, { stdin: e.target.value })}
          />
          <textarea
            className="notes"
            placeholder="expected output"
            value={c.expected_output}
            onChange={(e) => update(i, { expected_output: e.target.value })}
          />
          <button className="mini" onClick={() => setCases(cases.filter((_, j) => j !== i))}>
            ✕
          </button>
        </div>
      ))}
    </div>
  );
}

export default function QuestionsPage() {
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
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const isSql = languages.length === 1 && languages[0] === "sql";

  const refresh = useCallback(
    () => authFetch(`${API}/questions`).then(async (r) => setExisting(await r.json())),
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
    setMsg(null);
    if (!title.trim() || !statement.trim()) return setMsg({ ok: false, text: "Title and statement are required." });
    if (hints.some((h) => !h.trim())) return setMsg({ ok: false, text: "All 3 hint levels are required (nudge → direction → partial approach)." });
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
    if (!resp.ok) return setMsg({ ok: false, text: await resp.text() });
    setMsg({ ok: true, text: `Question "${title}" added — it can now be assigned from Conduct interview.` });
    setTitle(""); setStatement(""); setSolution(""); setTwist("");
    setVisible([emptyCase("v", 1)]); setHidden([emptyCase("h", 1)]); setHints(["", "", ""]);
    void refresh();
  };

  return (
    <>
      <Nav />
      <main className="admin">
        <h1>Question bank</h1>
        <table>
          <thead>
            <tr><th>Title</th><th>Languages</th><th>Difficulty</th><th>Hidden tests</th><th>Twist</th></tr>
          </thead>
          <tbody>
            {existing.map((q) => (
              <tr key={q.id}>
                <td>{q.title}</td>
                <td>{q.language_targets.join(", ")}</td>
                <td>{q.difficulty}</td>
                <td>{q.hidden_test_count}</td>
                <td>{q.has_twist ? "✓" : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <h2>Add a question</h2>
        <div className="score-row">
          <label>Title</label>
          <input className="notes" style={{ maxWidth: 380 }} value={title}
            onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Merge overlapping intervals" />
          <label style={{ width: "auto", marginLeft: 16 }}>Difficulty</label>
          <select className="notes" style={{ width: 70 }} value={difficulty}
            onChange={(e) => setDifficulty(Number(e.target.value))}>
            {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </div>
        <div className="score-row" style={{ alignItems: "flex-start" }}>
          <label>Languages</label>
          <div>
            {LANGS.map((l) => (
              <button key={l}
                className={`mini ${languages.includes(l) ? "sel-lang" : ""}`}
                style={{ marginRight: 6 }}
                onClick={() =>
                  setLanguages((ls) =>
                    ls.includes(l) ? ls.filter((x) => x !== l) : [...ls, l],
                  )
                }
              >
                {l}
              </button>
            ))}
          </div>
        </div>
        <b>Problem statement (candidate sees this)</b>
        <textarea className="notes doc-area" value={statement}
          onChange={(e) => setStatement(e.target.value)}
          placeholder="Markdown. State input/output format precisely — tests compare stdout exactly." />
        <b>Reference solution (admin-only; stored for review, never exposed via API)</b>
        <textarea className="notes doc-area" value={solution}
          onChange={(e) => setSolution(e.target.value)} placeholder="Optional reference solution." />

        <CaseEditor label="Visible tests" cases={visible} setCases={setVisible} prefix="v"
          showSql={isSql} note="Shown to the candidate in the Run panel with full output." />
        <CaseEditor label="Hidden tests" cases={hidden} setCases={setHidden} prefix="h"
          showSql={isSql}
          note="Run on submit; the candidate only ever sees pass/fail — expected outputs never leave the backend." />

        <b>Graduated hints (engine-controlled escalation)</b>
        {["Level 1 — nudge", "Level 2 — direction", "Level 3 — partial approach"].map((lbl, i) => (
          <input key={i} className="notes" style={{ margin: "4px 0" }} placeholder={lbl}
            value={hints[i]}
            onChange={(e) => setHints((h) => h.map((x, j) => (j === i ? e.target.value : x)))} />
        ))}
        <b style={{ display: "block", marginTop: 10 }}>Twist (optional requirement change)</b>
        <input className="notes" value={twist} onChange={(e) => setTwist(e.target.value)}
          placeholder='e.g. "Now the input no longer fits in memory — adapt your approach."' />

        <button className="submit-btn" onClick={save}>Add question</button>
        {msg && <p style={{ color: msg.ok ? "#3fb950" : "#f85149" }}>{msg.text}</p>}
      </main>
    </>
  );
}
