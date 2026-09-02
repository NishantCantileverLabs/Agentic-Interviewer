"use client";

import { useEffect, useMemo, useState } from "react";
import Nav from "../../components/Nav";
import { API, authFetch } from "../../lib/auth";
import "../admin.css";

interface QuestionRow {
  id: string;
  title: string;
  language_targets: string[];
  difficulty: number;
  hidden_test_count: number;
}

interface RoundDraft {
  id: string;
  type: string;
  minutes: number;
  question: string | null;
}

const ROUND_TYPES = ["intro", "warmup", "discussion", "coding", "sql", "wrapup"];
const NEEDS_QUESTION = ["coding", "sql"];

// 30-minute default interview
const DEFAULT_ROUNDS: RoundDraft[] = [
  { id: "intro", type: "intro", minutes: 2, question: null },
  { id: "warmup", type: "warmup", minutes: 5, question: null },
  { id: "coding", type: "coding", minutes: 14, question: null },
  { id: "sql", type: "sql", minutes: 7, question: null },
  { id: "wrapup", type: "wrapup", minutes: 2, question: null },
];

/** Interview builder: the backend owns what gets asked. This page just
 * authors the plan (rounds + questions + budgets) that drives everything. */
export default function SetupPage() {
  const [candidateLink, setCandidateLink] = useState<string | null>(null);
  const [questions, setQuestions] = useState<QuestionRow[]>([]);
  const [rounds, setRounds] = useState<RoundDraft[]>(DEFAULT_ROUNDS);
  const [candidate, setCandidate] = useState("");
  const [jd, setJd] = useState("");
  const [resume, setResume] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const uploadInto = (setter: (t: string) => void) => async (file: File | undefined) => {
    if (!file) return;
    setError(null);
    const form = new FormData();
    form.append("file", file);
    const resp = await authFetch(`${API}/documents/extract`, { method: "POST", body: form });
    if (!resp.ok) return setError(`could not read ${file.name}: ${await resp.text()}`);
    setter(((await resp.json()) as { text: string }).text);
  };

  useEffect(() => {
    authFetch(`${API}/questions`).then(async (r) => setQuestions(await r.json()));
  }, []);

  const questionsFor = useMemo(
    () => (type: string) =>
      questions.filter((q) =>
        type === "sql"
          ? q.language_targets.includes("sql")
          : !q.language_targets.every((l) => l === "sql"),
      ),
    [questions],
  );

  const update = (i: number, patch: Partial<RoundDraft>) =>
    setRounds((rs) => rs.map((r, j) => (j === i ? { ...r, ...patch } : r)));

  const move = (i: number, dir: -1 | 1) =>
    setRounds((rs) => {
      const next = [...rs];
      const j = i + dir;
      if (j < 0 || j >= next.length) return rs;
      [next[i], next[j]] = [next[j], next[i]];
      return next;
    });

  const addRound = (type: string) => {
    const base = type;
    let n = 1;
    let id = base;
    while (rounds.some((r) => r.id === id)) id = `${base}_${++n}`;
    const defaults: Record<string, number> = { coding: 5, sql: 3, discussion: 4 };
    setRounds((rs) => [
      ...rs.slice(0, -1),
      { id, type, minutes: defaults[type] ?? 2, question: null },
      ...rs.slice(-1), // keep wrapup last
    ]);
  };

  const launch = async () => {
    setError(null);
    for (const r of rounds) {
      if (NEEDS_QUESTION.includes(r.type) && !r.question)
        return setError(`Round "${r.id}" needs a question.`);
    }
    setBusy(true);
    try {
      const configs = await (await authFetch(`${API}/role-configs`)).json();
      if (!configs.length) throw new Error("no role config. Run the seed script");
      const plan = {
        role_config_id: configs[0].name,
        rounds: rounds.map((r) => ({
          id: r.id,
          type: r.type,
          minutes: r.minutes,
          ...(r.question ? { question: r.question } : {}),
        })),
        competencies: Object.entries(configs[0].weights as Record<string, number>).map(
          ([id, weight]) => ({ id, weight, probe_budget: 3 }),
        ),
        language_default: "python",
      };
      const resp = await authFetch(`${API}/plans`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role_config_id: configs[0].id, plan }),
      });
      if (!resp.ok) throw new Error(`plan create failed: ${await resp.text()}`);
      const { id } = await resp.json();
      // Create the session here so JD + resume are attached and auditable
      const sessionResp = await authFetch(`${API}/sessions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          candidate_label: candidate.trim() || "ui-candidate",
          plan_id: id,
          jd_text: jd.trim() || null,
          resume_text: resume.trim() || null,
        }),
      });
      if (!sessionResp.ok) throw new Error(`session create failed: ${await sessionResp.text()}`);
      const session = (await sessionResp.json()) as { id: string };
      setCandidateLink(`${window.location.origin}/interview?session=${session.id}`);
      setBusy(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  };

  const total = rounds.reduce((s, r) => s + (Number(r.minutes) || 0), 0);

  return (
    <>
      <Nav />
      <main className="admin">
        <h1>New interview</h1>
        <p className="page-sub">
          Compose the next interview. The plan, job description, and resume are stored
          server-side and drive the engine. Every transition, question, and hint stays
          auditable.
        </p>

        <h2>Candidate &amp; role</h2>
        <div className="score-row">
          <label>Candidate name</label>
          <input className="notes" style={{ maxWidth: 280 }} value={candidate}
            onChange={(e) => setCandidate(e.target.value)} placeholder="e.g. Priya S." />
        </div>
        <div className="doc-grid">
          <div>
            <div className="doc-head">
              <b>Job description</b>
              <label className="mini upload-label">
                upload .pdf/.txt
                <input type="file" accept=".pdf,.txt" hidden
                  onChange={(e) => uploadInto(setJd)(e.target.files?.[0])} />
              </label>
            </div>
            <textarea className="notes doc-area" value={jd}
              onChange={(e) => setJd(e.target.value)}
              placeholder="Paste the JD here (or upload). The interviewer grounds its questions in these requirements, and the evaluation scores against them." />
          </div>
          <div>
            <div className="doc-head">
              <b>Candidate resume</b>
              <label className="mini upload-label">
                upload .pdf/.txt
                <input type="file" accept=".pdf,.txt" hidden
                  onChange={(e) => uploadInto(setResume)(e.target.files?.[0])} />
              </label>
            </div>
            <textarea className="notes doc-area" value={resume}
              onChange={(e) => setResume(e.target.value)}
              placeholder="Paste the resume here (or upload). Warmup and deep-dive questions get drawn from the candidate's actual experience." />
          </div>
        </div>

        <h2>Rounds</h2>
        <table>
          <thead>
            <tr>
              <th style={{ width: 90 }}>Order</th><th>Round</th><th>Type</th>
              <th style={{ width: 110 }}>Minutes</th><th>Question</th><th />
            </tr>
          </thead>
          <tbody>
            {rounds.map((r, i) => (
              <tr key={r.id}>
                <td>
                  <button className="mini" onClick={() => move(i, -1)}>↑</button>{" "}
                  <button className="mini" onClick={() => move(i, 1)}>↓</button>
                </td>
                <td>{r.id}</td>
                <td>{r.type}</td>
                <td>
                  <input
                    type="number" min={1} max={60} value={r.minutes}
                    className="notes" style={{ width: 70 }}
                    onChange={(e) => update(i, { minutes: Number(e.target.value) })}
                  />
                </td>
                <td>
                  {NEEDS_QUESTION.includes(r.type) ? (
                    <select
                      className="notes"
                      value={r.question ?? ""}
                      onChange={(e) => update(i, { question: e.target.value || null })}
                    >
                      <option value="">choose a question</option>
                      {questionsFor(r.type).map((q) => (
                        <option key={q.id} value={q.id}>
                          {q.title} (difficulty {q.difficulty}, {q.hidden_test_count} hidden tests)
                        </option>
                      ))}
                    </select>
                  ) : (
                    <span style={{ color: "#8b949e" }}>conversation</span>
                  )}
                </td>
                <td>
                  {!["intro", "wrapup"].includes(r.type) && (
                    <button className="mini" onClick={() => setRounds((rs) => rs.filter((_, j) => j !== i))}>
                      âœ•
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p>
          Add round:{" "}
          {ROUND_TYPES.filter((t) => !["intro", "wrapup"].includes(t)).map((t) => (
            <button key={t} className="mini" style={{ marginRight: 8 }} onClick={() => addRound(t)}>
              + {t}
            </button>
          ))}
          <span style={{ color: "#8b949e", marginLeft: 12 }}>total ~{total} min</span>
        </p>
        <button className="submit-btn" onClick={launch} disabled={busy}>
          {busy ? "Creating interview…" : "Create interview →"}
        </button>
        {error && <p style={{ color: "#f85149" }}>{error}</p>}
        {candidateLink && (
          <div className="link-card">
            <b>Interview created.</b> Share this link with the candidate:
            <div className="link-row">
              <code>{candidateLink}</code>
              <button className="mini" onClick={() => navigator.clipboard.writeText(candidateLink)}>
                copy
              </button>
              <a className="mini" href={candidateLink} target="_blank" rel="noreferrer">
                open ↗
              </a>
            </div>
            <span style={{ color: "#8b949e", fontSize: 13 }}>
              Track it afterwards in Overview → review / brief.
            </span>
          </div>
        )}
      </main>
    </>
  );
}
