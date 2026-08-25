import type { Metadata } from "next";
import Link from "next/link";
import { ButtonLink } from "../../components/ui";

export const metadata: Metadata = {
  title: "AI Interview — voice interviews with evidence",
  description:
    "A live voice AI conducts structured hiring interviews; every score cites its evidence; a human reviews every assessment.",
};

/** Landing — the product's front door. Instrument aesthetic (DESIGN.md):
 * ruled rails, monospace ticks, one accent. Static and honest: no invented
 * metrics, no data fetched (private reads require login by design). */

const PILLARS = [
  {
    title: "A real interview, not a quiz",
    body: "A live voice interviewer that listens, probes claims two levels deep, and adapts — with coding, SQL, case, and system-design rounds worked in real tools: a collaborative editor, exhibits with a calc scratchpad, a whiteboard.",
  },
  {
    title: "Decisions that show their work",
    body: "A second model evaluates the transcript against your rubric. Every competency score cites the exact moment behind it — two clicks from any number to the replay. Uncited scores are flagged, never hidden.",
  },
  {
    title: "People stay in charge",
    body: "Borderline and degraded results route to your review queue. Overrides require written rationale, the record is append-only, and AI scores ship in shadow mode until they agree with your human reviewers.",
  },
];

const PROOF = [
  { k: "Complete record", v: "every word, keystroke, and hint — replayable" },
  { k: "Consent first", v: "nothing records before the candidate agrees" },
  { k: "Numbers checked by code", v: "SQL re-executed, math verified" },
  { k: "Calibrated", v: "AI scores earn trust against your reviewers first" },
];

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-paper text-ink">
      {/* nav */}
      <header className="sticky top-0 z-40 border-b border-line bg-paper/95 backdrop-blur">
        <nav className="mx-auto flex h-14 max-w-[1080px] items-center gap-6 px-5">
          <Link href="/" className="flex items-center gap-2.5 font-display text-md font-semibold">
            <span aria-hidden className="h-5 w-5 rounded-sm bg-accent" />
            AI Interview
          </Link>
          <a href="#how" className="hidden text-base text-muted hover:text-ink sm:block">
            How it works
          </a>
          <a href="#trust" className="hidden text-base text-muted hover:text-ink sm:block">
            Why trust it
          </a>
          <Link href="/guide" className="hidden text-base text-muted hover:text-ink sm:block">
            Platform guide
          </Link>
          <div className="ml-auto flex items-center gap-2">
            <ButtonLink href="/login" variant="secondary" size="sm">
              Log in
            </ButtonLink>
          </div>
        </nav>
      </header>

      {/* hero */}
      <section className="mx-auto max-w-[1080px] px-5 pb-10 pt-12 md:pt-10">
        <div className="max-w-[680px]">
          <p className="font-mono text-xs uppercase tracking-widest text-accent">
            Structured hiring interviews, conducted by voice AI
          </p>
          <h1 className="mt-3 font-display text-3xl font-semibold leading-tight">
            Interviews that run themselves.
            <br />
            Decisions that explain themselves.
          </h1>
          <p className="mt-4 max-w-[560px] text-md leading-relaxed text-ink-soft">
            A live voice AI conducts the interview — coding, SQL, case, system design,
            behavioral. A second model scores it with cited evidence. A human reviews
            every assessment before anything is decided.
          </p>
          <div className="mt-6 flex flex-wrap items-center gap-3">
            <ButtonLink href="/login">Open the console</ButtonLink>
            <a
              href="#invite"
              className="inline-flex h-11 items-center rounded-md px-4 text-base font-medium text-ink-soft underline-offset-4 hover:text-ink hover:underline"
            >
              I received an interview invite
            </a>
          </div>
        </div>
      </section>

      {/* pillars */}
      <section id="how" className="scroll-mt-20 border-t border-line bg-panel">
        <div className="mx-auto grid max-w-[1080px] gap-6 px-5 py-12 md:grid-cols-3">
          {PILLARS.map((p) => (
            <div key={p.title}>
              <h2 className="font-display text-lg font-semibold">{p.title}</h2>
              <p className="mt-2 text-base leading-relaxed text-ink-soft">{p.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* trust strip */}
      <section id="trust" className="scroll-mt-20 border-t border-line">
        <div className="mx-auto max-w-[1080px] px-5 py-12">
          <h2 className="font-display text-lg font-semibold">Built for evidence</h2>
          <div className="mt-5 grid gap-px overflow-hidden rounded-lg border border-line bg-line sm:grid-cols-2">
            {PROOF.map((row) => (
              <div key={row.k} className="bg-panel p-4">
                <div className="font-mono text-sm font-semibold text-accent">{row.k}</div>
                <p className="mt-1 text-sm text-ink-soft">{row.v}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* invited candidates */}
      <section id="invite" className="scroll-mt-20 border-t border-line bg-panel">
        <div className="mx-auto max-w-[1080px] px-5 py-12">
          <div className="max-w-[560px]">
            <h2 className="font-display text-lg font-semibold">Invited to interview?</h2>
            <p className="mt-2 text-md leading-relaxed text-ink-soft">
              Your invitation email contains a personal link — open it and the flow walks
              you through everything: what to expect, your consent, picking a time, and a
              system check before you begin. No account or download needed. You will need
              Chrome or Edge, a microphone, and a quiet room.
            </p>
            <p className="mt-3 text-base text-muted">
              Want to try it first?{" "}
              <Link href="/login" className="text-accent underline-offset-2 hover:underline">
                Create a free candidate account
              </Link>{" "}
              and take a ten-minute practice interview — no stakes, nothing shared.
            </p>
          </div>
        </div>
      </section>

      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-[1080px] flex-wrap items-center gap-4 px-5 py-6 text-sm text-muted">
          <span className="flex items-center gap-2 font-display font-semibold text-ink">
            <span aria-hidden className="h-4 w-4 rounded-sm bg-accent" />
            AI Interview
          </span>
          <span aria-hidden>·</span>
          <Link href="/guide" className="hover:text-ink">Platform guide</Link>
          <span aria-hidden>·</span>
          <Link href="/login" className="hover:text-ink">Log in</Link>
          <span className="ml-auto font-mono text-xs">
            a human reviews every assessment
          </span>
        </div>
      </footer>
    </div>
  );
}
