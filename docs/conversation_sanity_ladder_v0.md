# Chatterbox Conversation Sanity Ladder v0

This document defines the next proof ladder for Chatterbox as a real,
non-mocked voice-agent system. It is a contract for rungs 1-6, not a claim that
the rungs already pass.

The current server already has live receipts for ASR-gated batch synthesis,
accepted-audio cache fill/hit, PCM chunk streaming, interruption stale-chunk
skips, and cancel/duck/stop controls. Those receipts prove transport and
rendering behaviors only. They do not prove listener behavior, conversational
quality, memory-grounded response selection, Brave Search integration, or
dynamic emotional steering.

## Global Rules

Every rung must write a copyable JSON receipt under
`/tmp/chatterbox-fork-agent-out/conversation-ladder/<run-id>/`.

Every receipt must include:

- `schema`: stable rung receipt schema name.
- `rung`: integer from 1 to 6.
- `run_id`: unique run identifier.
- `mocked`: must be `false`.
- `live`: must be `true`.
- `started_at_utc` and `ended_at_utc`.
- `services`: health and URL metadata for every live service used.
- `inputs`: paths, hashes, durations, and text fixtures.
- `events`: ordered turn/listener/ASR/memory/tool/TTS/playback events.
- `artifacts`: generated audio, transcripts, child receipts, and logs.
- `failed_gates`: empty only when the rung passes.
- `claims.proves`: exact behavior proven by this rung.
- `claims.does_not_prove`: explicit boundaries that remain out of scope.

No rung may use fake ASR, fake TTS, fake memory recall, fake Brave Search
results, synthetic provider responses, or placeholder production data as final
evidence. Fixture audio files are allowed as real input media; patched services
are not.

## Services

Expected local services:

- Chatterbox agent server: `http://127.0.0.1:8018`
- OpenAI-compatible Whisper ASR: configured by the Chatterbox server and/or
  smoke harness.
- Memory daemon: `http://127.0.0.1:8601`
- Brave Search: through the `$brave-search` runtime or a server-side tool
  adapter that records the raw Brave result payload.

The listener can start as a file-backed audio listener. A live microphone is a
transport mode, not a different conversation contract. The listener contract is
the same in both cases:

```text
audio_input -> VAD/endpointing/listener event -> ASR transcript -> turn router
```

## Rung 1: Scripted Audio Turn

Purpose: prove one real audio input can enter the system and produce one
ASR-verified Chatterbox audio response.

Input:

- One short WAV fixture containing a simple user request.
- Expected transcript text for the fixture.
- Deterministic response plan that does not require memory or tools.

Required live path:

```text
WAV fixture -> listener/ASR -> transcript -> response text ->
Chatterbox TTS -> response WAV -> ASR verification
```

Pass gates:

- Chatterbox `/health` returns `ok=true`.
- Listener records input audio path, SHA-256, duration, sample rate, and channel
  count.
- ASR transcript WER against expected user transcript is <= configured threshold.
- Response text is non-empty and names the selected route as `scripted_simple`.
- Response audio exists and has bytes greater than WAV header size.
- Output ASR transcript WER against response text is <= configured threshold.
- Receipt has `mocked=false`, `live=true`, and empty `failed_gates`.

Receipt schema: `chatterbox.conversation_ladder.rung1.v1`

Claims this proves:

- File-backed listener input can drive one real ASR/TTS loop.
- The generated response audio is playable enough for ASR verification.

Does not prove:

- Live microphone capture.
- Multi-turn context.
- Memory correctness.
- Tool use.
- Emotional steering quality.

Stop rule:

- Do not start rung 2 until rung 1 has a passing receipt and the input/output
  WAV files are inspectable.

## Rung 2: Two-Turn Context And Listener State

Purpose: prove the listener and turn router preserve short conversation state
across two user turns.

Input:

- Two WAV fixtures from the same scripted user.
- Turn 1 establishes a simple topic.
- Turn 2 refers back with a pronoun or shorthand.

Required live path:

```text
turn 1 WAV -> ASR -> route -> TTS
turn 2 WAV -> ASR -> context resolution -> response text -> TTS
```

Pass gates:

- Includes every rung 1 gate for both turns.
- Receipt has stable `session_id`, `turn_id`, and monotonic event sequence.
- Turn 2 response references the turn 1 topic through recorded state, not a
  hidden hard-coded answer.
- State snapshot records the active topic before and after each turn.
- Output ASR verifies both response WAV files.

Receipt schema: `chatterbox.conversation_ladder.rung2.v1`

Claims this proves:

- The file-backed listener can run a two-turn conversation.
- The router can preserve and use short local state.

