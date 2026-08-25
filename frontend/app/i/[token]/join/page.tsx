"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { Button, ButtonLink, Modal } from "../../../../components/ui";
import {
  API,
  INTERVIEWER_VOICES,
  setSessionVoice,
  startInterview,
} from "../../../../lib/portal";
import { PortalScreen, StepCard } from "../PortalScreen";

type CheckState = "pending" | "running" | "pass" | "fail" | "warn";

interface Check {
  id: string;
  label: string;
  state: CheckState;
  detail?: string;
  required: boolean;
}

function browserGuidance(): string {
  const ua = navigator.userAgent;
  if (ua.includes("Firefox"))
    return "Click the microphone icon in the address bar and choose 'Allow', then run the check again.";
  if (ua.includes("Safari") && !ua.includes("Chrome"))
    return "Open Safari → Settings → Websites → Microphone and allow this site, then run the check again.";
  return "Click the camera/microphone icon at the right of the address bar, allow the microphone, then run the check again.";
}

/** C6 System check + C7 Lobby in one route. `?check=only` returns to the
 * landing after a passing check instead of entering the lobby. */
export default function JoinPage() {
  const { token } = useParams<{ token: string }>();
  const search = useSearchParams();
  const checkOnly = search.get("check") === "only";
  const router = useRouter();

  const [phase, setPhase] = useState<"check" | "lobby">("check");
  const [checks, setChecks] = useState<Check[]>([
    { id: "browser", label: "Browser support", state: "pending", required: true },
    { id: "mic", label: "Microphone", state: "pending", required: true },
    { id: "speaker", label: "Speakers", state: "pending", required: false },
    { id: "net", label: "Network", state: "pending", required: true },
    { id: "cam", label: "Camera", state: "pending", required: false },
  ]);
  const [level, setLevel] = useState(0);
  const [leaveOpen, setLeaveOpen] = useState(false);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const [voice, setVoice] = useState<string>(INTERVIEWER_VOICES[0].id);
  const audioRef = useRef<{ ctx: AudioContext; stream: MediaStream } | null>(null);

  const set = useCallback((id: string, patch: Partial<Check>) => {
    setChecks((cs) => cs.map((c) => (c.id === id ? { ...c, ...patch } : c)));
  }, []);

  // ── the checks ──────────────────────────────────────────────────
  const runChecks = useCallback(async () => {
    // browser
    set("browser", { state: "running" });
    const ok =
      typeof navigator.mediaDevices?.getUserMedia === "function" &&
      typeof WebSocket === "function" &&
      typeof AudioContext === "function";
    set("browser", {
      state: ok ? "pass" : "fail",
      detail: ok ? undefined : "Use a recent Chrome or Edge on this device.",
    });

    // camera — this organization has video proctoring disabled
    set("cam", { state: "pass", detail: "Not required by this organization" });

    // network RTT to the interview service
    set("net", { state: "running" });
    try {
      const samples: number[] = [];
      for (let i = 0; i < 3; i++) {
        const t0 = performance.now();
        await fetch(`${API}/health`, { cache: "no-store" });
        samples.push(performance.now() - t0);
      }
      const rtt = Math.round(Math.min(...samples));
      set("net", {
        state: rtt < 400 ? "pass" : "warn",
        detail:
          rtt < 400
            ? `${rtt} ms`
            : `${rtt} ms. A slow connection may add pauses; a wired or strong wifi network helps`,
      });
    } catch {
      set("net", {
        state: "fail",
        detail: "Could not reach the interview service. Check your connection.",
      });
    }

    // microphone with live level meter
    set("mic", { state: "running", detail: "Say a few words…" });
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const ctx = new AudioContext();
      const src = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 512;
      src.connect(analyser);
      audioRef.current = { ctx, stream };
      const data = new Uint8Array(analyser.frequencyBinCount);
      let heard = false;
      const tick = () => {
        if (!audioRef.current) return;
        analyser.getByteTimeDomainData(data);
        let peak = 0;
        for (let i = 0; i < data.length; i++) peak = Math.max(peak, Math.abs(data[i] - 128) / 128);
        setLevel(peak);
        if (peak > 0.06 && !heard) {
          heard = true;
          set("mic", { state: "pass", detail: "We can hear you" });
        }
        requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    } catch {
      set("mic", { state: "fail", detail: browserGuidance() });
    }
  }, [set]);

  useEffect(() => {
    void runChecks();
    return () => {
      audioRef.current?.stream.getTracks().forEach((t) => t.stop());
      void audioRef.current?.ctx.close();
      audioRef.current = null;
    };
  }, [runChecks]);

  const playTone = async () => {
    set("speaker", { state: "running" });
    const ctx = new AudioContext();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    gain.gain.value = 0.08;
    osc.frequency.value = 440;
    osc.connect(gain).connect(ctx.destination);
    osc.start();
    setTimeout(() => {
      osc.stop();
      void ctx.close();
      set("speaker", { state: "pass", detail: "If you heard the tone, you are set" });
    }, 700);
  };

  const requiredPass = checks
    .filter((c) => c.required)
    .every((c) => c.state === "pass" || c.state === "warn");

  // ── entering the room ───────────────────────────────────────────
  const enter = async () => {
    setStarting(true);
    setStartError(null);
    try {
      const result = await startInterview(token);
      // the backend returns the legacy room path; the new flow keeps the
      // candidate inside /i — same session, same candidate token
      const legacy = new URLSearchParams(result.interview_path.split("?")[1] ?? "");
      const candidateToken = legacy.get("candidate_token") ?? "";
      // persist the voice pick before the agent bootstraps in the room; a
      // hiccup here means default voice, never a blocked interview
      try {
        await setSessionVoice(result.session_id, candidateToken, voice);
      } catch {
        /* default voice */
      }
      router.push(
        `/i/${token}/room?session=${result.session_id}&candidate_token=${candidateToken}`,
      );
    } catch (e) {
      setStartError(e instanceof Error ? e.message : String(e));
      setStarting(false);
    }
  };

  return (
    <PortalScreen>
      {(portal) => {
        const slot = portal.schedule ? new Date(portal.schedule.slot_start) : null;

        if (phase === "lobby") {
          return (
            <Lobby
              slot={slot}
              roleName={portal.role_name}
              onEnter={enter}
              starting={starting}
              startError={startError}
              voice={voice}
              setVoice={setVoice}
              onLeave={() => setLeaveOpen(true)}
              leaveOpen={leaveOpen}
              closeLeave={() => setLeaveOpen(false)}
              leaveTo={`/i/${token}/confirm`}
            />
          );
        }

        return (
          <StepCard>
            <h1 className="font-display text-xl font-semibold text-ink">System check</h1>
            <p className="mt-1 text-sm text-muted">
              A minute now prevents most problems later.
            </p>

            <ul className="mt-4 flex flex-col gap-2">
              {checks.map((c) => (
                <li
                  key={c.id}
                  className="flex items-start justify-between gap-3 rounded-md border border-line p-3"
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 font-medium text-ink">
                      <StateGlyph state={c.state} />
                      {c.label}
                      {!c.required && <span className="text-xs text-muted">(optional)</span>}
                    </div>
                    {c.detail && <p className="mt-0.5 text-sm text-muted">{c.detail}</p>}
                    {c.id === "mic" && c.state !== "fail" && (
                      <div
                        className="mt-2 h-1.5 w-48 overflow-hidden rounded-full bg-paper"
                        role="meter"
                        aria-label="Microphone level"
                        aria-valuenow={Math.round(level * 100)}
                        aria-valuemin={0}
                        aria-valuemax={100}
                      >
                        <div
                          className="h-full bg-accent transition-[width] duration-75"
                          style={{ width: `${Math.min(100, level * 240)}%` }}
                        />
                      </div>
                    )}
                  </div>
                  {c.id === "speaker" && c.state !== "running" && (
                    <Button size="sm" variant="secondary" onClick={playTone}>
                      Play test tone
                    </Button>
                  )}
                  {c.id === "mic" && c.state === "fail" && (
                    <Button size="sm" variant="secondary" onClick={() => void runChecks()}>
                      Run again
                    </Button>
                  )}
                </li>
              ))}
            </ul>

            {checks.some((c) => c.required && c.state === "fail") && (
              <p className="mt-3 text-sm text-muted">
                Stuck? This link also works on another computer. You can switch devices
                and pick up right here.
              </p>
            )}

            <div className="mt-5 text-center">
              {checkOnly ? (
                <ButtonLink href={`/i/${token}`} variant="secondary">
                  Back to overview
                </ButtonLink>
              ) : (
                <Button
                  onClick={() => setPhase("lobby")}
                  disabledReason={
                    requiredPass ? undefined : "The required checks must pass to continue"
                  }
                >
                  Enter waiting room
                </Button>
              )}
            </div>
          </StepCard>
        );
      }}
    </PortalScreen>
  );
}

