Architecture decision

Build the executable campaign runner in agent-skills/skills/embry-voice-control, not in Chatterbox.

Chatterbox should continue to own the stress-matrix contract and response rendering. RealtimeSTT should own the managed capture process. The campaign runner should own case selection, session and turn identities, source-audio authority, journal correlation, stage execution, idempotency, receipts, and final counting.

The runner must execute every selected case through one invariant path:

immutable case contract
-> qualified or physical source audio
-> PipeWire capture
-> RealtimeSTT events
-> speaker verification
-> Memory
-> bounded Tau tick and optional skill
-> Tau plan
-> Chatterbox render
-> authoritative Jabra playback
-> shared Chat/orb projection
-> journal-only replay
-> case oracle

The existing typed runner must not be called to execute a counted case. It reads session["question"] and branches directly into Memory, Brave, Tau, Chatterbox turn control, or UX routes, bypassing RealtimeSTT and the canonical journal turn spine.

The existing fixed voice runner is also not the campaign runner: it indexes eight named scenarios and explicitly delegates to lower smokes.

Critical corrections to the current model
The matrix contains 300 cases, not 200

The committed matrix contains:

15 route families
5 difficulty levels
4 question templates per family
300 cases total

Its own claims state that it does not prove all sessions were spoken or replayed.

A 200-case run should therefore be a manifested, stratified selection from the 300-case source matrix, not an assumption that the source matrix itself has 200 cases.

The matrix does not currently contain a static-facts family

The 15 committed families are:

sparta_qra_compliance
persona_memory_recall
persona_memory_miss
brave_research
tau_tool_orchestration
skill_create_evidence_case
skill_create_figure
skill_analytics
skill_sparta_validator
chat_ux_sync
voice_control_skill
interruption
speaker_identity
factory_noise
tone_emotion

There is no static_facts family in the current builder.

The capital-of-France turn remains a canonical integration canary, but it is not currently one of the matrix’s 300 cases. Add a static-facts family before claiming that the matrix campaign covers static facts.

Not every valid turn should synthesize speech

Several matrix cases require:

block_before_speech
reject non-primary speaker
do not answer unsupported memory
refuse speaking a blocked answer

Consequently, a universal per-turn requirement for Chatterbox and playback would create false failures or, worse, unsafe speech.

Each turn needs one of these explicit expectations:

speech_required
clarification_speech_required
speech_forbidden
continue_old_turn_only

A speech_forbidden turn passes only when no Chatterbox render and no response playback occurred. The conversation may still exercise Chatterbox through a later clarification or accepted turn.

The existing physical listener cannot yet drive a multi-turn campaign unchanged

The current physical runner keeps one capture process open, but it binds the event publisher to one turn ID per process:

Python
Run
turn_id=f"listener-process-{process_run_number}"

All accepted cycles in that process therefore share that turn ID.

The 300-case runner requires a distinct canonical turn ID for every accepted utterance while retaining one persistent capture process. This is the smallest necessary RealtimeSTT patch.

1. Exact repository and file ownership
grahama1970/chatterbox

Chatterbox owns the semantic test catalog and pure case oracles.

Add:

docs/
├── EMBRY_AUDIO_E2E_SOURCE_POLICY.json
├── EMBRY_AUDIO_E2E_SELECTIONS.json
└── schemas/
    ├── embry.audio_e2e_source_policy.v1.schema.json
    └── embry.audio_e2e_selection.v1.schema.json

scripts/
├── compile_embry_audio_e2e_plan.py
├── embry_stress_oracles.py
└── tests/
    ├── test_compile_embry_audio_e2e_plan.py
    └── test_embry_stress_oracles.py

Modify narrowly:

scripts/build_embry_stress_session_matrix.py

Only add stable source-sensitive metadata or a schema version pointer. Do not put orchestration, microphone control, source synthesis, or playback in this repository.

The current matrix builder already owns route oracles, required receipts, conversation arcs, steering, tone families, emotion tags, pause requirements, and interruption policy.

Move reusable pure validation functions from smoke_embry_intelligence_stress.py into embry_stress_oracles.py. The typed runner and audio runner may both call those validators, but only the audio runner may execute counted E2E cases.

grahama1970/agent-skills

This repository owns the campaign runtime.

Add:

