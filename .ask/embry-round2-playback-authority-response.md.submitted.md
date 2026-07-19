# WebGPT Create-Architecture Review: Embry Round 2 Playback Authority

## Objective

Define the smallest implementation and deterministic proof for one authoritative Unix/PipeWire playback of the already accepted Embry Chatterbox artifact.

This is Round 2 only:

```text
hash-bound accepted audio artifact
-> playback.requested
-> audible PipeWire/Jabra playback
-> playback.started
-> playback.ended
-> same SQLite journal lineage
```

Do not broaden into orb, envelope animation, replay, interruption, browser microphone, synthesis, Memory, Tau, or the 200+ suite.

## Proven Inputs

- Session: `physical-hot-mic-20260711T010233Z-2668d0b9`
- Turn: `listener-process-1`
- Source event: `listener.final_transcript.e05728f278813654`, sequence `29`
- Tau plan event: `tau.turn_plan.completed.67d7b5460593b43d`
- Chatterbox render event: `chatterbox.voice_render.completed.ae1fa93d74f80c92`
- Tau plan SHA-256: `sha256:61740738d24d978c8c56f7712ec05ad78f123d248a542f1e659f6d168e9afeca`
- TTS/display text SHA-256: `a1b7eb2ee7a6aded8dda4e6cf30826f5afffb28a5597ee9389e91eb326d4e319`
- Text: `The capital of France is Paris.`
- Audio artifact: accepted `finished_response.wav` from the canonical physical turn
- Audio SHA-256: `909a462da7f2e34ebbcb07c1b028b252e4f0798fb4757799a6b3d392103a3ddc`
- Audio bytes: `97998`
- Format: mono, 24 kHz, 2.04 seconds, WAV
- Causal render receipt schema: `embry.voice.causal_chatterbox_render_receipt.v1`, status `PASS`, all 16 acceptance fields true
- Journal database: canonical Round 1 SQLite WAL journal containing 46 ordered events through the accepted render
- Journal service: `http://127.0.0.1:8032`
- Round 1 browser receipt schema: `embry.chat_ux_projection_receipt.v1`, `ok=true`, `live=true`, `mocked=false`

## Local Audio State

```text
PipeWire version: 1.0.5
Playback command: pw-play from the workstation PipeWire package
Selected sink: 64, Jabra SPEAK 510 Analog Stereo, volume 0.70
Selected microphone: 62, Jabra SPEAK 510 Mono, volume 0.94
```

`wpctl status` currently marks sink `64` as active/default among live sinks.

## Current Boundary

- `agent-skills/skills/embry-voice-control` owns session/turn authority and the SQLite journal.
- RealtimeSTT owns listening.
- Memory and Tau own response planning.
- Chatterbox owns rendering.
- UX Lab owns projection only.
- No component currently owns authoritative audible playback lifecycle.

## Required Events

All events must use `embry.voice_event.v1`, server-assigned journal sequence, `live=true`, `mocked=false`, and the exact session/turn/correlation lineage.

```text
playback.requested
playback.started
playback.ended
```

They must carry at least:

```text
playback_authority_id
artifact_id
audio_sha256
audio_bytes
audio format/duration
selected PipeWire sink identity and stable node name
pw-play command and PID
monotonic requested/started/ended timestamps
process exit code
causation_id chain
render event ID
Tau plan hash
```

## Fail-Closed Requirements

- Resolve the artifact only through the journaled render event.
- Rehash and remeasure the WAV before playback.
- Reject wrong session, turn, artifact ID, hash, byte count, or render lineage.
- Reject missing/non-Jabra sink or ambiguous target.
- Do not use default-sink inference as proof when an explicit stable sink name is available.
- Do not emit `playback.started` merely because the process spawned; define a defensible start receipt.
- Do not emit `playback.ended` unless the process exits successfully and timing is plausible.
- A repeated idempotency key must not start a second playback.
- Cancellation/interruption is out of scope in this rung.
- Browser audio is out of scope.
- Orb remains idle/audio-ready throughout this proof.

## Human Acceptance

The human must audibly hear exactly:

```text
The capital of France is Paris.
```

The receipt must separate machine evidence from the human audible-witness field. Do not fabricate the human witness; define how the project agent records it after asking the human.

## Questions

1. Which component/file should own the playback controller and why?
2. Should playback execute directly with `pw-play --target <stable-node-name>` or through an existing PipeWire/Pulse service/package already on the workstation?
3. What is the smallest correct start-detection rule for `playback.started` with `pw-play`?
4. Give exact event payloads, causation IDs, idempotency behavior, process lifecycle, and receipt schema.
5. Give exact file ownership and focused deterministic tests.
6. Give the one live run command for sink 64/Jabra and the exact stop condition.
7. Identify any false assumptions in using numeric sink `64` versus a stable node name.
8. State what Round 2 proves and explicitly does not prove.

Return an implementation-oriented architecture decision, not a generic diagram. The next project-agent action must be one singular runnable patch and proof.

---

Completion contract for browser automation:

At the very end of your final answer, print exactly:

<<<WEBGPT_DONE:20260711T130346Z:c8f914c5>>>

Do not print anything after that marker.
