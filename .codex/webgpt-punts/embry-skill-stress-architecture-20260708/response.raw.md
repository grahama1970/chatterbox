Blunt current status

The latest Chatterbox work is useful but narrow.

Implemented/proven:

chatterbox has FastAPI endpoint /tau/voice-render.

Commit d3a0762 Block unanswerable Tau voice renders is pushed.

Receipt 20260708T010111Z-answerability-runtime-block/receipt.json proves mocked=false, live=true, ok=true, case_count=12, failed_gates=[].

That proves one downstream invariant: when Tau voice render receives block_before_speech, Chatterbox does not produce finished_response_audio.

Not proven:

Upstream memory answer quality.

Tau skill orchestration.

Brave Search source-backed research.

RealtimeSTT-to-memory-to-Tau-to-Chatterbox full loop.

Shared Chat UX sync from the same event journal.

Orb sync from actual Embry audio.

Replay from real event journals.

Interruption/barge-in.

The architecture should now shift from “fixing individual routes” to a ledger-backed, generated stress harness with deterministic receipts.

1. Numbered architecture model
1. Stress generator

Status: intended / missing as architecture spine.

Generates 200+ expandable stress sessions from source-backed templates.

Inputs:

SPARTA corpora / QRA / compliance evidence.

persona_memory, scoped by Horus, Embry, unknown speaker, ambiguous speaker.

Brave Search research templates.

Tau skill manifests.

Voice/chat modality templates.

Negative controls and memory-miss templates.

Output:

embry.stress_case.v1 cases.

Expected route.

Expected answerability.

Expected receipts.

Exact pass/fail gates.

The generator must not create tests that have no oracle. “Unlimited” should mean unlimited generated cases from finite source-backed templates, not random uncheckable prompts.

2. Event journal and receipt spine

Status: missing / should be first-class.

Every run writes one append-only event journal. This is the proof authority.

The journal owns:

Session events.

RealtimeSTT events.

Speaker identity decisions.

Memory retrieval and answerability.

Tau routing and skill handoff.

Brave Search source receipts.

Chatterbox render events.

Chat UX render receipts.

Orb playback state.

Interruption events.

Replay receipts.

Final proof result.

UX Lab, browser DOM state, screenshots, and Chatterbox audio files are evidence only when linked to journal events.

3. Ingress layer: chat and voice

Status: partial.

Two accepted ingress modes:

Chat ingress for deterministic lower-rung memory/Tau/skill tests.

RealtimeSTT voice ingress for real microphone/VAD/ASR tests.

RealtimeSTT owns:

Real audio capture handoff.

VAD.

ASR partial/final transcript events.

Audio artifact hashes.

Timing metadata.

RealtimeSTT does not own memory policy or tool routing.

4. Memory-owned identity, recall, intent, answerability, and tone

Status: partial and currently failing in important cases.

Memory is first in the reasoning path.

Memory owns:

Speaker identity / speaker resolve policy.

Persona and SPARTA retrieval.

Horus/Embry/unknown scope enforcement.

Intent hints.

Tone/emotion hints.

Answerability decision.

Fail-closed behavior when retrieval is unrelated.

Known failures become hard gates:

No unrelated SPARTA/persona records.

No deprecated-control text for unrelated QRA questions.

No skill descriptions as persona facts.

Memory miss must return clarify, no_answer, or block_before_speech.

5. Tau as router and tool authority

Status: partial / missing receipts.

Tau consumes memory output and decides:

Direct answer.

Clarification.

Block before speech.

Brave Search route.

Skill call route.

Multi-step DAG route.

Tau owns:

tau.route_decision.v1

tau.agent_handoff.v1

Work order creation.

DAG receipt creation.

Skill-call authorization.

No UI component and no Chatterbox endpoint may invoke skills directly.

6. Direct skills through Tau

Status: missing as enforceable architecture.

Skills live behind a Tau-controlled skill gateway.

Examples:

create-figure

analytics

create-evidence-case

SPARTA validators

memory tools

Brave Search

voice-control skills

Every skill call must produce a skill.call.receipt.v1 before Tau may produce a speakable response.

7. Brave Search external research route

Status: currently a route family, not proven enough.

Brave Search must be treated as a real external research skill/tool route.

Required:

Live external request unless explicitly marked as replay.

Provider request ID or equivalent trace.

Query string.

Retrieved source URLs.

Source timestamps where available.

Source hashes or normalized result hashes.

Claim-to-source support map.

brave_search.source_receipt.v1.

Cache-only or static-fixture-only search is not a live Brave Search proof.

8. Response planner

Status: intended / partially implied.

Tau produces a response plan only after memory answerability and skill/source receipts are complete.

The response plan includes:

Final assistant text.

Answerability receipt reference.

Memory receipt reference.

Skill receipt references.