skills/embry-voice-control/
├── src/embry_voice_control/audio_e2e/
│   ├── __init__.py
│   ├── __main__.py
│   ├── campaign.py
│   ├── campaign_state.py
│   ├── case_compiler.py
│   ├── case_executor.py
│   ├── event_waiter.py
│   ├── source_authority.py
│   ├── source_playback.py
│   ├── source_qualification.py
│   ├── transcript_oracle.py
│   ├── turn_dispatch.py
│   ├── ui_oracle.py
│   ├── replay_oracle.py
│   ├── interruption_oracle.py
│   └── receipts.py
│
├── proofs/tau/embry-audio-e2e-turn/
│   ├── goal-packet.json
│   ├── dag-contract.template.json
│   ├── command-specs/embry-audio-turn/tau-dispatch-command.json
│   ├── scripts/run_embry_audio_turn_handoff.py
│   └── tests/
│       ├── test_audio_turn_handoff.py
│       └── test_skill_routes.py
│
├── scripts/
│   ├── qualify_horus_audio_source.py
│   ├── record_horus_source_witness.py
│   └── build_audio_e2e_failure_bundle.py
│
├── schemas/
│   ├── embry.audio_e2e_campaign_manifest.v1.schema.json
│   ├── embry.audio_e2e_case_manifest.v1.schema.json
│   ├── embry.audio_source_receipt.v1.schema.json
│   ├── embry.audio_e2e_turn_receipt.v1.schema.json
│   ├── embry.audio_e2e_case_receipt.v1.schema.json
│   └── embry.audio_e2e_campaign_receipt.v1.schema.json
│
└── tests/audio_e2e/
    ├── test_campaign_state.py
    ├── test_case_compiler.py
    ├── test_source_authority.py
    ├── test_transcript_oracle.py
    ├── test_case_executor.py
    ├── test_resume.py
    └── test_failure_bundle.py

Reuse rather than duplicate:

event_journal.py
artifact_authority.py
chat_projection.py
pipewire_playback.py
pipewire_graph.py
the journal -> Memory -> Tau proof lane
the causal Chatterbox render script

The existing artifact authority already resolves audio only through a matching accepted render event and rechecks path, size, and SHA-256.

The existing playback controller already has journal-bound idempotency, exact render-event resolution, sink validation, playback.requested, graph-observed playback.started, and plausible playback.ended.

grahama1970/RealtimeSTT

Add a managed, per-turn control layer while reusing the existing physical capture implementation:

proofs/embry_pipewire_ingress/
├── run_managed_audio_e2e_listener.py
├── managed_turn_protocol.py
└── tests/
    ├── test_managed_turn_protocol.py
    └── test_managed_audio_e2e_listener.py

The managed listener must keep one pw-record and RealtimeSTT process open while accepting control packets over a Unix socket or FIFO.

Control packet:

JSON
{
  "schema": "embry.listener_turn_command.v1",
  "command": "arm",
  "campaign_id": "campaign_...",
  "case_id": "sparta_qra_compliance-simple-01",
  "attempt_id": "attempt_01",
  "session_id": "embry-e2e-...",
  "turn_id": "sparta_qra_compliance-simple-01:turn-001",
  "source_authority_id": "source_...",
  "wake_required": true
}

It must not contain:

typed transcript
expected response
fixture transcript
Memory result
Tau route

The managed listener emits:

listener.turn_armed
listener.recording_started
listener.partial_transcript*
listener.recording_stopped
listener.final_transcript
listener.turn_completed

with the supplied session and turn IDs.

The current physical listener already saves accepted WAV segments, hashes them, publishes partial and final callbacks, and validates non-source-WAV physical PipeWire capture.

grahama1970/tau

No Tau production patch should be required.

Add no matrix-specific routing to Tau itself. The campaign creates one bounded DAG tick per accepted user turn using the existing persistent-subagent contract:

session_mode=persistent
tau_control=bounded_receipt_gated_ticks
tick_budget=1
unbounded_autonomy_allowed=false

The new proof lane belongs in agent-skills because it packages the Embry turn contract and command adapter.

grahama1970/graph-memory-operator

No campaign-runner code belongs here.

The runner calls the existing endpoints:

/speaker/resolve
/intent
/answer

and stores exact request and response hashes. Memory is not allowed to generate input speech, run Brave directly, or control playback.

grahama1970/pi-mono

The UI owns only journal projection and browser acceptance.

Add or finish:

packages/ux-lab/
├── src/components/embry-voice/
│   ├── useEmbryJournalOrbState.ts
│   ├── embryJournalOrbState.ts
│   ├── EmbryJournalReplay.tsx
│   └── embryJournalReplay.ts
│
├── scripts/
│   ├── prove-embry-audio-e2e-turn.mjs
│   └── prove-embry-journal-replay.mjs
│
└── server/
    └── embry-voice-journal-proxy.ts

The campaign runner invokes these proof scripts and validates their receipts. It does not manufacture Chat, orb, or replay evidence itself.

2. Runner CLI and process model

Expose one module:

Bash
python -m embry_voice_control.audio_e2e

Subcommands:

