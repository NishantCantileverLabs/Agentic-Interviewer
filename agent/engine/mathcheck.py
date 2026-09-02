"""T20 — deterministic number extraction + tolerance adjudication.

Invariant #16: numbers are adjudicated by code. This module parses spoken /
written numeric expressions ("about three forty million", "0.34B", "34
crore", "$2.5m", "12%") into floats and compares against reference values
with tolerance. The LLM discusses numbers; this module decides correctness.
"""

import re
from dataclasses import dataclass

_WORD_VALUES = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
    "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
    "hundred": 100,
}

_MULTIPLIERS = {
    "k": 1e3, "thousand": 1e3,
    "m": 1e6, "mm": 1e6, "million": 1e6, "mn": 1e6,
    "b": 1e9, "billion": 1e9, "bn": 1e9,
    "t": 1e12, "trillion": 1e12,
    # Indian numbering
    "lakh": 1e5, "lakhs": 1e5, "lac": 1e5, "lacs": 1e5,
    "crore": 1e7, "crores": 1e7, "cr": 1e7,
}

_NUM_RE = re.compile(
    r"(?<![\w.])[-+]?\$?€?₹?\s*(\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*"
    r"(k|m|mm|mn|b|bn|t|thousand|million|billion|trillion|lakh|lakhs|lac|lacs|crore|crores|cr)?"
    r"\s*(%|percent)?(?![\w])",
    re.IGNORECASE,
)


def _words_to_number(text: str) -> float | None:
    """'three forty' -> 340, 'twenty five' -> 25, 'three hundred forty' -> 340."""
    tokens = [t for t in re.split(r"[\s-]+", text.lower()) if t and t not in ("and", "point")]
    if not tokens or not all(t in _WORD_VALUES for t in tokens):
        return None
    total = 0.0
    current = 0.0
    for t in tokens:
        v = _WORD_VALUES[t]
        if v == 100:
            current = (current or 1) * 100
        elif v >= 20 and current and current < 20:
            # "three forty" pattern: 3 -> 340 (3*100 + 40)
            current = current * 100 + v
        else:
            current += v
    total += current
    return total


def extract_numbers(text: str) -> list[float]:
    """All numeric values in a candidate utterance, normalized to absolute
    floats (multipliers applied; % returned as fraction-of-hundred value,
    i.e. '12%' -> 12.0 with is-percent left to the caller's block context)."""
    values: list[float] = []

    # digit forms with optional multiplier suffixes
    for m in _NUM_RE.finditer(text):
        raw, suffix, _pct = m.groups()
        num = float(raw.replace(",", ""))
        if suffix:
            num *= _MULTIPLIERS[suffix.lower()]
        values.append(num)

    # spoken-word forms with multiplier words: "three forty million"
    word_pattern = re.compile(
        r"\b((?:(?:" + "|".join(_WORD_VALUES) + r")[\s-]*)+)"
        r"(thousand|million|billion|trillion|lakh|lakhs|crore|crores)\b",
        re.IGNORECASE,
    )
    for m in word_pattern.finditer(text):
        base = _words_to_number(m.group(1).strip())
        if base is not None:
            values.append(base * _MULTIPLIERS[m.group(2).lower()])

    # "point three four billion"
    pt = re.search(
        r"\bpoint\s+((?:(?:" + "|".join(_WORD_VALUES) + r")\s*)+)"
        r"(thousand|million|billion|trillion)\b",
        text,
        re.IGNORECASE,
    )
    if pt:
        digits = [str(int(_WORD_VALUES[w.lower()])) for w in pt.group(1).split()]
        if all(len(d) == 1 for d in digits):
            frac = float("0." + "".join(digits))
            values.append(frac * _MULTIPLIERS[pt.group(2).lower()])

    return values


@dataclass(frozen=True)
class MathVerdict:
    stated: float | None
    correct: bool
    expected: float
    tolerance_pct: float


def check_answer(text: str, expected: float, tolerance_pct: float = 2.0) -> MathVerdict:
    """The candidate's FINAL stated number vs. the reference. Picks the value
    in the utterance closest to expected (candidates restate givens); correct
    iff within tolerance."""
    values = extract_numbers(text)
    if not values:
        return MathVerdict(None, False, expected, tolerance_pct)
    stated = min(values, key=lambda v: abs(v - expected))
    ok = expected != 0 and abs(stated - expected) / abs(expected) * 100 <= tolerance_pct
    if expected == 0:
        ok = stated == 0
    return MathVerdict(stated, ok, expected, tolerance_pct)