Brave Search receipt references.

Tone/emotion tags.

Chatterbox permission: can_speak=true | false.

Chat UX payload references.

9. Chatterbox as renderer / Tau voice ingress

Status: partially implemented.

Chatterbox owns:

/tau/voice-render

Speech rendering.

Audio artifact generation.

Refusal to speak blocked/unanswerable responses.

Chatterbox audio receipts.

Chatterbox must not own:

Retrieval.

Answerability.

Tool routing.

Skill execution.

Persona facts.

Brave Search.

The current receipt proves only that Chatterbox blocks block_before_speech at render time.

10. Shared Chat UX as event-journal renderer

Status: incomplete / design drift.

Shared Chat UX must render the same event journal used by voice.

It should display:

User text.

Voice transcript.

Speaker identity.

Memory reasoning.

Entity underlines.

Skill/source receipts.

Assistant response.

Chatterbox audio state.

Orb state.

Interruption events.

Replay timeline.

It must not become a second source of truth.

11. Orb sync from actual audio

Status: missing.

The orb must track actual Embry audio playback, not fake state.

Required source events:

chatterbox.audio.generated.v1

audio.playback.started.v1

audio.playback.progress.v1

audio.playback.ended.v1

audio.playback.cancelled.v1

Orb state must reference playback event IDs or audio envelope data.

12. Interruption / barge-in

Status: missing.

During Embry speech, RealtimeSTT continues listening.

A valid Horus barge-in requires:

Embry audio is actually playing.

RealtimeSTT detects new speech.

Speaker identity resolves to Horus with sufficient confidence.

Interruption manager cancels playback.

New turn begins.

Memory policy remains gated by speaker identity.

Unknown or ambiguous barge-in must not unlock personal memory.

13. Replay

Status: incomplete.

Replay must load the real event journal and artifacts.

Replay is allowed to use previous live artifacts, but it must mark the run as replay, not live proof.

Replay output:

Timeline hash.

Artifact hash verification.

UX render receipt.

Audio playback references.

Orb state references.

Final replay.receipt.v1.

2. Implemented vs intended/missing status map
Area	Status	Comment
Chatterbox /tau/voice-render	Implemented partial	Exists and blocks known block_before_speech cases.
Answerability runtime block	Implemented narrow	12 cases passed; downstream only.
Upstream memory quality	Failing	Returns unrelated SPARTA/persona records in known cases.
Memory-first routing	Partial	Needs answerability receipts and hard fail-closed gates.
Tau tool orchestration	Failing/missing	No tau.agent_handoff.v1 work order or DAG receipt.
Brave Search source receipts	Missing/partial	Must prove real external source-backed route.
Direct skill access	Missing as architecture	Must go through Tau skill gateway only.
Chat UX sync	Missing/partial	Must render journal, not prove truth.
RealtimeSTT factory/browser capture	Partial	Browser mic usability is source-dependent.
Speaker identity / diarization	Partial	Some live slices exist, but not full harness-backed.
Orb sync	Missing	Must be audio-playback-driven.
Replay	Missing/partial	Must replay journal and artifacts.
Interruption / barge-in	Missing	Needs full playback + RealtimeSTT + identity path.
200-session matrix	Partial inventory	9 passed, 31 failed, 160 not run. Not full proof.
3. Generated stress session schema

Recommended file format: YAML or JSON. YAML is easier for generated suites plus human review.

YAML
schema: embry.stress_case.v1
case_id: memory.sparta_qra.easy.001
suite_id: embry_voice_chat_stress_200_plus
title: "SPARTA QRA answerable control"
status: generated

route_family: memory.sparta_qra
difficulty: easy
modalities:
  chat: true
  voice: false
  replay: false

source_generation:
  generated_by: stress_generator
  generated_at: "2026-07-08T01:06:09Z"
  seed: 733156
  source_refs:
    - kind: sparta_corpus
      corpus_id: sparta_qra
      record_ids: ["qra:control:example"]
      hash: "sha256:..."
  fixture_policy:
    live_required: false
    replay_allowed: true
    static_fixture_allowed: false

speaker_context:
  speaker_status: known
  speaker_id: horus_lupercal
  expected_personal_memory_allowed: true
  diarization_case: single_speaker

input:
  prompt_text: "What evidence supports the QRA control for ..."
  voice:
    required: false
    phrase_nonce_required: false
    min_asr_confidence: null

expected_route:
  first_authority: memory
  tau_route: direct_answer
  allowed_tools: []
  forbidden_tools: ["chatterbox_before_answerability"]
  brave_search_required: false
  skill_required: false

expected_answerability:
  decision: answerable
  can_speak: true
  required_evidence:
    min_records_used: 1
    allowed_record_kinds: ["sparta_qra", "sparta_compliance_evidence"]
    forbidden_record_patterns:
      - "S0609"
      - "deprecated-control"
      - "unrelated skill description"
  unsupported_claim_policy: fail

