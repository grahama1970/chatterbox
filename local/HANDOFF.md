# Handoff Report: Chatterbox / Embry Voice Integration

**Timestamp**: 2026-07-16T19:39:46Z
**Active Agent**: Codex

## 1. Project Overview

- **Ecosystem**: Python, FastAPI, PyTorch/CUDA, Docker, PipeWire, RealtimeSTT, Graph Memory, Tau, and Chatterbox Turbo.
- **Core Purpose**: Chatterbox is the strict speech renderer in the Embry voice system. It receives an approved Tau turn plan, renders interruptible audio, and emits immutable audio and lineage receipts. Listener, identity, Memory, orchestration, playback, UI, orb, and replay authority belong to sibling components.
- **Immediate objective**: Preserve the completed 200-case mixed-qualified campaign, then prove the remaining Chat, playback, orb, replay, and interruption gates in one unified lineage manifest.

## 2. Current State (Doc-Code Alignment)

- **Documented Features**:
  - FastAPI renderer endpoints including `/tau/voice-render`, batch/stream synthesis, cancel, duck, and stop.
  - ASR-gated audio acceptance, sentence-aware chunking, blessed-QRA playback, and receipt-backed audits.
  - A manifest-driven Embry readiness auditor that must leave `suite_ready=false` until one unified run proves every required gate.
- **Implemented Reality**:
  - Chatterbox renders live approved turns and has a GPU runtime image. The latest runtime-image repairs install the correct Python launcher and `ffprobe`.
  - A live-service, mixed-qualified campaign completed all 200 cases and 650 turns using qualified Horus-clone input. RealtimeSTT, Memory, Tau, and Chatterbox were exercised without mocked services or typed transcripts.
  - Campaign ID: `campaign_7f9b4103a9f6d86aa3cf3ad5`.
  - Campaign result: `PASS`, 200/200 cases, 650/650 turns, zero unresolved turns, zero current failures, and 10 retained historical failures that were repaired or recovered.
  - The campaign correctly reports `suite_ready=false` and `release_readiness_authority=false`.
- **Drift/Misalignments**:
  - `README.md` and `PROJECT_KNOWLEDGE.md` predate the completed campaign and still describe the 200+ run as pending.
  - Existing component audit JSON files are historical slices. They must not be relabeled as unified release evidence.
  - The completed campaign used qualified synthetic Horus-clone speech, not fresh physical human speech. It is an intermediate live regression, not physical release qualification.

## 3. What is Working Well

- **Campaign receipt**: `/tmp/embry-audio-e2e-200/runtime-a01/campaign-receipt.json`
  - SHA-256: `b5530a348cb8aa23f8ed184fa0f4886f592eab4935a7c1689cea0aa6160a53dd`
  - `status=PASS`, `ok=true`, `live=true`, `mocked=false`
  - `case_count=200`, `completed_case_count=200`
- **Campaign state**: `/tmp/embry-audio-e2e-200/state-a01.json`
  - SHA-256: `a019ac7c748f34684bff2985c5e792145010b3626396f14b43a7fe6a9f9c3a35`
  - `status=completed`, 200 cases, 650 turns, zero current failures, 10 historical failures.
- **Campaign manifest**: `/tmp/embry-audio-e2e-200/manifest.json`
  - SHA-256: `5369e97022dce0590389f856f9820121ee5f15cc3322373538d7b9bc7443947a`
  - 15 scenario folders, 200 cases, and 650 turns.
- Independent artifact verification found 650 listener receipts, 650 Memory/Tau receipts, 650 render receipts, and 200 case receipts. It checked 4,100 receipt/artifact locators with zero missing files and zero hash mismatches, plus 650 audio files with zero hash mismatches.
- The bounded Memory retry repaired a live Qdrant `httpx.RemoteProtocolError`/HTTP 500 path. Relevant agent-skills commit: `4de098b9851662a79f5b5f9fbd7fa153c591c3f0`.
- Chatterbox HEAD: `fd8f20bb8e488b0fd64f1a7b1523a9858857c4c9`.

## 4. What is Currently Broken or Pending

- **Unified release evidence is missing**: Chat projection, authoritative playback, orb envelope, provider-free replay, and old-turn/new-turn interruption are not proven together in one physical-session manifest.
- **Physical authority is missing from this campaign**: qualified Horus-clone audio is acceptable for the intermediate regression but does not prove fresh physical microphone wake, capture, or human speaker identity for every case.
- **Historical failures remain visible by design**: eight listener failures, one Chatterbox render-acceptance failure, and one Memory/Tau Qdrant 500 occurred during the campaign. All affected turns later completed; do not erase this history.
- **Readiness remains false**: neither the campaign receipt nor component audits may promote `suite_ready=true`.
- **Documentation is stale**: update current-status documentation only after preserving the campaign receipts and clearly retaining the intermediate-regression boundary.

## 5. Next Steps

1. Do not rerun the completed 650-turn campaign unless a regression or artifact-integrity check fails.
2. Build one unified manifest lane using a single session, turn lineage, source event, Tau plan hash, and Chatterbox audio hash.
3. Prove journal-backed Shared Chat projection from the exact accepted listener and Tau events, with no provider calls from React.
4. Prove authoritative playback start/end for the exact Chatterbox artifact, then bind orb envelope state to those playback events.
5. Replay the same journal without rerunning RealtimeSTT, Memory, Tau, Chatterbox, or entity extraction.
6. Prove interruption with explicit `old_turn_id`, `new_turn_id`, speaker decision, cancel/stop events, zero stale old-turn bytes, and new-turn-wins behavior.
7. Regenerate the canonical manifest audit. Only a unified, hash-consistent pass may permit the suite promoter to set `suite_ready=true`.

## 6. Project Context for Success

- **Key Chatterbox files**:
  - `src/chatterbox/agent/server.py`: render API, Tau request mapping, streaming, and turn control.
  - `docker/Dockerfile.runtime`: GPU runtime image.
  - `scripts/audit_horus_live_loop_gates.py`: manifest-driven readiness audit.
  - `scripts/smoke_voice_chat_e2e.py`: fixed eight-scenario smoke; not the 200-case campaign runner.
  - `docs/EMBRY_HORUS_E2E_STATUS_AUDIT.json`: canonical historical status artifact; regenerate from a unified manifest rather than editing it.
- **Cross-repository runtime authority**:
  - `agent-skills/skills/embry-voice-control`: journal, mixed-qualified campaign runner, Memory/Tau controller, and unified proof ownership.
  - `RealtimeSTT`: listener and acoustic-event producer.
  - `graph-memory-operator`: speaker resolution, intent, answerability, and voice policy.
  - `tau`: bounded orchestration and turn-plan handoff.
  - `pi-mono`/Embry OS: Shared Chat projection, playback, orb, and replay presentation.
- **Recent Chatterbox commits**:
  - `fd8f20b` Install ffprobe in runtime image.
  - `8e5eeb1` Fix runtime image Python launcher.
  - `fc59f24` Fix live Memory miss and browser replay checks.
  - `45462a3` Fix Embry replay targeting and stress circuit breaker.
  - `a780a9e` Add Chatterbox GPU runtime image.
- **Proof boundary**:
  - `mocked: no`
  - `live: yes` for RealtimeSTT, Memory, Tau, and Chatterbox service execution in the mixed-qualified campaign.
  - Proven: executable 200-case/650-turn live-service regression with qualified Horus-clone audio and complete artifact hashing.
  - Not proven: fresh physical-human qualification for the campaign, unified Chat/playback/orb/replay/interruption lineage, or release readiness.
