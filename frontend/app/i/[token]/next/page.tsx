"use client";

import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "../../../../components/ui";
import { API } from "../../../../lib/portal";
import { PortalScreen, StepCard } from "../PortalScreen";

const BREAK_SECONDS = 120;

interface AdvanceResult {
  gate_state: "advancing" | "awaiting_review" | "ended" | "completed";
  round_index?: number;
  round_type?: string;
  session_id?: string;
  interview_path?: string;
  reason?: string;
}

/** C9. Round transition. Asks the pipeline orchestrator what happens next:
 * another round (with an optional 2-minute break), a review gate, or done. */
export default function NextRoundPage() {
  const { token } = useParams<{ token: string }>();
  const router = useRouter();
  const [next, setNext] = useState<AdvanceResult | null>(null);
  const [checked, setChecked] = useState(false);
  const [secondsLeft, setSecondsLeft] = useState(BREAK_SECONDS);
  const started = useRef(false);

  const advance = useCallback(async () => {
    try {
      const resp = await fetch(`${API}/candidacies/${token}/advance`, { method: "POST" });
      if (resp.status === 404) {
        // single-interview candidacy. No pipeline, straight to completion
        router.replace(`/i/${token}/done`);
        return;
      }
      const data = (await resp.json()) as AdvanceResult;
      if (data.gate_state === "completed" || data.gate_state === "ended") {
        router.replace(`/i/${token}/done`);
        return;
      }
      setNext(data);
    } finally {
      setChecked(true);
    }
  }, [token, router]);

  useEffect(() => {
    void advance();
  }, [advance]);

  const startNext = useCallback(() => {
    if (started.current || !next?.interview_path || !next.session_id) return;
    started.current = true;
    const legacy = new URLSearchParams(next.interview_path.split("?")[1] ?? "");
    router.push(
      `/i/${token}/room?session=${next.session_id}&candidate_token=${legacy.get("candidate_token") ?? ""}`,
    );
  }, [next, router, token]);

  // optional break: counts down and auto-starts at zero
  useEffect(() => {
    if (!next || next.gate_state !== "advancing") return;
    const t = setInterval(() => setSecondsLeft((s) => Math.max(0, s - 1)), 1000);
    return () => clearInterval(t);
  }, [next]);

  useEffect(() => {
    if (secondsLeft === 0) startNext();
  }, [secondsLeft, startNext]);

  return (
    <PortalScreen>
      {() => {
        if (!checked) {
          return (
            <StepCard>
              <p className="text-center text-muted" aria-busy="true">
                Checking what comes next…
              </p>
            </StepCard>
          );
        }

        if (next?.gate_state === "awaiting_review") {
          return (
            <StepCard>
              <h1 className="text-center font-display text-xl font-semibold text-ink">
                Round complete
              </h1>
              <p className="mt-3 text-center text-ink-soft">
                Nice work. The team will review this round and follow up by email.
                Nothing more to do today.
              </p>
            </StepCard>
          );
        }

        if (next?.gate_state === "advancing" && next.round_type) {
          const mm = String(Math.floor(secondsLeft / 60)).padStart(2, "0");
          const ss = String(secondsLeft % 60).padStart(2, "0");
          return (
            <StepCard>
              <h1 className="text-center font-display text-xl font-semibold text-ink">
                Round complete ✓
              </h1>
              <p className="mt-2 text-center text-ink-soft">
                Next up: <b className="capitalize">{next.round_type.replace(/_/g, " ")}</b>.
                Take a short break if you need one.
              </p>
              <div
                className="mt-4 text-center font-display text-2xl font-semibold tabular-nums text-muted"
                aria-label="Break time remaining"
              >
                {mm}:{ss}
              </div>
              <div className="mt-4 text-center">
                <Button onClick={startNext}>Start next round</Button>
              </div>
              <p className="mt-2 text-center text-xs text-muted">
                The next round starts automatically when the timer ends.
              </p>
            </StepCard>
          );
        }

        return (
          <StepCard>
            <p className="text-center text-muted">Wrapping up, one moment.</p>
          </StepCard>
        );
      }}
    </PortalScreen>
  );
}
