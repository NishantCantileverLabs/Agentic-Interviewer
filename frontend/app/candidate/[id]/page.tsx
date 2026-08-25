"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import "../../interview/room.css";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface Portal {
  id: string;
  candidate_name: string;
  status: string;
  schedule: { slot_start: string; reschedule_count: number } | null;
  policy_version: string;
  policies: Record<string, string>;
  required_items: string[];
  consents: Record<string, boolean>;
}

const ITEM_LABELS: Record<string, string> = {
  audio_processing: "Audio recording & AI-assisted assessment (required)",
  video_proctoring: "Camera-based integrity monitoring (not used by this organization)",
  data_retention: "Data retention & your rights (required)",
};

const STEPS = ["welcome", "consent", "schedule", "begin"] as const;
type Step = (typeof STEPS)[number];

/** T11 — candidate guided flow. One screen, one decision: welcome →
 * consent → schedule → begin. The consent gate is API-enforced; this
 * page is just the honest surface. */
export default function CandidatePortal() {
  const { id } = useParams<{ id: string }>();
  const [portal, setPortal] = useState<Portal | null>(null);
  const [step, setStep] = useState<Step>("welcome");
  const [slot, setSlot] = useState("");
  const [agree, setAgree] = useState<Record<string, boolean>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const r = await fetch(`${API}/candidacies/${id}`);
    if (r.ok) setPortal(await r.json());
    else setError("This invitation link was not found or has expired.");
  }, [id]);

  useEffect(() => { void load(); }, [load]);

  const schedule = async () => {
    setError(null);
    const r = await fetch(`${API}/candidacies/${id}/schedule`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ slot_start: new Date(slot).toISOString() }),
    });
    if (!r.ok) return setError(await r.text());
    await load();
    setStep("begin");
  };

  const submitConsent = async () => {
    setError(null);
    setBusy(true);
    try {
      const items = Object.fromEntries(
        Object.keys(portal?.policies ?? {}).map((k) => [k, !!agree[k]]),
      );
      const c = await fetch(`${API}/candidacies/${id}/consent`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ items }),
      });
      if (!c.ok) throw new Error(await c.text());
      setStep("schedule");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const startInterview = async () => {
    setError(null);
    setBusy(true);
    try {
      const s = await fetch(`${API}/candidacies/${id}/start-interview`, { method: "POST" });
      if (!s.ok) throw new Error(await s.text());
      const data = (await s.json()) as { interview_path: string };
      window.location.assign(data.interview_path);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  };

  if (!portal) {
    return (
      <main className="lobby">
        <div className="lobby-card">
          <h1>{error ? "Hmm." : "Loading…"}</h1>
          {error && <p className="error">{error}</p>}
          {error && (
            <p className="contact-foot">
              Questions? Contact the team that invited you.
            </p>
          )}
        </div>
      </main>
    );
  }

  const requiredOk = portal.required_items.every((i) => agree[i]);
  const stepIdx = STEPS.indexOf(step);

  return (
    <main className="lobby">
      <div className="lobby-card" style={{ maxWidth: 560, textAlign: "left" }}>
        <div className="step-dots">
          {STEPS.map((s, i) => (
            <span key={s} className={i < stepIdx ? "done" : i === stepIdx ? "now" : ""} />
          ))}
        </div>

        {step === "welcome" && (
          <>
            <h1 style={{ textAlign: "center" }}>Hi {portal.candidate_name} 👋</h1>
            <p style={{ textAlign: "center" }}>
              Here&apos;s what to expect from your interview. No trick surprises.
            </p>
            <div className="expect-grid">
              <div className="expect-item">
                <span className="n">1</span>
                <div>
                  <b>Talk with our AI interviewer</b>
                  <span>
                    A natural voice conversation about your experience. Think aloud, take your
                    time. Pauses are expected, and clarifying questions are welcome.
                  </span>
                </div>
              </div>
              <div className="expect-item">
                <span className="n">2</span>
                <div>
                  <b>Hands-on rounds</b>
                  <span>
                    Depending on the role: coding in your language of choice, SQL, a business
                    case, or a whiteboard design. 30–60 minutes total.
                  </span>
                </div>
              </div>
              <div className="expect-item">
                <span className="n">3</span>
                <div>
                  <b>A human reviews everything</b>
                  <span>
                    Your responses are assessed with evidence-cited scoring, and a human
                    reviews every automated assessment before any decision.
                  </span>
                </div>
              </div>
            </div>
            <p style={{ fontSize: 13, color: "var(--faint)", marginTop: 14 }}>
              You&apos;ll need: Chrome or Edge, a working microphone, and a quiet room.
            </p>
            <div style={{ textAlign: "center" }}>
              <button className="start-btn" onClick={() => setStep("consent")}>
                Continue
              </button>
            </div>
          </>
        )}

        {step === "consent" && (
          <>
            <h1 style={{ textAlign: "center" }}>Your consent</h1>
            <p style={{ textAlign: "center", fontSize: 13.5 }}>
              Policy version {portal.policy_version}. Nothing proceeds without your agreement.
            </p>
            {Object.entries(portal.policies).map(([item, text]) => (
              <div key={item} className="consent-item">
                <label>
                  <input type="checkbox" checked={!!agree[item]}
                    onChange={(e) => setAgree((a) => ({ ...a, [item]: e.target.checked }))} />
                  <span>
                    <b>{ITEM_LABELS[item] ?? item}</b>
                    <span className="policy-text">{text}</span>
                  </span>
                </label>
              </div>
            ))}
            <div style={{ textAlign: "center" }}>
              <button className="start-btn" onClick={submitConsent}
                disabled={busy || !requiredOk}>
                {busy ? "Saving…" : "I agree & continue"}
              </button>
              {!requiredOk && (
                <p style={{ fontSize: 12.5, color: "var(--faint)" }}>
                  The required items must be checked to proceed.
                </p>
              )}
            </div>
          </>
        )}

        {step === "schedule" && (
          <>
            <h1 style={{ textAlign: "center" }}>Pick your time</h1>
            {portal.schedule && (
              <p style={{ color: "var(--ok)", textAlign: "center" }}>
                ✓ Currently scheduled for{" "}
                {new Date(portal.schedule.slot_start).toLocaleString()}
                {" "}(rescheduled {portal.schedule.reschedule_count}×, max 2)
              </p>
            )}
            <p style={{ textAlign: "center", fontSize: 13.5 }}>
              Choose a time that works for you, or start right away.
            </p>
            <div style={{ display: "flex", gap: 10, justifyContent: "center", margin: "14px 0" }}>
              <input type="datetime-local" className="notes" style={{ maxWidth: 260 }}
                value={slot} onChange={(e) => setSlot(e.target.value)} />
            </div>
            <div style={{ textAlign: "center" }}>
              <button className="start-btn" onClick={schedule} disabled={!slot}>
                Confirm this time
              </button>
              <br />
              <button className="ghost-btn" onClick={() => setStep("begin")}>
                {portal.schedule ? "Keep my current time" : "Skip, I'm ready now"}
              </button>
            </div>
          </>
        )}

        {step === "begin" && (
          <>
            <h1 style={{ textAlign: "center" }}>You&apos;re all set</h1>
            <p style={{ textAlign: "center" }}>
              {portal.schedule
                ? `Your interview is scheduled for ${new Date(portal.schedule.slot_start).toLocaleString()}. You can also begin now if you're ready.`
                : "Find a quiet spot, check your microphone, and begin when ready."}
            </p>
            <div style={{ textAlign: "center" }}>
              <button className="start-btn" onClick={startInterview} disabled={busy}>
                {busy ? "Preparing your room…" : "Start my interview"}
              </button>
              <br />
              <button className="ghost-btn" onClick={() => setStep("schedule")}>
                Change my time
              </button>
            </div>
          </>
        )}

        {error && <p className="error" style={{ textAlign: "center" }}>{error}</p>}
        <p className="contact-foot" style={{ textAlign: "center" }}>
          Questions? Contact the team that invited you.
        </p>
      </div>
    </main>
  );
}