function StateGlyph({ state }: { state: CheckState }) {
  if (state === "pass") return <span className="text-green" aria-label="passed">✓</span>;
  if (state === "warn") return <span className="text-amber" aria-label="warning">▲</span>;
  if (state === "fail") return <span className="text-rust" aria-label="failed">✕</span>;
  return (
    <span
      aria-label="checking"
      className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-line border-t-accent motion-reduce:animate-none"
    />
  );
}

function Lobby({
  slot,
  roleName,
  onEnter,
  starting,
  startError,
  voice,
  setVoice,
  onLeave,
  leaveOpen,
  closeLeave,
  leaveTo,
}: {
  slot: Date | null;
  roleName: string | null;
  onEnter: () => void;
  starting: boolean;
  startError: string | null;
  voice: string;
  setVoice: (v: string) => void;
  onLeave: () => void;
  leaveOpen: boolean;
  closeLeave: () => void;
  leaveTo: string;
}) {
  const router = useRouter();
  const [now, setNow] = useState(() => Date.now());
  const fired = useRef(false);

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  const msLeft = slot ? slot.getTime() - now : 0;
  const ready = msLeft <= 0;

  // auto-transition into the room at T-0
  useEffect(() => {
    if (ready && !fired.current && !starting) {
      fired.current = true;
      onEnter();
    }
  }, [ready, starting, onEnter]);

  const mm = Math.max(0, Math.floor(msLeft / 60000));
  const ss = Math.max(0, Math.floor((msLeft % 60000) / 1000));

  return (
    <StepCard>
      <div className="text-center">
        {ready ? (
          <>
            <h1 className="font-display text-xl font-semibold text-ink">
              {starting ? "Preparing your room" : "Your interview is ready"}
            </h1>
            {starting && (
              <p className="mt-2 text-sm text-muted" aria-busy="true">
                Setting up your room. This takes a few seconds.
              </p>
            )}
            {startError && (
              <div className="mt-3">
                <p role="alert" className="text-sm text-rust">{startError}</p>
                <div className="mt-2">
                  <Button onClick={onEnter}>Try again</Button>
                </div>
              </div>
            )}
          </>
        ) : (
          <>
            <h1 className="font-display text-xl font-semibold text-ink">
              Your interview begins in
            </h1>
            <div className="mt-2 font-display text-3xl font-semibold tabular-nums text-accent">
              {String(mm).padStart(2, "0")}:{String(ss).padStart(2, "0")}
            </div>
          </>
        )}

        <div className="mt-5 rounded-md border border-line bg-paper p-4 text-left">
          <div className="font-medium text-ink">While you wait</div>
          <p className="mt-1 text-sm text-ink-soft">
            You will be speaking with our AI interviewer. Take your time. Pauses to
            think are expected. You can ask it to repeat or clarify anything.
          </p>
          {roleName && (
            <p className="mt-2 text-sm text-muted">Interview for {roleName}.</p>
          )}
        </div>

        <fieldset className="mt-4 rounded-md border border-line bg-paper p-4 text-left">
          <legend className="px-1 font-medium text-ink">Interviewer voice</legend>
          <p className="text-sm text-muted">
            Pick the voice you would like to hear. This is set once, before you enter.
          </p>
          <div className="mt-3 grid grid-cols-2 gap-2">
            {INTERVIEWER_VOICES.map((v) => {
              const active = voice === v.id;
              return (
                <label
                  key={v.id}
                  className={
                    "cursor-pointer rounded-md border p-3 transition-colors " +
                    (active
                      ? "border-accent bg-panel ring-1 ring-accent"
                      : "border-line bg-panel hover:border-muted")
                  }
                >
                  <input
                    type="radio"
                    name="interviewer-voice"
                    className="sr-only"
                    value={v.id}
                    checked={active}
                    disabled={starting}
                    onChange={() => setVoice(v.id)}
                  />
                  <span className="flex items-center gap-2 font-medium text-ink">
                    <span
                      aria-hidden
                      className={
                        "inline-block h-2.5 w-2.5 rounded-full border " +
                        (active ? "border-accent bg-accent" : "border-line bg-paper")
                      }
                    />
                    {v.name}
                  </span>
                  <span className="mt-0.5 block pl-[18px] text-xs text-muted">{v.blurb}</span>
                </label>
              );
            })}
          </div>
        </fieldset>

        <button
          onClick={onLeave}
          className="mt-4 text-sm text-muted underline-offset-2 hover:text-ink hover:underline"
        >
          Leave
        </button>
      </div>

      <Modal
        open={leaveOpen}
        onClose={closeLeave}
        title="Leave the waiting room"
        footer={
          <>
            <Button variant="ghost" onClick={closeLeave}>
              Stay
            </Button>
            <Button variant="secondary" onClick={() => router.push(leaveTo)}>
              Leave
            </Button>
          </>
        }
      >
        <p className="text-ink-soft">
          Your booking is kept. You can come back any time before your slot.
        </p>
      </Modal>
    </StepCard>
  );
}