compile
qualify-source
run
resume
status
bundle-failure
Compile
Bash
python -m embry_voice_control.audio_e2e compile \
  --matrix <matrix.json> \
  --source-policy <source-policy.json> \
  --selection <selection expression> \
  --output <campaign-manifest.json>
Run
Bash
python -m embry_voice_control.audio_e2e run \
  --manifest <campaign-manifest.json> \
  --campaign-dir <directory> \
  --journal-db <sqlite path> \
  --journal-url <url> \
  --realtimestt-repo <path> \
  --memory-url <url> \
  --tau-repo <path> \
  --chatterbox-url <url> \
  --ux-url <url> \
  --listener-source-node <stable node.name> \
  --source-output-node <stable node.name or human-live> \
  --response-output-node <stable Jabra node.name> \
  --require-gates all
Process topology

Run cases serially. One physical microphone and one output sink cannot truthfully support parallel E2E cases.

Long-lived campaign children:

managed RealtimeSTT listener
journal service
Memory service
Chatterbox service
UX Lab/browser oracle

Per-turn children:

source playback, unless human-live
speaker verification
Memory calls
one Tau DAG tick
optional skill call
Chatterbox render
authoritative response playback
browser projection check
replay check

The supervisor must use process groups and terminate all descendants on cancellation or crash.

3. Audio-source strategy

Choose option 3: a two-tier system.

Tier P — Physical or recorded Horus

Two admissible source classes:

physical_live_horus
recorded_physical_horus
physical_live_horus

Graham/Horus speaks the exact turn after the managed listener emits listener.turn_armed.

Receipt fields:

JSON
{
  "source_class": "physical_live_horus",
  "synthetic": false,
  "physical_human": true,
  "prerecorded": false,
  "voice_clone": false,
  "capture_class": "physical_jabra_microphone"
}
recorded_physical_horus

Graham records the exact utterance once. During campaign execution, the recording must still be played through a PipeWire source-output fixture and recaptured by RealtimeSTT; it must not be fed directly as a transcript or directly into Memory.

Receipt fields:

JSON
{
  "source_class": "recorded_physical_horus",
  "synthetic": false,
  "physical_human_origin": true,
  "physical_human_live_this_run": false,
  "prerecorded": true,
  "voice_clone": false,
  "capture_class": "physical_room_or_qualified_pipewire_fixture"
}
Tier Q — Qualified Horus clone

A clone is usable only after a separate source-qualification campaign passes.

It must always be labeled:

JSON
{
  "source_class": "qualified_horus_clone",
  "synthetic": true,
  "physical_human": false,
  "prerecorded": true,
  "voice_clone": true,
  "mocked": false
}

mocked=false means the waveform traversed real PipeWire, RealtimeSTT, Memory, Tau, Chatterbox, and playback. It does not mean the source was a physical human.

Clone qualification gate

Before any clone-generated utterance can count:

Use a Horus-only voice profile derived from the physical enrollment.

Pin model, reference-audio, tokenizer, generation parameters, and code commits.

Generate at least 40 held-out calibration sentences not used in enrollment.

Require every counted calibration sample to:

have a unique audio hash;

be non-silent and unclipped;

pass Horus verification at the configured threshold;

preserve the configured margin over the closest impostor;

fail the Embry-self-audio identity test;

achieve normalized ASR WER at or below 0.15;

preserve all critical names, IDs, numbers, and negations.

Store score distributions, not only one average.

Qualify expressive modes independently:

frustrated;

hostile;

discouraged;

playful;

interrupting/urgent.

Expire qualification when the model, profile, reference set, or generation parameters change.

Generate qualified source assets before the counted campaign. During a counted case, the response-side Chatterbox call must still occur only from a Tau plan. A source-generation call must never be mistaken for response rendering.

Exactly which cases can be automated

The matrix has 20 cases per family.

After only neutral Horus-clone qualification

These 11 families, 220 cases, can be automated:

sparta_qra_compliance
persona_memory_recall
persona_memory_miss
brave_research
tau_tool_orchestration
skill_create_evidence_case
skill_create_figure
skill_analytics
skill_sparta_validator
chat_ux_sync
voice_control_skill

Some voice_control_skill templates still require later interruption or idle-policy implementation, but their input speech can use the neutral clone.

Additional source assets required
speaker_identity — 20 cases

Automation additionally requires:

qualified Horus source
qualified unknown/non-Horus source
female distractor source
controlled ambiguous-score or overlap source

These sources need their own immutable identity receipts.

factory_noise — 20 cases

Automation additionally requires:

hash-bound factory-noise assets
declared SNR and gain policy
qualified physical or virtual capture fixture
the actual HD-webcam source for the webcam-specific template
tone_emotion — 20 cases

These require Graham/Horus unless expressive Horus generation is separately qualified for the required input tones.

