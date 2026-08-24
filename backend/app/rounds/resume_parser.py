"""T24 — deterministic resume parsing: structured claims + contradiction checks.

Versioned; parse failures degrade to raw-text mode (never block). Heuristic
by design — quantified claims and date ranges are what the behavioral round
needs, and dates/overlaps must be checked in code, not by an LLM.
"""

import re
from typing import Any

PARSER_VERSION = "heuristic-1.0"

_DATE_RANGE = re.compile(
    r"(?P<start>(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}|\d{4})"
    r"\s*[-–—to]+\s*"
    r"(?P<end>(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}|\d{4}|present|current|now)",
    re.IGNORECASE,
)
_QUANTIFIED = re.compile(
    r"\d+(?:\.\d+)?\s*(?:%|percent|x|×|k|m|b|million|billion|crore|lakh)", re.IGNORECASE
)
_NUMERIC = re.compile(r"\d+(?:\.\d+)?")


def _is_quantified(line: str) -> bool:
    """Suffix-marked number, or two+ numbers (e.g. 'AUC from 0.71 to 0.83')."""
    if _QUANTIFIED.search(line):
        return True
    return len(_NUMERIC.findall(line)) >= 2 and not _DATE_RANGE.search(line)


def _year(token: str) -> int | None:
    m = re.search(r"\d{4}", token)
    return int(m.group()) if m else None


def parse_resume(raw_text: str) -> dict[str, Any]:
    """Returns {roles: [{line, start_year, end_year}], quantified_claims: [str],
    parser_version}. Degrades to empty structures on any surprise."""
    try:
        roles = []
        for line in raw_text.splitlines():
            m = _DATE_RANGE.search(line)
            if m:
                end_tok = m.group("end").lower()
                is_present = end_tok in ("present", "current", "now")
                roles.append(
                    {
                        "line": line.strip()[:200],
                        "start_year": _year(m.group("start")),
                        "end_year": 9999 if is_present else _year(m.group("end")),
                    }
                )
        claims = [
            line.strip()[:200]
            for line in raw_text.splitlines()
            if _is_quantified(line) and len(line.strip()) > 15
        ][:12]
        return {"roles": roles, "quantified_claims": claims, "parser_version": PARSER_VERSION}
    except Exception:  # noqa: BLE001 - degrade, never block (T24 acceptance)
        return {"roles": [], "quantified_claims": [], "parser_version": PARSER_VERSION,
                "degraded_raw_mode": True}


def find_contradictions(parsed: dict[str, Any]) -> list[str]:
    """Deterministic checks only: impossible date ranges and heavy overlaps."""
    out = []
    roles = parsed.get("roles", [])
    for r in roles:
        s, e = r.get("start_year"), r.get("end_year")
        if s and e and e != 9999 and e < s:
            out.append(f"the range in '{r['line'][:80]}' ends before it starts")
    # 3+ concurrent full ranges is worth one neutral question
    for i, a in enumerate(roles):
        overlaps = 0
        for b in roles[i + 1:]:
            sa, ea = a.get("start_year") or 0, a.get("end_year") or 0
            sb, eb = b.get("start_year") or 0, b.get("end_year") or 0
            if sa and sb and max(sa, sb) < min(ea, eb):
                overlaps += 1
        if overlaps >= 2:
            out.append(
                f"several roles appear concurrent with '{a['line'][:80]}'"
            )
            break
    return out[:2]