expected_tone:
  memory_intent_required: true
  allowed_tags: ["memory_confident"]
  forbidden_generic_when_specific_expected: true

expected_chatterbox:
  should_request_tts: true
  should_finish_response_audio: true
  require_audio_artifact_hash: true

expected_ux:
  shared_chat_required: false
  render_from_event_journal_only: true

expected_replay:
  replay_required: false
  require_artifact_hash_check: true

pass_fail_gates:
  - gate_id: no_mock_transcript
    rule: "source.mocked must be false for live voice cases"
  - gate_id: memory_before_tau_response
    rule: "memory.answerability.v1 must precede assistant.response.plan.v1"
  - gate_id: no_speech_before_answerability
    rule: "chatterbox.audio.finished must not occur unless answerability.can_speak is true"
  - gate_id: evidence_relevance
    rule: "records_used must match allowed_record_kinds and source_refs"

For generated tests, require every case to have one of these oracle types:

YAML
oracle:
  type: one_of
  allowed:
    - exact_record_grounded
    - answerability_negative_control
    - skill_receipt_required
    - brave_source_required
    - identity_policy_required
    - voice_transport_required
    - replay_integrity_required

Do not accept generated cases with oracle.type: none into the pass/fail suite. Put those in exploratory runs only.

4. Skill call receipt schema

Every direct skill call must produce this before Embry speaks from the result.

YAML
schema: embry.skill_call_receipt.v1
receipt_id: skillrec_01
session_id: ses_01
turn_id: turn_01
trace_id: trace_01

requested_by:
  component: tau
  event_id: evt_tau_agent_handoff
  work_order_id: wo_01
  dag_id: dag_01

skill:
  name: create-evidence-case
  version: "1.2.0"
  owner_repo: agent-skills
  manifest_hash: "sha256:..."
  input_schema_hash: "sha256:..."
  output_schema_hash: "sha256:..."

authorization:
  tau_authorized: true
  caller: tau.skill_gateway
  ui_direct_call: false
  chatterbox_direct_call: false
  policy_scope:
    speaker_id: horus_lupercal
    personal_memory_allowed: true

input:
  normalized_input_hash: "sha256:..."
  redacted_preview: "Create an evidence case for ..."
  source_event_ids:
    - evt_memory_answerability
    - evt_tau_route_decision

execution:
  started_at: "2026-07-08T01:06:09Z"
  finished_at: "2026-07-08T01:06:12Z"
  status: success
  deterministic_mode: false
  mocked: false
  live: true

outputs:
  artifacts:
    - kind: evidence_case
      uri: "ledger://ses_01/artifacts/evidence_case.json"
      sha256: "sha256:..."
  structured_result_hash: "sha256:..."
  summary_for_tau: "Evidence case created with 4 supporting records."

validation:
  output_schema_valid: true
  required_artifacts_present: true
  source_support_complete: true
  errors: []

speech_gate:
  may_be_spoken_by_embry: true
  reason: "skill succeeded and receipt is complete"

Hard fail conditions:

Missing tau.agent_handoff.v1.

Missing work order ID.

Missing DAG ID or DAG receipt.

Skill called by UI.

Skill called by Chatterbox.

Missing output artifact hash.

Embry speaks before this receipt exists.

5. Answerability receipt schema
YAML
schema: embry.answerability_receipt.v1
receipt_id: ansrec_01
session_id: ses_01
turn_id: turn_01
trace_id: trace_01

authority:
  component: memory
  event_id: evt_memory_answerability
  memory_version: "git:..."
  config_hash: "sha256:..."

speaker_policy:
  speaker_status: known
  speaker_id: horus_lupercal
  personal_memory_allowed: true
  source_event_id: evt_speaker_identity

question:
  normalized_text_hash: "sha256:..."
  redacted_text: "What does SPARTA say about ...?"

route_hint:
  suggested_route: direct_answer
  needs_tau_tool: false
  needs_brave_search: false
  needs_clarification: false

retrieval:
  records_considered:
    count: 12
    kinds: ["sparta_qra", "sparta_compliance_evidence"]
  records_used:
    - record_id: qra:control:example
      kind: sparta_qra
      score: 0.91
      source_hash: "sha256:..."
  forbidden_records_used: []
  unrelated_record_detected: false

decision:
  answerability: answerable
  can_speak: true
  block_before_speech: false
  confidence: 0.86
  reason: "Relevant SPARTA QRA evidence found."

claims:
  supported_claim_count: 3
  unsupported_claim_count: 0
  claim_support_map_hash: "sha256:..."

tone_intent:
  tone: memory_confident
  emotion: calm
  specific_tone_required: false