Neutral TTS reading the words “I am frustrated” does not prove acoustic frustration detection.

interruption — 20 cases

These require Graham/Horus unless the workstation has a qualified, independent source-output route capable of injecting the new Horus utterance while Embry is already speaking through the Jabra sink.

Using the same output stream as both Embry output and the interrupting source is not a valid full-duplex barge-in proof.

Physical-Horus claim

To claim that all 200 cases are physical-Horus cases, Graham must either:

speak every exact counted utterance live

or:

record a complete exact-text Horus corpus for every counted utterance and follow-up

A 25-case physical subset may qualify room acoustics, but it cannot relabel the remaining clone cases as physical.

4. Converting one matrix row into a multi-turn audio session

The current matrix provides one question plus conversation requirements. It does not provide a complete spoken conversation script.

The compiler must generate and hash a deterministic turn_script. Runtime generation by an LLM is forbidden.

Example

Source matrix case:

sparta_qra_compliance-simple-01
What evidence should a SPARTA QRA include to be acceptable?

Compiled session:

JSON
{
  "session_id": "embry-e2e-<campaign>-sparta-qra-simple-01-a01",
  "case_id": "sparta_qra_compliance-simple-01",
  "turns": [
    {
      "turn_id": "sparta_qra_compliance-simple-01:turn-001",
      "speaker": "horus_lupercal",
      "utterance": "Hey Embry, what evidence should a SPARTA QRA include to be acceptable?",
      "purpose": "matrix_question",
      "speech_expectation": "speech_required"
    },
    {
      "turn_id": "sparta_qra_compliance-simple-01:turn-002",
      "speaker": "horus_lupercal",
      "utterance": "Which source in your evidence trail supports that answer?",
      "purpose": "steering_followup",
      "speech_expectation": "speech_required"
    }
  ]
}

Difficulty policy:

simple       2 user turns
medium       3 user turns
advanced     3 user turns plus required skill/result follow-up
adversarial  3–4 user turns including challenge, ambiguity, or rejection
soak         5 repeated turns with stable semantics and varied timing

Every utterance becomes a separate:

turn_id
listener.final_transcript
speaker decision
Memory request set
Tau tick
turn receipt

The Tau subagent remains persistent at the session level, but each user turn receives exactly one bounded tick.

5. Event contracts

All operational events continue to use:

embry.voice_event.v1

Add campaign metadata to payloads rather than changing the base journal schema:

JSON
{
  "campaign_id": "campaign_...",
  "case_id": "sparta_qra_compliance-simple-01",
  "case_contract_sha256": "sha256:...",
  "attempt_id": "attempt_01",
  "turn_index": 1,
  "source_authority_id": "source_..."
}
New source-side events
campaign.case.started
listener.turn_armed
input_source.prepared
input_source.playback.requested       # clone/corpus
input_source.playback.started
input_source.playback.ended
input_source.human_prompted           # physical live
listener.recording_started
listener.partial_transcript*
listener.final_transcript
audio_source.completed
speaker.verification.completed

audio_source.completed is the authoritative source receipt event:

JSON
{
  "schema": "embry.audio_source_receipt.v1",
  "source_authority_id": "source_...",
  "source_class": "physical_live_horus",
  "synthetic": false,
  "physical_human": true,
  "expected_utterance_sha256": "sha256:...",
  "captured_audio_path": "...",
  "captured_audio_sha256": "sha256:...",
  "captured_pcm_sha256": "sha256:...",
  "captured_audio_bytes": 123456,
  "duration_ms": 4200,
  "rms_dbfs": -21.3,
  "peak_dbfs": -3.2,
  "pipewire_source_node": "alsa_input....",
  "listener_final_event_id": "listener.final_transcript....",
  "listener_final_sequence": 17,
  "qualification_receipt": null
}

For a clone:

JSON
{
  "source_class": "qualified_horus_clone",
  "synthetic": true,
  "physical_human": false,
  "source_asset_path": "...",
  "source_asset_sha256": "sha256:...",
  "qualification_receipt_path": "...",
  "qualification_receipt_sha256": "sha256:...",
  "source_playback_event_ids": ["...", "..."],
  "captured_audio_sha256": "sha256:..."
}
Downstream events

Reuse or extend:

memory.speaker_resolved
memory.intent_resolved
memory.answer_resolved
tau.skill.started
tau.skill.completed
tau.turn_plan.completed
tau.persistent_tick.completed
chatterbox.voice_render.completed
playback.requested
playback.started
playback.ended
ux.chat_projection.completed
ux.orb_projection.completed
replay.completed
campaign.turn.completed

For speech_forbidden turns, require:

