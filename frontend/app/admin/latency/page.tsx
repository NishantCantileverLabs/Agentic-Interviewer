"use client";

import { useEffect, useState } from "react";
import Nav from "../../components/Nav";
import "../admin.css";

import { API, authFetch } from "../../lib/auth";

interface SessionLatency {
  session_id: string;
  candidate_label: string;
  created_at: string;
  turns: number;
  p50_ms: number;
  p95_ms: number;
  stage_p50_ms: { eou: number | null; llm_ttft: number | null; tts_ttfb: number | null };
  recent_e2e_ms: number[];
}

interface LLMRow {
  role: string;
  model: string;
  calls: number;
  input_tokens: number;
  output_tokens: number;
  avg_ttft_ms: number | null;
  cost_estimate_usd: number | null;
}

function Spark({ values, target }: { values: number[]; target: number }) {
  const max = Math.max(...values, target * 1.2);
  return (
    <div className="spark" title={values.join(", ") + " ms"}>
      {values.map((v, i) => (
        <div
          key={i}
          className={v > target ? "over" : ""}
          style={{ height: `${Math.max(4, (v / max) * 42)}px` }}
        />
      ))}
    </div>
  );
}

export default function LatencyDashboard() {
  const [data, setData] = useState<{ targets: { p50_ms: number; p95_ms: number }; sessions: SessionLatency[] } | null>(null);
  const [llm, setLlm] = useState<LLMRow[]>([]);

  useEffect(() => {
    const load = () => {
      authFetch(`${API}/metrics/latency`).then(async (r) => setData(await r.json()));
      authFetch(`${API}/metrics/llm-calls`).then(async (r) => setLlm(await r.json()));
    };
    load();
    const t = setInterval(load, 15_000);
    return () => clearInterval(t);
  }, []);

  if (!data)
    return (
      <>
        <Nav />
        <main className="admin"><h1>Latency</h1><p>Loading…</p></main>
      </>
    );

  return (
    <>
    <Nav />
    <main className="admin">
      <h1>Voice latency</h1>
      <p>
        GATE 1 targets: p50 ≤ {data.targets.p50_ms}ms, p95 ≤ {data.targets.p95_ms}ms
        (end of candidate speech → first agent audio)
      </p>
      <table>
        <thead>
          <tr>
            <th>Session</th><th>Turns</th><th>p50</th><th>p95</th>
            <th>EOU / LLM / TTS (p50)</th><th>Recent turns</th>
          </tr>
        </thead>
        <tbody>
          {data.sessions.map((s) => (
            <tr key={s.session_id}>
              <td>{s.candidate_label}<br /><small style={{ color: "#8b949e" }}>{new Date(s.created_at).toLocaleString()}</small></td>
              <td>{s.turns}</td>
              <td><span className={`badge ${s.p50_ms <= data.targets.p50_ms ? "ok" : "bad"}`}>{s.p50_ms}ms</span></td>
              <td><span className={`badge ${s.p95_ms <= data.targets.p95_ms ? "ok" : "bad"}`}>{s.p95_ms}ms</span></td>
              <td>
                {s.stage_p50_ms.eou ?? "-"} / {s.stage_p50_ms.llm_ttft ?? "-"} / {s.stage_p50_ms.tts_ttfb ?? "-"} ms
              </td>
              <td><Spark values={s.recent_e2e_ms} target={data.targets.p50_ms} /></td>
            </tr>
          ))}
        </tbody>
      </table>

      <h1>LLM calls</h1>
      <table>
        <thead>
          <tr><th>Role</th><th>Model</th><th>Calls</th><th>In tokens</th><th>Out tokens</th><th>Avg TTFT</th><th>Est. cost</th></tr>
        </thead>
        <tbody>
          {llm.map((r, i) => (
            <tr key={i}>
              <td>{r.role}</td><td>{r.model}</td><td>{r.calls}</td>
              <td>{r.input_tokens.toLocaleString()}</td>
              <td>{r.output_tokens.toLocaleString()}</td>
              <td>{r.avg_ttft_ms ? `${r.avg_ttft_ms}ms` : "-"}</td>
              <td>{r.cost_estimate_usd ? `$${r.cost_estimate_usd}` : "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
    </>
  );
}
