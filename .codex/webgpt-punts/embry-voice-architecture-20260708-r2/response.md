Blunt status

There is no proven full Embry voice/chat loop yet. The evidence supports only a narrow live speaker-identity slice and several partial component paths.

Implemented evidence:

Area	Status
Live speaker identity slice	Implemented narrowly. mocked=false, live=true, 4/4 simple sessions passed. Known Horus, unknown speaker, ambiguous low-confidence, and Horus/female overlap all produced the expected memory-access policy.
Stress matrix inventory	Implemented as tracking, not proof. 200 labeled sessions exist, but only 9 passed, 31 failed, and 160 were not run.
Tau doctor execution	Implemented as a component behavior only. It runs, but Embry sessions do not yet emit tau.agent_handoff.v1 work orders or DAG receipts.
Browser getUserMedia capture	Partial. It can capture audio, but transcript quality is device/source dependent. HD webcam worked once; Jabra browser capture often produced empty transcripts.

Partial behavior:

Area	Status
RealtimeSTT live loop	Partial. It is the right listener/VAD/ASR companion, but the current proof record does not establish the full voice loop.
Chatterbox	Partial. It should render Embry speech, but tone/emotion intent upstream is currently unreliable.
Shared Chat UX	Partial and drifting. It must become a ledger renderer, not a separate proof path.
Orb behavior	Partial at best. It must be driven by real Embry audio playback telemetry, not fake state or timers.
Replay	Missing as a trustworthy system behavior unless it replays the real event journal with audio, text, memory reasoning, interruptions, Tau handoff, and orb state.

Known blockers:

The memory layer can return unrelated records. Tone/emotion intent collapses to generic memory_confident. Tau handoff is not represented in Embry session journals. Browser ASR cannot be used as proof authority. UI-only proof must be rejected.

1. Source-derived architecture model for the final system
1. Event journal is the system spine

Every component emits and consumes typed events from a shared append-only session journal. The journal is the proof source, replay source, UI source, and debugging source.

The UI, UX Lab, DOM screenshots, and direct speech calls are not proof authorities. They may render or inspect journaled events, but they do not define whether the voice loop passed.

Missing today: canonical ledger contract and deterministic rung receipts.

2. Real audio capture layer

Audio capture must produce real microphone audio artifacts and transport metadata.

Allowed capture sources:

Native microphone path.

Browser getUserMedia path, but only as audio capture transport.

Previously captured real-audio fixtures only for replay/regression, not as proof of a new live run.

Rejected as proof:

Mock transcripts.

Typed transcripts standing in for speech.

Browser ASR as the authoritative ASR path.

Direct window.embrySpeak(...) as full-loop evidence.

The capture layer emits audio chunk/segment events with device/source metadata and artifact hashes.

Partial today: browser capture exists, but source quality varies. Jabra failures should be treated as transport failures, not patched over downstream.

3. RealtimeSTT is listener, VAD, and ASR companion

RealtimeSTT consumes real captured audio and emits:

VAD start/end.

ASR partials.

ASR finals.

Audio segment references.

ASR confidence and timing metadata.

RealtimeSTT must not decide whether personal memory is allowed. It produces candidate speech; it does not authorize identity.

Partial today: RealtimeSTT is the right architectural owner, but the full loop is not proven.

4. Speaker identity and diarization gate

The speaker gate consumes audio segments and speaker evidence. It decides whether Horus is the primary authoritative speaker.

Required outcomes:

Scenario	Required gate result
Known Horus	status=known, speaker_id=horus_lupercal, primary_speaker=true, personal memory allowed
Unknown speaker	status=unknown, no authoritative speaker, personal memory disabled, identity prompt allowed
Ambiguous low confidence	status=unknown or ambiguous, personal memory disabled
Horus/female overlap	status=ambiguous, no authoritative speaker, personal memory disabled

The gate emits speaker.identity.decision.v1 and turn.gate.decision.v1.

Implemented narrowly: the 4/4 live speaker identity slice is the best current evidence. It should be preserved, formalized, and rerun under the new ledger contract.

5. Turn controller enforces memory policy

The turn controller converts STT + speaker gate output into one of these states:

accepted_full: Horus is authoritative; personal memory may be used.

accepted_limited: speech can be handled without personal memory.

identity_prompt: unknown speaker; ask who they are.

rejected_or_deferred: ambiguous/overlap/noisy speech; do not answer with private context.

This layer prevents accidental memory calls for unknown or ambiguous speakers.

Partial today: speaker identity policy exists in slices, but the rest of the voice/chat loop does not consistently prove that policy through memory and Tau.

6. Memory layer owns retrieval, evidence, and answerability

