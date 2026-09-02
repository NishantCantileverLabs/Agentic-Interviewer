"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { ButtonLink } from "../../../components/ui";
import { PortalScreen, StepCard } from "./PortalScreen";

const EXPLAINER = [
  {
    title: "Talk with our AI interviewer",
    body: "A natural voice conversation. Take your time. Pauses to think are expected, and clarifying questions are welcome.",
  },
  {
    title: "Solve a problem in the editor",
    body: "Depending on the role: coding in your language of choice, SQL, a business case, or a whiteboard design.",
  },
  {
    title: "Your responses reviewed by the team",
    body: "A human reviews every assessment before any decision is made.",
  },
];

/** C2 — Landing: what to expect. One primary action. */
export default function LandingPage() {
  const { token } = useParams<{ token: string }>();
  return (
    <PortalScreen step={0}>
      {(portal) => (
        <StepCard>
          <h1 className="font-display text-xl font-semibold text-ink">
            Hi {portal.candidate_name.split(" ")[0]}, here is what to expect
          </h1>
          {portal.role_name && (
            <p className="mt-1 text-sm text-muted">Interview for {portal.role_name}</p>
          )}

          <ol className="mt-5 flex flex-col gap-4">
            {EXPLAINER.map((s, i) => (
              <li key={s.title} className="flex gap-3">
                <span
                  aria-hidden
                  className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-accent-tint font-mono text-sm text-accent"
                >
                  {i + 1}
                </span>
                <div>
                  <div className="font-medium text-ink">{s.title}</div>
                  <p className="mt-0.5 text-sm text-ink-soft">{s.body}</p>
                </div>
              </li>
            ))}
          </ol>

          <div className="mt-5 rounded-md bg-paper p-3 text-sm text-muted">
            You will need: Chrome or Edge, a working microphone, and a quiet room.
            About 30 minutes.
          </div>

          <div className="mt-5 flex flex-col items-center gap-2">
            <ButtonLink href={`/i/${token}/consent`}>Continue</ButtonLink>
            <Link
              href={`/i/${token}/join?check=only`}
              className="text-sm text-muted underline-offset-2 hover:text-ink hover:underline"
            >
              Check my device now
            </Link>
          </div>
        </StepCard>
      )}
    </PortalScreen>
  );
}
