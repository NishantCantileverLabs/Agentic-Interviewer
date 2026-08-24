export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
export const YWS_URL = process.env.NEXT_PUBLIC_YWS_URL ?? "ws://localhost:1234";

/** Candidate links carry ?candidate_token= — every API call forwards it so
 * org scoping resolves to the token's session (T10). */
export function candidateToken(): string | null {
  if (typeof window === "undefined") return null;
  return new URLSearchParams(window.location.search).get("candidate_token");
}

export function apiUrl(path: string): string {
  const token = candidateToken();
  const base = `${API_URL}${path}`;
  if (!token) return base;
  const sep = path.includes("?") ? "&" : "?";
  return `${base}${sep}candidate_token=${encodeURIComponent(token)}`;
}

export interface RoomCredentials {
  token: string;
  url: string;
  room: string;
}

export interface QuestionView {
  id: string;
  title: string;
  statement_md: string;
  language_targets: string[];
  visible_tests: { cases: { id: string; stdin: string; expected_output: string }[] };
  hidden_test_count: number;
  language_default: string;
  round_id?: string;
  round_type?: string;
  is_current_round?: boolean;
}

export interface TestResult {
  id: string;
  passed: boolean;
  time_ms: number;
  hidden: boolean;
  status?: string;
  stdout?: string;
  stderr?: string;
}

export interface ExecuteResponse {
  status: string;
  stdout: string;
  stderr: string;
  per_test: TestResult[];
}

export interface ReplayEvent {
  id: number;
  seq: number;
  ts: string;
  type: string;
  payload: Record<string, unknown>;
}

async function check(resp: Response): Promise<Response> {
  if (!resp.ok) throw new Error(`${resp.url} -> ${resp.status}`);
  return resp;
}

export async function createSession(
  planId?: string | null,
  resumeText?: string | null,
): Promise<{ id: string }> {
  const resp = await fetch(apiUrl(`/sessions`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      candidate_label: "ui-candidate",
      ...(planId ? { plan_id: planId } : {}),
      ...(resumeText ? { resume_text: resumeText } : {}),
    }),
  });
  return (await check(resp)).json();
}

export async function getToken(sessionId: string): Promise<RoomCredentials> {
  return (await check(await fetch(apiUrl(`/sessions/${sessionId}/token`)))).json();
}

export async function getSessionStatus(sessionId: string): Promise<string> {
  const resp = await check(await fetch(apiUrl(`/sessions/${sessionId}`)));
  return ((await resp.json()) as { status: string }).status;
}

export async function getQuestion(sessionId: string): Promise<QuestionView | null> {
  const resp = await fetch(apiUrl(`/sessions/${sessionId}/question`));
  if (resp.status === 409) return null; // no plan / no coding question assigned
  return (await check(resp)).json();
}

export async function postEvents(
  sessionId: string,
  events: { type: string; payload: Record<string, unknown> }[],
): Promise<void> {
  if (!events.length) return;
  await fetch(apiUrl(`/sessions/${sessionId}/events`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ events }),
    keepalive: true,
  }).catch(() => undefined); // beacons never break the UI
}

export async function execute(
  sessionId: string,
  language: string,
  source: string,
  testSuiteId?: string,
): Promise<ExecuteResponse> {
  const resp = await fetch(apiUrl(`/execute`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      language,
      source,
      test_suite_id: testSuiteId ?? null,
    }),
  });
  if (resp.status === 429) throw new Error("A run is already in progress — wait a moment.");
  return (await check(resp)).json();
}

export async function replay(sessionId: string, afterSeq: number): Promise<ReplayEvent[]> {
  const resp = await fetch(apiUrl(`/sessions/${sessionId}/replay?after_seq=${afterSeq}`));
  return (await check(resp)).json();
}
