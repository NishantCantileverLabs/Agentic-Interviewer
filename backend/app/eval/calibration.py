"""T8 — AI vs human calibration math. Pure functions, unit-tested.

Honest-uncertainty rule: below MIN_SESSIONS dual-scored sessions the report
carries insufficient_data=True and no headline correlation is presented.
"""

from typing import Any

MIN_SESSIONS = 20
DISAGREEMENT_DELTA = 2


def _rank(values: list[float]) -> list[float]:
    """Average ranks (ties share the mean rank)."""
    indexed = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i
        while j + 1 < len(indexed) and values[indexed[j + 1]] == values[indexed[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[indexed[k]] = avg
        i = j + 1
    return ranks


def spearman(a: list[float], b: list[float]) -> float | None:
    """Spearman rank correlation via Pearson on ranks (tie-safe)."""
    if len(a) != len(b) or len(a) < 2:
        return None
    ra, rb = _rank(a), _rank(b)
    n = len(a)
    mean_a, mean_b = sum(ra) / n, sum(rb) / n
    cov = sum((x - mean_a) * (y - mean_b) for x, y in zip(ra, rb, strict=True))
    var_a = sum((x - mean_a) ** 2 for x in ra)
    var_b = sum((y - mean_b) ** 2 for y in rb)
    if var_a == 0 or var_b == 0:
        return None  # constant ranks — correlation undefined
    return round(float(cov) / float((var_a * var_b) ** 0.5), 3)


def calibration_report(
    pairs: list[dict[str, Any]],
    hire_threshold: float = 3.6,
    weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """pairs: [{session_id, ai: {comp: score}, human: {comp: score}}, ...]"""
    ai_comps = {c for p in pairs for c in p["ai"]}
    human_comps = {c for p in pairs for c in p["human"]}
    competencies = sorted(ai_comps & human_comps)

    per_competency: dict[str, Any] = {}
    disagreements: list[dict[str, Any]] = []
    for comp in competencies:
        ai_scores, human_scores = [], []
        for p in pairs:
            if comp in p["ai"] and comp in p["human"]:
                ai_scores.append(float(p["ai"][comp]))
                human_scores.append(float(p["human"][comp]))
                delta = abs(p["ai"][comp] - p["human"][comp])
                if delta >= DISAGREEMENT_DELTA:
                    disagreements.append(
                        {
                            "session_id": p["session_id"],
                            "competency": comp,
                            "ai": p["ai"][comp],
                            "human": p["human"][comp],
                            "delta": delta,
                        }
                    )
        mad = (
            round(sum(abs(x - y) for x, y in zip(ai_scores, human_scores, strict=True))
                  / len(ai_scores), 3)
            if ai_scores
            else None
        )
        per_competency[comp] = {
            "n": len(ai_scores),
            "spearman": spearman(ai_scores, human_scores),
            "mean_abs_diff": mad,
        }

    def weighted(scores: dict[str, Any]) -> float:
        w = weights or {c: 1.0 for c in scores}
        total = sum(w.get(c, 0) for c in scores) or 1.0
        return sum(float(s) * w.get(c, 0) for c, s in scores.items()) / total

    agree = 0
    for p in pairs:
        ai_pass = weighted(p["ai"]) >= hire_threshold
        human_pass = weighted(p["human"]) >= hire_threshold
        agree += ai_pass == human_pass
    agreement_rate = round(agree / len(pairs), 3) if pairs else None

    return {
        "n_sessions": len(pairs),
        "insufficient_data": len(pairs) < MIN_SESSIONS,
        "min_sessions_for_calibration": MIN_SESSIONS,
        "per_competency": per_competency,
        "pass_fail_agreement_rate": agreement_rate,
        "hire_threshold": hire_threshold,
        "disagreements": sorted(disagreements, key=lambda d: -d["delta"]),
        "review_queue": sorted({d["session_id"] for d in disagreements}),
    }
