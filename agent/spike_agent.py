"""T1 voice loop spike — LiveKit Agents pipeline with latency instrumentation.

Pipeline: Deepgram streaming STT -> conduct LLM (streaming) -> Cartesia/ElevenLabs
streaming TTS, all orchestrated by livekit-agents (built-in pipelining, barge-in,
semantic turn detection — PHASE1_ARCHITECTURE.md §2.2 technique 1).

Run (after `pip install -e .` and filling ../.env):
    python spike_agent.py console   # local terminal session, no LiveKit room
    python spike_agent.py dev       # connect to LiveKit Cloud room

GATE 1 acceptance: p50 <= 800ms / p95 <= 1500ms end-of-speech -> first audio
over 20 exchanges; barge-in works; a 10s thinking silence does not trigger a turn.
"""

import logging
import os
import pathlib

from dotenv import load_dotenv
from livekit import agents
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    EndpointingOptions,
    InterruptionOptions,
    PreemptiveGenerationOptions,
    TurnHandlingOptions,
    metrics,
)
from livekit.plugins import anthropic, cartesia, deepgram, elevenlabs, openai, silero
from livekit.plugins.turn_detector.english import EnglishModel

from event_sink import EventSink, create_backend_session
from latency import LatencyTracker

load_dotenv(pathlib.Path(__file__).parent.parent / ".env")

log = logging.getLogger("spike-agent")

PROMPT_PATH = pathlib.Path(__file__).parent.parent / "prompts" / "conduct" / "spike_v1.txt"
PROMPT_VERSION_NAME = "conduct/spike_v1"  # mirrored into prompt_versions in T2

CONDUCT_MODEL = os.environ.get("CONDUCT_MODEL", "claude-haiku-4-5")
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "anthropic")
TTS_PRIMARY = os.environ.get("TTS_PRIMARY", "cartesia")
ENDPOINTING_MIN_S = float(os.environ.get("DEEPGRAM_ENDPOINTING_MS", "300")) / 1000
# Spike exercises the hard case: tolerate long thinking pauses (CODING-state value)
SILENCE_MAXHOLD_S = float(os.environ.get("SILENCE_MAXHOLD_CODING_S", "12"))


def build_llm():  # noqa: ANN201 - plugin types differ per provider
    if LLM_PROVIDER == "openrouter":
        # OpenRouter is OpenAI-compatible; model must be an OpenRouter slug.
        return openai.LLM(
            model=os.environ.get("OPENROUTER_CONDUCT_MODEL", "anthropic/claude-haiku-4.5"),
            base_url=os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            api_key=os.environ["OPENROUTER_API_KEY"],
        )
    return anthropic.LLM(model=CONDUCT_MODEL)


def build_tts():  # noqa: ANN201
    if TTS_PRIMARY == "elevenlabs":
        # our config name is ELEVENLABS_API_KEY; the plugin's env var is ELEVEN_API_KEY.
        # Flash model for latency (ARCHITECTURE §2.1: TTS TTFB budget 90-200ms).
        return elevenlabs.TTS(model="eleven_flash_v2_5", api_key=os.environ["ELEVENLABS_API_KEY"])
    return cartesia.TTS(model="sonic-3")


class SpikeInterviewer(Agent):
    def __init__(self) -> None:
        super().__init__(instructions=PROMPT_PATH.read_text(encoding="utf-8"))


server = AgentServer()


# No agent_name: auto-dispatch to every new room (spike-simple; explicit
# dispatch rules come with the engine in T2).
@server.rtc_session()
async def spike_session(ctx: agents.JobContext) -> None:
    session_id = await create_backend_session(candidate_label="t1-voice-spike")
    sink = EventSink(session_id) if session_id else None
    tracker = LatencyTracker()

    session = AgentSession(
        stt=deepgram.STT(model="nova-3", language="en"),
        llm=build_llm(),
        tts=build_tts(),
        vad=silero.VAD.load(),
        turn_handling=TurnHandlingOptions(
            # Local semantic turn-detector model (ARCHITECTURE §2.2.3) — holds
            # the agent back on unfinished-sounding speech; runs on-device, no
            # LiveKit Cloud inference needed. max_delay is the state-aware
            # thinking-silence ceiling.
            turn_detection=EnglishModel(),
            endpointing=EndpointingOptions(
                mode="fixed",
                min_delay=max(ENDPOINTING_MIN_S / 1.5, 0.2),
                max_delay=SILENCE_MAXHOLD_S,
            ),
            # "adaptive" is LiveKit-Cloud-hosted (401 on the local dev server);
            # VAD-based barge-in runs entirely on-device.
            interruption=InterruptionOptions(mode="vad"),
            # §2.2 technique 10: start LLM+TTS on the interim transcript while
            # endpointing is still deciding; the framework cancels on mismatch.
            preemptive_generation=PreemptiveGenerationOptions(
                enabled=True, preemptive_tts=True
            ),
        ),
    )

    def emit(type_: str, payload: dict) -> None:
        if sink:
            sink.emit(type_, payload)

    @session.on("metrics_collected")
    def on_metrics(ev) -> None:  # noqa: ANN001 - event type varies by version
        m = getattr(ev, "metrics", ev)
        fields = tracker.record(m)
        if not fields:
            return
        # TTS TTFB closes out the stage chain for a turn
        if isinstance(m, metrics.TTSMetrics):
            turn = tracker.complete_turn()
            if turn:
                emit("turn_latency", {"prompt_version": PROMPT_VERSION_NAME, **turn})
                log.info("turn latency: %s", turn)

    @session.on("user_input_transcribed")
    def on_transcribed(ev) -> None:  # noqa: ANN001
        if getattr(ev, "is_final", False):
            emit("stt_final", {"text": ev.transcript})

    @session.on("conversation_item_added")
    def on_item(ev) -> None:  # noqa: ANN001
        item = ev.item
        if getattr(item, "role", None) == "assistant":
            interrupted = bool(getattr(item, "interrupted", False))
            emit("agent_turn", {"text": item.text_content or "", "interrupted": interrupted})
            if interrupted:
                emit("barge_in", {})

    if sink:
        await sink.start()
    emit("state_transition", {"to": "WARMUP", "note": "t1 spike single-state session"})

    await session.start(room=ctx.room, agent=SpikeInterviewer())
    await session.generate_reply(
        instructions="Greet the candidate warmly and ask what they have been building recently."
    )

    async def on_shutdown() -> None:
        summary = tracker.summary()
        log.info("== T1 LATENCY SUMMARY == %s", summary)
        emit("turn_latency", {"summary": True, **summary})
        if sink:
            await sink.close()

    ctx.add_shutdown_callback(on_shutdown)


if __name__ == "__main__":
    agents.cli.run_app(server)