Memory must return structured evidence and an answerability decision, not just arbitrary retrieved text.

Required memory output:

records_considered.

records_used.

record_types.

entity_matches.

confidence.

answerability: answerable, clarify, or no_answer.

reason_for_miss when not answerable.

Known bad behavior must become explicit failure criteria:

SPARTA QRA questions must not return unrelated S0609 or deprecated-control text.

Persona questions must not return unrelated skill descriptions instead of Horus facts.

Memory misses must clarify or say no answer; they must not answer from unrelated records.

Currently failing: memory answerability is not reliable enough for full-loop proof.

7. Tau owns reasoning, intent, tool/skill routing, and handoff

Tau consumes accepted turns and memory evidence. It decides:

Answer plan.

Reasoning trace summary.

Tone/emotion intent.

Whether a skill/tool handoff is required.

Whether a tau.agent_handoff.v1 work order must be created.

Tau must emit a durable work order and DAG receipt when a doctor/tool/skill action is invoked.

Partial today: Tau doctor runs, but Embry sessions do not yet create the required tau.agent_handoff.v1 event or DAG receipt. That is not full success.

8. Response planner emits renderable assistant output

Before speech is generated, the reasoning layer emits an assistant response plan:

Final text.

Memory reasoning trace.

Entity references.

Tone/emotion tags.

Tool/handoff references.

Safety/memory policy result.

Turn correlation IDs.

This is the single source for both Chatterbox speech and Chat UX rendering.

Missing today: reliable response-plan contract tying text, memory reasoning, Tau handoff, tone, and speech together.

9. Chatterbox is the speech renderer only

Chatterbox consumes the response plan and renders Embry audio.

It should emit:

chatterbox.tts.requested.v1

chatterbox.tts.generated.v1

audio.playback.started.v1

audio.playback.progress.v1

audio.playback.ended.v1

audio.playback.cancelled.v1

Chatterbox may use tone/emotion tags. It must not invent memory facts, decide speaker identity, decide answerability, or become the reasoning layer.

Partial today: speech rendering exists, but tone/emotion intent upstream is unreliable.

10. Shared Chat UX is a live ledger renderer

The shared Chat UX subscribes to the event journal and renders:

User transcript.

Speaker identity/gate state.

Accepted/rejected/limited turn state.

Assistant text.

Memory reasoning trace.

Entity underlines.

Tau handoff/work order status.

Chatterbox audio status.

Orb state.

Interruption events.

The Chat UX should not maintain a separate truth model. It should render journal events as they arrive and replay them later from the same ledger.

Current UI route drift should stop. UX Lab can help inspect rendering, but it must not define proof.

11. Orb tracks actual Embry audio playback

The orb is driven by real playback telemetry from Chatterbox/Embry audio output.

Accepted orb inputs:

Playback started.

Playback progress.

Audio amplitude/envelope.

Playback ended.

Playback cancelled/interrupted.

Audio artifact reference.

Rejected orb inputs:

Fake speaking state.

Timers not tied to audio.

DOM-only animation state.

Direct window.embrySpeak(...) state.

Every orb.state.v1 event must reference the source audio playback event or audio artifact it reflects.

Missing today: proof that orb state follows actual Embry audio.

12. Interruption manager handles live barge-in

During Embry speech, RealtimeSTT continues listening. If Horus speaks over Embry, the system must decide whether this is an authorized interruption.

Required event sequence for a valid Horus interruption:

audio.playback.started.v1

realtime_stt.vad.started.v1

speaker.identity.decision.v1

interruption.detected.v1

audio.playback.cancelled.v1

turn.started.v1 for the new user turn

Unknown or ambiguous interruption must not unlock personal memory.

Missing today: no full evidence for interruption handling through real STT, speaker gate, Chatterbox playback, Chat UX, and orb state.

2. Minimal event schema / ledger contract

The journal should be append-only NDJSON or equivalent. Each event must have a common envelope.

JSON
{
  "schema": "embry.event.v1",
  "event_id": "evt_01...",
  "session_id": "ses_01...",
  "sequence": 42,
  "trace_id": "trace_01...",
  "turn_id": "turn_01...",
  "parent_event_id": "evt_01...",
  "type": "speaker.identity.decision.v1",
  "component": "speaker_gate",
  "occurred_at": "2026-07-08T00:00:00.000Z",
  "ingested_at": "2026-07-08T00:00:00.010Z",
  "source": {
    "live": true,
    "mocked": false,
    "transport": "native_mic",
    "device_id_hash": "sha256:...",
    "fixture_from_live_audio": false
  },
  "payload": {},
  "artifacts": [
    {
      "kind": "audio_wav",
      "uri": "ledger://ses_01/artifacts/input_segment_003.wav",
      "mime": "audio/wav",
      "sha256": "sha256:...",
      "duration_ms": 1840
    }
  ],
  "provenance": {
    "code_version": "git:...",
    "config_hash": "sha256:...",
    "model_versions": {
      "realtime_stt": "...",
      "speaker_gate": "...",
      "memory": "...",
      "tau": "...",
      "chatterbox": "..."
    }
  },
  "receipt": {
    "checkable": true,
    "event_sha256": "sha256:..."
  }
}
Required ledger invariants

