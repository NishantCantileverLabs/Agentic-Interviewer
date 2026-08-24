/** Typed client for the candidate surface (/i/[token]).
 * The invite token is the candidacy id — it is the credential for the
 * pre-interview flow; the room itself still requires a session-scoped JWT. */

export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface PortalSchedule {
  slot_start: string;
  slot_end: string;
  reschedule_count: number;
}

export interface Portal {
  id: string;
  candidate_name: string;
  role_name: string | null;
  source: string;
  status: string;
  schedule: PortalSchedule | null;
  policy_version: string;
  policies: Record<string, string>;
  required_items: string[];
  consents: Record<string, boolean>;
}

export interface StartResult {
  session_id: string;
  interview_path: string;
}

export class PortalError extends Error {
  constructor(
    public kind: "not_found" | "conflict" | "validation" | "network",
    message: string,
  ) {
    super(message);
  }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(`${API}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new PortalError("network", "We could not reach the interview service. Check your connection and try again.");
  }
  if (resp.ok) return (await resp.json()) as T;
  const detail = await resp.text();
  if (resp.status === 404) throw new PortalError("not_found", detail);
  if (resp.status === 409) throw new PortalError("conflict", extractDetail(detail));
  throw new PortalError("validation", extractDetail(detail));
}

function extractDetail(raw: string): string {
  try {
    const parsed = JSON.parse(raw) as { detail?: string };
    return parsed.detail ?? raw;
  } catch {
    return raw;
  }
}

export const getPortal = (token: string) => req<Portal>(`/candidacies/${token}`);

export const recordConsent = (token: string, items: Record<string, boolean>) =>
  req<{ recorded: string[]; missing_required: string[] }>(
    `/candidacies/${token}/consent`,
    { method: "POST", body: JSON.stringify({ items }) },
  );

export const decline = (token: string) =>
  req<{ status: string }>(`/candidacies/${token}/decline`, { method: "POST" });

export const scheduleSlot = (token: string, slotStartIso: string) =>
  req<{ scheduled: string }>(`/candidacies/${token}/schedule`, {
    method: "POST",
    body: JSON.stringify({ slot_start: slotStartIso }),
  });

export const startInterview = (token: string) =>
  req<StartResult>(`/candidacies/${token}/start-interview`, { method: "POST" });

/** Interviewer voices offered in the lobby (Deepgram Aura-2 ids; must match
 * the backend whitelist in routes/sessions.py). */
export const INTERVIEWER_VOICES = [
  { id: "aura-2-thalia-en", name: "Thalia", blurb: "Clear and confident" },
  { id: "aura-2-andromeda-en", name: "Andromeda", blurb: "Calm and warm" },
  { id: "aura-2-orion-en", name: "Orion", blurb: "Approachable, deeper tone" },
  { id: "aura-2-arcas-en", name: "Arcas", blurb: "Natural and smooth" },
] as const;

/** Persist the candidate's voice pick on the session (auth: session-scoped
 * candidate token, same pattern as every in-room call). */
export const setSessionVoice = (
  sessionId: string,
  candidateToken: string,
  voice: string,
) =>
  req<{ id: string }>(
    `/sessions/${sessionId}/voice?candidate_token=${encodeURIComponent(candidateToken)}`,
    { method: "PATCH", body: JSON.stringify({ voice }) },
  );

/** Reschedule policy mirrored from the backend default (RESCHEDULE_MAX). */
export const RESCHEDULE_MAX = 2;

/** Consent items already granted under the current policy version? */
export function requiredConsentComplete(p: Portal): boolean {
  return p.required_items.every((item) => p.consents[item]);
}
