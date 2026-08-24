"""Sandboxed execution service — Judge0 wrapper (PHASE1_ARCHITECTURE.md §3.4).

The backend is the only path to Judge0. Hidden-test expected outputs never
leave this module: response shaping strips them (and their stdout) before
anything reaches an API response body — see `shape_response`, covered by the
CI contract test in tests/test_execution.py.
"""

from dataclasses import dataclass
from typing import Any

import httpx

from app.config import get_settings

# Judge0 CE language IDs (stable, documented at /languages)
LANGUAGE_IDS = {
    "python": 71,      # Python 3
    "javascript": 63,  # Node.js
    "java": 62,        # OpenJDK
    "cpp": 54,         # C++ (GCC)
    "sql": 82,         # SQLite
}

OUTPUT_TRUNCATE_BYTES = 64 * 1024

# Judge0 status ids -> our contract statuses
_STATUS_MAP = {
    3: "accepted",
    4: "wrong_answer",
    5: "time_limit_exceeded",
    6: "compile_error",
    13: "internal_error",
    14: "exec_format_error",
}


def map_status(judge0_status_id: int, description: str) -> str:
    if judge0_status_id in _STATUS_MAP:
        return _STATUS_MAP[judge0_status_id]
    if 7 <= judge0_status_id <= 12:
        # runtime errors incl. SIGSEGV/SIGKILL (OOM manifests here)
        return "runtime_error" if "SIGKILL" not in description else "memory_limit_exceeded"
    return "unknown"


def _truncate(text: str | None) -> str:
    if not text:
        return ""
    raw = text.encode("utf-8", errors="replace")[:OUTPUT_TRUNCATE_BYTES]
    return raw.decode("utf-8", errors="replace")


@dataclass
class ExecCase:
    id: str
    stdin: str
    expected_output: str
    hidden: bool
    setup_sql: str = ""  # SQL rounds: schema+data prepended to the candidate query


def load_test_cases(question: Any) -> list[ExecCase]:
    """Build the run list from a question row: visible examples + hidden cases."""
    cases: list[ExecCase] = []
    for hidden, bucket in ((False, question.visible_tests), (True, question.hidden_tests)):
        for case in bucket.get("cases", []):
            cases.append(
                ExecCase(
                    id=str(case["id"]),
                    stdin=str(case.get("stdin", "")),
                    expected_output=str(case.get("expected_output", "")),
                    hidden=hidden,
                    setup_sql=str(case.get("setup_sql", "")),
                )
            )
    return cases


def compose_source(language: str, source: str, case: ExecCase) -> str:
    """SQL cases run against per-case schema+data: setup_sql prepends the
    candidate's query so hidden cases can vary the dataset."""
    if language == "sql" and case.setup_sql:
        return case.setup_sql.rstrip().rstrip(";") + ";\n" + source
    return source


class Judge0Client:
    def __init__(self, base_url: str | None = None) -> None:
        settings = get_settings()
        self._limits = {
            "cpu_time_limit": settings.exec_cpu_limit_s,
            "memory_limit": settings.exec_mem_mb * 1000,  # Judge0 takes KB
            "enable_network": False,
        }
        # AUTHN: judge0.conf's AUTHN_TOKEN must match (production posture
        # requires it — an open Judge0 is arbitrary code execution)
        headers = (
            {"X-Auth-Token": settings.judge0_auth_token}
            if settings.judge0_auth_token
            else {}
        )
        self._client = httpx.AsyncClient(
            base_url=base_url or settings.judge0_url,
            timeout=httpx.Timeout(30.0, connect=5.0),
            headers=headers,
        )

    async def run(self, language: str, source: str, stdin: str = "") -> dict[str, Any]:
        """One synchronous submission; returns Judge0's raw result fields."""
        resp = await self._client.post(
            "/submissions",
            params={"wait": "true"},
            json={
                "language_id": LANGUAGE_IDS[language],
                "source_code": source,
                "stdin": stdin,
                **self._limits,
            },
        )
        resp.raise_for_status()
        result: dict[str, Any] = resp.json()
        return result

    async def close(self) -> None:
        await self._client.aclose()


def evaluate_case(result: dict[str, Any], case: ExecCase) -> dict[str, Any]:
    """Compare one Judge0 result against a test case. Full detail — internal only."""
    status = result.get("status") or {}
    mapped = map_status(int(status.get("id", 0)), str(status.get("description", "")))
    stdout = _truncate(result.get("stdout"))
    passed = mapped == "accepted" and stdout.rstrip("\n") == case.expected_output.rstrip("\n")
    time_ms = int(float(result.get("time") or 0) * 1000)
    return {
        "id": case.id,
        "passed": passed,
        "time_ms": time_ms,
        "hidden": case.hidden,
        "status": mapped,
        "stdout": stdout,
        "stderr": _truncate(result.get("stderr")),
        "expected_output": case.expected_output,
    }


def shape_response(
    overall_status: str, stdout: str, stderr: str, per_test: list[dict[str, Any]]
) -> dict[str, Any]:
    """Public response contract. Hidden cases: pass/fail only — no expected
    output, no stdout/stderr, no per-case status detail."""
    shaped = []
    for t in per_test:
        if t["hidden"]:
            shaped.append(
                {"id": t["id"], "passed": t["passed"], "time_ms": t["time_ms"], "hidden": True}
            )
        else:
            shaped.append(
                {
                    "id": t["id"],
                    "passed": t["passed"],
                    "time_ms": t["time_ms"],
                    "hidden": False,
                    "status": t["status"],
                    "stdout": t["stdout"],
                    "stderr": t["stderr"],
                }
            )
    return {
        "status": overall_status,
        "stdout": _truncate(stdout),
        "stderr": _truncate(stderr),
        "per_test": shaped,
    }