tau.turn_plan.completed with speech_expectation=speech_forbidden
no chatterbox.voice_render.completed
no playback.requested
6. Campaign manifest
JSON
{
  "schema": "embry.audio_e2e_campaign_manifest.v1",
  "campaign_id": "campaign_<hash>",
  "matrix": {
    "path": "/home/graham/workspace/experiments/chatterbox/docs/EMBRY_STRESS_SESSION_MATRIX.json",
    "sha256": "sha256:...",
    "schema": "embry.stress_session_matrix.v1",
    "source_case_count": 300
  },
  "selection": {
    "method": "stratified_round_robin",
    "requested_count": 200,
    "case_ids": [],
    "selection_sha256": "sha256:..."
  },
  "source_policy": {
    "path": ".../EMBRY_AUDIO_E2E_SOURCE_POLICY.json",
    "sha256": "sha256:...",
    "qualification_receipts": []
  },
  "repositories": {
    "chatterbox": "<commit>",
    "RealtimeSTT": "<commit>",
    "agent-skills": "<commit>",
    "tau": "<commit>",
    "graph-memory-operator": "<commit>",
    "pi-mono": "<commit>"
  },
  "hardware": {
    "listener_source_node": "<stable node.name>",
    "source_output_node": "<stable node.name or physical-live>",
    "response_output_node": "alsa_output.usb-0b0e_Jabra_SPEAK_510_USB_501AA5274B1D022000-00.analog-stereo"
  },
  "execution": {
    "concurrency": 1,
    "required_gates": "all",
    "fixture_substitution_allowed": false,
    "typed_transcript_allowed": false,
    "browser_microphone_allowed": false
  },
  "cases": [
    {
      "case_id": "...",
      "contract_path": "...",
      "contract_sha256": "sha256:...",
      "source_plan": {},
      "turn_script": []
    }
  ]
}

campaign_id derives from:

matrix hash
selection hash
source-policy hash
repository commits
hardware policy
gate policy

It must not derive from the current time.

7. Per-turn acceptance gates

A turn counts only when all applicable gates pass:

Gate	Required evidence
Source authority	Final embry.audio_source_receipt.v1
Source honesty	Explicit synthetic, physical-human, prerecorded, and capture-class fields
Input audio	Non-silent, non-clipped, hash-bound captured WAV/PCM
RealtimeSTT	Partial callback plus one accepted final event
Transcript	Wake stripped; deterministic semantic match to expected utterance
Turn identity	Exact campaign, case, attempt, session, and turn IDs
Speaker gate	Expected known, unknown, ambiguous, or overlap outcome
Memory identity	Exact speaker-resolution context preserved
Memory intent	Exact final transcript used as query
Memory answerability	Correct answer, clarify, deflect, or speech block
Tau	One bounded tick; no unbounded autonomy
Skill route	Required skill.call.receipt.v1 or explicit no-skill route
Plan	Exact display/TTS hashes and conversation-delivery policy
Chatterbox	Exact Tau-plan causation when speech is allowed
Playback	Jabra requested/started/ended authority when speech is required
No speech	No render/playback when speech is forbidden
Chat	Same session and turn; exact text and artifact hashes
Orb	State changes caused only by journal events
Replay	Journal snapshot reconstructs without provider calls
Interruption	Old/new turn lineage and stale-byte/stop bounds when required
Provenance	Every artifact live=true, mocked=false
Oracle	Route-family and case-specific oracle passes
Transcript match

Use a deterministic rule, not an LLM:

strip accepted Hey Embry wake phrase
normalize case and punctuation
WER <= 0.15
all critical tokens preserved
all numeric IDs preserved
no negation polarity change

The compiled case contract supplies critical_tokens. For the first QRA case:

SPARTA
QRA
evidence
acceptable

Embedding similarity may be recorded diagnostically, but it cannot override a failed critical-token or negation gate.

