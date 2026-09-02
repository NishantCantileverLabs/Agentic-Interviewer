import { cx } from "../../lib/cx";

export interface CandidateShellProps {
  children: React.ReactNode;
  /** org branding — name always, logo when configured */
  orgName: string;
  contactEmail?: string;
  /** multi-step progress: labels + current index. Rendered as a ticked rail
   * (the signature element), not dots. Omit on terminal screens. */
  steps?: string[];
  currentStep?: number;
}

/** The candidate surface: centered, max 560px, no navigation chrome, one
 * decision per screen. Calm by construction (FRONTEND.md). */
export function CandidateShell({
  children,
  orgName,
  contactEmail,
  steps,
  currentStep = 0,
}: CandidateShellProps) {
  return (
    <div className="flex min-h-screen flex-col items-center bg-paper px-4 py-8">
      <header className="mb-6 flex w-full max-w-[560px] items-center gap-2.5">
        <span aria-hidden className="h-5 w-5 rounded-sm bg-accent" />
        <span className="font-display text-md font-semibold text-ink">{orgName}</span>
      </header>

      {steps && steps.length > 0 && (
        <nav aria-label="Progress" className="mb-6 w-full max-w-[560px]">
          <ol className="flex items-center">
            {steps.map((label, i) => {
              const done = i < currentStep;
              const now = i === currentStep;
              return (
                <li key={label} className={cx("flex items-center", i > 0 && "flex-1")}>
                  {i > 0 && (
                    <span
                      aria-hidden
                      className={cx("h-px flex-1", done || now ? "bg-accent" : "bg-line")}
                    />
                  )}
                  <span
                    aria-current={now ? "step" : undefined}
                    title={label}
                    className={cx(
                      "mx-1 flex h-2 w-2 shrink-0 rounded-full",
                      done && "bg-accent",
                      now && "bg-accent ring-4 ring-accent-tint",
                      !done && !now && "bg-line",
                    )}
                  />
                </li>
              );
            })}
          </ol>
          <p className="mt-2 text-center text-sm text-muted">
            Step {Math.min(currentStep + 1, steps.length)} of {steps.length} ·{" "}
            {steps[Math.min(currentStep, steps.length - 1)]}
          </p>
        </nav>
      )}

      <main className="w-full max-w-[560px] flex-1">{children}</main>

      <footer className="mt-8 w-full max-w-[560px] border-t border-line pt-4 text-center text-sm text-muted">
        Questions?{" "}
        {contactEmail ? (
          <a href={`mailto:${contactEmail}`} className="text-accent underline-offset-2 hover:underline">
            Contact {orgName}
          </a>
        ) : (
          <span>Contact {orgName}</span>
        )}
      </footer>
    </div>
  );
}
