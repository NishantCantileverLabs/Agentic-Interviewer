"use client";

import { useState } from "react";
import { CandidateShell } from "../../../../components/shells/CandidateShell";
import { Button } from "../../../../components/ui";
import { PortalScreen } from "../PortalScreen";

/** C10 — Completion. Terminal screen: what happens next, optional two-question
 * survey. No scores, signals, or performance language, ever (FRONTEND.md
 * rule 3 — this file imports nothing from evaluation/integrity). */
export default function DonePage() {
  const [surveyOpen, setSurveyOpen] = useState(false);
  const [sent, setSent] = useState(false);

  return (
    <PortalScreen>
      {(portal) => (
        <div className="rounded-lg border border-line bg-panel p-6 text-center">
          <h1 className="font-display text-xl font-semibold text-ink">
            You are all set, {portal.candidate_name.split(" ")[0]}
          </h1>
          <p className="mt-3 text-ink-soft">
            Thanks for talking with us. The team will review your interview and be in
            touch about next steps.
          </p>

          {!sent && !surveyOpen && (
            <button
              className="mt-5 text-sm text-muted underline-offset-2 hover:text-ink hover:underline"
              onClick={() => setSurveyOpen(true)}
            >
              Share feedback on the experience
            </button>
          )}

          {surveyOpen && !sent && (
            <SurveyForm onDone={() => setSent(true)} />
          )}
          {sent && <p className="mt-5 text-sm text-green">Thanks — feedback noted.</p>}
        </div>
      )}
    </PortalScreen>
  );
}

function SurveyForm({ onDone }: { onDone: () => void }) {
  const [ease, setEase] = useState<number | null>(null);
  const [fair, setFair] = useState<number | null>(null);

  return (
    <div className="mt-5 rounded-md border border-line bg-paper p-4 text-left">
      <SurveyRow
        label="How easy was the experience, technically?"
        value={ease}
        onPick={setEase}
      />
      <SurveyRow
        label="Did the interview feel like a fair chance to show your skills?"
        value={fair}
        onPick={setFair}
        className="mt-4"
      />
      <div className="mt-4 text-center">
        <Button
          size="sm"
          onClick={onDone}
          disabledReason={ease === null || fair === null ? "Pick a rating for both questions" : undefined}
        >
          Send feedback
        </Button>
      </div>
    </div>
  );
}

function SurveyRow({
  label,
  value,
  onPick,
  className,
}: {
  label: string;
  value: number | null;
  onPick: (n: number) => void;
  className?: string;
}) {
  return (
    <div className={className}>
      <div className="text-sm font-medium text-ink">{label}</div>
      <div className="mt-2 flex gap-1.5" role="radiogroup" aria-label={label}>
        {[1, 2, 3, 4, 5].map((n) => (
          <button
            key={n}
            role="radio"
            aria-checked={value === n}
            onClick={() => onPick(n)}
            className={
              value === n
                ? "h-8 w-8 rounded-md bg-accent font-mono text-sm text-white"
                : "h-8 w-8 rounded-md border border-line bg-panel font-mono text-sm text-ink hover:border-accent"
            }
          >
            {n}
          </button>
        ))}
      </div>
    </div>
  );
}
