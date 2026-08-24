"use client";

import { CandidateShell } from "../../../../components/shells/CandidateShell";
import { CONTACT_EMAIL, ORG_NAME } from "../../../../lib/brand";

/** Polite end screen (declined / withdrawn). Terminal — no navigation. */
export default function DeclinedPage() {
  return (
    <CandidateShell orgName={ORG_NAME} contactEmail={CONTACT_EMAIL}>
      <div className="rounded-lg border border-line bg-panel p-6 text-center">
        <h1 className="font-display text-xl font-semibold text-ink">
          Thanks for letting us know
        </h1>
        <p className="mt-3 text-ink-soft">
          You will not be interviewed, and the team has been notified. If you change your
          mind, contact them using the link below and they can send a fresh invitation.
        </p>
      </div>
    </CandidateShell>
  );
}
