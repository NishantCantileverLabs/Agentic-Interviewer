"""Execution service unit + contract tests (no Judge0 required)."""

import json

from app.execution import ExecCase, evaluate_case, map_status, shape_response

HIDDEN_SECRET = "secret-expected-42"


def _make_results() -> list[dict[str, object]]:
    visible = ExecCase(id="t1", stdin="1 2", expected_output="3", hidden=False)
    hidden = ExecCase(id="h1", stdin="10 20", expected_output=HIDDEN_SECRET, hidden=True)
    ok = {"status": {"id": 3, "description": "Accepted"}, "stdout": "3\n", "time": "0.02"}
    wrong = {
        "status": {"id": 4, "description": "Wrong Answer"},
        "stdout": "31\n",
        "time": "0.03",
    }
    return [evaluate_case(ok, visible), evaluate_case(wrong, hidden)]


def test_hidden_expected_output_never_in_response() -> None:
    """CI contract test — invariant #4 (CLAUDE.md #5)."""
    response = shape_response("failed", "", "", _make_results())
    serialized = json.dumps(response)
    assert HIDDEN_SECRET not in serialized
    assert "expected_output" not in serialized
    hidden_entries = [t for t in response["per_test"] if t["hidden"]]
    assert hidden_entries == [{"id": "h1", "passed": False, "time_ms": 30, "hidden": True}]


def test_hidden_stdout_stderr_stripped() -> None:
    response = shape_response("failed", "", "", _make_results())
    for t in response["per_test"]:
        if t["hidden"]:
            assert "stdout" not in t and "stderr" not in t and "status" not in t


def test_visible_case_keeps_detail() -> None:
    response = shape_response("failed", "", "", _make_results())
    visible = next(t for t in response["per_test"] if not t["hidden"])
    assert visible["passed"] is True
    assert visible["stdout"] == "3\n"


def test_pass_requires_exact_output_match() -> None:
    case = ExecCase(id="t", stdin="", expected_output="7", hidden=False)
    wrong = {"status": {"id": 3, "description": "Accepted"}, "stdout": "6\n", "time": "0.01"}
    assert evaluate_case(wrong, case)["passed"] is False
    right = {"status": {"id": 3, "description": "Accepted"}, "stdout": "7\n", "time": "0.01"}
    assert evaluate_case(right, case)["passed"] is True


def test_status_mapping() -> None:
    assert map_status(5, "Time Limit Exceeded") == "time_limit_exceeded"
    assert map_status(11, "Runtime Error (SIGKILL)") == "memory_limit_exceeded"
    assert map_status(7, "Runtime Error (SIGSEGV)") == "runtime_error"
    assert map_status(6, "Compilation Error") == "compile_error"


def test_output_truncation_at_64kb() -> None:
    case = ExecCase(id="t", stdin="", expected_output="x", hidden=False)
    big = {"status": {"id": 3, "description": "Accepted"}, "stdout": "a" * 100_000, "time": "0.1"}
    result = evaluate_case(big, case)
    assert len(result["stdout"].encode()) <= 64 * 1024
