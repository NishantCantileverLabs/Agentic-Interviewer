"""Turn-latency instrumentation for the T1 spike.

Collects per-stage timings from LiveKit Agents metrics objects
(EOU delay, LLM TTFT, TTS TTFB) and accumulates the end-to-end
end-of-speech -> first-audio estimate. Extraction is defensive:
metric class shapes vary across livekit-agents minor versions, so we
read known attribute names via getattr and keep whatever is present.
"""

import statistics
from typing import Any

# attribute name -> our canonical field name (seconds unless *_ms)
_KNOWN_FIELDS = {
    "end_of_utterance_delay": "eou_delay_s",
    "transcription_delay": "transcription_delay_s",
    "on_user_turn_completed_delay": "turn_completed_delay_s",
    "ttft": "llm_ttft_s",
    "ttfb": "tts_ttfb_s",
    "duration": "duration_s",
}


def extract_metric_fields(obj: Any) -> dict[str, float]:
    out: dict[str, float] = {}
    for attr, name in _KNOWN_FIELDS.items():
        value = getattr(obj, attr, None)
        if isinstance(value, (int, float)) and value >= 0:
            out[name] = round(float(value), 4)
    return out


class LatencyTracker:
    """Accumulates per-turn stage timings and reports p50/p95."""

    def __init__(self) -> None:
        self._turns: list[dict[str, float]] = []
        self._current: dict[str, float] = {}

    def record(self, metric_obj: Any) -> dict[str, float]:
        fields = extract_metric_fields(metric_obj)
        self._current.update(fields)
        return fields

    def complete_turn(self) -> dict[str, float] | None:
        """Close out the current turn; returns its merged stage timings."""
        if not self._current:
            return None
        turn = dict(self._current)
        # end-of-candidate-speech -> first-audio-out estimate:
        # EOU detection + LLM time-to-first-token + TTS time-to-first-byte
        total = sum(
            turn.get(k, 0.0) for k in ("eou_delay_s", "llm_ttft_s", "tts_ttfb_s")
        )
        if total > 0:
            turn["e2e_first_audio_s"] = round(total, 4)
        self._turns.append(turn)
        self._current = {}
        return turn

    def summary(self) -> dict[str, Any]:
        e2e = [t["e2e_first_audio_s"] for t in self._turns if "e2e_first_audio_s" in t]
        if not e2e:
            return {"turns": len(self._turns), "note": "no complete e2e samples"}
        e2e_sorted = sorted(e2e)

        def pct(p: float) -> float:
            idx = min(len(e2e_sorted) - 1, round(p * (len(e2e_sorted) - 1)))
            return e2e_sorted[int(idx)]

        return {
            "turns": len(self._turns),
            "e2e_samples": len(e2e),
            "p50_ms": round(statistics.median(e2e) * 1000),
            "p95_ms": round(pct(0.95) * 1000),
            "min_ms": round(e2e_sorted[0] * 1000),
            "max_ms": round(e2e_sorted[-1] * 1000),
            "target": "p50 <= 800ms, p95 <= 1500ms (GATE 1)",
        }