failure_policy:
  if_unanswerable: block_before_speech
  if_unsupported_claims: block_before_speech
  if_unrelated_records: block_before_speech

For negative cases:

YAML
decision:
  answerability: no_answer
  can_speak: false
  block_before_speech: true
  reason: "No relevant Horus-scoped persona memory found."
6. Execution ladder from current state to full live loop
Rung 0 — Freeze current matrix and define generated case schema

Purpose: stop uncontrolled route drift.

Acceptance:

Existing 200 cases are migrated or wrapped into embry.stress_case.v1.

Current statuses are preserved: 9 passed, 31 failed, 160 not run.

No status is upgraded without a new receipt.

Rung 1 — Journal + receipt proof spine

Purpose: create the proof authority.

Acceptance:

Every test run writes events.ndjson.

Every run writes receipt.json.

Receipt verdict is computed from events, not UI state.

Mocked/static runs are labeled as such and cannot count as live proof.

Rung 2 — Chatterbox answerability enforcement regression

Purpose: preserve commit d3a0762.

Acceptance:

Re-run the 12 block_before_speech cases.

mocked=false, live=true, ok=true.

Zero finished_response_audio for blocked cases.

At least one answerable control case proves speech still works when can_speak=true.

Rung 3 — Memory answer quality and answerability

Purpose: fix the actual upstream failure.

Acceptance:

SPARTA QRA cases use relevant SPARTA/QRA records only.

Persona cases use correct Horus/Embry-scoped memory only.

Memory miss cases clarify or block.

Unrelated records cause block_before_speech.

Answerability receipt is emitted for every case.

Rung 4 — Tau work orders, DAG receipts, and skill gateway

Purpose: make direct skills real.

Acceptance:

Tool-required cases emit tau.agent_handoff.v1.

Work order ID exists.

DAG receipt exists.

Skill receipt exists.

Chatterbox does not speak until skill receipt exists and answerability is speakable.

Rung 5 — Brave Search with source receipts

Purpose: prove external research route.

Acceptance:

Brave Search cases make real provider calls.

Source receipts include query, source URLs, timestamps where available, and result hashes.

Final answer claims map to sources.

No source receipt means no speech.

Rung 6 — Shared chat + voice response plan

Purpose: unify chat and speech.

Acceptance:

Chat output and Chatterbox input reference the same assistant.response.plan.v1.

Chat UX renders event IDs from the journal.

No separate UI truth state.

Rung 7 — RealtimeSTT live ingress

Purpose: move from chat-only to real voice.

Acceptance:

Real audio artifacts exist.

RealtimeSTT emits VAD and final transcript.

Empty transcript fails.

Browser capture instability is reported as transport failure, not hidden.

Rung 8 — Speaker identity / diarization gates

Purpose: enforce Horus-scoped memory access.

Acceptance:

Known Horus can use personal memory.

Unknown speaker cannot.

Ambiguous low-confidence cannot.

Overlap cannot.

Gate decision appears before memory query.

Rung 9 — Chatterbox speech + orb sync

Purpose: prove actual rendered audio drives UI/orb.

Acceptance:

Chatterbox audio artifact exists.

Playback events reference that artifact.

Orb state references playback events or audio envelope.

Fake speaking flags fail.

Rung 10 — Interruption / barge-in

Purpose: prove live turn control.

Acceptance:

Horus interruption cancels Embry playback and starts a new turn.

Unknown/ambiguous interruption does not unlock memory.

Events show playback, VAD, identity, interruption, cancel, new turn.

Rung 11 — Replay

Purpose: prove sessions can be reconstructed.

Acceptance:

Replay uses journal and artifact hashes.

Chat UX timeline, audio, memory trace, skill receipts, orb state, and interruptions replay.

Replay receipt is labeled replay, not live proof.

Rung 12 — 200+ generated suite and expansion

Purpose: scale beyond hand-authored cases.

Acceptance:

At least 200 generated or migrated cases run.

Every case has an oracle.

Failures are classified by component.

New generated cases can be added without modifying the runner.

Unlimited expansion uses templates + source-grounded oracles.

7. Exact pass/fail gates for first 5 implementation steps
Step 1 — Implement stress case schema and runner wrapper

Owner: tau or shared stress harness under Tau authority.

Pass:

docs/EMBRY_STRESS_SESSION_MATRIX.json loads.

All 200 existing sessions are represented as embry.stress_case.v1.

Route family, difficulty, question, expected route, and current status are preserved.

Runner emits one receipt.json per attempted case.

No case with missing oracle is allowed into required pass/fail mode.

Fail:

Any migrated case loses route family or difficulty.

Any run result is inferred from logs only.

Any generated case is marked pass without an oracle.

Step 2 — Implement canonical event journal

Owner: tau for schema/runner; all components emit.

Pass:

Each run writes events.ndjson.

Event sequence is monotonic.