Does not prove:

- Long-term memory retrieval.
- Dynamic emotion adaptation.
- Interruption during playback.

Stop rule:

- Do not start memory-grounded rungs until local state is visible in the receipt
  and turn 2 fails closed when turn 1 is omitted.

## Rung 3: Memory-Grounded Embry Turn

Purpose: prove a conversation turn can query `$memory`, select scoped Embry
evidence, and produce a response that cites the memory evidence path in the
receipt.

Input:

- One WAV fixture asking an Embry/persona-memory question.
- Natural-language memory question, for example:
  `What memory explains why Embry Lawson reacts to Hawaii, surfing, Kai, and afternoon rain with grief?`
- Required memory tags, including `persona:embry`.

Required live path:

```text
WAV fixture -> ASR -> /intent or route selection -> /recall ->
evidence packet -> response text -> Chatterbox TTS -> output ASR
```

Pass gates:

- Includes rung 1 listener, ASR, TTS, and output ASR gates.
- Memory recall response has `found=true`, acceptable `confidence`, and
  `should_scan=false` or a documented fail-closed reason.
- Memory results are read from `items`, not `results`.
- Top memory items include the required persona scope or `persona_id`.
- Receipt preserves `_key`, collection, tags, `scores`, and relevant
  `retrieval_text` or source fields.
- Response text is grounded in returned memory evidence and does not introduce
  unsupported persona facts.

Receipt schema: `chatterbox.conversation_ladder.rung3.v1`

Claims this proves:

- A real voice turn can use scoped memory recall as evidence.
- Memory evidence is visible enough to audit.

Does not prove:

- Memory writes.
- Full Theory-of-Mind graph traversal.
- Subjective voice performance.

Stop rule:

- Do not start emotional steering until memory evidence fields are preserved in
  the receipt and an unscoped memory query fails the gate.

## Rung 4: Barge-In And Playback Interruption

Purpose: prove the listener can detect user speech while Chatterbox is speaking
and can stop, duck, or cancel stale output without emitting old-turn audio after
cancel.

Input:

- One long response prompt that produces multiple chunks.
- One interruption WAV fixture injected while output chunking is active.

Required live path:

```text
initial WAV -> ASR -> long response chunks -> playback starts
interruption WAV -> listener event -> cancel/duck/stop -> new turn response
```

Pass gates:

- Existing interruption gates still pass:
  `stale_skipped_count > 0`, stale chunks are not submitted after cancel, and
  `post_cancel_old_turn_audio_bytes_emitted == 0`.
- Turn-control endpoints record cancel, duck, and stop where applicable.
- Event timeline shows the exact sequence for input start, ASR completion,
  output chunk start, interruption detection, cancel acknowledgement, and new
  turn response start.
- New-turn output ASR verifies against new-turn response text.
- Receipt separates backchannel/false interruption from true interruption when
  that distinction is implemented; until then, `does_not_prove` must name it.

Receipt schema: `chatterbox.conversation_ladder.rung4.v1`

Claims this proves:

- Barge-in can suppress stale old-turn output in a real audio loop.
- Listener events and playback controls share an auditable timeline.

Does not prove:

- Robust noisy-room interruption handling.
- Adaptive false-interruption recovery unless explicitly implemented.

Stop rule:

- Do not start tool-latency or wait-behavior rungs until interruption receipts
  prove zero old-turn bytes after cancel.

## Rung 5: Tool Latency, Brave Search, And Wait Utterances

Purpose: prove a spoken turn can invoke a real external research/tool path,
surface wait behavior while work is pending, and produce a final ASR-verified
response.

Input:

- One WAV fixture asking for current external information where Brave Search is
  appropriate.
- A route policy that selects `brave-search` or a server-side Brave adapter.

Required live path:

```text
WAV fixture -> ASR -> route -> Brave Search raw result ->
wait decision -> optional wait utterance/audio -> final response text ->
Chatterbox TTS -> output ASR
```

Pass gates:

- Includes rung 1 listener, ASR, TTS, and output ASR gates.
- Brave Search result is live and records query, result URLs, titles, and
  descriptions.
- Receipt records tool latency and any wait-control estimate source.
- If expected wait is long enough, selected wait activity comes from
  `WAIT_ENTERTAINMENT_ACTIVITIES` or the wait-response policy and records
  `mood_tags`, `tone_tags`, and `avoid_when`.
- Final answer cites or records the Brave result sources used.
- Receipt states whether the wait utterance was spoken, muted, ducked, or
  skipped.

Receipt schema: `chatterbox.conversation_ladder.rung5.v1`

Claims this proves:

