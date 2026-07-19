# Handoff Report: Chatterbox

**Timestamp**: 2026-07-04T23:14:00Z
**Active Agent**: Gemini 3.5 Flash (Cursor Agent)

## 1. Project Overview

- **Ecosystem**: Python (FastAPI, PyTorch, RealtimeSTT, Resemblyzer)
- **Core Purpose**: Upstream Resemble AI Chatterbox models extended with a local FastAPI Chatterbox Turbo agent server. Features include ASR-gated audio acceptance, sentence-aware Turbo chunking, interruptible PCM streaming, turn controls, conversation sanity receipts, and memory-gated blessed-QRA instant playback.

## 2. Current State (Doc-Code Alignment)

- **Documented Features**:
  - Agent server (`src/chatterbox/agent/server.py`) exposing `/health`, `/presets`, `/render-plan`, `/synthesize`, `/synthesize-batch`, `/synthesize-batch-stream`, `/tau/voice-render`, `/turn/{turn_id}/cancel`, `/playback/{turn_id}/duck`, and `/playback/{turn_id}/stop`.
  - Docker launcher (`scripts/start_agent_server_docker.sh`) on port `8018`.
  - ASR acceptance, Turbo chunking (300-character clamp), and PCM streaming.
  - Blessed QRA pre-rendering hook (`scripts/qra_creation_audio_hook.py`).
  - Conversation sanity ladder (Rungs 1-7) for listener input, state, memory, and interruption.
- **Implemented Reality**:
  - Fully implemented and aligned with `PROJECT_KNOWLEDGE.md` and `docs/VOICE_CHAT_REQUIREMENTS.md`.
- **Drift/Misalignments**:
  - None. Code matches the extensive documentation perfectly.

## 3. What is Working Well

- **72/72 tests passing** with 100% success rate under `PYTHONPATH=src pytest`.
- **Audible Voice Chat E2E suite** (`scripts/smoke_voice_chat_e2e.py`) passes all 8 scenarios with real audio playback.
- **Primary speaker gating** (Resemblyzer threshold 0.82) and **Speaker-scoped memory** are fully functional.
- **Embry personality variant selection** renders 5 variants successfully.
- **Continuous voice-loop runner** with configurable probes (`--include-qra-cache-probe`, `--include-overlap-probe`) is stable.

## 4. What is Currently Broken

- **Browser ASR**: Browser getUserMedia capture passes transport but RealtimeSTT/Whisper returns empty transcripts. Architecture decision needed: PipeWire bridge vs better browser source.
- **Real-time Diarization**: CPU-based PyAnnote works on captured WAVs but is too slow for live streaming; GPU is blocked by NVIDIA driver/CUDA compatibility.
- **QRA Fast-path**: Not hit during live loops.
- **FastAPI Deprecation**: `on_event` is deprecated in FastAPI, needs migration to lifespan event handlers.
- **BaseModel Shadowing**: `schema` field in `TauVoiceRenderRequest` shadows parent `BaseModel` attribute.

## 5. Next Steps

1. **Fix Browser ASR Path**: Research better browser microphone configurations or implement a PipeWire virtual source bridge.
2. **Resolve Real-time Diarization**: Address NVIDIA/CUDA driver compatibility or run PyAnnote GPU inside Docker.
3. **Continuous Real-loop Integration**: Stitch browser/mic capture, RealtimeSTT, speaker gate, memory, and Chatterbox into a single continuous loop.
4. **Lifespan Migration**: Migrate FastAPI `on_event` to lifespan event handlers.

## 6. Project Context for Success

- **Key Files**:
  - `src/chatterbox/agent/server.py` (FastAPI server)
  - `scripts/smoke_voice_chat_e2e.py` (Main audible voice E2E suite)
  - `scripts/smoke_continuous_voice_loop.py` (Continuous runner with optional probes)
  - `scripts/smoke_conversation_ladder.py` (Rung 7 listener-boundary runner)
- **Recent Changes**:
  - Added Embry personality audition smoke (`scripts/smoke_embry_personality_audition.py`).
  - Required audible voice chat E2E playback (`scripts/smoke_voice_chat_e2e.py`).
  - Recorded browser ASR stress failures.
