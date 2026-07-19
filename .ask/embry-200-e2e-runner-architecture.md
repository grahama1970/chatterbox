# WebGPT Create-Architecture Request: Embry 200-Case Audio-First E2E Runner

## Objective

Design the missing executable runner that converts the existing 200+ Embry stress conversation matrix into real audio-first, journal-correlated E2E tests.

Every counted case must exercise:

```text
Horus speech audio
-> local PipeWire capture
-> RealtimeSTT partial/final callbacks
-> enrolled Horus speaker gate
-> canonical SQLite journal event
-> Memory speaker/intent/answer pipeline
-> one bounded persistent Tau tick and skill calls
-> Chatterbox render from Tau plan
-> explicit Jabra pw-play authority
-> Chat projection and orb lineage
-> replayable journal
-> interruption policy when required
```

Typed matrix prompts, mocked transcripts, fixture-only provider responses, and direct Chatterbox text calls must not count as E2E cases.

## Current Proven Canonical Turn

One physical turn passes with this lineage:

```text
session: physical-hot-mic-20260711T010233Z-2668d0b9
turn: listener-process-1
listener.final_transcript sequence 29
speaker.verification.completed sequence 32, Horus score 0.886888
tau.turn_plan.completed sequence 42
chatterbox.voice_render.completed sequence 46
playback.requested sequence 49
playback.started sequence 50
playback.ended sequence 51
human audible witness: EXACT
```

Audio authority:

```text
audio sha256: 909a462da7f2e34ebbcb07c1b028b252e4f0798fb4757799a6b3d392103a3ddc
bytes: 97998
mono, 24000 Hz, 2040 ms
Jabra sink node.name:
alsa_output.usb-0b0e_Jabra_SPEAK_510_USB_501AA5274B1D022000-00.analog-stereo
```

Final playback receipt:

```text
/tmp/embry-round2-pipewire-playback-v2/receipt.json
```

## Existing Repositories and Runners

```text
chatterbox:
/home/graham/workspace/experiments/chatterbox

stress matrix:
docs/EMBRY_STRESS_SESSION_MATRIX.json

typed integration runner:
scripts/smoke_embry_intelligence_stress.py

fixed-scenario voice index runner:
scripts/smoke_voice_chat_e2e.py

RealtimeSTT:
/home/graham/workspace/experiments/RealtimeSTT

voice authority and journal:
/home/graham/workspace/experiments/agent-skills/skills/embry-voice-control

Tau:
/home/graham/workspace/experiments/tau

Memory:
/home/graham/workspace/experiments/graph-memory-operator

Shared UI:
/home/graham/workspace/experiments/pi-mono/packages/ux-lab
```

## False-Green We Just Rejected

`smoke_embry_intelligence_stress.py` ran 55 live Memory/Tau/skill/Chatterbox cases and reported 55/55. Those results are excluded from E2E totals because they begin with typed matrix prompts and do not traverse RealtimeSTT or the canonical journal event spine.

`smoke_voice_chat_e2e.py` has eight fixed scenarios and delegates to lower smokes. It is not a 200-case matrix driver and does not guarantee one same-turn lineage through every required component.

Current truthful full E2E count is 1, not 55 or 200.

## Matrix Requirements

The existing matrix covers:

- SPARTA QRA/compliance
- persona memory
- static facts
- current research through Brave Search
- analytics and create-figure
- evidence-case generation
- frustrated, hostile, discouraged, and playful tone
- emotion tags and pause policy
- factory noise and overlap
- interruption and new-turn-wins
- idle hum/check-ins
- simple, medium, advanced, adversarial, and soak difficulty

Every conversation must preserve its arc, steering, interruption strategy, tone, emotion tags, and expected skill route.

## Critical Architecture Question: Horus Audio Generation

The runner needs distinct spoken audio for every matrix utterance while retaining Horus identity. Do not silently use `espeak-ng`, generic TTS, or Embry's own Chatterbox voice and then claim Horus speaker verification.

Decide the smallest defensible source strategy:

1. A qualified Horus TTS/voice-clone generator whose outputs pass held-out speaker verification.
2. A recorded Horus utterance corpus covering the matrix.
3. A two-tier system where most cases use qualified Horus synthesized speech and a smaller physical-human qualification subset proves room acoustics.

State exactly which cases can be automated, which require Graham/Horus to speak, and what evidence prevents synthetic voice from being relabeled as physical speech.

## Required Output

Return an implementation-ready architecture, not a generic diagram.

Provide:

1. Exact repository and file ownership.
2. Runner CLI and process model.
3. Audio-source qualification design.
4. How one matrix case becomes a multi-turn audio session.
5. Event and manifest schemas.
6. Per-case pass/fail gates.
7. Conversation-level and campaign-level receipts.
8. Durable resume, crash recovery, and idempotency.
9. How to run 1, then 5, then 25, then 200 cases without changing proof semantics.
10. How to capture live failures without substituting fixtures.
11. How Chat projection, orb, replay, and interruption are checked without browser mic authority.
12. Exact commands for the first single-case implementation and live proof.
13. A fail-closed answer if 200 physical-Horus utterances cannot be automated honestly.

## Required Stop Conditions

The proposed runner must not count a case unless:

```text
audio source receipt exists
captured PCM is non-silent and hash-bound
RealtimeSTT final event is nonempty and semantically matches expected utterance
speaker gate accepts Horus or records the scenario's expected rejection
one session/turn lineage survives Memory, Tau, Chatterbox, and playback
expected tool/skill route is observed
Chat projection uses the same turn
orb state comes only from playback events
replay reconstructs the journal without provider reruns
interruption cases include old/new turn causation and stale-byte bounds
all artifacts are live=true and mocked=false
```

Also state what can be implemented immediately using existing code versus what requires a new qualified Horus audio source.

End the response with the supplied terminal sentinel.
