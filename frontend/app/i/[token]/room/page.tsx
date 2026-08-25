"use client";

import dynamic from "next/dynamic";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { LiveKitRoom, RoomAudioRenderer, useLocalParticipant } from "@livekit/components-react";
import { Button, Drawer, Modal } from "../../../../components/ui";
import { cx } from "../../../../lib/cx";
import {
  type QuestionView,
  type RoomCredentials,
  apiUrl,
  getQuestion,
  getSessionStatus,
  getToken,
  postEvents,
} from "../../../interview/api";
import { AgentPanel } from "./AgentPanel";

const CodeTool = dynamic(() => import("./CodeTool").then((m) => m.CodeTool), { ssr: false });
const CanvasTool = dynamic(() => import("./RoundTools").then((m) => m.CanvasTool), { ssr: false });
const ExhibitsTool = dynamic(() => import("./RoundTools").then((m) => m.ExhibitsTool), { ssr: false });
const ScratchpadTool = dynamic(() => import("./RoundTools").then((m) => m.ScratchpadTool), { ssr: false });

/** F3 — the interview room. Chrome-light: the candidate's attention belongs on
 * the conversation and the editor; the single accent is reserved for agent
 * state. Voice is its own island — a connection drop never tears down the
 * working surface. */
export default function RoomPage() {
  const { token } = useParams<{ token: string }>();
  const search = useSearchParams();
  const sessionId = search.get("session");
  const router = useRouter();

  const [creds, setCreds] = useState<RoomCredentials | null>(null);
  const [dropped, setDropped] = useState(false);
  const [question, setQuestion] = useState<QuestionView | null>(null);
  const [tools, setTools] = useState<string[]>(["editor"]);
  const [captionsOn, setCaptionsOn] = useState(true);
  const [helpOpen, setHelpOpen] = useState(false);
  const [leaveOpen, setLeaveOpen] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);

  // ── bootstrap: room credentials + current round content ─────────
  const connect = useCallback(async () => {
    if (!sessionId) return;
    setError(null);
    try {
      setCreds(await getToken(sessionId));
      setDropped(false);
    } catch (e) {
      // a finished interview refuses room tokens (409): route to the
      // wrap-up screen instead of showing a join error
      try {
        const status = await getSessionStatus(sessionId);
        if (status === "completed" || status === "aborted") {
          router.push(`/i/${token}/next`);
          return;
        }
      } catch {
        /* fall through to the generic error */
      }
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [sessionId, router, token]);

  useEffect(() => {
    void connect();
    if (!sessionId) return;
    void getQuestion(sessionId).then(setQuestion).catch(() => undefined);
    // the first paint must already show the right tool for the current round
    void fetch(apiUrl(`/sessions/${sessionId}/tools`))
      .then(async (r) => {
        if (r.ok) setTools(((await r.json()) as { tools: string[] }).tools);
      })
      .catch(() => undefined);
  }, [connect, sessionId]);

  // round/tool polling — the backend decides what the candidate sees
  useEffect(() => {
    if (!sessionId) return;
    const t = setInterval(() => setElapsed((s) => s + 1), 1000);
    const poll = setInterval(async () => {
      try {
        const next = await getQuestion(sessionId);
        setQuestion((prev) => (next && next.id !== prev?.id ? next : prev));
        const toolResp = await fetch(apiUrl(`/sessions/${sessionId}/tools`));
        if (toolResp.ok) {
          const data = (await toolResp.json()) as { tools: string[] };
          setTools(data.tools);
        }
        if ((await getSessionStatus(sessionId)) === "completed") {
          // C9: the transition screen decides — next round, review gate, or done
          router.push(`/i/${token}/next`);
        }
      } catch {
        /* best-effort */
      }
    }, 10_000);
    return () => {
      clearInterval(t);
      clearInterval(poll);
    };
  }, [sessionId, router, token]);

  // ── beacons: tab visibility, buffered across offline windows ────
  const beaconQueue = useRef<{ type: string; payload: Record<string, unknown> }[]>([]);
  useEffect(() => {
    if (!sessionId) return;
    const push = (visible: boolean) =>
      beaconQueue.current.push({
        type: "tab_visibility",
        payload: { visible, at: new Date().toISOString() },
      });
    const onVisibility = () => push(!document.hidden);
    const onFocus = () => push(true);
    const onBlur = () => push(false);
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("focus", onFocus);
    window.addEventListener("blur", onBlur);
    // flush loop: survives offline windows — events stay queued until a send
    // succeeds (postEvents itself never throws, so probe connectivity first)
    const flush = setInterval(() => {
      if (!beaconQueue.current.length) return;
      const batch = beaconQueue.current;
      fetch(apiUrl(`/sessions/${sessionId}`), { method: "HEAD" })
        .then(() => {
          beaconQueue.current = [];
          void postEvents(sessionId, batch);
        })
        .catch(() => undefined); // still offline. Keep buffering
    }, 5_000);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("focus", onFocus);
      window.removeEventListener("blur", onBlur);
      clearInterval(flush);
    };
  }, [sessionId]);

  if (!sessionId) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-paper p-4">
        <div className="rounded-lg border border-line bg-panel p-6 text-center">
          <h1 className="font-display text-lg font-semibold text-ink">No session</h1>
          <p className="mt-2 text-ink-soft">Return to your invitation and press Join.</p>
        </div>
      </div>
    );
  }

  const conversationOnly = tools.length === 0;
  const roundLabel =
    question?.round_type?.replace(/_/g, " ") ??
    (tools.includes("editor")
      ? "coding"
      : tools.includes("canvas")
        ? "system design"
        : tools.includes("exhibits")
          ? "case"
          : conversationOnly
            ? "conversation"
            : "working");
  const mm = String(Math.floor(elapsed / 60)).padStart(2, "0");
  const ss = String(elapsed % 60).padStart(2, "0");

  return (
    <div className="flex h-screen flex-col bg-paper">
      {/* top bar */}
      <header className="flex items-center gap-3 border-b border-line bg-panel px-4 py-2">
        <span aria-hidden className="h-4 w-4 rounded-sm bg-accent" />
        <span className="font-display text-sm font-semibold text-ink">AI Interview</span>
        <span className="rounded-full border border-line px-2.5 py-0.5 text-xs capitalize text-ink-soft">
          {roundLabel} round
        </span>
        <span className="flex items-center gap-1.5 font-mono text-xs font-semibold text-rust">
          <span aria-hidden className="h-2 w-2 rounded-full bg-rust animate-live-pulse" />
          REC
        </span>
        <span className="ml-auto font-mono text-sm tabular-nums text-muted" aria-label="Elapsed time">
          {mm}:{ss}
        </span>
      </header>

      {/* reconnect banner */}
      {dropped && (
        <div
          role="alert"
          className="flex items-center justify-center gap-3 border-b border-amber/40 bg-panel px-4 py-2 text-sm text-amber"
        >
          Voice connection lost. Reconnecting. Your work is safe and the interview
          resumes where it left off.
          <Button size="sm" variant="secondary" onClick={() => void connect()}>
            Reconnect now
          </Button>
        </div>
      )}

      {/* body */}
      <div className="flex min-h-0 flex-1 gap-3 p-3">
        {creds ? (
          <LiveKitRoom
            serverUrl={creds.url}
            token={creds.token}
            connect
            audio
            video={false}
            onDisconnected={() => setDropped(true)}
            className={cx(
              "flex min-h-0 flex-col gap-3",
              conversationOnly ? "flex-1" : "w-[320px] shrink-0",
            )}
          >
            <AgentPanel sessionId={sessionId} captionsOn={captionsOn} fullWidth />
            <RoomAudioRenderer />
            <FooterControls
              captionsOn={captionsOn}
              onCaptions={() => setCaptionsOn((c) => !c)}
              onHelp={() => setHelpOpen(true)}
              onLeave={() => setLeaveOpen(true)}
            />
          </LiveKitRoom>
        ) : (
          <div
            className={cx(
              "flex items-center justify-center rounded-lg border border-line bg-panel",
              conversationOnly ? "flex-1" : "w-[320px] shrink-0",
            )}
          >
            <div className="p-4 text-center">
              <p className="text-sm text-muted" aria-busy={!error}>
                {error ?? "Connecting your voice line. A few seconds."}
              </p>
              {error && (
                <div className="mt-3">
                  <Button size="sm" onClick={() => void connect()}>
                    Try again
                  </Button>
                </div>
              )}
            </div>
          </div>
        )}

        {!conversationOnly && (
          <div className="flex min-h-0 flex-1 flex-col gap-3">
            {/* key={sessionId}: a new session gets a FRESH tool instance.
                Without it React reuses the mounted component, Monaco's
                onMount never re-runs, and the editor stays bound to the
                previous session's document. */}
            {tools.includes("editor") && (
              <CodeTool key={sessionId} sessionId={sessionId} question={question} />
            )}
            {tools.includes("canvas") && <CanvasTool key={sessionId} sessionId={sessionId} />}
            {tools.includes("exhibits") && <ExhibitsTool key={sessionId} sessionId={sessionId} />}
            {tools.includes("scratchpad") && (
              <ScratchpadTool key={sessionId} sessionId={sessionId} />
            )}
          </div>
        )}
      </div>

      {/* help drawer. Technical help only */}
      <Drawer open={helpOpen} onClose={() => setHelpOpen(false)} title="Help">
        <div className="flex flex-col gap-4 text-base text-ink-soft">
          <div>
            <div className="font-medium text-ink">Audio problems</div>
            <p className="mt-1 text-sm">
              Check your microphone is not muted at the system level, then reconnect.
            </p>
            <div className="mt-2">
              <Button size="sm" variant="secondary" onClick={() => void connect()}>
                Reconnect voice
              </Button>
            </div>
          </div>
          <div>
            <div className="font-medium text-ink">Still stuck?</div>
            <p className="mt-1 text-sm">
              This link works on another computer. You can switch devices and resume.
              For anything else, contact the team from your invitation email.
            </p>
          </div>
        </div>
      </Drawer>

      {/* leave confirm */}
      <Modal
        open={leaveOpen}
        onClose={() => setLeaveOpen(false)}
        title="End your interview"
        footer={
          <>
            <Button variant="ghost" onClick={() => setLeaveOpen(false)}>
              Go back
            </Button>
            <Button variant="danger" onClick={() => router.push(`/i/${token}/done`)}>
              End interview
            </Button>
          </>
        }
      >
        <p className="text-ink-soft">
          Your interview will end and be submitted as-is. This cannot be undone.
        </p>
      </Modal>
    </div>
  );
}

