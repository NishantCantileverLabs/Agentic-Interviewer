"""Engine-driven interview agent — plan-driven rounds.

The state machine owns the interview (D3): the plan defines an ordered list
of rounds; transitions fire from time budgets and completion criteria in a
background task; the conduct model only behaves within the current round.
Engine state is rebuilt from the event log on (re)join, so a crashed agent
resumes mid-interview.

Run:  python interview_agent.py dev
"""

import asyncio
import contextlib
import difflib
import logging
import os
import pathlib
import urllib.parse
from collections.abc import AsyncIterable
from datetime import UTC, datetime

from dotenv import load_dotenv
from livekit import agents
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    EndpointingOptions,
    InterruptionOptions,
    ModelSettings,
    PreemptiveGenerationOptions,
    TurnHandlingOptions,
    metrics,
)
from livekit.plugins import anthropic, cartesia, deepgram, elevenlabs, openai, silero
from livekit.plugins.turn_detector.english import EnglishModel

import engine.rounds  # noqa: F401 - registers all round-type plugins (T19)
from engine import (
    ENDED,
    EngineState,
    InterviewPlan,
    InterviewStateMachine,
    parse_meta,
    rebuild,
)
from engine.mathcheck import check_answer
from engine.round_registry import get_round_type, round_context
from engine.rounds.case import active_math_block, untouched_must_areas
from engine.rounds.case import current_phase as case_phase
from engine.rounds.design import component_coverage
from engine.state import apply_event
from event_sink import BackendClient, EventSink
from latency import LatencyTracker

load_dotenv(pathlib.Path(__file__).parent.parent / ".env")
log = logging.getLogger("interview-agent")


def _validate_agent_posture() -> None:
    """Mirror of backend app.config.validate_production_posture for the agent
    process: in production, refuse to run on dev credentials instead of
    silently authenticating with them."""
    if os.environ.get("ENVIRONMENT", "dev").strip().lower() not in ("production", "prod"):
        return
    problems = []
    if os.environ.get("INTERNAL_API_KEY", "dev-internal-key") == "dev-internal-key":
        problems.append("INTERNAL_API_KEY: still the dev default")
    if os.environ.get("LIVEKIT_API_KEY", "devkey") == "devkey":
        problems.append("LIVEKIT_API_KEY: still the dev default")
    if os.environ.get("LIVEKIT_API_SECRET", "secret") == "secret":
        problems.append("LIVEKIT_API_SECRET: still the dev default")
    if "localhost" in os.environ.get("BACKEND_URL", "http://localhost:8000"):
        problems.append("BACKEND_URL: still points at localhost")
    if problems:
        raise RuntimeError(
            "agent refusing to start in production posture — fix these first:\n"
            + "\n".join(f"  x {p}" for p in problems)
        )


_validate_agent_posture()

PROMPTS_DIR = pathlib.Path(__file__).parent.parent / "prompts" / "conduct"
CONDUCT_MODEL = os.environ.get("CONDUCT_MODEL", "claude-haiku-4-5")
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "anthropic")
TTS_PRIMARY = os.environ.get("TTS_PRIMARY", "deepgram")

DEFAULT_PLAN = {
    "role_config_id": "sde_backend_v1",
    "competencies": [
        {"id": "problem_solving", "weight": 0.3, "probe_budget": 3},
        {"id": "coding_proficiency", "weight": 0.3, "probe_budget": 3},
        {"id": "cs_fundamentals", "weight": 0.2, "probe_budget": 2},
        {"id": "communication", "weight": 0.2, "probe_budget": 2},
    ],
}


def _now() -> datetime:
    return datetime.now(UTC)


def build_llm():  # noqa: ANN201
    """Primary conduct LLM with provider failover when both are configured
    (T9: LLM timeout/outage falls back rather than dead-airing)."""
    from livekit.agents import llm as lk_llm

    candidates = []
    openrouter = (
        openai.LLM(
            model=os.environ.get("OPENROUTER_CONDUCT_MODEL", "anthropic/claude-haiku-4.5"),
            base_url=os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            api_key=os.environ["OPENROUTER_API_KEY"],
        )
        if os.environ.get("OPENROUTER_API_KEY")
        else None
    )
    anthropic_llm = (
        # caching="ephemeral": Anthropic prompt caching on system + history (D5)
        anthropic.LLM(model=CONDUCT_MODEL, caching="ephemeral")
        if os.environ.get("ANTHROPIC_API_KEY")
        else None
    )
    if LLM_PROVIDER == "openrouter":
        candidates = [c for c in (openrouter, anthropic_llm) if c]
    else:
        candidates = [c for c in (anthropic_llm, openrouter) if c]
    if not candidates:
        raise RuntimeError("no LLM provider configured")
    return candidates[0] if len(candidates) == 1 else lk_llm.FallbackAdapter(candidates)


