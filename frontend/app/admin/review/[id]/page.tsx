"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import Nav from "../../../components/Nav";
import "../../admin.css";

import { API, authFetch } from "../../../lib/auth";

const COMPETENCIES = [
  "problem_solving",
  "coding_proficiency",
  "cs_fundamentals",
  "communication",
];

interface ReplayEvent {
  seq: number;
  type: string;
  payload: Record<string, unknown>;
}

/** Blind shadow-scoring (T8): the reviewer sees the replay and scores the
 * rubric; AI scores are fetched only AFTER submission. */
export default function ReviewPage() {
  const { id } = useParams<{ id: string }>();
  const [events, setEvents] = useState<ReplayEvent[]>([]);
  const [reviewer, setReviewer] = useState("");
  const [scores, setScores] = useState<Record<string, number>>({});
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [submitted, setSubmitted] = useState(false);
  const [aiScores, setAiScores] = useState<Record<string, { score_1_to_5?: number }> | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    authFetch(`${API}/sessions/${id}/replay`).then(async (r) => setEvents(await r.json()));
  }, [id]);

  const submit = useCallback(async () => {
    setError(null);
    if (!reviewer.trim()) return setError("Enter your reviewer name.");
    if (Object.keys(scores).length < COMPETENCIES.length)
      return setError("Score every competency before submitting.");
    const rubric = Object.fromEntries(
      COMPETENCIES.map((c) => [c, { score_1_to_5: scores[c], notes: notes[c] ?? "" }]),
    );
    const resp = await authFetch(`${API}/sessions/${id}/human-evaluation`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reviewer, rubric }),
    });
    if (!resp.ok) return setError(`submit failed: ${resp.status}`);
    setSubmitted(true);
    // Blindness lifts only now
    const ai = await authFetch(`${API}/sessions/${id}/evaluation`);
    if (ai.ok) setAiScores((await ai.json()).rubric.competencies);
  }, [id, reviewer, scores, notes]);

  return (
    <>
    <Nav />
    <main className="admin">
      <h1>Shadow review</h1>
      <p style={{ color: "#8b949e" }}>
        Session {id}. Score the rubric from the replay below. AI scores stay hidden until you
        submit.
      </p>

      <h2>Replay</h2>
      <div className="transcript-box">
        {events.map((e) => {
          const p = e.payload as Record<string, string>;
          if (e.type === "stt_final") return <div key={e.seq}><b>Candidate:</b> {String(p.text)}</div>;
          if (e.type === "agent_turn") return <div key={e.seq}><b style={{ color: "#4f8ef7" }}>Interviewer:</b> {String(p.text)}</div>;
          if (e.type === "state_transition") return <div key={e.seq} style={{ color: "#d29922" }}>round: {String(p.to)}</div>;
          if (e.type === "execution_result") {
            const resp = (e.payload as { response?: { status?: string } }).response;
            return <div key={e.seq} style={{ color: "#8b949e" }}>[code run: {resp?.status}]</div>;
          }
          if (e.type === "hint_issued") return <div key={e.seq} style={{ color: "#8b949e" }}>[hint level {String((e.payload as { level?: number }).level)}]</div>;
          if (e.type === "paste") return <div key={e.seq} style={{ color: "#8b949e" }}>[paste: {String((e.payload as { length?: number }).length)} chars]</div>;
          return null;
        })}
      </div>

      <h2>Your rubric</h2>
      <div className="score-row">
        <label>Reviewer</label>
        <input className="notes" style={{ maxWidth: 240 }} value={reviewer}
          onChange={(ev) => setReviewer(ev.target.value)} placeholder="your name" />
      </div>
      {COMPETENCIES.map((c) => (
        <div key={c}>
          <div className="score-row">
            <label>{c}</label>
            {[1, 2, 3, 4, 5].map((n) => (
              <button
                key={n}
                className={scores[c] === n ? "sel" : ""}
                onClick={() => setScores((s) => ({ ...s, [c]: n }))}
                disabled={submitted}
              >
                {n}
              </button>
            ))}
            {submitted && aiScores && (
              <span style={{ marginLeft: 16 }}>
                AI: <b>{aiScores[c]?.score_1_to_5 ?? "-"}</b>
                {aiScores[c]?.score_1_to_5 !== undefined && scores[c] !== undefined &&
                  Math.abs((aiScores[c].score_1_to_5 as number) - scores[c]) >= 2 && (
                    <span className="badge bad" style={{ marginLeft: 8 }}>Δ ≥ 2</span>
                  )}
              </span>
            )}
          </div>
          <input className="notes" placeholder="notes (optional)" value={notes[c] ?? ""}
            onChange={(ev) => setNotes((s) => ({ ...s, [c]: ev.target.value }))}
            disabled={submitted} />
        </div>
      ))}
      {!submitted ? (
        <button className="submit-btn" onClick={submit}>Submit blind review</button>
      ) : (
        <p style={{ color: "#3fb950", fontWeight: 700 }}>
          Submitted. AI comparison shown above.{" "}
          <Link href="/admin/calibration">Calibration report</Link>
          {" · "}
          <Link href={`/admin/brief/${id}`}>Decision brief</Link>
        </p>
      )}
      {error && <p style={{ color: "#f85149" }}>{error}</p>}
    </main>
    </>
  );
}