session_id, sequence, type, component, occurred_at, source.mocked, and source.live are required.

sequence is monotonic within a session.

Every audio-derived event references the relevant audio artifact or parent event.

Every memory call references the gate decision that allowed it.

Every Chatterbox request references the Tau/response-plan event that produced it.

Every orb state event references a real playback event.

Every Tau handoff includes a work order ID and DAG receipt artifact.

Every proof rung emits a deterministic proof.receipt.v1.

A replay may use a real prior event journal, but it must mark source.fixture_from_live_audio=true where applicable.

A live proof must include source.live=true and source.mocked=false for capture, STT, speaker gate, and turn events.

Minimal event types
Event type	Owner	Required payload
session.started.v1	session runner	scenario ID, device info hash, config hash
audio.input.chunk.v1	capture	audio artifact ref, duration, sample rate, channel count
realtime_stt.vad.started.v1	RealtimeSTT	audio time offset, confidence
realtime_stt.vad.ended.v1	RealtimeSTT	segment duration, audio ref
realtime_stt.partial.v1	RealtimeSTT	partial text, confidence, segment ref
realtime_stt.final.v1	RealtimeSTT	final text, confidence, segment ref
speaker.identity.decision.v1	speaker gate	status, speaker ID, primary speaker boolean, confidence, overlap flag
turn.gate.decision.v1	turn controller	accepted state, personal memory allowed boolean, reason
memory.query.v1	memory	query text, allowed namespaces, gate event ID
memory.retrieval.v1	memory	records considered, scores, record types
memory.answerability.v1	memory	answerable/clarify/no_answer, records used, reason
tau.intent.v1	Tau	intent, tone, emotion, tool/skill need
tau.agent_handoff.v1	Tau	work order ID, DAG receipt artifact, skill/tool target
assistant.response.plan.v1	Tau/response planner	assistant text, tone tags, emotion tags, memory trace refs
chatterbox.tts.requested.v1	Chatterbox	text, tone/emotion tags, parent response plan
chatterbox.tts.generated.v1	Chatterbox	generated audio artifact, duration
audio.playback.started.v1	playback sink	audio artifact, start time
audio.playback.progress.v1	playback sink	playback offset, amplitude/envelope summary
audio.playback.ended.v1	playback sink	completed duration
audio.playback.cancelled.v1	playback sink	cancel reason, interrupt event ID
orb.state.v1	orb controller	state, amplitude/envelope, source playback event ID
interruption.detected.v1	interruption manager	interrupter speaker status, target playback event, action
chat.render.receipt.v1	Chat UX	rendered event IDs, DOM/view checksum, not proof authority
replay.receipt.v1	replay runner	journal hash, artifacts hash, rendered timeline hash
proof.receipt.v1	proof runner	rung ID, expected vs actual checks, pass/fail
3. Next proof rungs, in order
Rung 1 — Canonical event journal and proof receipt runner

Goal: create the shared contract before more UI or voice patches.

Run: start a session, append schema-valid events, close session, emit proof.receipt.v1.

Acceptance criteria:

Journal is append-only and ordered.

Every event validates against embry.event.v1.

Receipt includes rung ID, scenario ID, expected checks, actual checks, pass/fail, code version, config hash, and journal hash.

Pass/fail logic is computed from the journal, not from console logs or DOM state.

No mock transcript path is accepted as live proof.

Rung 2 — Real audio capture into RealtimeSTT

Goal: prove that real microphone audio reaches RealtimeSTT and produces journaled VAD/ASR events.

Run: speak a fixed set of short phrases through the real microphone path.

Acceptance criteria:

audio.input.chunk.v1 and realtime_stt.*.v1 events are present.

source.live=true, source.mocked=false.

Audio artifacts are stored with SHA-256 hashes.

ASR final events are non-empty for spoken segments.

Device/source metadata is recorded.

Empty Jabra transcripts fail this rung; they are not patched downstream.

Rung 3 — Formalize the existing live speaker identity slice

Goal: convert the current 4/4 speaker identity evidence into deterministic receipts.

