# Embry Audible E2E Overall Status Review

## Objective

Assess the project agent's exact status and blockers against this immutable human outcome:

> Every Chatterbox feature works through a live, non-mocked, human-audible end-to-end path: physical listener/wake input, speaker handling, Memory/Tau routing, Chatterbox generation, physical speaker playback, interruption/stale-audio suppression, shared Chat UX turn authority, replay, and durable per-case receipts. A passing claim requires physical playback plus recapture or direct human-audible acceptance, not only generated WAV files.

Do not design a new architecture and do not write code. Diagnose current status, identify exactly one current top blocker, and impose a tightly managed next action on the project agent.

## Required candor about the project agent

The project agent frequently fails to follow directions, drifts into side quests, and chooses solvable but pointless adjacent problems. It has repeatedly treated unit tests, deterministic wiring checks, generated artifacts, report work, and renderer-only successes as progress against the human's audible E2E goal. It needs close external management. Do not accept its prose summaries or self-reported PASS fields. Require exact commands and independently inspectable artifacts for the controlling gate.

## Current gate

One generated Chatterbox WAV must be played through a real physical sink owned by Graham's active graphical session, recaptured from an independent physical microphone with intelligible speech, and recorded in a durable receipt. Device ownership recovered and `pw-play` now succeeds, but two physical microphone recaptures contain no transcribable speech.

## Current operational evidence

### Renderer and service lanes that genuinely ran live

- `logs/e2e-all-features-20260717/full-live-sanity-final/full-live-sanity.json`
  - 9 child lanes reported no failed gates.
  - Real CUDA Chatterbox generation, Whisper ASR, cache fill/hit, streaming, stream cancel, interruption state, turn controls, listener fixture transcription, Tau render, and listener -> Memory -> QRA -> Tau render ran.
  - This aggregate did not invoke physical speaker playback.
- `logs/e2e-all-features-20260717/agent-server-routes.json`
  - Health, presets, render-plan, single synthesis, and batch synthesis returned live artifacts.
- `logs/e2e-all-features-20260717/continuous-core-retry2/index.json`
  - Explicitly records `audible_playback=false` and `playback_sink_target=null`.
- `logs/e2e-all-features-20260717/S05-overlap-retry1/overlap-turn-control.json`
  - Live pyannote overlap, Memory turn-taking policy, and Chatterbox response artifact passed.
- `logs/e2e-all-features-20260717/qra-cache-retry2/listener-memory-tau-qra.json`
  - Live ASR, Memory recall, five Chatterbox variants, blessed cache selection, and Tau render passed.

### False-positive semantics that hid the audible gap

- `src/chatterbox/agent/conversation.py:479-498` calls HTTP `/synthesize` and then emits `speech.played` with `status="played"` when synthesis returns `ok`.
- That function never invokes `pw-play` or another device player. The event means "audio artifact generated," not "speaker playback occurred."
- `scripts/smoke_voice_chat_e2e.py` performs real playback only when `--audible-playback` is supplied. The reported successful continuous-core command omitted it.
- The project agent nevertheless described these runs as live E2E success. That claim was too broad.

### Current physical audio blocker

- Device ownership recovered without an agent code change: Graham now has active session `2627` on `seat0`, `/dev/snd/controlC4` grants `user:graham:rw-`, and PipeWire enumerates Jabra sink `65`, Jabra source `66`, and C920 source `40`.
- Attempt 1 artifact: `logs/e2e-all-features-20260717/physical-jabra-playback-recapture-20260717T130239Z/`.
  - `pw-play --target 65` returned `0` for the generated `stream.wav`.
  - Jabra source `66` captured 13.653 seconds / 1,310,764 bytes, mean `-54.1 dB`, peak `-28.9 dB`.
  - Live Whisper returned HTTP `200` with `text=""`.
- Attempt 2 artifact: `logs/e2e-all-features-20260717/physical-jabra-playback-c920-recapture-20260717T130600Z/`.
  - `pw-play --target 65` returned `0` again.
  - Independent C920 source `40` captured 13.632 seconds / 1,308,716 bytes, mean `-53.3 dB`, peak `-35.7 dB`.
  - Live Whisper returned HTTP `200` with `text=""`.
- The original generated WAV independently transcribes as: `Okay, I can stream this in short chunks ... Anything else you need?`
- No direct human-audible acceptance has been recorded. The focused physical-recapture family stopped at its two-attempt budget.

### Remaining unproven or missing goal surfaces

- Physical speaker playback command: executed twice; process-level success only, not yet human-audible acceptance.
- Physical recapture: failed because neither independent microphone capture contains transcribable speech.
- Physical Unix/PipeWire listener ingress under Graham's session: not rerun after device recovery.
- Browser getUserMedia input: not rerun after device recovery.
- Human-audible wake scenario: not run after crash.
- Shared Chat UX visible turn/audio/orb agreement: not freshly proven.
- Replay through the same Chat UX timeline: not freshly proven.
- `/readiness`: renderer returns HTTP 404.
- The historical 200-case campaign's raw state and campaign receipt were under `/tmp` and were lost on workstation restart. Only the handoff summary survives; the recovered manifest currently reports `not_started`.

## Project-agent changes already made

- Commit `89df295810c484735e9c0d523d8b94736ccd7ed9` pushed to `origin/main`.
- Runtime outputs now default to repository `logs/` instead of `/tmp`.
- Docker launcher selects the image's working Python 3.11 interpreter.
- Container/host output mapping and QRA ledger paths now use durable `logs/` storage.
- RealtimeSTT runner now uses its durable project virtual environment.
- These retention and harness repairs do not satisfy the audible gate.

## Research context

- MDN states `getUserMedia()` rejects with `NotFoundError` when no media track satisfying the requested type/constraints can be found: https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia
- Fedora's PipeWire overview describes `/dev/snd` ACL ownership and systemd-logind's role in device access: https://fedoramagazine.org/introduction-to-pipewire/
- ArchWiki documents `wpctl status` as the user-level source/sink inventory and `wpctl set-default ID` for choosing a real source/sink: https://wiki.archlinux.org/title/PipeWire

## Exact questions for WebGPT

1. Give an overall accounting against the immutable goal using only: `passed`, `failed`, `blocked_by_systemic_failure`, and `not_run`. Do not merge artifact generation with audible playback.
2. Name exactly one TOP_BLOCKER for the current gate.
3. Prescribe exactly one next action for the project agent, with one command-level live stop condition.
4. State explicit forbidden side quests that the project agent must not pursue before the current gate closes.
5. Explain how WebGPT should manage this agent closely given its repeated direction-following failures and attraction to solvable but pointless adjacent work.

## Required deliverable

Return:

1. `DIAGNOSIS`
2. A compact overall status table
3. `TOP_BLOCKER: <exactly one blocker>`
4. `NEXT_ACTION: <exactly one bounded action>`
5. `LIVE_STOP_CONDITION: <one command/artifact condition>`
6. `FORBIDDEN_SIDE_QUESTS: <explicit list>`
7. Exactly one ruling:
   - `PASS_CURRENT_GATE`
   - `BLOCKED_CURRENT_GATE: <one concrete blocker>`
   - `REJECTED_SCOPE_EXPANSION`
