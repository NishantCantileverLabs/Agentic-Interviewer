# /agent — LiveKit Agents voice worker

Lands in T1 (voice loop spike). Structure per PHASE1_ARCHITECTURE.md §3.2/§9:

```
engine/       state machine, context builder (cache-stable §6.3 layout), plan
pipeline/     stt, tts, llm nodes, latency instrumentation
observation/  code-observation loop (CODING state)
```

During the T1 spike the worker runs locally (not containerized) so latency numbers
aren't skewed by Docker Desktop networking on the dev machine.

## T1 spike — how to run

Requires keys in the repo-root `.env`: `DEEPGRAM_API_KEY`, `CARTESIA_API_KEY`
(or `ELEVENLABS_API_KEY` + `TTS_PRIMARY=elevenlabs`), `ANTHROPIC_API_KEY`
(or `OPENROUTER_API_KEY` + `LLM_PROVIDER=openrouter`), and — for room mode —
`LIVEKIT_URL` / `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET` from a LiveKit Cloud project.

```bash
cd agent
python -m venv .venv && .venv/Scripts/pip install -e .
python spike_agent.py console     # local mic/speaker session, no LiveKit room needed
python spike_agent.py dev         # join a LiveKit Cloud room
```

With the docker stack up, every turn posts `turn_latency` / `stt_final` /
`agent_turn` / `barge_in` events to the backend event log; the shutdown hook
logs the p50/p95 summary against GATE 1 (p50 ≤ 800ms, p95 ≤ 1500ms).