- A real voice turn can survive a live tool call and keep user-facing audio
  behavior auditable.
- Wait utterances are tied to actual latency evidence.

Does not prove:

- Search result factual correctness beyond recorded source evidence.
- Long-running multi-tool orchestration.
- Emotional steering beyond wait-state selection.

Stop rule:

- Do not start full emotional steering until tool latency and wait behavior are
  receipt-backed.

## Rung 6: Dynamic Emotional Steering With Memory Comparison

Purpose: prove Chatterbox can use live conversational cues plus scoped memory
evidence to choose an emotional stance, utterance style, and voice delivery
policy in real time.

Input:

- At least three WAV fixtures in one session:
  1. neutral request,
  2. emotionally salient cue,
  3. follow-up that tests whether the system adapts without overreacting.
- A scoped memory question for `persona:embry` or a user/persona memory profile.

Required live path:

```text
WAV turn -> ASR -> cue extraction -> memory recall -> emotion state update ->
utterance style policy -> response text -> Chatterbox TTS -> output ASR
```

Pass gates:

- Includes rung 2 multi-turn state gates and rung 3 memory evidence gates.
- Cue extraction records the observed cue text spans and normalized cue labels.
- Memory comparison records natural-language memory questions, returned keys,
  persona/user scope, ToM fields when present, and intensity fields when present.
- Emotion state update records prior state, evidence, selected state, intensity,
  decay or reset behavior, and confidence.
- Utterance policy records selected delivery stage, wait activity if any,
  forbidden/avoid conditions, and why alternatives were rejected.
- Response text remains factually grounded and avoids unsupported claims about
  the user's inner state.
- Output ASR verifies every generated response.

Receipt schema: `chatterbox.conversation_ladder.rung6.v1`

Claims this proves:

- Dynamic emotion steering is driven by auditable live cues and memory evidence.
- Utterance style choices are visible enough to debug and regress.

Does not prove:

- That the emotional performance is subjectively ideal.
- That memory salience ranking is globally correct.
- That live microphone behavior is production-ready unless the live-mic
  transport mode is used for this rung.

Stop rule:

- Do not claim emotional steering works from prompt text alone. Rung 6 requires
  receipt-backed cue spans, memory evidence, emotion-state transition, utterance
  policy, response audio, and output ASR.

## Rung 7: Listener Service Contract

Purpose: define the first production listener boundary without folding memory,
reasoning, or TTS rendering into the listener itself.

Input:

- A session id and turn id.
- Real audio frames from one transport:
  - `audio/pcm; rate=16000; channels=1`, or
  - containerized chunks such as WAV/WebM only if the transport adapter records
    exact codec, sample rate, channels, chunk sequence, and timestamp.
- Optional endpointing metadata from a VAD adapter.

Required live path:

```text
audio frames -> listener ingest -> VAD/endpoint events -> streaming ASR ->
heard-text ledger -> coordinator turn events -> renderer request envelope
```

Required outputs:

- `listener.audio_frame_received` events with sequence, byte count, timestamp,
  sample rate, and session/turn ids.
- `listener.speech_started`, `listener.speech_partial`,
  `listener.speech_final`, and `listener.speech_ended` events where available.
- A heard-text ledger containing final ASR text, partial transcript history,
  timing, ASR backend identity, and confidence or unavailable reason.
- Coordinator turn events:
  - `turn.started`,
  - `turn.user_text_final`,
  - `turn.cancel_requested` when barge-in targets old audio,
  - `turn.renderer_request_created`.
- Renderer request envelope with `turn_id`, response text, delivery stage, and
  the external evidence pointers used by the coordinator.

Pass gates:

- Audio frames are accepted from a real client/transport, not a direct function
  call with synthetic transcript text.
- Final ASR transcript is produced by the configured ASR backend and preserved
  in the receipt.
- A cancellation-intent utterance creates a coordinator cancel event tied to the
  old turn id.
- The listener does not call memory, search, or the Chatterbox model directly.
  It only emits transcript and endpointing events.
- The coordinator, not the listener, creates the renderer request envelope.

Receipt schema: `chatterbox.conversation_ladder.rung7.listener_contract.v1`

Claims this proves:

- The listener boundary can turn real audio frames into auditable ASR and
  coordinator events.
- Chatterbox remains a renderer behind an explicit request envelope.

Does not prove:

- Production noise robustness.
- Subjective interruption feel.
- Browser/WebRTC readiness unless that exact transport is the tested adapter.
- Memory salience, tool correctness, or final answer quality.

Stop rule:

- Do not add memory/tool/emotion logic inside the listener to make a demo pass.
  Rung 7 passes only when the listener boundary emits auditable events and the
  coordinator owns downstream decisions.

