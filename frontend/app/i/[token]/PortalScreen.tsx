"use client";

import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { CandidateShell } from "../../../components/shells/CandidateShell";
import { Button } from "../../../components/ui";
import { getPortal, type Portal, PortalError } from "../../../lib/portal";

export const STEPS = ["What to expect", "Consent", "Schedule", "Confirm"];
const DEMO_STEPS = ["What to expect", "Consent", "Interview"];

import { CONTACT_EMAIL as CONTACT, ORG_NAME } from "../../../lib/brand";

interface PortalScreenProps {
  step?: number;
  /** which §7 candidate surfaces this page serves; anything else redirects */
  children: (portal: Portal, refresh: () => Promise<void>) => React.ReactNode;
}

/** Shared frame for every /i/[token] page: fetches the candidacy, resolves the
 * token states (valid / expired / withdrawn / completed) with their own copy —
 * no dead ends — and routes by status per §7. */
export function PortalScreen({ step, children }: PortalScreenProps) {
  const { token } = useParams<{ token: string }>();
  const router = useRouter();
  const [portal, setPortal] = useState<Portal | null>(null);
  const [error, setError] = useState<PortalError | null>(null);

  const refresh = useCallback(async () => {
    try {
      setPortal(await getPortal(token));
      setError(null);
    } catch (e) {
      setError(e instanceof PortalError ? e : new PortalError("network", String(e)));
    }
  }, [token]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // §7 routing: terminal states own their screens regardless of the URL step
  useEffect(() => {
    if (!portal) return;
    const path = window.location.pathname;
    if (portal.status === "withdrawn" && !path.endsWith("/declined")) {
      router.replace(`/i/${token}/declined`);
    } else if (
      ["completed", "in_review", "reviewed"].includes(portal.status) &&
      !path.endsWith("/done")
    ) {
      router.replace(`/i/${token}/done`);
    }
  }, [portal, router, token]);

  if (error?.kind === "not_found") {
    return (
      <CandidateShell orgName={ORG_NAME} contactEmail={CONTACT}>
        <div className="rounded-lg border border-line bg-panel p-6 text-center">
          <h1 className="font-display text-xl font-semibold text-ink">This link has expired</h1>
          <p className="mt-3 text-ink-soft">
            The invitation may have been used already, or it is no longer valid. The team
            that invited you can send a fresh link.
          </p>
        </div>
      </CandidateShell>
    );
  }

  if (error) {
    return (
      <CandidateShell orgName={ORG_NAME} contactEmail={CONTACT}>
        <div className="rounded-lg border border-line bg-panel p-6 text-center">
          <h1 className="font-display text-xl font-semibold text-ink">
            Something went wrong on our side
          </h1>
          <p className="mt-3 text-ink-soft">{error.message}</p>
          <div className="mt-4">
            <Button onClick={() => void refresh()}>Try again</Button>
          </div>
        </div>
      </CandidateShell>
    );
  }

  if (!portal) {
    return (
      <CandidateShell orgName={ORG_NAME} contactEmail={CONTACT} steps={STEPS} currentStep={step ?? 0}>
        <div
          className="rounded-lg border border-line bg-panel p-6 text-center text-muted"
          aria-busy="true"
        >
          Loading…
        </div>
      </CandidateShell>
    );
  }

  const steps = portal.source === "demo" ? DEMO_STEPS : STEPS;
  return (
    <CandidateShell
      orgName={ORG_NAME}
      contactEmail={CONTACT}
      steps={step === undefined ? undefined : steps}
      currentStep={step}
    >
      {children(portal, refresh)}
    </CandidateShell>
  );
}

/** Card wrapper used by every step — one screen, one decision. */
export function StepCard({ children }: { children: React.ReactNode }) {
  return <div className="rounded-lg border border-line bg-panel p-6">{children}</div>;
}