Each event has session_id, turn_id, event_id, type, component, occurred_at, mocked, live, parent_event_ids.

Final receipt includes journal hash.

Verdict is computed by scanning event types and payloads.

Fail:

DOM-only evidence.

Console-log-only evidence.

Missing journal hash.

Post-hoc receipt not tied to events.

Step 3 — Preserve Chatterbox answerability block

Owner: chatterbox.

Pass:

Re-run the 12 block cases from the latest receipt.

case_count=12.

failed_gates=[].

block_before_speech=true for each negative case.

No finished_response_audio for blocked cases.

Add at least one positive control where can_speak=true and Chatterbox emits audio.

Fail:

Any blocked case produces Chatterbox audio.

Any case lacks answerability receipt reference.

Chatterbox invents or overrides answerability.

Step 4 — Implement memory answerability receipts

Owner: memory.

Pass:

Every memory route emits embry.answerability_receipt.v1.

SPARTA cases use SPARTA/QRA/compliance records only.

Persona cases use correct Horus/Embry-scoped records only.

Memory-miss cases return clarify, no_answer, or block_before_speech.

Unrelated records set unrelated_record_detected=true and can_speak=false.

Fail:

Any unrelated record appears in records_used.

Any memory miss produces confident answer text.

Any Chatterbox request happens before answerability.

Step 5 — Implement Tau handoff and skill receipts

Owner: tau plus agent-skills.

Pass:

Tool-required cases emit tau.agent_handoff.v1.

Each handoff has work order ID and DAG ID.

Each called skill emits embry.skill_call_receipt.v1.

Skill receipt references the Tau handoff event.

Assistant response plan references the skill receipt.

Chatterbox speaks only after successful skill receipt and answerability receipt.

Fail:

Skill is called directly by UI.

Skill is called directly by Chatterbox.

“Tau doctor ran” appears without work order and DAG receipt.

Chatterbox speaks before skill receipt exists.

Skill output lacks artifact/result hash.

8. Ownership by repo/component
Area	Owner	Notes
Stress schema	tau	Tau is routing/proof authority.
Stress runner / verdict engine	tau	Computes pass/fail from journal.
Event journal schema	tau primary, all components emit	Shared contract.
RealtimeSTT audio/VAD/ASR events	RealtimeSTT	Real ingress only.
Speaker identity / resolve	memory	Memory-first identity and scope policy.
Persona/SPARTA retrieval	memory	Must emit answerability receipts.
Intent/tone hints	memory	Tau may consume but not fabricate memory evidence.
Final routing decision	tau	Direct answer, Brave Search, skill, clarify, block.
Work orders / DAG receipts	tau	Required before skill-backed speech.
Skill implementations	agent-skills	Skills expose manifests and receipts.
Skill gateway authorization	tau	Only Tau calls skills.
Brave Search skill/tool	agent-skills implementation, tau authorization	Must emit source receipts.
/tau/voice-render	chatterbox	Renderer ingress only.
Chatterbox audio generation	chatterbox	Must block failed answerability.
Audio playback events	chatterbox or playback shell	Must produce real playback telemetry.
Shared Chat UX	ux-lab / shared UI	Renders journal only. Not proof authority.
Orb rendering	ux-lab / shared UI	Driven by playback events only.
Replay renderer	ux-lab consuming journal	Replay receipts computed from journal/artifacts.
9. Direct skill access without UI or Chatterbox bypassing Tau

Required flow:

RealtimeSTT or Chat
  -> memory identity / recall / answerability / tone
  -> Tau route decision
  -> Tau agent handoff
  -> Tau skill gateway
  -> agent-skills execution
  -> skill.call.receipt.v1
  -> Tau response plan
  -> Chatterbox render if can_speak=true
  -> Shared Chat UX renders same journal

Enforcement:

Skills require Tau-issued work order IDs.

Skills reject calls without tau.agent_handoff.v1.

Skill receipts include caller identity.

UI has no skill credentials.

Chatterbox has no skill credentials.

Chatterbox accepts only response plans and answerability receipts.

Stress runner fails any event sequence where skill.call.* occurs without prior Tau handoff.

Stress runner fails any sequence where Chatterbox audio occurs before required receipts.

Voice-control skills should also go through Tau. They may emit commands such as audio.playback.cancel.requested.v1, but they should not directly mutate UI state without ledger events.

10. Preventing mocked proof and static fixture theater

Use separate run modes:

Mode	Allowed for pass/fail?	Meaning
live	Yes	Real current component execution.
replay	Yes, for replay rungs only	Uses prior live journal/artifacts.
fixture_regression	Yes, only for component regression	Clearly marked non-live.
mock	No for proof	Development only.
dom_only	No	UI inspection only.

Hard anti-theater rules:

Live voice cases require real audio artifact hashes.