Run these live scenarios:

Known Horus.

Unknown speaker.

Ambiguous low-confidence speaker.

Horus/female overlap.

Acceptance criteria:

Known Horus emits status=known, speaker_id=horus_lupercal, primary_speaker=true.

Unknown emits status=unknown, no authoritative speaker, personal memory disabled.

Ambiguous emits no authoritative speaker, personal memory disabled.

Overlap emits status=ambiguous, no authoritative speaker, personal memory disabled.

Each scenario writes speaker.identity.decision.v1, turn.gate.decision.v1, and proof.receipt.v1.

This is the first rung that can preserve the current live 4/4 result.

Rung 4 — Gate-to-memory policy enforcement

Goal: prove speaker identity actually controls memory access.

Run: use real spoken prompts for known Horus, unknown speaker, ambiguous speaker, and overlap.

Acceptance criteria:

Known Horus may produce memory.query.v1 against personal memory namespaces.

Unknown/ambiguous/overlap must not query personal memory.

Unknown speaker receives identity prompt or limited non-personal response.

Ambiguous/overlap receives clarification or one-at-a-time prompt.

Receipt fails if any personal memory event appears after a non-authoritative gate decision.

Rung 5 — Memory answerability regression suite

Goal: stop unrelated-memory answers before continuing UI work.

Run: accepted Horus turns ask memory questions covering:

SPARTA QRA.

Horus persona facts.

Known memory miss.

Ambiguous memory query.

Entity-specific query.

Acceptance criteria:

SPARTA QRA answers must cite relevant SPARTA/QRA records or return clarify/no-answer.

Persona answers must use Horus persona records, not unrelated skill descriptions.

Memory miss must produce answerability=no_answer or clarify.

No answer may use unrelated S0609, deprecated-control, or skill-description records.

memory.answerability.v1 must identify records used and reason for answerability.

Receipt fails on unrelated record use even if the final answer sounds plausible.

This is currently a failing family and should block full-loop claims.

Rung 6 — Tau intent and tone/emotion contract

Goal: force Tau to produce specific tone/emotion intent before Chatterbox renders speech.

Run: accepted Horus turns requesting or implying:

Firm tone.

Humorous tone.

Gentle tone.

One-at-a-time / interruption-management tone.

Neutral memory-confident tone.

Acceptance criteria:

tau.intent.v1 emits the expected tone/emotion tags.

assistant.response.plan.v1 carries those tags.

Generic memory_confident fails when the scenario expects firm, humorous, gentle, or one-at-a-time.

Chatterbox receives, but does not invent, the tags.

Rung 7 — Tau agent handoff work order and DAG receipt

Goal: prove Embry sessions create real Tau handoff artifacts.

Run: accepted Horus voice prompt that requires doctor/tool/skill work.

Acceptance criteria:

Tau emits tau.agent_handoff.v1.

Event includes work_order_id, target agent/tool/skill, parent turn ID, and requested action.

DAG receipt artifact is attached and hashed.

Assistant response references the handoff state.

Receipt fails if the only evidence is “Tau doctor ran.”

Rung 8 — Chatterbox speech from response plan, with shared Chat UX render

Goal: prove text and speech come from the same response plan and same ledger.

Run: accepted Horus voice turn through memory/Tau, then Chatterbox.

Acceptance criteria:

assistant.response.plan.v1 precedes Chatterbox request.

chatterbox.tts.requested.v1 references the response-plan event.

chatterbox.tts.generated.v1 stores generated audio artifact hash and duration.

Shared Chat UX renders user transcript, assistant text, tone/emotion, memory trace, and audio state from event IDs.

chat.render.receipt.v1 may prove rendering coverage, but not voice-loop correctness by itself.

Direct window.embrySpeak(...) fails this rung.

Rung 9 — Orb from actual audio playback and live interruption

Goal: prove the orb and interruption behavior follow real Embry audio, not fake state.

Run: Embry speaks through Chatterbox. During playback, Horus interrupts once; unknown speaker interrupts once in a separate session.

Acceptance criteria:

audio.playback.started.v1 references generated Chatterbox audio.

orb.state.v1 references playback events or audio envelope data.

Orb enters speaking/reactive state only while real playback is active.

Horus interruption emits interruption.detected.v1 and audio.playback.cancelled.v1.

Unknown/ambiguous interruption does not unlock personal memory.

Receipt fails if orb state is driven by a timer, DOM animation, or fake speaking flag.

Rung 10 — Full session replay from real event journal

Goal: prove replay reconstructs the real session.

Run: replay completed sessions from the journal.

Acceptance criteria:

