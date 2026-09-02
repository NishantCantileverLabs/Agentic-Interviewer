"""Pass 0 — deterministic process signals (PHASE1_ARCHITECTURE.md §8).

Computed in pure Python from the event stream. The LLM never computes these
(invariant D6); the eval model receives them read-only.
"""

import statistics
from datetime import datetime
from typing import Any

PASTE_FLAG_THRESHOLD = 120  # chars; larger pastes are flagged for reviewer attention


def _ts(ev: dict[str, Any]) -> datetime:
    ts = ev["ts"]
    return datetime.fromisoformat(ts) if isinstance(ts, str) else ts


def compute_signals(events: list[dict[str, Any]]) -> dict[str, Any]:
    """events: ordered replay rows (id, seq, ts, type, payload)."""
    hints = [e for e in events if e["type"] == "hint_issued"]
    pastes = [e for e in events if e["type"] == "paste"]
    runs = [e for e in events if e["type"] == "run_clicked"]
    executions = [e for e in events if e["type"] == "execution_result"]
    tab_hidden = [
        e for e in events
        if e["type"] == "tab_visibility" and not e["payload"].get("visible", True)
    ]
    barge_ins = [e for e in events if e["type"] == "barge_in"]
    transitions = [e for e in events if e["type"] == "state_transition"]
    latencies = [
        e["payload"] for e in events
        if e["type"] == "turn_latency" and "e2e_first_audio_s" in e.get("payload", {})
    ]

    # time to first line of code after entering the first code round
    code_round_entry: datetime | None = None
    for t in transitions:
        p = t["payload"]
        if p.get("round_type") in ("coding", "sql") or p.get("to") == "CODING":
            code_round_entry = _ts(t)
            break
    first_edit: datetime | None = None
    for e in events:
        if e["type"] == "editor_delta_batch" and code_round_entry and _ts(e) >= code_round_entry:
            first_edit = _ts(e)
            break
    time_to_first_line_s = (
        round((first_edit - code_round_entry).total_seconds(), 1)
        if first_edit and code_round_entry
        else None
    )

    # run cadence: seconds between consecutive runs
    run_gaps = [
        round((_ts(b) - _ts(a)).total_seconds(), 1)
        for a, b in zip(runs, runs[1:], strict=False)
    ]

    last_statuses = [
        e["payload"].get("response", {}).get("status") for e in executions
    ]

    flagged_pastes = [
        {"event_id": e["id"], "length": int(e["payload"].get("length", 0))}
        for e in pastes
        if int(e["payload"].get("length", 0)) > PASTE_FLAG_THRESHOLD
    ]

    e2e = [p["e2e_first_audio_s"] for p in latencies]

    return {
        "hints_used": len(hints),
        "hint_levels": [int(h["payload"].get("level", 0)) for h in hints],
        "paste_count": len(pastes),
        "flagged_pastes": flagged_pastes,
        "tab_switches_away": len(tab_hidden),
        "barge_ins": len(barge_ins),
        "run_count": len(runs),
        "run_gap_seconds": run_gaps,
        "execution_statuses": last_statuses,
        "final_execution_status": last_statuses[-1] if last_statuses else None,
        "time_to_first_line_s": time_to_first_line_s,
        "twist_fired": any(e["type"] == "twist_injected" for e in events),
        "candidate_turns": sum(1 for e in events if e["type"] == "stt_final"),
        "agent_turns": sum(1 for e in events if e["type"] == "agent_turn"),
        "voice_latency_p50_s": round(statistics.median(e2e), 3) if e2e else None,
        "rounds_visited": [t["payload"].get("to") for t in transitions],
    }