Live RealtimeSTT cases require mocked=false, live=true, non-empty transcript, and audio hash.

Live Brave Search cases require real source receipts.

Skill cases require real skill receipts and artifact/result hashes.

Chatterbox speech requires answerability receipt plus response plan.

UI receipts prove rendering coverage only.

Replay must reference previous live journal hashes.

Random nonce phrases should be used in live voice prompts to prevent transcript reuse.

Generated tests should include negative controls and near-neighbor distractors.

Receipts must include git commit, config hash, schema version, and generated-case seed.

Static fixtures can be useful, but they must be labeled and cannot satisfy live-loop claims.

11. Minimal clarification interview tree

The agent should ask these only when the answer affects test generation or pass/fail oracles. Defaults allow implementation to proceed.

A. Corpus scope

Question: Which SPARTA corpora and QRA/evidence directories are in scope?

Default: include all non-secret SPARTA/QRA/compliance corpora already indexed by memory; exclude records marked secret, draft-only, or unsafe for test logs.

Blocks: SPARTA generated tests.

B. Persona memory scopes

Question: Which persona namespaces are authoritative for Horus and Embry?

Default:

Horus facts only from Horus-scoped persona memory.

Embry self-description only from Embry-scoped persona memory.

Unknown or ambiguous speaker gets no personal memory.

Blocks: persona generated tests.

C. Skill registry

Question: Which skills are enabled for proof?

Default: enable only skills with manifest, input schema, output schema, and receipt implementation. Disable unmanifested skills from pass/fail suite.

Blocks: direct-skill generated tests.

D. Brave Search credentials and policy

Question: Is live Brave Search available in the test environment?

Default: if credentials exist, run live source-receipt tests. If missing, mark as blocked_environment, not pass.

Blocks: external research live proof.

E. Voice hardware

Question: Which microphone path is proof-authoritative?

Default: native mic or known-good HD webcam path. Jabra browser capture remains a known unstable transport and should be tested as a failure/diagnostic path, not proof authority.

Blocks: live voice rungs.

F. Answerability thresholds

Question: What retrieval confidence and evidence count are required for answerable SPARTA/persona cases?

Default:

At least one relevant source record for simple facts.

At least two relevant records for compliance/evidence synthesis.

Zero unrelated records in records_used.

Unsupported claims block speech.

Blocks: memory answerability pass/fail.

G. Tone/emotion expectations

Question: Which tone labels are canonical?

Default:

memory_confident

firm

humorous

gentle

one_at_a_time

clarifying

blocked_safe

Blocks: tone/emotion route tests.

H. Replay retention

Question: Where should event journals and artifacts be retained?

Default: per-session artifact directory with immutable hashes; replay consumes only those references.

Blocks: replay proof.

I. Suite expansion target

Question: How many generated cases per route family before voice integration?

Default:

Keep current 200.

Add at least 20 per new direct-skill route.

Add at least 20 Brave Search source-backed cases.

Add at least 20 negative answerability cases.

Do chat-first for memory/Tau/skill rungs, then voice+chat once RealtimeSTT and speaker identity rungs pass.

Blocks: none; use default.

