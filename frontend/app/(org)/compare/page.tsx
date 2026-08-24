"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { ButtonLink } from "../../../components/ui";
import { type CompareSide, OrgApiError, compareSessions } from "../../../lib/org";

/** Compare — same-role side-by-side. Cross-role comparison is refused by the
 * backend, and the refusal is shown honestly, never fudged. */
export default function ComparePage() {
  return (
    <Suspense>
      <CompareInner />
    </Suspense>
  );
}

function CompareInner() {
  const params = useSearchParams();
  const a = params.get("a");
  const b = params.get("b");
  const [data, setData] = useState<{ a: CompareSide; b: CompareSide } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!a || !b) return;
    compareSessions(a, b)
      .then(setData)
      .catch((e) =>
        setError(e instanceof OrgApiError ? e.message : "Could not load the comparison"),
      );
  }, [a, b]);

  if (!a || !b) {
    return (
      <div className="mx-auto max-w-[700px] text-center">
        <h1 className="font-display text-xl font-semibold text-ink">Compare</h1>
        <p className="mt-2 text-muted">
          Pick two candidates from the Candidates list and press Compare.
        </p>
        <div className="mt-4">
          <ButtonLink href="/candidates" variant="secondary">
            Go to Candidates
          </ButtonLink>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="mx-auto max-w-[700px] text-center">
        <h1 className="font-display text-xl font-semibold text-ink">Compare</h1>
        <p role="alert" className="mt-3 text-rust">
          {error}
        </p>
      </div>
    );
  }

  if (!data) {
    return <p className="text-muted" aria-busy="true">Loading both evaluations…</p>;
  }

  const compNames = Array.from(
    new Set([
      ...Object.keys(data.a.rubric?.competencies ?? {}),
      ...Object.keys(data.b.rubric?.competencies ?? {}),
    ]),
  );

  return (
    <div className="mx-auto max-w-[1000px]">
      <h1 className="font-display text-xl font-semibold text-ink">Compare</h1>
      <div className="mt-4 overflow-x-auto rounded-lg border border-line">
        <table className="w-full bg-panel text-base">
          <thead>
            <tr className="border-b border-line bg-paper text-left">
              <th className="px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-muted">
                Competency
              </th>
              {[data.a, data.b].map((side) => (
                <th key={side.session_id} className="px-4 py-2.5">
                  <div className="font-medium normal-case text-ink">{side.candidate_label}</div>
                  <a
                    href={`/sessions/${side.session_id}`}
                    className="font-mono text-xs font-normal text-accent hover:underline"
                  >
                    open session →
                  </a>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {compNames.map((name) => {
              const ca = data.a.rubric?.competencies?.[name];
              const cb = data.b.rubric?.competencies?.[name];
              return (
                <tr key={name} className="border-b border-line last:border-0">
                  <td className="px-4 py-3 capitalize text-ink">{name.replace(/_/g, " ")}</td>
                  {[ca, cb].map((c, i) => (
                    <td key={i} className="px-4 py-3">
                      <span className="font-display text-lg font-semibold text-ink">
                        {typeof c?.score_1_to_5 === "number" ? `${c.score_1_to_5}/5` : "—"}
                      </span>
                      {c?.evidence?.[0]?.quote && (
                        <p className="mt-1 max-w-72 text-sm text-muted">
                          “{c.evidence[0].quote}”
                        </p>
                      )}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
