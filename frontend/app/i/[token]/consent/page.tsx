"use client";

import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { Button, Checkbox, Modal } from "../../../../components/ui";
import { decline, recordConsent } from "../../../../lib/portal";
import { PortalScreen, StepCard } from "../PortalScreen";

const ITEM_TITLES: Record<string, string> = {
  audio_processing: "Audio recording and AI-assisted assessment",
  video_proctoring: "Camera-based integrity monitoring",
  data_retention: "Data retention and your rights",
};

/** C3 — Consent: policy sections come from the API with their version; the
 * consent write resolves before navigation (spec requirement). */
export default function ConsentPage() {
  const { token } = useParams<{ token: string }>();
  const router = useRouter();
  const [agree, setAgree] = useState<Record<string, boolean> | null>(null);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [declineOpen, setDeclineOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  return (
    <PortalScreen step={1}>
      {(portal) => {
        // A returning candidate's recorded consents pre-fill the boxes — they
        // never re-tick what they already granted under this policy version.
        if (agree === null) {
          setAgree({ ...portal.consents });
          return null;
        }
        const requiredOk = portal.required_items.every((i) => agree[i]);

        const submit = async () => {
          setBusy(true);
          setError(null);
          try {
            const items = Object.fromEntries(
              Object.keys(portal.policies).map((k) => [k, !!agree[k]]),
            );
            await recordConsent(token, items);
            // practice interviews skip scheduling — straight to the system check
            router.push(
              portal.source === "demo" ? `/i/${token}/join` : `/i/${token}/schedule`,
            );
          } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
            setBusy(false);
          }
        };

        const doDecline = async () => {
          setBusy(true);
          try {
            await decline(token);
            router.push(`/i/${token}/declined`);
          } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
            setBusy(false);
          }
        };

        return (
          <StepCard>
            <h1 className="font-display text-xl font-semibold text-ink">Your consent</h1>
            <p className="mt-1 text-sm text-muted">
              Policy version <span className="font-mono">{portal.policy_version}</span>.
              Nothing proceeds without your agreement.
            </p>

            <div className="mt-5 flex flex-col gap-3">
              {Object.entries(portal.policies).map(([item, text]) => {
                const required = portal.required_items.includes(item);
                const isOpen = !!expanded[item];
                return (
                  <div key={item} className="rounded-md border border-line p-3">
                    <Checkbox
                      checked={!!agree[item]}
                      onChange={(e) => setAgree((a) => ({ ...a, [item]: e.target.checked }))}
                      label={
                        <span className="font-medium text-ink">
                          {ITEM_TITLES[item] ?? item}
                          {required && <span className="ml-1 text-muted">(required)</span>}
                        </span>
                      }
                    />
                    <button
                      className="ml-6 mt-1 text-sm text-accent underline-offset-2 hover:underline"
                      onClick={() => setExpanded((x) => ({ ...x, [item]: !isOpen }))}
                      aria-expanded={isOpen}
                    >
                      {isOpen ? "Hide full policy" : "View full policy"}
                    </button>
                    {isOpen && <p className="ml-6 mt-2 text-sm text-ink-soft">{text}</p>}
                  </div>
                );
              })}
            </div>

            {error && (
              <p role="alert" className="mt-3 text-sm text-rust">
                {error}
              </p>
            )}

            <div className="mt-5 flex flex-col items-center gap-2">
              <Button
                onClick={submit}
                loading={busy}
                disabledReason={
                  requiredOk ? undefined : "The required items must be checked to continue"
                }
              >
                I agree and continue
              </Button>
              <button
                className="text-sm text-muted underline-offset-2 hover:text-ink hover:underline"
                onClick={() => setDeclineOpen(true)}
              >
                I do not wish to proceed
              </button>
            </div>

            <Modal
              open={declineOpen}
              onClose={() => setDeclineOpen(false)}
              title="Decline this interview"
              footer={
                <>
                  <Button variant="ghost" onClick={() => setDeclineOpen(false)}>
                    Go back
                  </Button>
                  <Button variant="danger" onClick={doDecline} loading={busy}>
                    Decline interview
                  </Button>
                </>
              }
            >
              <p className="text-ink-soft">
                No problem — the team will be notified and this link will close. You can
                always contact them if you change your mind.
              </p>
            </Modal>
          </StepCard>
        );
      }}
    </PortalScreen>
  );
}