ALLOWED_VOICES = (
    "aura-2-thalia-en",
    "aura-2-andromeda-en",
    "aura-2-orion-en",
    "aura-2-arcas-en",
)


def build_tts(voice: str | None = None):  # noqa: ANN201
    """Primary TTS with provider failover across the configured providers (T9).

    TTS_PRIMARY picks who speaks first (deepgram | elevenlabs | cartesia);
    the rest become FallbackAdapter tiers. Deepgram Aura shares the STT key,
    so it's always available and ~5x cheaper than ElevenLabs. `voice` is the
    candidate's per-session pick (Aura voices only; unknown values fall back
    to the default)."""
    from livekit.agents import tts as lk_tts

    aura_voice = voice if voice in ALLOWED_VOICES else "aura-2-thalia-en"
    providers = {
        "deepgram": (
            lambda: deepgram.TTS(model=aura_voice)
            if os.environ.get("DEEPGRAM_API_KEY")
            else None
        ),
        "elevenlabs": (
            lambda: elevenlabs.TTS(
                model="eleven_flash_v2_5", api_key=os.environ["ELEVENLABS_API_KEY"]
            )
            if os.environ.get("ELEVENLABS_API_KEY")
            else None
        ),
        "cartesia": (
            lambda: cartesia.TTS(model="sonic-3")
            if os.environ.get("CARTESIA_API_KEY")
            else None
        ),
    }
    order = [TTS_PRIMARY] + [name for name in providers if name != TTS_PRIMARY]
    candidates = [tts for name in order if name in providers and (tts := providers[name]())]
    if not candidates:
        raise RuntimeError("no TTS provider configured")
    return candidates[0] if len(candidates) == 1 else lk_tts.FallbackAdapter(candidates)


_META_TOKEN = "@meta"


def _meta_prefix_tail(buffer: str) -> int:
    """Length of the longest buffer suffix that is a prefix of "@meta"
    (a header may be split across stream chunks)."""
    for n in range(min(len(_META_TOKEN), len(buffer)), 0, -1):
        if buffer.endswith(_META_TOKEN[:n]):
            return n
    return 0


async def _strip_meta_stream(text: AsyncIterable[str]) -> AsyncIterable[str]:
    """Remove EVERY @meta{...} header from a token stream before TTS or
    transcription display — wherever it appears, even split across chunks.
    Holds back at most a few chars, so the voice path never stalls."""
    buffer = ""
    after_header = False
    async for chunk in text:
        buffer += chunk
        if after_header:
            buffer = buffer.lstrip("\n ")
            after_header = not buffer
        while buffer:
            idx = buffer.find(_META_TOKEN)
            if idx == -1:
                tail = _meta_prefix_tail(buffer)
                if len(buffer) > tail:
                    yield buffer[: len(buffer) - tail]
                    buffer = buffer[len(buffer) - tail :]
                break
            if idx > 0:
                yield buffer[:idx]
                buffer = buffer[idx:]
            end = buffer.find("}")
            if end == -1:
                break  # header still streaming in — hold
            buffer = buffer[end + 1 :].lstrip("\n ")
            after_header = not buffer
    if buffer and not buffer.startswith(_META_TOKEN):
        yield buffer