Replay shows ordered user text, speaker gate decisions, memory reasoning, Tau handoff, assistant text, audio artifacts, playback, interruptions, and orb state.

Replay uses the same shared Chat UX renderer where possible.

Audio artifacts are loaded from ledger references and hash-checked.

Replay emits replay.receipt.v1.

Replay receipt includes journal hash, artifact hashes, rendered timeline hash, and pass/fail.

Replay proof is labeled replay proof, not new live voice proof.

4. Existing partial work: keep, quarantine, or replace
Keep
Work	Keep because	Condition
Live 4/4 speaker identity slice	It is the strongest current real evidence.	Convert to ledger-backed deterministic receipts.
RealtimeSTT role	Correct owner for listening, VAD, and ASR companion behavior.	Must consume real audio and emit journal events.
Chatterbox rendering path	Correct owner for Embry speech rendering.	Must consume Tau response-plan tags; no reasoning.
Tau doctor component	Useful component capability.	Must emit tau.agent_handoff.v1 and DAG receipt in Embry sessions.
Browser getUserMedia capture	Useful transport path.	Treat it as capture only; do not trust browser ASR as proof.
HD webcam capture receipt	Useful evidence that one browser capture source can work.	Must be rerun under the ledger proof runner.
200-session stress matrix labels	Useful scenario inventory.	Current pass/fail counts are not final architecture proof.
Shared Chat UX visual components	Useful UI base.	Must render the event journal and stop owning truth.
Quarantine
Work	Reason
Mock transcripts	Explicitly disallowed as proof.
DOM-only proof	Cannot prove voice loop behavior.
Direct window.embrySpeak(...)	Only proves renderer invocation, not full loop.
UX Lab proof authority	UX Lab may inspect, not decide system truth.
Browser ASR-dependent receipts	Source-dependent and already failed on Jabra empty transcripts.
Current 9 passed stress sessions	Do not treat as final proof unless rerun under the new ledger contract.
31 failed stress sessions	Keep as regression targets; do not patch around them casually.
160 not-run sessions	Inventory only. They are not evidence.
Memory answers using unrelated records	Must be blocked by answerability tests.
Generic memory_confident tone fallback	Acceptable only where expected; otherwise a failure.
UI route patches not tied to ledger events	Design drift. Freeze or isolate until ledger renderer exists.
Replace
Replace	With
Ad hoc logs and screenshots	Canonical event journal plus deterministic receipts.
UI-specific truth state	Shared Chat UX rendering the event ledger.
Fake orb state	Audio playback telemetry-driven orb.state.v1.
Browser ASR as proof source	RealtimeSTT ASR events from real audio.
Chatterbox-as-behavior proof	Chatterbox as renderer of Tau response plans.
Memory free-form answer behavior	Structured retrieval plus answerability contract.
Tau “doctor ran” evidence	tau.agent_handoff.v1 work order plus DAG receipt.
Patch-by-patch stress fixes	Ordered proof rungs with explicit acceptance criteria.
5. Next concrete implementation task for the Codex project agent

Stop UI patching. The next task should be:

Implement the canonical event journal and migrate the live speaker identity slice into it.

Concrete scope:

Add embry.event.v1 JSON Schema for the common event envelope.

Add schemas for:

session.started.v1

audio.input.chunk.v1

realtime_stt.vad.started.v1

realtime_stt.vad.ended.v1

realtime_stt.final.v1

speaker.identity.decision.v1

turn.gate.decision.v1

proof.receipt.v1

Implement an append-only EventJournal writer:

monotonic sequence

schema validation on append

artifact SHA-256 support

code/config provenance

source.live

source.mocked

Implement a proof CLI for the existing four live speaker scenarios:

known Horus

unknown speaker

ambiguous low-confidence

Horus/female overlap

The CLI must use real RealtimeSTT/speaker-gate output, not mock transcripts.

The CLI must write:

events.ndjson

audio artifacts or artifact references

receipt.json

receipt.json must include expected vs actual checks and final PASS or FAIL.

Merge is blocked unless all four speaker identity scenarios produce deterministic receipts.

Expected receipt checks:

JSON
{
  "rung_id": "rung_03_live_speaker_identity",
  "scenario": "known_horus",
  "expected": {
    "source.live": true,
    "source.mocked": false,
    "speaker.status": "known",
    "speaker_id": "horus_lupercal",
    "primary_speaker": true,
    "personal_memory_allowed": true
  },
  "actual": {},
  "result": "PASS"
}

That task turns the one credible existing slice into reusable architecture proof. After that, the agent should proceed to gate-to-memory policy enforcement and memory answerability. It should not return to UI route design until the journal-backed proof spine exists.
