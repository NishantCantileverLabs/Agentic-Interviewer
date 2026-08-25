/** Typed client for the org surface. All calls carry the session bearer token
 * (lib/auth); the backend's require_role gates are the enforcement point. */

import { API, authFetch } from "./auth";
import type { CandidacyStatus } from "./visibility";

export { API };

export class OrgApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await authFetch(`${API}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!resp.ok) {
    let detail = await resp.text();
    try {
      detail = (JSON.parse(detail) as { detail?: string }).detail ?? detail;
    } catch {
      /* plain text */
    }
    throw new OrgApiError(resp.status, detail);
  }
  return (await resp.json()) as T;
}

// ── candidacies ──────────────────────────────────────────────────────

export interface CandidacyRow {
  id: string;
  candidate_name: string;
  candidate_email: string;
  status: string;
  source: string;
  job_role_id: string | null;
  role_name: string | null;
  slot_start: string | null;
  has_brief: boolean;
  latest_session_id: string | null;
  created_at: string;
}

/** Backend statuses → the §7 vocabulary (completed splits by brief state). */
export function toStatus(row: { status: string; has_brief?: boolean }): CandidacyStatus {
  if (row.status === "completed") return row.has_brief ? "brief_ready" : "processing";
  const known: CandidacyStatus[] = [
    "invited", "scheduled", "in_progress", "in_review", "reviewed", "synced", "withdrawn",
  ];
  return known.includes(row.status as CandidacyStatus)
    ? (row.status as CandidacyStatus)
    : "invited";
}

export const listCandidacies = () => req<CandidacyRow[]>("/candidacies");

export interface TimelineDetail {
  id: string;
  candidate_name: string;
  candidate_email: string;
  status: string;
  role_name: string | null;
  events: { at: string; label: string; detail?: string }[];
  sessions: {
    id: string;
    status: string;
    round_type: string | null;
    created_at: string;
    has_brief: boolean;
  }[];
}

export const getTimeline = (id: string) => req<TimelineDetail>(`/candidacies/${id}/timeline`);

export const inviteCandidate = (body: {
  candidate_name: string;
  candidate_email: string;
  job_role_id?: string;
}) => req<{ id: string; invite_link: string; email_sent: boolean }>("/candidacies", {
  method: "POST",
  body: JSON.stringify(body),
});

// ── roles / stats ────────────────────────────────────────────────────

export interface JobRoleRow {
  id: string;
  name: string;
  description: string | null;
  status: string;
  pipeline_name: string | null;
  plan_id: string | null;
  candidates: number;
  created_at: string;
}

export const listJobRoles = () => req<JobRoleRow[]>("/job-roles");

export interface HiringStats {
  total_candidates: number;
  scheduled: number;
  interviewed: number;
  by_role: { role_id: string; role_name: string; invited: number; interviewed: number }[];
  unassigned: { invited: number; interviewed: number };
}

export const hiringStats = () => req<HiringStats>("/metrics/hiring");

export interface SessionRow {
  id: string;
  candidate_label: string;
  status: string;
  created_at: string;
  ai_evaluations: number;
  human_evaluations: number;
  briefs: number;
}

export const listSessions = () => req<SessionRow[]>("/sessions");

// ── review ───────────────────────────────────────────────────────────

export interface QueueItem {
  session_id: string;
  candidate_label: string;
  inflow: "integrity" | "borderline" | "degraded";
  reason: string;
  signal?: string;
  created_at: string;
}

export const reviewQueue = () => req<QueueItem[]>("/review-queue");

export const submitDecision = (
  sessionId: string,
  body: { inflow: string; decision: "confirm" | "override"; rationale: string },
) => req<{ id: string }>(`/sessions/${sessionId}/review-decision`, {
  method: "POST",
  body: JSON.stringify(body),
});

// ── session detail (R9) ──────────────────────────────────────────────

export interface ReplayEvent {
  id: number;
  seq: number;
  ts: string;
  type: string;
  payload: Record<string, unknown>;
}

export const sessionReplay = (id: string) => req<ReplayEvent[]>(`/sessions/${id}/replay`);

export const codeAt = (id: string, tsIso: string) =>
  req<{ code?: string; language?: string }>(
    `/sessions/${id}/code_at?ts=${encodeURIComponent(tsIso)}`,
  );

export interface EvaluationView {
  id: string;
  version: number;
  model: string;
  rubric: {
    competencies?: Record<
      string,
      {
        score_1_to_5?: number;
        confidence?: string;
        evidence?: { quote?: string; seq?: number; ts?: string }[];
        rationale?: string;
      }
    >;
    degraded?: boolean;
    /** why the evaluation degraded (provider failure, empty transcript, …) */
    degraded_reason?: string;
  };
  signals: Record<string, unknown>;
  created_at: string;
}

export const sessionEvaluation = (id: string) => req<EvaluationView>(`/sessions/${id}/evaluation`);

/** Operator health of the evaluation pipeline (queue depth, dead-letter,
 * sessions completed but never evaluated). */
export interface EvalHealth {
  queue_depth: number;
  dead_letter: number;
  stuck_sessions: number;
  healthy: boolean;
}

export const evalHealth = () => req<EvalHealth>("/metrics/eval-health");

export interface BriefView {
  id: string;
  evaluation_id: string;
  html_url: string;
  summary: Record<string, unknown>;
  created_at: string;
}

export const sessionBrief = (id: string) => req<BriefView>(`/sessions/${id}/brief`);

// ── compare / analytics ──────────────────────────────────────────────

export interface CompareSide {
  session_id: string;
  candidate_label: string;
  rubric: EvaluationView["rubric"] | null;
  signals: Record<string, unknown> | null;
  recruiter: Record<string, unknown> | null;
}

export const compareSessions = (a: string, b: string) =>
  req<{ a: CompareSide; b: CompareSide }>(`/compare?session_a=${a}&session_b=${b}`);

export interface CalibrationReport {
  n: number;
  competencies?: Record<
    string,
    { n: number; agreement_within_1?: number; spearman?: number | null }
  >;
  [k: string]: unknown;
}

export const calibration = () => req<CalibrationReport>("/calibration");

export interface LatencyReport {
  targets: { p50_ms: number; p95_ms: number };
  sessions: {
    session_id: string;
    candidate_label: string;
    created_at: string;
    turns: number;
    p50_ms: number;
    p95_ms: number;
  }[];
}

export const latencyReport = () => req<LatencyReport>("/metrics/latency");

// ── compliance (A4 data-subject tools) ───────────────────────────────

export const exportCandidacy = (id: string) =>
  req<Record<string, unknown>>(`/candidacies/${id}/export`);

export const eraseCandidacy = (id: string) =>
  req<{ erased_sessions: number; events_purged: number }>(`/candidacies/${id}/erase`, {
    method: "POST",
  });