8. Turn, case, and campaign receipts
Turn receipt
JSON
{
  "schema": "embry.audio_e2e_turn_receipt.v1",
  "status": "PASS",
  "live": true,
  "mocked": false,
  "campaign_id": "...",
  "case_id": "...",
  "attempt_id": "...",
  "session_id": "...",
  "turn_id": "...",
  "source": {
    "receipt_path": "...",
    "receipt_sha256": "sha256:...",
    "source_class": "qualified_horus_clone",
    "synthetic": true,
    "physical_human": false
  },
  "journal": {
    "start_sequence": 1,
    "end_sequence": 22,
    "selected_event_ids": [],
    "selected_chain_sha256": "sha256:..."
  },
  "transcript": {
    "expected_sha256": "sha256:...",
    "observed_sha256": "sha256:...",
    "wer": 0.06,
    "critical_tokens_preserved": true
  },
  "speaker": {},
  "memory": {},
  "tau": {},
  "chatterbox": {},
  "playback": {},
  "chat": {},
  "orb": {},
  "replay": {},
  "interruption": null,
  "failed_gates": []
}
Case receipt
JSON
{
  "schema": "embry.audio_e2e_case_receipt.v1",
  "status": "PASS",
  "counted": true,
  "live": true,
  "mocked": false,
  "case_id": "...",
  "case_contract_sha256": "sha256:...",
  "session_id": "...",
  "turn_count": 2,
  "passed_turn_count": 2,
  "source_class_counts": {
    "physical_live_horus": 2,
    "qualified_horus_clone": 0
  },
  "conversation_requirements": {
    "arc_preserved": true,
    "steering_preserved": true,
    "tone_policy_preserved": true,
    "emotion_tags_preserved": true,
    "pause_policy_preserved": true,
    "interruption_policy_preserved": true
  },
  "replay_snapshot_sha256": "sha256:...",
  "oracle": {
    "type": "exact_record_grounded",
    "passed": true
  },
  "turn_receipts": [],
  "failed_gates": []
}
Campaign receipt

Report separate counts:

JSON
{
  "schema": "embry.audio_e2e_campaign_receipt.v1",
  "status": "PASS",
  "requested_case_count": 200,
  "counted_case_count": 200,
  "passed_case_count": 200,
  "failed_case_count": 0,
  "blocked_case_count": 0,
  "source_counts": {
    "physical_live_horus": 25,
    "recorded_physical_horus": 0,
    "qualified_horus_clone": 175,
    "negative_or_distractor_source": 20
  },
  "capture_counts": {
    "physical_jabra_microphone": 45,
    "qualified_pipewire_fixture": 175
  },
  "human_output_witness_count": 25,
  "machine_playback_authority_count": 200,
  "case_receipts": [],
  "failed_gates": []
}

Never collapse those source counts into an unlabeled “physical E2E” count.

9. Durable resume, crash recovery, and idempotency

Create a campaign-local SQLite database:

<campaign-dir>/campaign.sqlite3

Tables:

campaigns
cases
attempts
stages
artifacts
leases

Each stage stores:

stage_name
status
lease_owner
lease_expires_at
input_hash
receipt_path
receipt_sha256
journal_event_id
started_at
ended_at
Resume rules

On resume:

Load and hash-check the campaign manifest.

Reconcile stage state against the operational journal.

A stage is complete only when its expected event and receipt both exist and hashes agree.

A stale running stage with no external side effect becomes abandoned.

A complete stage is not rerun.

An uncertain hardware stage becomes failed_uncertain_side_effect, not silently retried.

A retry uses:

the same case contract;

a new attempt ID;

a new session ID;

preserved prior failure evidence.

Idempotency keys

Derive per-stage keys:

source generation:
  source text hash + source profile hash + generation config hash

source playback:
  source artifact hash + capture fixture + case attempt

listener turn:
  attempt ID + turn ID

Memory/Tau:
  listener final event ID

Chatterbox:
  Tau plan ID and plan hash

response playback:
  render event ID + audio hash + Jabra node.name

Chat/orb:
  journal snapshot hash + through_sequence

replay:
  immutable journal snapshot hash

The current event journal already server-assigns sequence numbers, returns exact duplicate event IDs idempotently, and rejects conflicting duplicates.

10. Running 1, 5, 25, and 200 cases

All four runs use the same compiler and executor. Only the immutable selection manifest changes.

Use deterministic stratified round-robin selection across:

folder_id
difficulty
template_index

Do not use the first N matrix rows; that would omit later route families.

One case
Bash
python -m embry_voice_control.audio_e2e compile \
  --matrix "$CHATTERBOX/docs/EMBRY_STRESS_SESSION_MATRIX.json" \
  --source-policy "$CHATTERBOX/docs/EMBRY_AUDIO_E2E_SOURCE_POLICY.json" \
  --case-id sparta_qra_compliance-simple-01 \
  --output "$OUT/manifest.json"
Five cases
Bash
python -m embry_voice_control.audio_e2e compile \
  --matrix "$CHATTERBOX/docs/EMBRY_STRESS_SESSION_MATRIX.json" \
  --source-policy "$CHATTERBOX/docs/EMBRY_AUDIO_E2E_SOURCE_POLICY.json" \
  --stratified-count 5 \
  --output "$OUT/manifest.json"
Twenty-five cases
Bash
python -m embry_voice_control.audio_e2e compile \
  --matrix "$CHATTERBOX/docs/EMBRY_STRESS_SESSION_MATRIX.json" \
  --source-policy "$CHATTERBOX/docs/EMBRY_AUDIO_E2E_SOURCE_POLICY.json" \
  --stratified-count 25 \
  --output "$OUT/manifest.json"