class InterviewConductor(Agent):
    def __init__(
        self,
        session_id: str,
        plan: InterviewPlan,
        round_meta: dict[str, dict],  # round_id -> {statement, hints, twist}
        sink: EventSink | None,
        initial_state: EngineState,
        jd_text: str | None = None,
        resume_text: str | None = None,
    ) -> None:
        self.session_id = session_id
        self.plan = plan
        self.sm = InterviewStateMachine(plan)
        self.es = initial_state
        self.sink = sink
        self.round_meta = round_meta
        self.jd_text = (jd_text or "").strip()[:4000]
        self.resume_text = (resume_text or "").strip()[:4000]
        self.latest_observation: str | None = None
        # live signals maintained by the observation loop
        self.tests_failing: dict[str, bool] = {}
        self.visible_passed: dict[str, bool] = {}
        self.recent_editing = False
        self._pending_nudge = False
        self._pending_math: dict | None = None
        self.transcript_text = ""  # rolling candidate transcript (coverage checks)
        self.canvas_labels: list[str] = []
        self.scratchpad_text = ""
        # v2 adds the guardrails: no invented documents, structure stays
        # confidential, strict interview-only scope, no solution walkthroughs
        self.base_prompt = (PROMPTS_DIR / "base_v2.txt").read_text(encoding="utf-8")
        first = initial_state.round_id or plan.first_round().id
        super().__init__(instructions=self._instructions_for(first))

    # ── engine plumbing ──────────────────────────────────────────────

    def _round_type(self, round_id: str) -> str:
        round_ = self.plan.round_by_id(round_id)
        return round_.type if round_ else "wrapup"

    def _round_def(self, round_id: str):  # noqa: ANN202
        return get_round_type(self._round_type(round_id))

    def _instructions_for(self, round_id: str) -> str:
        parts = [self.base_prompt]
        # JD + resume are stable per session -> cache-friendly block B content.
        if self.jd_text:
            parts.append(
                "The role being interviewed for (job description — ground your "
                "questions in these requirements, never read it aloud):\n" + self.jd_text
            )
        if self.resume_text:
            parts.append(
                "The candidate's resume (draw warmup and deep-dive questions from "
                "their actual experience; probe claims made here; never recite it):\n"
                + self.resume_text
            )
        else:
            parts.append(
                "No resume was provided for this candidate. You have not seen their "
                "resume or CV — never claim otherwise. Open background questions with "
                "something like 'walk me through what you've been working on'."
            )
        path = PROMPTS_DIR / f"{self._round_def(round_id).prompt_file}.txt"
        if path.exists():
            parts.append(path.read_text(encoding="utf-8"))
        meta = self.round_meta.get(round_id) or {}
        statement = meta.get("statement")
        if statement:
            parts.append("The problem the candidate sees on screen:\n" + statement)
        pack = meta.get("case_pack")
        if pack:
            clar = "\n".join(
                f"- if asked about {c.get('trigger_topics')}: {c.get('answer_md')}"
                for c in pack.get("clarifications", [])
            )
            parts.append(
                "Case pack (yours only — the candidate sees nothing until you present "
                "or release it):\nSituation: " + pack.get("prompt_md", "")
                + ("\nClarification answers:\n" + clar if clar else "")
                + "\nSynthesis expectation: " + pack.get("synthesis_expectation_md", "")
            )
        return "\n\n".join(parts)

    def current_prompt_version(self) -> str:
        rid = self.es.round_id or self.plan.first_round().id
        return f"conduct/{self._round_def(rid).prompt_file}"

    def in_code_round(self) -> bool:
        rid = self.es.round_id
        return rid is not None and rid != ENDED and self._round_def(rid).is_code_round

    def _elapsed_frac(self) -> float:
        rid = self.es.round_id
        round_ = self.plan.round_by_id(rid) if rid else None
        if not round_ or not self.es.round_entered_ts:
            return 0.0
        return min(
            1.0,
            (_now() - self.es.round_entered_ts).total_seconds() / (round_.minutes * 60),
        )

    def plugin_ctx(self) -> dict:
        rid = self.es.round_id or ""
        meta = self.round_meta.get(rid) or {}
        ctx = round_context(
            elapsed_frac=self._elapsed_frac(),
            case_pack=meta.get("case_pack"),
            design_question=meta.get("design_question"),
            unprobed_claims=meta.get("unprobed_claims"),
            contradictions=meta.get("contradictions"),
        )
        if meta.get("case_pack"):
            ctx["untouched_must_areas"] = untouched_must_areas(
                meta["case_pack"], self.transcript_text
            )
        if meta.get("design_question"):
            ctx["component_coverage"] = component_coverage(
                meta["design_question"].get("reference_components", []),
                self.canvas_labels,
            )
        return ctx

    def fold(self, type_: str, payload: dict) -> None:
        """Mirror an emitted event into local engine state (same fold as rebuild)."""
        self.es = apply_event(self.es, type_, payload, _now())
        if self.sink:
            self.sink.emit(type_, payload)

    async def transition_to(self, round_id: str, session: AgentSession) -> None:
        old = self.es.round_id
        type_ = self._round_type(round_id) if round_id != ENDED else ENDED
        self.fold("state_transition", {"to": round_id, "from": old, "round_type": type_})
        log.info("state transition %s -> %s (%s)", old, round_id, type_)
        if round_id == ENDED:
            return
        self.latest_observation = None  # fresh observation window per round
        await self.update_instructions(self._instructions_for(round_id))
        hint = self._round_def(round_id).transition_hint
        await session.generate_reply(
            instructions=f"You are now in the '{round_id}' round. Transition naturally in one "
            f"or two spoken sentences. {hint}"
        )

    # ── pipeline hooks ───────────────────────────────────────────────

    def _hint_directive(self) -> str | None:
        """Graduated hints: only the engine-authorized level's content enters
        context; the model may use it only if the candidate asks for help."""
        rid = self.es.round_id or ""
        hints = (self.round_meta.get(rid) or {}).get("hints") or []
        if not self.in_code_round() or not hints:
            return None
        failing = self.tests_failing.get(rid, True)
        level = self.sm.authorized_hint_level(self.es, _now(), tests_failing=failing)
        if level is None or level > len(hints):
            return (
                "Hint policy: no further hints are authorized. If asked for help, "
                "encourage them to keep going with what they have."
            )
        return (
            f"Hint policy: ONLY if the candidate asks for help (or is clearly stuck and "
            f"asks you to weigh in), you may give this level-{level} hint, phrased "
            f'naturally, tagged intent "hint" with hint_level {level}: "{hints[level - 1]}"'
        )

    async def on_user_turn_completed(self, turn_ctx, new_message) -> None:  # noqa: ANN001
        # The directive rides INSIDE the user turn as a delimited block (the
        # base prompt explains it). Injecting it as an assistant message
        # taught the model to imitate internal-note speech aloud — never again.
        parts = [self.sm.directive(self.es, _now())]
        rid = self.es.round_id or ""
        extra_fn = self._round_def(rid).directive_extra
        if extra_fn:
            extra = extra_fn(self.es, rid, self.plugin_ctx())
            if extra:
                parts.append(extra)
        if self._pending_math:
            v = self._pending_math
            parts.append(
                f"ENGINE MATH VERDICT for block {v['block_id']}: candidate stated "
                f"{v['stated']}, which is {'CORRECT' if v['correct'] else 'INCORRECT'} "
                f"(reference ±{v['tolerance_pct']}%). React per the math doctrine."
            )
        hint = self._hint_directive()
        if hint:
            parts.append(hint)
        if self.latest_observation:
            parts.append(self.latest_observation)
        new_message.content.append(
            "\n<engine_directive>\n" + "\n".join(parts) + "\n</engine_directive>"
        )

    def tts_node(self, text: AsyncIterable[str], model_settings: ModelSettings):  # noqa: ANN201
        return Agent.default.tts_node(self, _strip_meta_stream(text), model_settings)

    def transcription_node(self, text, model_settings: ModelSettings):  # noqa: ANN001, ANN201
        return Agent.default.transcription_node(self, _strip_meta_stream(text), model_settings)


