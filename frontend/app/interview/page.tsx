"use client";

import { useCallback, useEffect, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { LiveKitRoom } from "@livekit/components-react";
import "@livekit/components-styles";
import "./room.css";
import "../admin/admin.css";
import Nav from "../components/Nav";
import {
  QuestionView,
  RoomCredentials,
  apiUrl,
  createSession,
  getQuestion,
  getSessionStatus,
  getToken,
} from "./api";
import VoicePanel from "./VoicePanel";

const CodePanel = dynamic(() => import("./CodePanel"), { ssr: false });
const CanvasPanel = dynamic(() => import("./CanvasPanel"), { ssr: false });
const ScratchpadPanel = dynamic(() => import("./ScratchpadPanel"), { ssr: false });
const ExhibitsPanel = dynamic(() => import("./ExhibitsPanel"), { ssr: false });

function Statement({ question }: { question: QuestionView | null }) {
  if (!question) {
    return (
      <div className="panel statement">
        <span className="console-hint">
          No coding question assigned to this session&apos;s plan yet. Run the seed script.
        </span>
      </div>
    );
  }
  return (
    <div className="panel statement">
      <h2>{question.title}</h2>
      <pre className="statement-body">{question.statement_md.replace(/^#+\s.*\n+/, "")}</pre>
      <div className="statement-meta">
        {question.visible_tests.cases.length} visible tests · {question.hidden_test_count} hidden
        tests on submit
      </div>
    </div>
  );
}

export default function InterviewPage() {
  const [creds, setCreds] = useState<RoomCredentials | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [question, setQuestion] = useState<QuestionView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [finished, setFinished] = useState(false);
  const [tools, setTools] = useState<string[]>(["editor"]);
  const [assigned, setAssigned] = useState(false);
  const [resumeText, setResumeText] = useState("");
  const [showDocs, setShowDocs] = useState(false);

  useEffect(() => {
    setAssigned(new URLSearchParams(window.location.search).has("session"));
  }, []);

  const uploadResume = async (file: File | undefined) => {
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    const resp = await fetch(apiUrl(`/documents/extract`), { method: "POST", body: form });
    if (resp.ok) setResumeText(((await resp.json()) as { text: string }).text);
    else setError(`could not read ${file.name}`);
  };

  const start = useCallback(async () => {
    setStarting(true);
    setError(null);
    try {
      // ?session=<id> rejoins an existing session (rejoin keeps the shared
      // editor state via Yjs; the event log continues seamlessly).
      // ?plan=<id> starts a fresh session on a specific plan (Setup page).
      const params = new URLSearchParams(window.location.search);
      const existing = params.get("session");
      const id =
        existing ?? (await createSession(params.get("plan"), resumeText.trim() || null)).id;
      setSessionId(id);
      setQuestion(await getQuestion(id));
      setCreds(await getToken(id));
      if (!existing) {
        const url = new URL(window.location.href);
        url.searchParams.set("session", id);
        window.history.replaceState(null, "", url);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setStarting(false);
    }
  }, []);

  useEffect(() => {
    if (!sessionId) return;
    const t = setInterval(() => setElapsed((s) => s + 1), 1000);
    // The current round's question is backend-decided; poll so the panel
    // switches when the engine moves to another code round (e.g. SQL).
    const q = setInterval(async () => {
      try {
        const next = await getQuestion(sessionId);
        setQuestion((prev) => (next && next.id !== prev?.id ? next : prev));
        const toolResp = await fetch(apiUrl(`/sessions/${sessionId}/tools`));
        if (toolResp.ok) {
          const t = (await toolResp.json()) as { tools: string[] };
          setTools(t.tools);
        }
        if ((await getSessionStatus(sessionId)) === "completed") setFinished(true);
      } catch {
        /* best-effort */
      }
    }, 10_000);
    return () => {
      clearInterval(t);
      clearInterval(q);
    };
  }, [sessionId]);

  const mm = String(Math.floor(elapsed / 60)).padStart(2, "0");
  const ss = String(elapsed % 60).padStart(2, "0");

  const reconnectVoice = useCallback(async () => {
    if (!sessionId) return;
    setCreds(null);
    try {
      setCreds(await getToken(sessionId));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [sessionId]);

  if (!sessionId) {
    return (
      <>
      <Nav variant="user" />
      <main className="lobby" style={{ minHeight: "calc(100vh - 53px)" }}>
        <div className="lobby-card">
          <h1>AI Technical Interview</h1>
          <p>
            A live voice interview with an AI interviewer, including a collaborative coding
            round. Allow microphone access when prompted. Everything is recorded to an
            auditable session log.
          </p>
          {assigned ? (
            <p style={{ color: "#3fb950" }}>
              ✓ Your interview has been set up for you. Just press start.
            </p>
          ) : (
            <div style={{ textAlign: "left", margin: "8px 0" }}>
              <button className="mini" onClick={() => setShowDocs((s) => !s)}>
                {showDocs ? "▾" : "▸"} add my resume (optional)
              </button>
              {showDocs && (
                <div style={{ marginTop: 8 }}>
                  <label className="mini upload-label" style={{ marginBottom: 6 }}>
                    upload .pdf/.txt
                    <input type="file" accept=".pdf,.txt" hidden
                      onChange={(e) => uploadResume(e.target.files?.[0])} />
                  </label>
                  <textarea className="notes doc-area" value={resumeText}
                    onChange={(e) => setResumeText(e.target.value)}
                    placeholder="Paste your resume. The interviewer will ask about your actual experience." />
                </div>
              )}
            </div>
          )}
          <button className="start-btn" onClick={start} disabled={starting}>
            {starting ? "Setting up your room…" : "Start interview"}
          </button>
          {error && <p className="error">{error}</p>}
        </div>
      </main>
      </>
    );
  }

  if (finished) {
    return (
      <>
      <Nav variant="user" />
      <main className="lobby" style={{ minHeight: "calc(100vh - 53px)" }}>
        <div className="lobby-card">
          <h1>You are all set 🎉</h1>
          <p>
            Thanks for talking with us. The team will review your interview and be in
            touch about next steps.
          </p>
          {/* No scores, briefs, or review links on the candidate surface, ever
              (spec §7 hard rule). Org-side results live in the console. */}
          <p style={{ marginTop: 16 }}>
            {/* plain anchor: full reload drops the ?session param for a fresh session */}
            <a href="/interview" style={{ color: "#8b949e" }}>Start a new interview</a>
          </p>
        </div>
      </main>
      </>
    );
  }

  return (
    <main className="room">
      <header className="room-header">
        <Link href="/" className="brand" style={{ textDecoration: "none" }}>
          <span className="brand-dot" />
          AI Interview
        </Link>
        <span className="round-tag">
          {tools.includes("editor") ? "Coding round" :
            tools.includes("canvas") ? "Design round" :
            tools.includes("exhibits") ? "Case round" : "Conversation"}
        </span>
        <span className="rec-dot">REC</span>
        <span className="timer">{mm}:{ss}</span>
        <span className="session-tag" title={sessionId}>
          session {sessionId.slice(0, 8)}
        </span>
      </header>
      <div className="room-grid">
        <div className="left-col">
          {creds ? (
            // Voice is its own island: a mic/connection failure never tears
            // down the coding round.
            <LiveKitRoom
              serverUrl={creds.url}
              token={creds.token}
              connect
              audio
              video={false}
              onDisconnected={() => setCreds(null)}
            >
              <VoicePanel sessionId={sessionId} />
            </LiveKitRoom>
          ) : (
            <div className="panel voice-panel">
              <div className="agent-card">
                <p className="console-hint">Voice disconnected.</p>
                <button className="start-btn" onClick={reconnectVoice}>
                  Reconnect voice
                </button>
                {error && <p className="error">{error}</p>}
              </div>
            </div>
          )}
        </div>
        <div className="right-col">
          {tools.includes("editor") && (
            <>
              <Statement question={question} />
              <CodePanel sessionId={sessionId} question={question} />
            </>
          )}
          {tools.includes("canvas") && <CanvasPanel sessionId={sessionId} />}
          {tools.includes("exhibits") && <ExhibitsPanel sessionId={sessionId} />}
          {tools.includes("scratchpad") && <ScratchpadPanel sessionId={sessionId} />}
          {tools.length === 0 && (
            <div className="panel statement" style={{ flex: 1 }}>
              <h2>Conversation round</h2>
              <p style={{ color: "#8b949e" }}>
                No tools needed here, just talk with the interviewer.
              </p>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