Two hundred cases
Bash
python -m embry_voice_control.audio_e2e compile \
  --matrix "$CHATTERBOX/docs/EMBRY_STRESS_SESSION_MATRIX.json" \
  --source-policy "$CHATTERBOX/docs/EMBRY_AUDIO_E2E_SOURCE_POLICY.json" \
  --stratified-count 200 \
  --output "$OUT/manifest.json"
All 300 cases
Bash
python -m embry_voice_control.audio_e2e compile \
  --matrix "$CHATTERBOX/docs/EMBRY_STRESS_SESSION_MATRIX.json" \
  --source-policy "$CHATTERBOX/docs/EMBRY_AUDIO_E2E_SOURCE_POLICY.json" \
  --all \
  --output "$OUT/manifest.json"

Execution is identical:

Bash
python -m embry_voice_control.audio_e2e run \
  --manifest "$OUT/manifest.json" \
  --campaign-dir "$OUT/run" \
  ...service and hardware arguments...
  --require-gates all

Development flags such as --through-stage stt may exist, but they must force:

JSON
{
  "counted": false,
  "status": "PARTIAL"
}
11. Live failure capture

On any failure, freeze:

case contract
source receipt and source waveform
captured listener segment
all partial and final STT events
speaker scores
Memory requests and responses
Tau DAG, handoff, skill receipts, stdout, stderr
Chatterbox request, response, and audio
PipeWire graph snapshots
playback events
Chat/orb browser receipt
replay receipt
journal snapshot through failure sequence
service health snapshots
browser network log and screenshot

Write:

<campaign>/cases/<case-id>/<attempt-id>/failure-bundle.json

The failure bundle must contain:

JSON
{
  "schema": "embry.audio_e2e_failure_bundle.v1",
  "failure_stage": "speaker_verification",
  "failed_gate": "horus_not_accepted",
  "fixture_substitution_used": false,
  "typed_prompt_substitution_used": false,
  "provider_fallback_used": false,
  "retry_recommended": false,
  "artifacts": []
}

Never:

inject the expected transcript
reuse a prior Memory response
switch to a fixture skill receipt
call Chatterbox directly with expected answer text
reuse another turn’s journal events

A service outage is a live E2E failure or block, not permission to use fixtures.

12. Chat, orb, replay, and interruption without browser mic authority
Chat

The browser receives only:

session_id
turn_id
journal projection
hash-bound artifacts

It must not call Memory, Tau, or Chatterbox.

The existing journal Chat projection already resolves the exact audio artifact, plan, and trace from journal events and marks the audio as audio_ready with playback disabled in the projection contract.

Orb

The orb state reducer must consume journal events:

listener.recording_started     -> listening
tau tick started               -> processing
chatterbox render completed    -> ready, not speaking
playback.started               -> speaking
playback.ended                 -> idle
interruption accepted          -> interrupted
real transport disconnect      -> offline/error

For every state transition, the browser receipt must carry the causing event ID and sequence.

No browser microphone permission is requested.

Replay

Freeze the session journal at:

through_sequence
snapshot_sha256

Replay must:

reconstruct human and Embry messages;

use captured human audio and rendered Embry audio;

reproduce execution trace and orb transitions;

respect recorded monotonic offsets;

make no Memory, Tau, Brave, skill, Chatterbox, or RealtimeSTT call.

The browser oracle should fail on any provider request during replay.

Interruption

An interruption case requires:

old_turn_id
new_turn_id
new source-audio receipt
new listener final event
new speaker-verification event
interrupt_at_monotonic_ns
duck requested/acknowledged
cancel requested/acknowledged
playback stop
old bytes after cancel
new turn accepted
new turn wins

A non-primary or ambiguous interrupter must not win.

Full automation requires an independent source-output path or virtual input fixture that remains valid while the Jabra is playing Embry audio. Without that, interruption cases remain human-live.

13. First single-case implementation and live command

The first counted matrix proof should use:

sparta_qra_compliance-simple-01

and physical live Graham/Horus speech. This avoids falsely claiming that a Horus clone already exists.

Resolve the stable Jabra microphone node rather than using object ID 62:

Bash
set -euo pipefail

AGENT_SKILLS=/home/graham/workspace/experiments/agent-skills
SKILL_ROOT="$AGENT_SKILLS/skills/embry-voice-control"
CHATTERBOX=/home/graham/workspace/experiments/chatterbox
REALTIMESTT=/home/graham/workspace/experiments/RealtimeSTT
TAU=/home/graham/workspace/experiments/tau
OUT=/tmp/embry-audio-e2e-single-sparta

