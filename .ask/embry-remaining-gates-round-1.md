# Embry Remaining Gates Architecture Review — Round 1

## Objective

Create an implementation and proof sequence that closes every remaining gate
before the 200+ integrated Embry voice/chat stress suite begins. Review one
singular rung at a time and preserve one session/turn/event lineage.

## Current proven live chain

One physical Jabra microphone turn is proven, live and non-mocked:

```text
RealtimeSTT final transcript
-> physical Horus verification score 0.886888
-> Memory intent and answer
-> irrelevant Memory answer rejected
-> one bounded persistent Tau tick
-> tau.turn_plan.v1
-> Chatterbox /tau/voice-render
-> 97,998-byte mono 24 kHz WAV, 2.04 seconds
```

Canonical identifiers:

```text
source event: listener.final_transcript.e05728f278813654
sequence: 29
session: physical-hot-mic-20260711T010233Z-2668d0b9
turn: listener-process-1
speaker event: speaker.verification.completed.26acf38666e41115
Tau plan hash: sha256:61740738d24d978c8c56f7712ec05ad78f123d248a542f1e659f6d168e9afeca
TTS text hash: a1b7eb2ee7a6aded8dda4e6cf30826f5afffb28a5597ee9389e91eb326d4e319
audio hash: 909a462da7f2e34ebbcb07c1b028b252e4f0798fb4757799a6b3d392103a3ddc
answer: The capital of France is Paris.
```

The causal render receipt has 16/16 acceptance fields true. Agent-skills main
contains the implementation at commit `648999e0b`. Chatterbox main records the
proof at `a64d6e7`.

## Source-derived operational model

1. **Implemented:** physical listener, final transcript, audio hash and source
   event.
2. **Implemented:** event-specific Horus verification and fail-closed Memory
   identity.
3. **Implemented:** Memory intent/answer followed by one persistent Tau tick and
   immutable turn plan.
4. **Implemented:** Chatterbox render from only the hashed Tau plan.
5. **Missing:** shared Watch/Sparta Chat UX projection from the operational
   journal. It must render human transcript, Embry answer, entity underlines,
   dynamic reasoning trace, and the exact audio artifact without invoking
   Memory, Tau, or Chatterbox from React.
6. **Missing:** actual playback authority. Browser or PipeWire playback must
   emit started/ended events for the same artifact/session/turn.
7. **Missing:** orb state and audio-envelope projection from playback events.
   `audio_ready` must not mean speaking.
8. **Missing:** replay from the complete session journal, rebuilding Chat UX,
   playing human and Embry audio at recorded offsets, and replaying orb states
   without rerunning providers.
9. **Missing:** integrated interruption lineage: old turn, new primary turn,
   speaker decision, duck/cancel/stop, stale-byte bound, and new-turn-wins.
10. **Missing:** one eight-turn green-path qualification repeated three times.
11. **Blocked until 5–10 pass:** 200+/300 integrated stress suite.

## Constraints

- Shared Watch/Sparta Chat UX only; no bespoke Embry chat.
- UX Lab is a journal projection, never the reasoning authority.
- `$extract-entities` output must use shared inline underline components; no
  static regex extraction.
- Reasoning trace must be the shared dynamic/collapsible Memory/Tau trace.
- Text, audio, orb and replay must share the exact session and turn IDs.
- Browser microphone is diagnostic only; Unix/PipeWire remains listener
  authority.
- No fixture/static replay may promote readiness.
- Every proof must state `live` and `mocked` and preserve hashes.
- Commit only relevant files in their owning repositories.

## Round 1 questions

1. Define the smallest correct **Chat UX projection rung** using the current
   operational SQLite journal and existing shared Watch/Sparta Chat components.
2. Name exact repository/file ownership and the endpoint/event adapter needed.
3. Define the minimum receipt and deterministic browser acceptance checks.
4. Explain how the shared entity-underlining and reasoning-trace components
   consume Memory/Tau events without duplicating extraction or reasoning.
5. Define the stop condition before proceeding to playback/orb.
6. Identify any false assumptions in the current operational model.

Return exact implementation steps and receipt schemas for Round 1 only, plus a
short preview of Rounds 2–5. Do not create generic architecture theater.