## Implementation Order

1. Add `scripts/smoke_conversation_ladder.py` with `--rung 1` only. Initial
   runner exists, and live rung-1 receipt
   `/tmp/chatterbox-fork-agent-out/conversation-ladder/rung1-live-20260702T111209Z/rung1.json`
   passed with `mocked=false`, `live=true`, empty `failed_gates`, input ASR WER
   `0.0`, and output ASR WER `0.0`.
2. Add fixture manifest support:
   `tests/fixtures/conversation_ladder/manifest.json`.
3. Implement rung 1 file-backed listener contract.
4. Extend the same runner to rung 2 local state. Initial rung-2 runner exists,
   and live rung-2 receipt
   `/tmp/chatterbox-fork-agent-out/conversation-ladder/rung2-live-20260702T111722Z/rung2.json`
   passed with `mocked=false`, `live=true`, empty `failed_gates`, turn 1
   input/output ASR WER `0.0`, turn 2 input/output ASR WER `0.0`, final state
   `favorite_color=blue`, and omitted-turn-1 fail-closed proof.
5. Add memory recall adapter and rung 3 gates. Initial rung-3 runner exists,
   and live rung-3 receipt
   `/tmp/chatterbox-fork-agent-out/conversation-ladder/rung3-live-20260702T112209Z/rung3.json`
   passed with `mocked=false`, `live=true`, empty `failed_gates`, input ASR WER
   `0.1667`, output ASR WER `0.0`, memory `found=true`, confidence `124.598`,
   `should_scan=false`, top memory key `embry_age15_19_b03_memory_040`,
   `persona_id=embry`, top emotion `grief, longing`, and response text
   `Rain links Kai with grief.`.
6. Reuse existing interruption and turn-control primitives for rung 4. Initial
   rung-4 runner exists, and live rung-4 receipt
   `/tmp/chatterbox-fork-agent-out/conversation-ladder/rung4-live-20260702T112513Z/rung4.json`
   passed with `mocked=false`, `live=true`, empty `failed_gates`, interrupt
   input ASR WER `0.0`, `stale_skipped_count=2`,
   `post_cancel_old_turn_audio_bytes_emitted=0`,
   `new_turn_audio_started_after_cancel=true`, and turn-control action order
   `[cancel, duck, stop]`.
7. Add Brave Search/tool-latency adapter and rung 5 gates. Initial rung-5
   runner exists, and live rung-5 receipt
   `/tmp/chatterbox-fork-agent-out/conversation-ladder/rung5-live-20260702T112808Z/rung5.json`
   passed with `mocked=false`, `live=true`, empty `failed_gates`, input ASR WER
   `0.1667`, output ASR WER `0.1429`, Brave Search latency `1732.789 ms`,
   three recorded result URLs, wait text `I see.`, and response text
   `I found voice agent turn detection results.`.
8. Add cue extraction, memory comparison, and emotion-state receipt fields for
   rung 6. Initial rung-6 runner exists, and live rung-6 receipt
   `/tmp/chatterbox-fork-agent-out/conversation-ladder/rung6-live-20260702T113313Z/rung6.json`
   passed with `mocked=false`, `live=true`, empty `failed_gates`, all turn
   input/output ASR WER values `0.0`, memory evidence key
   `embry_age15_19_b03_memory_040`, observed cues `sensory_rain`,
   `relationship_kai`, and `requested_gentleness`, and final emotion state
   `gentle_followup` with tone `gentle`.
9. Add rung 7 as a listener service contract. The first implementation should
   choose one transport, persist a heard-text ledger, emit coordinator turn
   events, and prove that the listener does not own memory, search, reasoning,
   or Chatterbox rendering.

Each step must update the runner receipt schema before adding more behavior.

## First Runnable Slice

The first implementation slice should be rung 1 only:

```bash
python scripts/smoke_conversation_ladder.py \
  --rung 1 \
  --base-url http://127.0.0.1:8018 \
  --memory-url http://127.0.0.1:8601 \
  --fixture tests/fixtures/conversation_ladder/rung1_simple.wav \
  --expected-transcript "Can you say hello and tell me you are listening?" \
  --out /tmp/chatterbox-fork-agent-out/conversation-ladder/<run-id>/rung1.json
```

Rung 1 may use a generated fixture WAV only if it is generated before the run
and then treated as real input media with path, hash, duration, and ASR
verification. The receipt must label the fixture provenance.

## Goal Completion Boundary

The active goal is not complete when this plan exists. Completion requires
implemented rungs 1-6, real live receipts for each rung, and a final audit that
maps every rung requirement to current artifacts and command results.