/** Footer controls live inside LiveKitRoom so the mute toggle can reach the
 * local participant. Static bar at the bottom of the agent column — never an
 * overlay, so it can't sit on top of captions or the editor. */
function FooterControls({
  captionsOn,
  onCaptions,
  onHelp,
  onLeave,
}: {
  captionsOn: boolean;
  onCaptions: () => void;
  onHelp: () => void;
  onLeave: () => void;
}) {
  const { localParticipant } = useLocalParticipant();
  const [muted, setMuted] = useState(false);

  const toggleMute = async () => {
    const next = !muted;
    await localParticipant.setMicrophoneEnabled(!next);
    setMuted(next);
  };

  return (
    <div className="flex shrink-0 flex-wrap items-center justify-center gap-2 rounded-lg border border-line bg-panel px-3 py-2">
      <button
        onClick={toggleMute}
        aria-pressed={muted}
        className={cx(
          "rounded-full px-3 py-1.5 text-sm font-medium",
          muted ? "bg-rust text-white" : "bg-paper text-ink hover:bg-accent-tint",
        )}
      >
        {muted ? "Unmute" : "Mute"}
      </button>
      <button
        onClick={onCaptions}
        aria-pressed={captionsOn}
        className={cx(
          "rounded-full px-3 py-1.5 text-sm font-medium",
          captionsOn ? "bg-accent-tint text-accent" : "bg-paper text-ink hover:bg-accent-tint",
        )}
      >
        Captions
      </button>
      <button
        onClick={onHelp}
        className="rounded-full bg-paper px-3 py-1.5 text-sm font-medium text-ink hover:bg-accent-tint"
      >
        Help
      </button>
      <button
        onClick={onLeave}
        className="rounded-full bg-paper px-3 py-1.5 text-sm font-medium text-rust hover:bg-rust hover:text-white"
      >
        Leave
      </button>
    </div>
  );
}