SOURCE_NODE="$(
  pw-dump --no-colors |
  jq -er '
    [
      .[]
      | select(.type == "PipeWire:Interface:Node")
      | .info.props
      | select(.["media.class"] == "Audio/Source")
      | select((.["node.description"] // "") | test("Jabra SPEAK 510 Mono"; "i"))
      | .["node.name"]
    ]
    | if length == 1 then .[0]
      else error("expected_one_jabra_input_source")
      end
  '
)"

RESPONSE_SINK='alsa_output.usb-0b0e_Jabra_SPEAK_510_USB_501AA5274B1D022000-00.analog-stereo'

rm -rf "$OUT"
mkdir -p "$OUT"

uv run --project "$SKILL_ROOT" --locked --no-sync \
  python -m embry_voice_control.audio_e2e compile \
  --matrix "$CHATTERBOX/docs/EMBRY_STRESS_SESSION_MATRIX.json" \
  --source-policy "$CHATTERBOX/docs/EMBRY_AUDIO_E2E_SOURCE_POLICY.json" \
  --case-id sparta_qra_compliance-simple-01 \
  --source-mode physical_live_horus \
  --output "$OUT/manifest.json"

Run:

Bash
uv run --project "$SKILL_ROOT" --locked --no-sync \
  python -m embry_voice_control.audio_e2e run \
  --manifest "$OUT/manifest.json" \
  --campaign-dir "$OUT/run" \
  --journal-db /mnt/storage12tb/skills/embry-voice-control/state/voice-events.sqlite3 \
  --journal-url http://127.0.0.1:8032 \
  --realtimestt-repo "$REALTIMESTT" \
  --memory-url http://127.0.0.1:8601 \
  --tau-repo "$TAU" \
  --chatterbox-url http://127.0.0.1:8018 \
  --ux-url http://127.0.0.1:3002 \
  --listener-source-node "$SOURCE_NODE" \
  --source-mode physical_live_horus \
  --response-output-node "$RESPONSE_SINK" \
  --require-gates all \
  --require-human-output-witness

The managed listener prompts Graham with the exact first utterance:

Hey Embry, what evidence should a SPARTA QRA include to be acceptable?

It must not pass that text to RealtimeSTT as data.

The run may stop at:

MACHINE_PASS_HUMAN_WITNESS_PENDING

The project agent then asks the human whether the exact expected Embry response was heard. It must not answer on the human’s behalf.

Final single-case stop condition:

case receipt status PASS
counted=true
all required turns PASS
source class physical_live_horus
captured PCM hash present
RealtimeSTT transcript gate PASS
speaker gate known/horus_lupercal
Memory/Tau route oracle PASS
Chatterbox response causally linked
Jabra playback requested/started/ended
human output witness recorded
Chat same-turn projection PASS
orb event lineage PASS
journal-only replay PASS
no failed gates
14. What can be implemented immediately

Using existing code, the project can immediately implement:

campaign manifest compilation;

stratified selection;

durable campaign state;

the managed per-turn RealtimeSTT control protocol;

physical-live source receipts;

deterministic transcript comparison;

journal event waiting;

generic Memory/Tau turn execution;

reuse of causal Chatterbox render;

reuse of Jabra playback authority;

reuse of the journal Chat projection;

failure bundles;

one new physical-live matrix case.

The current journal, artifact authority, physical listener, Chat projection, and response playback provide most of the primitives. The missing work is orchestration and per-turn control rather than another rewrite.

15. What requires a new qualified Horus source

The following cannot be automated honestly until a source qualification or corpus exists:

bulk source utterance generation;

expressive frustrated, hostile, discouraged, and playful inputs;

automated physical-room barge-in during Embry playback;

ambiguous and female-distractor identity sources;

factory-noise and alternate-microphone source fixtures;

any claim that clone-generated cases are physical-human.

Until source qualification passes, the runner must mark selected automated cases:

JSON
{
  "status": "BLOCKED",
  "counted": false,
  "failed_gates": [
    "qualified_horus_audio_source_missing"
  ]
}
Fail-closed 200-case answer

If 200 exact Horus utterances cannot be produced through either:

qualified_horus_clone
recorded_physical_horus corpus
physical_live_horus

then the campaign must not report 200 E2E cases.

It should report, for example:

JSON
{
  "requested_case_count": 200,
  "counted_case_count": 37,
  "passed_case_count": 37,
  "blocked_case_count": 163,
  "status": "BLOCKED_SOURCE_COVERAGE",
  "physical_human_case_count": 12,
  "qualified_clone_case_count": 25,
  "failed_gates": [
    "source_coverage_below_requested_count"
  ]
}

No generic TTS, Embry reference voice, typed transcript, or fixture response may fill the missing 163 cases.

The truthful current full-chain count remains one until the new runner produces additional complete case receipts.

<<<WEBGPT_DONE:20260711T140539Z:33c7194e>>>
