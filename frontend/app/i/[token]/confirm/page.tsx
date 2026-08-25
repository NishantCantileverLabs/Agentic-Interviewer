"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Button, ButtonLink, Modal } from "../../../../components/ui";
import { decline, RESCHEDULE_MAX } from "../../../../lib/portal";
import { PortalScreen, StepCard } from "../PortalScreen";

const JOIN_WINDOW_MIN = 10;

function icsFor(slotStart: string, slotEnd: string, title: string): string {
  const fmt = (iso: string) => iso.replace(/[-:]/g, "").replace(/\.\d+/, "");
  return [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//AI Interview//EN",
    "BEGIN:VEVENT",
    `DTSTART:${fmt(slotStart)}`,
    `DTEND:${fmt(slotEnd)}`,
    `SUMMARY:${title}`,
    "DESCRIPTION:Join from the interview link in your invitation email.",
    "END:VEVENT",
    "END:VCALENDAR",
  ].join("\r\n");
}

/** C5 — Confirmation: summary card, calendar file, reschedule, cancel. */
export default function ConfirmPage() {
  const { token } = useParams<{ token: string }>();
  const router = useRouter();
  const [cancelOpen, setCancelOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(t);
  }, []);

  return (
    <PortalScreen step={3}>
      {(portal) => {
        if (!portal.schedule) {
          return (
            <StepCard>
              <h1 className="font-display text-xl font-semibold text-ink">Almost there</h1>
              <p className="mt-3 text-ink-soft">You have not picked a time yet.</p>
              <div className="mt-4 text-center">
                <ButtonLink href={`/i/${token}/schedule`}>Pick a time</ButtonLink>
              </div>
            </StepCard>
          );
        }

        const start = new Date(portal.schedule.slot_start);
        const joinable = now >= start.getTime() - JOIN_WINDOW_MIN * 60_000;
        const atLimit = portal.schedule.reschedule_count >= RESCHEDULE_MAX;

        const downloadIcs = () => {
          const blob = new Blob(
            [icsFor(portal.schedule!.slot_start, portal.schedule!.slot_end, `Interview${portal.role_name ? `: ${portal.role_name}` : ""}`)],
            { type: "text/calendar" },
          );
          const a = document.createElement("a");
          a.href = URL.createObjectURL(blob);
          a.download = "interview.ics";
          a.click();
          URL.revokeObjectURL(a.href);
        };

        const doCancel = async () => {
          setBusy(true);
          try {
            await decline(token);
            router.push(`/i/${token}/declined`);
          } finally {
            setBusy(false);
          }
        };

        return (
          <StepCard>
            <h1 className="font-display text-xl font-semibold text-ink">You are booked</h1>
            <div className="mt-4 rounded-md border border-line bg-paper p-4">
              <div className="font-display text-lg font-semibold text-ink">
                {start.toLocaleString(undefined, { dateStyle: "full", timeStyle: "short" })}
              </div>
              <div className="mt-1 text-sm text-muted">
                {portal.role_name ? `${portal.role_name} · ` : ""}about 30 minutes ·
                voice conversation with hands-on rounds
              </div>
            </div>

            <div className="mt-5 flex flex-col items-center gap-2">
              {joinable ? (
                <ButtonLink href={`/i/${token}/join`}>Join interview</ButtonLink>
              ) : (
                <Button disabledReason={`Joining opens ${JOIN_WINDOW_MIN} minutes before your slot`}>
                  Join interview
                </Button>
              )}
              <div className="mt-1 flex items-center gap-4 text-sm">
                <button
                  onClick={downloadIcs}
                  className="text-accent underline-offset-2 hover:underline"
                >
                  Add to calendar
                </button>
                {atLimit ? (
                  <span className="text-muted">
                    Reschedule limit reached. Contact the team to change your time
                  </span>
                ) : (
                  <Link
                    href={`/i/${token}/schedule`}
                    className="text-muted underline-offset-2 hover:text-ink hover:underline"
                  >
                    Reschedule ({portal.schedule.reschedule_count} of {RESCHEDULE_MAX} used)
                  </Link>
                )}
                <button
                  onClick={() => setCancelOpen(true)}
                  className="text-muted underline-offset-2 hover:text-rust hover:underline"
                >
                  Cancel interview
                </button>
              </div>
            </div>

            <Modal
              open={cancelOpen}
              onClose={() => setCancelOpen(false)}
              title="Cancel this interview"
              footer={
                <>
                  <Button variant="ghost" onClick={() => setCancelOpen(false)}>
                    Keep my booking
                  </Button>
                  <Button variant="danger" onClick={doCancel} loading={busy}>
                    Cancel interview
                  </Button>
                </>
              }
            >
              <p className="text-ink-soft">
                This withdraws you from the process and notifies the team. If you only need
                a different time, choose Reschedule instead.
              </p>
            </Modal>
          </StepCard>
        );
      }}
    </PortalScreen>
  );
}
