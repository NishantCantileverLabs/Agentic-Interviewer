"""Interview plan schema — plan-driven rounds.

A plan defines an ordered list of rounds; the engine walks them in order.
Round types decide behavior: `coding`/`sql` rounds bind a question, enable
code observation, and carry post-solution completion criteria.

Legacy plans (PHASE1_ARCHITECTURE.md §6.2: time_budget_min + question_refs)
are synthesized into the classic five-round sequence, keeping their original
state names as round ids so existing event logs rebuild unchanged.
"""

from dataclasses import dataclass, field
from typing import Any

ROUND_TYPES = ("intro", "warmup", "discussion", "coding", "sql", "quiz", "artifact", "wrapup")
CODE_ROUND_TYPES = ("coding", "sql")

ENDED = "ENDED"  # virtual terminal round id

_LEGACY_SEQUENCE = [
    ("INTRO", "intro", 2),
    ("WARMUP", "warmup", 5),
    ("TECHNICAL_DEEPDIVE", "discussion", 12),
    ("CODING", "coding", 22),
    ("WRAPUP", "wrapup", 4),
]


@dataclass(frozen=True)
class Round:
    id: str
    type: str
    minutes: float
    question_id: str | None = None


@dataclass(frozen=True)
class Competency:
    id: str
    weight: float
    probe_budget: int = 3


@dataclass(frozen=True)
class InterviewPlan:
    role_config_id: str
    competencies: tuple[Competency, ...]
    rounds: tuple[Round, ...]
    question_refs: dict[str, Any] = field(default_factory=dict)
    language_default: str = "python"

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "InterviewPlan":
        if "rounds" in data:
            rounds = tuple(
                Round(
                    id=str(r["id"]),
                    type=str(r["type"]),
                    minutes=float(r["minutes"]),
                    question_id=r.get("question"),
                )
                for r in data["rounds"]
            )
        else:
            budgets = data.get("time_budget_min", {})
            coding_q = (data.get("question_refs") or {}).get("coding")
            rounds = tuple(
                Round(
                    id=state,
                    type=type_,
                    minutes=float(budgets.get(state, default_min)),
                    question_id=coding_q if type_ == "coding" else None,
                )
                for state, type_, default_min in _LEGACY_SEQUENCE
            )
        return cls(
            role_config_id=data["role_config_id"],
            competencies=tuple(
                Competency(
                    id=c["id"],
                    weight=float(c["weight"]),
                    probe_budget=int(c.get("probe_budget", 3)),
                )
                for c in data["competencies"]
            ),
            rounds=rounds,
            question_refs=data.get("question_refs", {}),
            language_default=data.get("language_default", "python"),
        )

    def round_by_id(self, round_id: str) -> Round | None:
        for r in self.rounds:
            if r.id == round_id:
                return r
        return None

    def next_round(self, round_id: str) -> Round | None:
        """The round after `round_id`, or None when it was the last (-> ENDED)."""
        ids = [r.id for r in self.rounds]
        try:
            idx = ids.index(round_id)
        except ValueError:
            return self.rounds[0] if self.rounds else None
        return self.rounds[idx + 1] if idx + 1 < len(self.rounds) else None

    def first_round(self) -> Round:
        return self.rounds[0]

    def probe_budget(self, competency_id: str) -> int:
        for c in self.competencies:
            if c.id == competency_id:
                return c.probe_budget
        return 0