def _prewarm(proc: agents.JobProcess) -> None:
    """Per-process warm-up: load the VAD model before any candidate joins."""
    proc.userdata["vad"] = silero.VAD.load()


# num_idle_processes=1: keep a warmed process ready so a joining candidate
# never waits for process init (dev default is 0 — the main cause of a slow
# first greeting).
# load_fnc=0: the default reports system CPU as worker load, and the SERVER
# refuses to dispatch to a worker whose load exceeds its capacity target —
# on a busy single-worker deployment that silently strands candidates in the
# lobby ("no servers available"). One worker must always accept; a slow
# interview beats an interviewer that never arrives. Scale-out later means
# restoring a real load_fnc alongside multiple workers.
server = AgentServer(num_idle_processes=1, setup_fnc=_prewarm, load_fnc=lambda: 0.0)


# Named agent + explicit dispatch (requested in the room token) instead of
# automatic dispatch: deterministic assignment, immune to the availability
# race we hit on resource-starved machines.
@server.rtc_session(agent_name="interviewer")
async def interview_session(ctx: agents.JobContext) -> None:
    room_name = ctx.room.name
    session_id = (
        room_name.removeprefix("interview-") if room_name.startswith("interview-") else None
    )
    backend = BackendClient()
    tracker = LatencyTracker()

    plan_data = DEFAULT_PLAN
    round_meta: dict[str, dict] = {}
    initial = EngineState()
    sink: EventSink | None = None
    jd_text: str | None = None
    resume_text: str | None = None
    session_voice: str | None = None

    if session_id:
        sink = EventSink(session_id)
        # One parallel burst instead of four sequential round-trips. A None
        # session_row means the FETCH failed (the room only exists for a real
        # session) — retry, then refuse the job rather than conducting the
        # DEFAULT_PLAN against a real session and polluting its event log
        # with a spurious fresh-start transition.
        session_row = bundle = questions = None
        history: list[dict] = []
        for attempt in range(3):
            session_row, bundle, questions, history = await asyncio.gather(
                backend.get_json(f"/sessions/{session_id}"),
                backend.get_json(f"/sessions/{session_id}/plan"),
                backend.get_json(f"/sessions/{session_id}/round-content"),
                backend.replay(session_id),
            )
            if session_row is not None:
                break
            log.warning("bootstrap fetch failed (attempt %d/3); backing off", attempt + 1)
            await asyncio.sleep(2 * (attempt + 1))
        if session_row is None:
            await backend.close()
            raise RuntimeError(
                f"backend unreachable during bootstrap for session {session_id} — "
                "refusing to conduct a default-plan interview against a real session"
            )
        if session_row.get("status") in ("completed", "aborted"):
            # a finished interview never resurrects: without this, re-entering
            # the room re-dispatched the agent, which rebuilt the old
            # transcript and "resumed" the ended conversation
            log.info("session %s already %s - refusing dispatch", session_id, session_row["status"])
            await backend.close()
            ctx.shutdown(reason="session already ended")
            return
        if session_row:
            jd_text = session_row.get("jd_text")
            resume_text = session_row.get("resume_text")
            session_voice = session_row.get("voice")
        if bundle:
            plan_data = bundle["plan"]
        if questions:
            round_meta = questions  # /round-content: per-round statement/hints/pack/etc.
        initial = rebuild(history, InterviewPlan.from_json(plan_data))
        if initial.round_id == ENDED:
            log.info("session %s event log is at ENDED - refusing dispatch", session_id)
            await backend.close()
            ctx.shutdown(reason="interview already ended per event log")
            return
        log.info(
            "session %s bootstrap: %d prior events, resuming in %s",
            session_id, len(history), initial.round_id,
        )

    plan = InterviewPlan.from_json(plan_data)
    conductor = InterviewConductor(
        session_id or "adhoc", plan, round_meta, sink, initial,
        jd_text=jd_text, resume_text=resume_text,
    )

    # TURN_DETECTOR: "semantic" = local ONNX model (best hold-back, needs CPU
    # headroom); "stt" = Deepgram-native endpointing (lightest — use on
    # constrained dev machines); "vad" = silence only.
    detector_mode = os.environ.get("TURN_DETECTOR", "stt")
    turn_detection = EnglishModel() if detector_mode == "semantic" else detector_mode

    session = AgentSession(
        # endpointing_ms raised from the plugin default: premature STT finals
        # fragmented utterances into many tiny turns, which produced doubled
        # answers (the agent replied, the sentence's tail arrived, it replied
        # again). utterance_end_ms groups trailing fragments into one final.
        stt=deepgram.STT(
            model="nova-3",
            language="en",
            interim_results=True,
            endpointing_ms=int(os.environ.get("DEEPGRAM_ENDPOINTING_MS", "500")),
            utterance_end_ms=1000,
        ),
        llm=build_llm(),
        tts=build_tts(voice=session_voice),
        vad=ctx.proc.userdata.get("vad") or silero.VAD.load(),
        turn_handling=TurnHandlingOptions(
            turn_detection=turn_detection,
            # min_delay 0.9s: candidates pause mid-sentence; answering into
            # those pauses is the #1 perceived voice bug.
            endpointing=EndpointingOptions(mode="fixed", min_delay=0.9, max_delay=12.0),
            # 0.6s of sustained speech to interrupt — breaths and "mm" don't cut
            # the interviewer off mid-sentence.
            interruption=InterruptionOptions(mode="vad", min_duration=0.6),
            # keep the early LLM start for latency, but never SPEAK before the
            # turn is committed — speaking early doubled responses.
            preemptive_generation=PreemptiveGenerationOptions(
                enabled=os.environ.get("SPECULATIVE_GENERATION", "true").lower() != "false",
                preemptive_tts=False,
            ),
        ),
    )

    # strong refs: the event loop keeps only weak references to tasks, so an
    # untracked fire-and-forget log task can be GC'd before it ever runs
    bg_tasks: set[asyncio.Task] = set()

    def _track(task: asyncio.Task) -> None:
        bg_tasks.add(task)

        def _done(t: asyncio.Task) -> None:
            bg_tasks.discard(t)
            if not t.cancelled() and t.exception() is not None:
                log.warning("background task failed: %r", t.exception())

        task.add_done_callback(_done)

    @session.on("metrics_collected")
    def on_metrics(ev) -> None:  # noqa: ANN001
        m = getattr(ev, "metrics", ev)
        fields = tracker.record(m)
        if isinstance(m, metrics.LLMMetrics):
            _track(asyncio.create_task(
                backend.log_llm_call(
                    {
                        "session_id": session_id,
                        "prompt_version_name": conductor.current_prompt_version(),
                        "role": "conduct",
                        # FallbackAdapter turns may be served by a non-primary
                        # model; prefer the metric's own attribution
                        "model": getattr(m, "model", None) or CONDUCT_MODEL,
                        "input_tokens": getattr(m, "prompt_tokens", 0) or 0,
                        "cached_tokens": getattr(m, "prompt_cached_tokens", 0) or 0,
                        "output_tokens": getattr(m, "completion_tokens", 0) or 0,
                        "ttft_ms": int((getattr(m, "ttft", 0) or 0) * 1000),
                        "total_ms": int((getattr(m, "duration", 0) or 0) * 1000),
                    }
                )
            ))
        if isinstance(m, metrics.TTSMetrics) and fields:
            turn = tracker.complete_turn()
            if turn and sink:
                pv = conductor.current_prompt_version()
                sink.emit("turn_latency", {"prompt_version": pv, **turn})

    @session.on("user_input_transcribed")
    def on_transcribed(ev) -> None:  # noqa: ANN001
        if not getattr(ev, "is_final", False):
            return
        conductor.fold("stt_final", {"text": ev.transcript})
        conductor.transcript_text += " " + ev.transcript
        # Deterministic math adjudication (invariant #16): check the utterance
        # against the active math/estimation block, stash for the next turn.
        rid = conductor.es.round_id or ""
        meta = conductor.round_meta.get(rid) or {}
        block = None
        if meta.get("case_pack"):
            phase = case_phase(conductor.es, rid, conductor._elapsed_frac())
            block = active_math_block(meta["case_pack"], conductor.es, rid, phase)
        elif meta.get("design_question"):
            blocks = meta["design_question"].get("estimation_blocks") or []
            unanswered = [
                b for b in blocks
                if f"{rid}:{b['id']}" not in conductor.es.math_correct
            ]
            block = unanswered[0] if unanswered else None
        if block:
            verdict = check_answer(
                ev.transcript,
                float(block["correct_value"]),
                float(block.get("tolerance_pct", 2)),
            )
            if verdict.stated is not None:
                conductor._pending_math = {
                    "block_id": block["id"],
                    "stated": verdict.stated,
                    "correct": verdict.correct,
                    "tolerance_pct": verdict.tolerance_pct,
                }

    @session.on("error")
    def on_error(ev) -> None:  # noqa: ANN001
        # T9 error taxonomy: everything lands in the log for the dashboard
        err = getattr(ev, "error", ev)
        if sink:
            sink.emit(
                "error",
                {"source": type(err).__name__, "detail": str(err)[:300]},
            )

    @session.on("conversation_item_added")
    def on_item(ev) -> None:  # noqa: ANN001
        item = ev.item
        if getattr(item, "role", None) != "assistant":
            return
        raw = item.text_content or ""
        if raw.startswith("[engine directive"):
            return
        meta, spoken = parse_meta(raw)
        payload = {
            "text": spoken,
            "meta": {
                "intent": meta.intent,
                "competency": meta.competency,
                "hint_level": meta.hint_level,
            },
            "interrupted": bool(getattr(item, "interrupted", False)),
        }
        if conductor._pending_nudge:
            payload["nudge"] = True
            conductor._pending_nudge = False
        if conductor._pending_math:
            payload["math_verdict"] = conductor._pending_math
            conductor._pending_math = None
        conductor.fold("agent_turn", payload)
        if meta.intent == "hint" and meta.hint_level:
            conductor.fold(
                "hint_issued", {"round_id": conductor.es.round_id, "level": meta.hint_level}
            )
        if meta.intent == "release_exhibit" and meta.competency:
            # Engine-owned exhibit release (T21): validate against the pack
            from engine.rounds.case import exhibit_release_allowed

            rid = conductor.es.round_id or ""
            pack = (conductor.round_meta.get(rid) or {}).get("case_pack") or {}
            ex_id = meta.competency
            if exhibit_release_allowed(pack, ex_id, conductor.es, rid):
                exhibit = next(e for e in pack["exhibits"] if e["id"] == ex_id)
                conductor.fold(
                    "exhibit_revealed",
                    {
                        "round_id": rid,
                        "exhibit_id": ex_id,
                        "title": exhibit.get("title"),
                        "content_md": exhibit.get("content_md"),
                    },
                )
        if payload["interrupted"] and sink:
            sink.emit("barge_in", {})

    async def transition_loop() -> None:
        while True:
            await asyncio.sleep(5)
            rid = conductor.es.round_id or ""
            # Twist injection (§7.3): visible tests pass with >=40% budget left
            twist_text = (conductor.round_meta.get(rid) or {}).get("twist")
            if conductor.sm.should_fire_twist(
                conductor.es,
                _now(),
                visible_tests_passed=conductor.visible_passed.get(rid, False),
                has_twist=bool(twist_text),
            ):
                conductor.fold("twist_injected", {"round_id": rid})
                await session.generate_reply(
                    instructions="Their solution passes the visible tests with time to spare. "
                    f"Introduce this requirement change conversationally: {twist_text}"
                )
                continue
            # Think-aloud nudge: silent coding >90s, max 2 per round
            if conductor.in_code_round() and conductor.sm.should_nudge(
                conductor.es, _now(), editing=conductor.recent_editing
            ):
                conductor._pending_nudge = True
                await session.generate_reply(
                    instructions="The candidate has been coding silently for a while. Give one "
                    "gentle, short invitation to walk you through their thinking. Do not "
                    "pressure them."
                )
                continue
            target = conductor.sm.should_transition(conductor.es, _now())
            if target is not None:
                await conductor.transition_to(target, session)
                if target == ENDED:
                    await session.generate_reply(
                        instructions="Close the interview warmly in one or two sentences: thank "
                        "them, tell them the team will follow up. intent wrapup."
                    )
                    await asyncio.sleep(8)
                    if session_id:
                        await backend.set_status(session_id, "completed")
                    if sink:
                        await sink.close()
                    ctx.shutdown(reason="interview complete")
                    return

    async def observation_loop() -> None:
        """Round-generic observation (T19): code for code rounds, canvas +
        scratchpad for design/case rounds — all from the event log."""
        last_code = ""
        last_seq = -1
        prev_shapes: list | None = None
        last_run_summary: str | None = None
        last_run_failures: list[str] = []
        while True:
            # code rounds poll fast: the candidate can ask "can you see my
            # code?" at any moment and a 15s-old snapshot answers wrongly.
            # Still off the voice path - this is a background task.
            await asyncio.sleep(4 if conductor.in_code_round() else 15)
            if not session_id:
                continue
            rid = conductor.es.round_id or ""
            tools = get_round_type(conductor._round_type(rid)).tools if rid else ()
            if not conductor.in_code_round() and tools:
                # canvas / scratchpad observation from the latest events
                tail = await backend.replay(session_id, after_seq=max(-1, last_seq - 500))
                obs_parts: list[str] = []
                if "canvas" in tools:
                    snaps = [e for e in tail if e["type"] == "canvas_snapshot"]
                    if snaps:
                        shapes = snaps[-1]["payload"].get("shapes", [])
                        from engine.canvas import labels as canvas_labels
                        from engine.canvas import observation_block

                        obs_parts.append(observation_block(shapes, prev_shapes))
                        conductor.canvas_labels = canvas_labels(shapes)
                        prev_shapes = shapes
                if "scratchpad" in tools:
                    pads = [e for e in tail if e["type"] == "scratchpad_delta"]
                    if pads:
                        conductor.scratchpad_text = pads[-1]["payload"].get("text", "")
                        obs_parts.append(
                            "@scratchpad\n" + conductor.scratchpad_text[:1200]
                        )
                if tail:
                    last_seq = tail[-1]["seq"]
                if obs_parts:
                    conductor.latest_observation = "\n".join(obs_parts)
                continue
            if not conductor.in_code_round():
                continue
            # ts must be URL-encoded: the "+00:00" offset's "+" decodes to a
            # space and 422s the request — which made the agent believe the
            # editor was empty while the candidate was typing.
            snap = await backend.get_json(
                f"/sessions/{session_id}/code_at?ts={urllib.parse.quote(_now().isoformat())}"
            )
            events = await backend.replay(session_id, after_seq=last_seq)
            if events:
                last_seq = events[-1]["seq"]
            runs = [e for e in events if e["type"] == "execution_result"]
            rid = conductor.es.round_id or ""
            if runs:
                # remember across polls (each poll sees only NEW events)
                _resp = runs[-1]["payload"].get("response", {})
                _per = _resp.get("per_test", [])
                _passed = sum(1 for t in _per if t.get("passed"))
                last_run_summary = f"{_resp.get('status')} - {_passed}/{len(_per)} tests passed"
                last_run_failures = []
                for t in _per:
                    if t.get("hidden") or t.get("passed"):
                        continue
                    detail = (t.get("stderr") or t.get("stdout") or "").strip()[:300]
                    last_run_failures.append(
                        f"failing_visible_test {t.get('id')}: "
                        f"{t.get('status') or 'wrong output'}"
                        + (f"\noutput: {detail}" if detail else "")
                    )
            if runs:
                resp = runs[-1]["payload"].get("response", {})
                per = resp.get("per_test", [])
                visible = [t for t in per if not t.get("hidden")]
                conductor.visible_passed[rid] = bool(visible) and all(
                    t.get("passed") for t in visible
                )
                conductor.tests_failing[rid] = resp.get("status") != "accepted"
            if snap is None:
                # observation failed — never tell the model the editor is
                # empty when we simply couldn't look (it would gaslight the
                # candidate about their own code)
                conductor.latest_observation = (
                    "@code_observation\ncurrent_code_in_editor: (observation "
                    "temporarily unavailable — do not claim the editor is empty)"
                )
                continue
            code = snap.get("code", "")
            conductor.recent_editing = code != last_code
            if len(code) < 20_000 and len(last_code) < 20_000:
                diff_lines = list(
                    difflib.unified_diff(
                        last_code.splitlines(), code.splitlines(), lineterm="", n=1
                    )
                )
                diff = "\n".join(diff_lines[2:])[:1200]
            else:
                # difflib is quadratic — a huge paste must not stall the event
                # loop the live audio pipeline runs on
                diff = "(large edit — diff skipped)" if code != last_code else ""
            last_code = code
            # The observation always carries the FULL current code so the model
            # can genuinely read it — not just recent diffs (§7.2, revised).
            lines = ["@code_observation"]
            if code.strip():
                lines.append(f"current_code_in_editor:\n```\n{code[:3000]}\n```")
            else:
                lines.append("current_code_in_editor: (editor is empty)")
            if last_run_summary:
                lines.append(f"last_run: {last_run_summary}")
                # VISIBLE failing tests only (the candidate already sees these);
                # hidden-test expectations never enter context (invariant #3).
                # Carried across polls: each poll sees only NEW events, so the
                # run detail used to vanish from the model's view after one
                # 15s window.
                lines.extend(last_run_failures)
            if diff:
                lines.append("recent_changes:\n" + diff)
            conductor.latest_observation = "\n".join(lines)

    if sink:
        await sink.start()
    fresh_session = initial.round_id is None
    if session_id and fresh_session:
        first = plan.first_round()
        conductor.fold(
            "state_transition", {"to": first.id, "from": None, "round_type": first.type}
        )
        await backend.set_status(session_id, "in_progress")

    await session.start(room=ctx.room, agent=conductor)

    async def _supervise(name: str, loop_fn) -> None:  # noqa: ANN001
        """An iteration crash must log and restart the loop — never silently
        kill the interview state machine (the old failure mode: a single
        provider exception froze the interview with no transition ever
        firing again)."""
        while True:
            try:
                await loop_fn()
                return  # clean return: interview ended
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("%s crashed; restarting in 5s", name)
                await asyncio.sleep(5)

    t1 = asyncio.create_task(_supervise("transition_loop", transition_loop))
    t2 = asyncio.create_task(_supervise("observation_loop", observation_loop))

    await session.generate_reply(
        instructions="Greet the candidate warmly, confirm they can hear you, and set expectations "
        "for the interview in one or two sentences."
        if fresh_session
        else f"You are resuming after a brief connection drop, mid-'{initial.round_id}' round. "
        "Apologize briefly for the glitch and pick the conversation back up."
    )

    async def on_shutdown() -> None:
        for t in (t1, t2):
            t.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await t
        summary = tracker.summary()
        log.info("== LATENCY SUMMARY == %s", summary)
        if sink:
            sink.emit("turn_latency", {"summary": True, **summary})
            await sink.close()
        await backend.close()

    ctx.add_shutdown_callback(on_shutdown)


if __name__ == "__main__":
    agents.cli.run_app(server)
