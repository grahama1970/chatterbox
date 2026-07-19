# WebGPT architecture request: Embry voice/chat stress system

You are reviewing the Embry voice/chat initiative as an architecture reviewer.
The project agent has been drifting between UI patches, local bug fixes, and
partial stress tests. The human explicitly says this is a larger architectural
challenge, not a bug-fixing exercise.

## Goal

Design the next practical architecture and proof sequence for a shared Embry
voice/chat system:

1. RealtimeSTT listens to real audio.
2. Speaker identity/diarization gates decide whether Horus is the primary speaker.
3. Accepted turns go through memory and Tau.
4. Chatterbox generates Embry speech with tone/emotion tags.
5. Shared Chat UX updates at the same time as voice output.
6. The Embry orb tracks the actual Embry audio, not fake state.
7. Sessions replay the real event journal with text, audio, memory reasoning,
   interruption events, and orb state.

## Current evidence

The current stress matrix has 200 labeled sessions:

- 9 passed
- 31 failed
- 160 not run

Recent live speaker identity slice:

- mocked=false
- live=true
- 4/4 simple speaker identity sessions passed
- known Horus -> status known, speaker_id horus_lupercal, personal memory allowed
- unknown speaker -> status unknown, personal memory disabled, identity prompt
- ambiguous low-confidence -> status unknown, personal memory disabled
- Horus/female overlap -> status ambiguous, no authoritative speaker, personal memory disabled

Current known failure families:

- SPARTA QRA memory answers can return unrelated S0609/deprecated-control text.
- Persona memory answers can return unrelated skill descriptions instead of Horus facts.
- Memory miss can return unrelated records instead of clarifying or no-answer.
- Tone/emotion intent often returns generic memory_confident instead of firm,
  humorous, gentle, or one-at-a-time tones.
- Tau doctor runs, but Embry sessions do not yet create a tau.agent_handoff.v1
  work order or DAG receipt.
- Browser getUserMedia transport can capture audio, but browser ASR quality is
  source-dependent. HD webcam worked in one receipt; Jabra browser capture often
  produced empty transcripts.
- UI route has had repeated design drift. It should use the shared Chat UX and
  show dynamic replay, memory reasoning trace, entity underlines, audio, and orb
  state from the same event ledger.

## Hard constraints

- No mock transcripts as proof.
- No DOM-only proof for voice loop behavior.
- No direct `window.embrySpeak(...)` as full-loop proof.
- Do not let UX Lab be the proof authority. It must render the event journal.
- Chatterbox is the renderer. It is not the reasoning layer.
- RealtimeSTT is listener/VAD/ASR companion.
- memory/Tau owns reasoning, answerability, intent, and skill/tool handoff.
- Agent must produce deterministic pass/fail receipts for every rung.

## Question

Please produce:

1. A source-derived numbered architecture model for the final system.
2. A minimal event schema / ledger contract that all components should share.
3. The next 7-10 proof rungs, in order, with acceptance criteria.
4. Which existing partial work should be kept, quarantined, or replaced.
5. The next concrete implementation task the Codex project agent should do
   after receiving your answer.

Be blunt. Separate implemented, partial, and missing behavior. Do not claim
full-loop success unless the evidence above supports it.
