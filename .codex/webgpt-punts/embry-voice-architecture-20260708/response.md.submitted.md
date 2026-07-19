# WebGPT Architecture Review Request: Embry Voice/Chat Stress Testing

You are reviewing the Embry voice/chat stress-test architecture. The project agent has been drifting between UI, voice, memory, Tau, and listener fixes. The human asked whether this is now a larger architectural question and requested WebGPT + create-architecture help before continuing.

## Core Objective

Stress test the Embry voice/chat system to identify concrete failures across RealtimeSTT ingress, speaker identity/diarization, memory/Tau routing, Chatterbox speech, shared Chat UX sync, Embry orb sync, replay, interruption/barge-in, Brave Search research, and voice delivery tone/emotion from memory intent.

The human wants about 200 labeled session tests with difficulty, pass/fail, receipt paths, and logs. Tests must be real/non-mocked where the route claims live behavior.

## Current Evidence Summary

Stress matrix artifact:

```text
session_count: 200
status_counts: {passed: 5, failed: 35, not_run: 160}
route_families:
  - memory.sparta_qra
  - memory.persona_memory
  - memory.persona_memory.fail_closed
  - brave-search.source_receipt
  - tau.agent_handoff
  - ux-lab.shared_chat
  - chatterbox.turn_control
  - memory.speaker.resolve
  - realtimestt.factory_capture
  - memory.intent.voice_delivery
```

Memory/search subset receipt summary:

```text
id: matrix-simple-memory-search-v2
mocked: false
live: true
ok: false
selected_count: 16
passed: 4 Brave Search sessions
failed: 12 memory-backed sessions
```

Observed failures:

- SPARTA QRA questions leaked unrelated S0609/deprecated-control answers.
- Persona memory recall used unrelated source collections and missed Cthonia.
- Persona memory miss answered unrelated records instead of clarifying.

Simple-rest subset receipt summary:

```text
id: matrix-simple-rest
mocked: false
live: false
ok: false
selected_count: 24
```

Observed failures:

- Tau tool orchestration: runner_route_not_implemented
- Chat UX sync: runner_route_not_implemented
- interruption: runner_route_not_implemented
- speaker identity: runner_route_not_implemented
- factory noise: runner_route_not_implemented
- tone/emotion: initially runner_route_not_implemented

Tone rerun receipt summary:

```text
id: matrix-tone-simple
mocked: false
live: true
ok: false
selected_count: 4
```

Observed tone results:

- tone_emotion-simple-01: PASS. Frustrated/warm de-escalation returned memory_confident/satisfied.
- tone_emotion-simple-02: FAIL. Hostile/humorous boundary returned memory_confident/satisfied, expected one of firm_boundary, deflect_calm, playful_light.
- tone_emotion-simple-03: FAIL. Discouraged/gentle next-check returned memory_confident/satisfied, expected one of neutral_warm, calm_precise, careful_concerned, relieved.
- tone_emotion-simple-04: FAIL. Two-speaker overlap returned memory_confident/satisfied, expected one_at_a_time_interrupt or firm_boundary.

## Current Problem

The stress matrix is useful, but six route families still lack executable route implementations in the runner, and the implemented memory/tone paths reveal semantic failures. The project needs a better architecture for:

- deciding which tests belong in Chatterbox vs memory vs Tau vs UX Lab vs agent-skills,
- defining endpoint contracts so agents do not bespoke test code,
- sequencing fixes so the system moves toward the full live loop instead of adding dashboards or logs,
- making pass/fail deterministic without pretending unimplemented routes are live,
- making the shared Chat UX and voice output sync testable from the same event ledger.

## Request

Please provide a source-derived architecture recommendation.

Required response sections:

1. Numbered model: 10-15 steps from user audio/text input to memory/Tau reasoning to Chatterbox speech to Chat UX/orb/replay.
2. Implemented vs missing: label each step as implemented, partial, missing, or failing based on the evidence above.
3. Test architecture: specify where each route family should be tested and what endpoint/receipt contract each needs.
4. Failure-fix order: choose the next 5 implementation slices that produce the most useful receipts, not UI theater.
5. Pass/fail rules: define deterministic gates for the 200-session matrix, including when live=false is acceptable as a failure state.
6. Architecture YAML: return a create-architecture compatible YAML with components and connections. Use colors: green=verified, amber=partial, red=failing/missing, blue=ingress/retrieval, purple=UX/orchestration.

Constraints:

- Do not recommend more UI polish as the next step.
- Do not treat DOM screenshots as proof of voice/listener correctness.
- Do not call a direct Chatterbox speak proof a full live loop.
- Keep Chatterbox as renderer, RealtimeSTT as listener, memory/Tau as reasoning/routing, UX Lab as renderer/replay surface.
- Prioritize real endpoint contracts and receipts.
- The immediate next actions should be narrow enough for a project agent to implement without redesigning the whole system.

---

Completion contract for browser automation:

At the very end of your final answer, print exactly:

<<<WEBGPT_DONE:20260708T002236Z:a1a0461b>>>

Do not print anything after that marker.
