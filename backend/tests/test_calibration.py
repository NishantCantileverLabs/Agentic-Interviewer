"""T8 calibration math — verified against hand-computed values."""

from app.eval.calibration import calibration_report, spearman


def test_spearman_perfect_and_inverse() -> None:
    assert spearman([1, 2, 3, 4], [2, 3, 4, 5]) == 1.0
    assert spearman([1, 2, 3, 4], [5, 4, 3, 2]) == -1.0


def test_spearman_hand_computed() -> None:
    # ranks a: [1,2,3,4,5], b: [2,1,4,3,5] -> sum d^2 = 1+1+1+1+0 = 4
    # rho = 1 - 6*4 / (5*24) = 1 - 0.2 = 0.8
    assert spearman([10, 20, 30, 40, 50], [15, 5, 40, 30, 60]) == 0.8


def test_spearman_undefined_cases() -> None:
    assert spearman([1], [2]) is None            # n < 2
    assert spearman([3, 3, 3], [1, 2, 3]) is None  # constant -> undefined
    assert spearman([1, 2], [1, 2, 3]) is None   # length mismatch


PAIRS = [
    {"session_id": "s1", "ai": {"a": 4, "b": 3}, "human": {"a": 4, "b": 2}},
    {"session_id": "s2", "ai": {"a": 5, "b": 2}, "human": {"a": 3, "b": 2}},
    {"session_id": "s3", "ai": {"a": 2, "b": 4}, "human": {"a": 2, "b": 4}},
]


def test_report_insufficient_data_below_20() -> None:
    report = calibration_report(PAIRS)
    assert report["insufficient_data"] is True
    assert report["n_sessions"] == 3


def test_report_mad_and_disagreements() -> None:
    report = calibration_report(PAIRS, hire_threshold=3.0, weights={"a": 0.5, "b": 0.5})
    # competency a diffs: |4-4|, |5-3|, |2-2| -> MAD = 2/3
    assert report["per_competency"]["a"]["mean_abs_diff"] == round(2 / 3, 3)
    # s2 competency a delta 2 -> disagreement + review queue
    assert report["disagreements"] == [
        {"session_id": "s2", "competency": "a", "ai": 5, "human": 3, "delta": 2}
    ]
    assert report["review_queue"] == ["s2"]


def test_pass_fail_agreement_hand_computed() -> None:
    # weighted (equal): s1 ai 3.5 human 3.0; s2 ai 3.5 human 2.5; s3 ai 3.0 human 3.0
    # threshold 3.0: s1 pass/pass agree; s2 pass/fail disagree; s3 pass/pass agree
    report = calibration_report(PAIRS, hire_threshold=3.0, weights={"a": 0.5, "b": 0.5})
    assert report["pass_fail_agreement_rate"] == round(2 / 3, 3)
