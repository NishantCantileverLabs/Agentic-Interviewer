"""code_at reconstruction unit tests."""

from datetime import UTC, datetime, timedelta

from app.replay import apply_delta_batch, code_at

T0 = datetime(2026, 8, 23, 12, 0, 0, tzinfo=UTC)


def ev(seq: int, type_: str, payload: dict, seconds: float) -> dict:
    return {"seq": seq, "ts": T0 + timedelta(seconds=seconds), "type": type_, "payload": payload}


def test_apply_delta_insert_and_delete() -> None:
    code = apply_delta_batch("hello world", {"deltas": [{"rangeOffset": 5, "rangeLength": 6, "text": ", code"}]})
    assert code == "hello, code"


def test_code_at_snapshot_plus_deltas() -> None:
    events = [
        ev(0, "editor_snapshot", {"code": "def f():\n    pass", "language": "python"}, 0),
        ev(1, "editor_delta_batch", {"deltas": [{"rangeOffset": 13, "rangeLength": 4, "text": "return 1"}]}, 10),
        ev(2, "editor_snapshot", {"code": "def f():\n    return 1", "language": "python"}, 30),
        ev(3, "editor_delta_batch", {"deltas": [{"rangeOffset": 21, "rangeLength": 0, "text": " + 2"}]}, 40),
    ]
    # before any edits
    at_5 = code_at(events, T0 + timedelta(seconds=5))
    assert at_5["code"] == "def f():\n    pass"
    # after first delta, before second snapshot
    at_15 = code_at(events, T0 + timedelta(seconds=15))
    assert at_15["code"] == "def f():\n    return 1"
    assert at_15["base_snapshot_seq"] == 0 and at_15["delta_batches_applied"] == 1
    # after second snapshot + delta: reconstruction uses the later snapshot
    at_45 = code_at(events, T0 + timedelta(seconds=45))
    assert at_45["code"] == "def f():\n    return 1 + 2"
    assert at_45["base_snapshot_seq"] == 2


def test_code_at_empty_history() -> None:
    result = code_at([], T0)
    assert result["code"] == "" and result["base_snapshot_seq"] is None
