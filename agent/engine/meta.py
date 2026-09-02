"""Conduct-model output header parsing (PHASE1_ARCHITECTURE.md §6.4).

The conduct model prefixes each spoken turn with one machine-readable line:

    @meta{"intent":"probe","competency":"problem_solving","hint_level":null}

Malformed headers never block the voice path: we log a warning upstream and
fall back to intent "chat".
"""

import json
import logging
import re
from dataclasses import dataclass

log = logging.getLogger("engine.meta")

META_PREFIX = "@meta"
# scrubs any inline header occurrence (model sometimes emits one mid-response)
META_SCRUB_RE = re.compile(r"@meta\s*\{[^}]*\}\s*")

VALID_INTENTS = (
    "chat",
    "question",
    "probe",
    "hint",
    "acknowledge",
    "complexity_question",
    "testing_question",
    "wrapup",
)


@dataclass(frozen=True)
class TurnMeta:
    intent: str = "chat"
    competency: str | None = None
    hint_level: int | None = None


def parse_meta(raw_turn: str) -> tuple[TurnMeta, str]:
    """Extract the first @meta header (anywhere) and return (meta, spoken_text)
    with ALL header occurrences scrubbed from the spoken text."""
    match = re.search(r"@meta\s*(\{[^}]*\})", raw_turn)
    spoken = META_SCRUB_RE.sub(" ", raw_turn).strip()
    spoken = re.sub(r"[ \t]{2,}", " ", spoken)
    if match is None:
        return TurnMeta(), spoken

    try:
        data = json.loads(match.group(1))
        intent = data.get("intent", "chat")
        if intent not in VALID_INTENTS:
            log.warning("unknown intent %r, treating as chat", intent)
            intent = "chat"
        hint_level = data.get("hint_level")
        return (
            TurnMeta(
                intent=intent,
                competency=data.get("competency"),
                hint_level=int(hint_level) if hint_level is not None else None,
            ),
            spoken,
        )
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        log.warning("malformed @meta header (%s); treating as chat: %r", exc, match.group(0)[:120])
        return TurnMeta(), spoken