12. create-architecture-ready YAML
YAML
architecture:
  schema: create-architecture.v1
  name: Embry Skill-Backed Voice/Chat Stress Harness
  version: 2026-07-08
  purpose: >
    Expand Embry stress testing beyond fixed UI patches into a source-backed,
    receipt-driven harness covering RealtimeSTT ingress, speaker identity,
    memory/Tau routing, direct skills, Brave Search, Chatterbox speech,
    shared Chat UX sync, orb sync, replay, and interruption.

  source_facts:
    chatterbox_endpoint: "/tau/voice-render"
    chatterbox_commit: "d3a0762 Block unanswerable Tau voice renders"
    latest_receipt:
      path: "/tmp/chatterbox-fork-agent-out/embry-answerability-runtime-block/20260708T010111Z-answerability-runtime-block/receipt.json"
      mocked: false
      live: true
      ok: true
      case_count: 12
      failed_gates: []
      proves:
        - "block_before_speech prevents finished_response_audio"
      does_not_prove:
        - "upstream memory answer quality"
        - "Tau skill orchestration"
        - "full RealtimeSTT to Chatterbox loop"
    current_matrix:
      path: "docs/EMBRY_STRESS_SESSION_MATRIX.json"
      total_sessions: 200
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
      status_counts:
        passed: 9
        failed: 31
        not_run: 160

  components:
    - id: stress_generator
      owner: tau
      status: intended
      responsibilities:
        - "Generate 200+ expandable source-backed stress cases"
        - "Require an oracle for each pass/fail case"
        - "Generate SPARTA, persona, Brave Search, skill, voice, UX, replay, and interruption cases"
      emits:
        - embry.stress_case.v1

    - id: verdict_engine
      owner: tau
      status: intended
      responsibilities:
        - "Compute pass/fail from event journal"
        - "Reject DOM-only proof"
        - "Reject mock proof for live rungs"
      consumes:
        - embry.event_journal.v1
      emits:
        - proof.receipt.v1

    - id: event_journal
      owner: tau
      status: intended
      responsibilities:
        - "Append-only session ledger"
        - "Monotonic event sequence"
        - "Artifact hashes"
        - "Git/config provenance"
      event_types:
        - session.started.v1
        - realtime_stt.final.v1
        - speaker.identity.decision.v1
        - memory.answerability.v1
        - tau.route_decision.v1
        - tau.agent_handoff.v1
        - skill.call.receipt.v1
        - brave_search.source_receipt.v1
        - assistant.response.plan.v1
        - chatterbox.voice_render.requested.v1
        - chatterbox.audio.finished.v1
        - chat.render.receipt.v1
        - orb.state.v1
        - interruption.detected.v1
        - replay.receipt.v1
        - proof.receipt.v1

    - id: chat_ingress
      owner: tau
      status: partial
      responsibilities:
        - "Deterministic text ingress for lower rungs"
        - "Create turn events"
      emits:
        - turn.input.chat.v1

    - id: realtime_stt
      owner: RealtimeSTT
      status: partial
      responsibilities:
        - "Real audio ingress"
        - "VAD"
        - "ASR partial/final transcripts"
        - "Audio artifact hashes"
      emits:
        - audio.input.chunk.v1
        - realtime_stt.vad.started.v1
        - realtime_stt.vad.ended.v1
        - realtime_stt.partial.v1
        - realtime_stt.final.v1

    - id: memory
      owner: memory
      status: failing_partial
      responsibilities:
        - "Speaker identity and memory scope"
        - "SPARTA/persona retrieval"
        - "Intent and tone hints"
        - "Answerability"
        - "Fail closed on unrelated records"
      emits:
        - speaker.identity.decision.v1
        - memory.retrieval.v1
        - memory.answerability.v1
        - memory.intent_tone.v1

    - id: tau_router
      owner: tau
      status: partial
      responsibilities:
        - "Route decision"
        - "Tool authority"
        - "Work order creation"
        - "DAG receipt creation"
        - "Response planning"
      emits:
        - tau.route_decision.v1
        - tau.agent_handoff.v1
        - tau.dag_receipt.v1
        - assistant.response.plan.v1

    - id: skill_gateway
      owner: tau
      status: intended
      responsibilities:
        - "Authorize all direct skill calls"
        - "Reject UI and Chatterbox direct calls"
        - "Attach work_order_id and dag_id"
      emits:
        - skill.call.requested.v1

    - id: agent_skills
      owner: agent-skills
      status: partial
      responsibilities:
        - "Execute create-figure, analytics, create-evidence-case, SPARTA validators, memory, Brave Search, voice-control skills"
        - "Validate input/output schemas"
        - "Emit skill receipts"
      emits:
        - skill.call.receipt.v1

    - id: brave_search
      owner: agent-skills
      status: intended
      responsibilities:
        - "Perform real external research through Brave Search"
        - "Return source receipts"
        - "Map answer claims to sources"
      emits:
        - brave_search.source_receipt.v1

    - id: chatterbox
      owner: chatterbox
      status: implemented_partial
      responsibilities:
        - "Expose /tau/voice-render"
        - "Render Embry speech"
        - "Block unanswerable responses before speech"
        - "Emit audio artifacts"
      must_not:
        - "Perform memory retrieval"
        - "Route tools"
        - "Call skills directly"
        - "Invent answerability"
      emits:
        - chatterbox.voice_render.requested.v1
        - chatterbox.voice_render.blocked.v1
        - chatterbox.audio.finished.v1

    - id: shared_chat_ux
      owner: ux-lab
      status: incomplete
      responsibilities:
        - "Render event journal"
        - "Display text, transcript, memory trace, entities, receipts, audio, orb, replay"
      must_not:
        - "Act as proof authority"
        - "Maintain independent truth state"
      emits:
        - chat.render.receipt.v1

    - id: orb
      owner: ux-lab
      status: missing
      responsibilities:
        - "Track actual Embry audio playback"
        - "Use playback events and audio envelope"
      emits:
        - orb.state.v1

    - id: replay_runner
      owner: ux-lab
      status: intended
      responsibilities:
        - "Replay real event journals"
        - "Verify artifact hashes"
        - "Render timeline"
      emits:
        - replay.receipt.v1

  connections:
    - from: stress_generator
      to: verdict_engine
      carries:
        - embry.stress_case.v1

    - from: chat_ingress
      to: event_journal
      carries:
        - turn.input.chat.v1

    - from: realtime_stt
      to: event_journal
      carries:
        - audio.input.chunk.v1
        - realtime_stt.final.v1

    - from: event_journal
      to: memory
      carries:
        - turn input
        - RealtimeSTT transcript
        - speaker audio metadata

    - from: memory
      to: event_journal
      carries:
        - speaker.identity.decision.v1
        - memory.answerability.v1
        - memory.intent_tone.v1

    - from: memory
      to: tau_router
      carries:
        - answerability receipt
        - retrieval evidence
        - intent/tone hints

    - from: tau_router
      to: skill_gateway
      condition: "route requires direct skill"
      carries:
        - tau.agent_handoff.v1
        - work_order_id
        - dag_id

    - from: skill_gateway
      to: agent_skills
      carries:
        - authorized skill call

    - from: agent_skills
      to: event_journal
      carries:
        - skill.call.receipt.v1

    - from: brave_search
      to: event_journal
      carries:
        - brave_search.source_receipt.v1

    - from: tau_router
      to: event_journal
      carries:
        - assistant.response.plan.v1

    - from: event_journal
      to: chatterbox
      condition: "assistant.response.plan.can_speak == true"
      carries:
        - response text
        - answerability receipt id
        - tone/emotion tags
        - skill/source receipt ids

    - from: chatterbox
      to: event_journal
      carries:
        - chatterbox.voice_render.requested.v1
        - chatterbox.voice_render.blocked.v1
        - chatterbox.audio.finished.v1

    - from: event_journal
      to: shared_chat_ux
      carries:
        - full session timeline

    - from: chatterbox
      to: orb
      carries:
        - audio playback events
        - audio envelope/progress

    - from: orb
      to: event_journal
      carries:
        - orb.state.v1

    - from: realtime_stt
      to: event_journal
      condition: "speech during Embry playback"
      carries:
        - interruption candidate transcript

    - from: event_journal
      to: replay_runner
      carries:
        - session events
        - artifact references

    - from: event_journal
      to: verdict_engine
      carries:
        - all events and receipts

  hard_gates:
    - id: no_mock_live_proof
      rule: "Live proof requires mocked=false and live=true on relevant events"

    - id: memory_before_speech
      rule: "memory.answerability.v1 must exist before chatterbox.audio.finished.v1"

    - id: no_unanswerable_speech
      rule: "If answerability.block_before_speech=true, no finished_response_audio may exist"

    - id: tau_only_skills
      rule: "Every skill.call.receipt.v1 must reference prior tau.agent_handoff.v1"

    - id: skill_receipt_before_speech
      rule: "Skill-backed responses require skill.call.receipt.v1 before Chatterbox render"

    - id: brave_sources_before_speech
      rule: "Brave Search responses require brave_search.source_receipt.v1 before speech"

    - id: ux_not_authority
      rule: "chat.render.receipt.v1 can prove rendering coverage only, not voice correctness"

    - id: orb_audio_driven
      rule: "orb.state.v1 must reference actual playback event or audio envelope"

    - id: replay_not_live
      rule: "Replay runs must be labeled replay and cannot count as new live ingress proof"

  first_five_steps:
    - step: 1
      name: "Migrate matrix to embry.stress_case.v1"
      owner: tau
      pass_gates:
        - "200 cases loaded"
        - "route family and difficulty preserved"
        - "oracle present for pass/fail cases"
      fail_gates:
        - "missing oracle"
        - "status upgraded without receipt"

    - step: 2
      name: "Implement canonical event journal"
      owner: tau
      pass_gates:
        - "events.ndjson produced"
        - "monotonic sequence"
        - "journal hash in receipt"
      fail_gates:
        - "DOM-only evidence"
        - "console-only evidence"

    - step: 3
      name: "Preserve Chatterbox answerability block"
      owner: chatterbox
      pass_gates:
        - "12 block cases pass"
        - "no finished_response_audio when block_before_speech=true"
        - "positive answerable control still speaks"
      fail_gates:
        - "blocked case produces audio"
        - "Chatterbox overrides answerability"

    - step: 4
      name: "Memory answerability receipts"
      owner: memory
      pass_gates:
        - "SPARTA answers use SPARTA/QRA records"
        - "persona answers use scoped persona records"
        - "memory misses clarify/no_answer/block"
      fail_gates:
        - "unrelated record in records_used"
        - "confident answer on memory miss"

    - step: 5
      name: "Tau handoff and skill receipts"
      owner: tau_and_agent_skills
      pass_gates:
        - "tau.agent_handoff.v1 exists"
        - "work_order_id exists"
        - "dag receipt exists"
        - "skill.call.receipt.v1 exists before speech"
      fail_gates:
        - "UI direct skill call"
        - "Chatterbox direct skill call"
        - "speech before skill receipt"

<<<WEBGPT_DONE:20260708T010609Z:fa15614e>>>
