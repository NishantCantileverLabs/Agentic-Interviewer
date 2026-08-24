"""Coding + SQL round types — Phase 1 behaviors as the first plugins."""

from engine.round_registry import RoundTypeDef, register

register(
    RoundTypeDef(
        type="coding",
        prompt_file="coding_v1",
        tools=("editor",),
        is_code_round=True,
        completion_intents=("complexity_question", "testing_question"),
        transition_hint=(
            "Introduce the coding exercise: tell them the problem statement is on "
            "their screen and invite questions before they start."
        ),
        silence_maxhold_s=12,
    )
)

register(
    RoundTypeDef(
        type="sql",
        prompt_file="sql_v1",
        tools=("editor",),
        is_code_round=True,
        completion_intents=("complexity_question", "testing_question"),
        transition_hint=(
            "Introduce the SQL exercise: the schema and task are on their screen. "
            "Invite questions before they start writing the query."
        ),
        silence_maxhold_s=12,
    )
)
