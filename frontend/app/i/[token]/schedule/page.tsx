"use client";

import { useParams, useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { Button, Select } from "../../../../components/ui";
import { RESCHEDULE_MAX, scheduleSlot } from "../../../../lib/portal";
import { PortalScreen, StepCard } from "../PortalScreen";

const TIMEZONES = [
  "Asia/Kolkata",
  "Asia/Singapore",
  "Europe/London",
  "Europe/Berlin",
  "America/New_York",
  "America/Chicago",
  "America/Los_Angeles",
  "Australia/Sydney",
  "UTC",
];

/** Half-hour slots 09:00–17:30 local for the next 7 days, as instants.
 * Switching timezone re-labels the same instants (never shifts them). */
function buildSlots(): Date[] {
  const out: Date[] = [];
  const now = new Date();
  for (let d = 0; d < 7; d++) {
    for (let h = 9; h < 18; h++) {
      for (const m of [0, 30]) {
        const t = new Date(now.getFullYear(), now.getMonth(), now.getDate() + d, h, m);
        if (t.getTime() > now.getTime() + 5 * 60_000) out.push(t);
      }
    }
  }
  return out;
}

function labelIn(tz: string, d: Date, opts: Intl.DateTimeFormatOptions): string {
  return new Intl.DateTimeFormat(undefined, { ...opts, timeZone: tz }).format(d);
}

/** C4 — Schedule: date strip + slot grid in the candidate's timezone. */
export default function SchedulePage() {
  const { token } = useParams<{ token: string }>();
  const router = useRouter();
  const detected = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const [tz, setTz] = useState(detected);
  const [dayIdx, setDayIdx] = useState(0);
  const [picked, setPicked] = useState<Date | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const slots = useMemo(buildSlots, []);
  const days = useMemo(() => {
    const seen = new Map<string, Date>();
    for (const s of slots) {
      const key = labelIn(tz, s, { year: "numeric", month: "2-digit", day: "2-digit" });
      if (!seen.has(key)) seen.set(key, s);
    }
    return Array.from(seen.entries()).slice(0, 7);
  }, [slots, tz]);

  const dayKey = days[dayIdx]?.[0];
  const daySlots = slots.filter(
    (s) => labelIn(tz, s, { year: "numeric", month: "2-digit", day: "2-digit" }) === dayKey,
  );

  const confirm = async () => {
    if (!picked) return;
    setBusy(true);
    setError(null);
    try {
      await scheduleSlot(token, picked.toISOString());
      router.push(`/i/${token}/confirm`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  };

  return (
    <PortalScreen step={2}>
      {(portal) => {
        const atLimit = (portal.schedule?.reschedule_count ?? 0) >= RESCHEDULE_MAX;
        if (portal.schedule && atLimit) {
          return (
            <StepCard>
              <h1 className="font-display text-xl font-semibold text-ink">Pick your time</h1>
              <p className="mt-3 text-ink-soft">
                Your interview is set for{" "}
                <b>{labelIn(tz, new Date(portal.schedule.slot_start), { dateStyle: "full", timeStyle: "short" })}</b>{" "}
                and the reschedule limit has been reached. If this time no longer works,
                contact the team using the link below.
              </p>
              <div className="mt-4 text-center">
                <Button onClick={() => router.push(`/i/${token}/confirm`)}>
                  Review my booking
                </Button>
              </div>
            </StepCard>
          );
        }

        return (
          <StepCard>
            <h1 className="font-display text-xl font-semibold text-ink">Pick your time</h1>
            {portal.schedule && (
              <p className="mt-1 text-sm text-muted">
                Currently{" "}
                {labelIn(tz, new Date(portal.schedule.slot_start), {
                  dateStyle: "medium",
                  timeStyle: "short",
                })}{" "}
                — choosing a new slot reschedules ({portal.schedule.reschedule_count} of{" "}
                {RESCHEDULE_MAX} used).
              </p>
            )}

            <div className="mt-4 w-56">
              <Select
                label="Timezone"
                value={tz}
                onChange={(e) => setTz(e.target.value)}
                options={[detected, ...TIMEZONES.filter((z) => z !== detected)].map((z) => ({
                  value: z,
                  label: z.replace(/_/g, " "),
                }))}
              />
            </div>

            <div className="mt-4 flex gap-1 overflow-x-auto pb-1" role="tablist" aria-label="Day">
              {days.map(([key, sample], i) => (
                <button
                  key={key}
                  role="tab"
                  aria-selected={i === dayIdx}
                  onClick={() => {
                    setDayIdx(i);
                    setPicked(null);
                  }}
                  className={
                    i === dayIdx
                      ? "shrink-0 rounded-md bg-accent px-3 py-2 text-sm font-medium text-white"
                      : "shrink-0 rounded-md border border-line bg-panel px-3 py-2 text-sm text-ink-soft hover:border-accent"
                  }
                >
                  {labelIn(tz, sample, { weekday: "short", day: "numeric", month: "short" })}
                </button>
              ))}
            </div>

            {daySlots.length === 0 ? (
              <div className="mt-4 rounded-md bg-paper p-4 text-center text-muted">
                No times available on this day — pick another day, or contact the team to
                request more times.
              </div>
            ) : (
              <div className="mt-3 grid grid-cols-4 gap-2" role="listbox" aria-label="Time slot">
                {daySlots.map((s) => {
                  const selected = picked?.getTime() === s.getTime();
                  return (
                    <button
                      key={s.toISOString()}
                      role="option"
                      aria-selected={selected}
                      onClick={() => setPicked(s)}
                      className={
                        selected
                          ? "rounded-md bg-accent px-2 py-2 font-mono text-sm text-white"
                          : "rounded-md border border-line bg-panel px-2 py-2 font-mono text-sm text-ink hover:border-accent"
                      }
                    >
                      {labelIn(tz, s, { hour: "2-digit", minute: "2-digit" })}
                    </button>
                  );
                })}
              </div>
            )}

            {error && (
              <p role="alert" className="mt-3 text-sm text-rust">
                {error}
              </p>
            )}

            <div className="mt-5 text-center">
              <Button
                onClick={confirm}
                loading={busy}
                disabledReason={picked ? undefined : "Choose a time slot first"}
              >
                {picked
                  ? `Confirm ${labelIn(tz, picked, { weekday: "short", hour: "2-digit", minute: "2-digit" })}`
                  : "Confirm time"}
              </Button>
            </div>
          </StepCard>
        );
      }}
    </PortalScreen>
  );
}
