0. Source baseline and priority call

Use docs/EMBRY_STRESS_SESSION_MATRIX.json as the row authority: 300 sessions, 210 passed, 90 failed, 0 not_run. The highest-value failing route families are:

realtimestt.factory_capture: 20/20 failed

chatterbox.turn_control: 20/20 failed in matrix, despite separate narrow live interruption/chatterbox audits passing

tau.skill.embry_voice_control: 19/20 failed

ux-lab.shared_chat: 16/20 failed

memory.intent.voice_delivery: 15/20 failed

The goal coverage audit still says the system is not ready. Treat passing narrow audits as component evidence, not full-loop success.

Priority call: fix Tau skill/DAG receipts first, then Chat UX turn lineage, then RealtimeSTT browser/device ingress. Between Chat UX lineage and RealtimeSTT ingress, Chat UX turn lineage comes first because it is a deterministic service/journal boundary. Without assistant.response.plan.v1 -> chat.render.receipt.v1 turn lineage, a successful STT run still cannot prove that voice and chat are rendering the same turn. RealtimeSTT browser/device ingress is important, but current evidence shows it is device-sensitive and will waste cycles unless the downstream journal/render contract is already checkable.

Global invariant for every slice: no flat tests. Every stress case must validate conversation_arc, steering_strategy, interruption_strategy, memory_intent tone selection, and inline emotion tags before it can update a matrix row to passed.

1. Tau skill handoff, DAG, and skill-call receipt slice
Subsystem boundary

memory/Tau routing -> Tau skill gateway -> agent-skills -> Tau response plan -> Chatterbox permission gate

This slice fixes the concrete failure class: skill_call_receipt_not_emitted, tau_agent_handoff_not_exercised, and tau_dag_receipt_not_created.

Required endpoint / receipt schema

Required events or receipts:

YAML
tau.agent_handoff.v1:
  session_id: string
  turn_id: string
  route: string
  required_skill: string
  work_order_id: string
  dag_id: string
  parent_answerability_receipt_id: string
  caller: tau
  live: true
  mocked: false

tau.dag_receipt.v1:
  session_id: string
  turn_id: string
  dag_id: string
  work_order_id: string
  nodes:
    - node_id: string
      skill: string
      status: success|failed|blocked
  artifact_hashes: [string]
  live: true
  mocked: false

skill.call_receipt.v1:
  session_id: string
  turn_id: string
  work_order_id: string
  dag_id: string
  skill_name: string
  caller: tau.skill_gateway
  ui_direct_call: false
  chatterbox_direct_call: false
  input_hash: string
  output_hash: string
  status: success|failed|blocked
  live: true
  mocked: false

Required service action: add or harden Tau-owned route execution behind a command equivalent to:

Bash
python scripts/run_embry_stress_matrix.py \
  --route tau.skill.embry_voice_control \
  --live \
  --require-receipts tau.agent_handoff.v1,tau.dag_receipt.v1,skill.call_receipt.v1
Pass/fail gates

Pass only if:

memory.answerability.v1 exists before Tau route decision.

tau.agent_handoff.v1 exists before any skill execution.

tau.dag_receipt.v1 exists and references the same work_order_id.

skill.call_receipt.v1 exists and references the same turn_id, work_order_id, and dag_id.

Caller is Tau, not UI and not Chatterbox.

assistant.response.plan.v1 references the skill receipt.

Chatterbox does not speak until the skill receipt and answerability receipt both permit speech.

The conversation envelope includes arc, steering, interruption policy, memory-selected tone, and inline emotion tags.

Fail if:

Skill preflight succeeds but no Tau handoff is emitted.

“Tau doctor ran” is the only proof.

Any skill call is launched from UI or Chatterbox.

Chatterbox speaks before skill receipt completion.

A neutral/flat spoken response is accepted.

Matrix update

Re-run all 20 tau.skill.embry_voice_control rows.

Expected update if gates pass: flip the 19 failed rows to passed and remove:

tau_agent_handoff_not_exercised

skill_call_receipt_not_emitted

tau_dag_receipt_not_created

Do not alter unrelated Tau rows already marked passed unless they are re-run with the same receipt schema.

Must not claim

Do not claim full memory/Tau routing is complete. This proves direct voice-control skill orchestration receipts only. It does not prove RealtimeSTT ingress, Chat UX sync, orb sync, replay, or subjective Chatterbox quality.

2. Shared Chat UX turn lineage and entity-underlines slice
Subsystem boundary

assistant.response.plan.v1 -> shared Chat UX renderer -> chat.render.receipt.v1 -> extract-entities receipt -> entity underline receipt -> Chatterbox audio link

This is not dashboard work. It is the proof boundary that voice and chat share the same turn.

Required endpoint / receipt schema

Required events:

YAML
assistant.response.plan.v1:
  session_id: string
  turn_id: string
  response_plan_id: string
  answerability_receipt_id: string
  memory_reasoning_trace_id: string
  memory_intent_receipt_id: string
  tone: string
  inline_emotion_tags: [string]
  spoken_text: string
  chat_text: string
  audio_expected: boolean
  skill_receipt_ids: [string]
  source_receipt_ids: [string]

extract_entities.receipt.v1:
  session_id: string
  turn_id: string
  response_plan_id: string
  entities:
    - text: string
      type: string
      span_start: integer
      span_end: integer
      source: extract-entities
  live: true
  mocked: false

chat.render.receipt.v1:
  session_id: string
  turn_id: string
  response_plan_id: string
  rendered_message_id: string
  rendered_audio_artifact_ids: [string]
  memory_trace_dropdown_rendered: true
  entity_underlines_rendered: true
  extract_entities_receipt_id: string
  turn_id_matches_response_plan: true
  rendered_from_event_journal: true
  screenshot_path: string|null
  live: true
  mocked: false

Required browser/service action:

Bash
python scripts/run_embry_chat_ux_lineage.py \
  --live \
  --case-ids chat_ux_sync-simple-03,chat_ux_sync-simple-04,chat_ux_sync-medium-03,chat_ux_sync-medium-04 \
  --require-audio \
  --require-entity-underlines \
  --emit-chat-render-receipt

The browser may inspect DOM attributes, but the pass/fail verdict must come from the emitted receipt and event journal.

Pass/fail gates

Pass only if:

assistant.response.plan.v1 exists.

chat.render.receipt.v1 exists.

chat.render.receipt.v1.turn_id == assistant.response.plan.v1.turn_id.

Assistant message, Chatterbox audio element, memory trace dropdown, and entity underlines all carry the same turn_id.

extract_entities.receipt.v1 exists and is linked to the underline receipt.

Chatterbox audio artifact ID in Chat UX matches the response plan or Chatterbox render event.

The visible spoken transcript includes inline emotion tags or explicitly rendered delivery metadata.

Screenshot is attached as supporting evidence only, not the proof source.

Fail if:

Text and audio appear in the browser but have no common turn_id.

Entity underlines are inferred from visible text without an extract_entities receipt.

A screenshot marker is used as the proof authority.

Chat UX uses a separate local truth model instead of the event journal.

Matrix update

Re-run all 20 ux-lab.shared_chat rows.

Expected first update:

Flip the 2 lineage rows once assistant_response_plan_v1_not_linked, chat_render_receipt_v1_not_emitted, and chat_turn_id_matches_response_plan_not_proven are cleared.

Flip the 2 entity rows once extract_entities_receipt_not_linked, entity_underline_render_receipt_not_emitted, and spoken_transcript_entity_underlines_not_proven are cleared.

Implement runner route for advanced/adversarial/soak rows; those 12 must become real pass/fail, not “route missing.”

Must not claim

Do not claim Chat UX proves the service loop. It proves rendering lineage from the event journal. It does not prove RealtimeSTT capture, speaker identity correctness, memory answer correctness, or Chatterbox speech quality.

3. Memory intent voice-delivery and conversation-envelope slice
Subsystem boundary

memory /intent -> memory_intent_voice_delivery_receipt -> Tau response plan -> Chatterbox voice render

This slice enforces the human’s invariant that no tests are flat or neutral.

Required endpoint / receipt schema

Required memory endpoint behavior: /intent or equivalent must return a structured delivery envelope, not only memory_confident.

YAML
memory_intent.voice_delivery_receipt.v1:
  session_id: string
  turn_id: string
  prompt_class: hostile|discouraged|overlap|normal|compliance|skill_wait
  conversation_arc: string
  steering_strategy: string
  interruption_strategy:
    required: true
    default_policy: string
    unknown_or_ambiguous_speaker_policy: string
  selected_tone: firm_boundary|deflect_calm|playful_light|careful_concerned|neutral_warm|relieved|one_at_a_time_interrupt|calm_precise
  inline_emotion_tags:
    - string
  pause_strategy: string
  memory_intent_source: memory
  flat_neutral_allowed: false
  live: true
  mocked: false

Required command:

Bash
python scripts/run_embry_stress_matrix.py \
  --route memory.intent.voice_delivery \
  --live \
  --require-conversation-envelope \
  --fail-on-generic-tone
Pass/fail gates

Pass only if:

Hostile inputs do not collapse to generic memory_confident; they produce firm, deflecting, or playful boundary tone.

Discouraged inputs produce gentle/supportive tone such as careful-concerned, neutral-warm, or relieved.

Overlap inputs produce one-at-a-time or firm-boundary interruption tone.

Every spoken response contains inline emotion tags.

assistant.response.plan.v1 carries the memory-selected tone unchanged into Chatterbox.

Chatterbox may render tone; it may not invent or override the reasoning-layer tone.

Fail if:

selected_tone=memory_confident is returned for a hostile, discouraged, or overlap prompt.

inline_emotion_tags is empty.

conversation_arc, steering_strategy, or interruption_strategy is missing.

The test is passed as neutral/flat.

Matrix update

Re-run all 20 memory.intent.voice_delivery rows.

Expected update if gates pass: flip the 15 failed rows and clear:

voice_delivery_tone_expected_deflect_calm_or_firm_boundary_or_playful_light

voice_delivery_tone_expected_calm_precise_or_careful_concerned_or_neutral_warm_or_relieved

voice_delivery_tone_expected_firm_boundary_or_one_at_a_time_interrupt

Must not claim

Do not claim Chatterbox personality quality is solved. This proves structured memory intent and delivery metadata, not subjective voice quality.

4. RealtimeSTT browser/device and factory-capture ingress slice
Subsystem boundary

browser getUserMedia / PipeWire / physical mic -> RealtimeSTT listener -> VAD/final transcript -> source identity receipt -> matrix runner

This comes after Chat UX lineage because it is hardware-sensitive and should feed a stable downstream event contract.

Required endpoint / receipt schema

Required receipt:

YAML
realtimestt.ingress_receipt.v1:
  session_id: string
  turn_id: string
  case_id: string
  transport: browser_getusermedia|pipewire_monitor_loopback|pipewire_physical_microphone
  device_label_hash: string
  device_id_hash: string
  capture_backend: string
  captured_audio_path: string
  captured_audio_sha256: string
  captured_audio_rms: number
  non_silent_frame_ratio: number
  sample_rate: integer
  duration_ms: integer
  vad_started: boolean
  vad_ended: boolean
  asr_final_transcript: string
  asr_final_transcript_present: boolean
  listener_events_path: string
  source_identity_proven: boolean
  live: true
  mocked: false

Required live action:

Bash
python scripts/run_realtimestt_ingress_matrix.py \
  --live \
  --route realtimestt.factory_capture \
  --transports browser_getusermedia,pipewire_monitor_loopback,pipewire_physical_microphone \
  --nonce-phrase \
  --emit-ingress-receipt

Browser action for the browser leg:

Open the voice test page.

Select the target input device.

Record a nonce phrase spoken or played live.

Send captured PCM/WAV to RealtimeSTT.

Wait for final transcript.

Save audio hash, listener event log, and transcript.

Pass/fail gates

Pass only if:

live=true, mocked=false.

Captured audio file exists and has nonzero RMS above the configured threshold.

RealtimeSTT emits VAD and final transcript.

Final transcript is non-empty and contains the nonce or expected semantic phrase.

Device/source identity is recorded.

Browser failures remain failures; do not silently switch to PipeWire and call the browser row passed.

Factory rows with runner_route_not_implemented are converted into real measured pass/fail runs.

Fail if:

Captured RMS is zero or near-zero.

Final transcript is empty.

Device identity is absent.

A static WAV fixture is used as live proof.

A screenshot or UI waveform is used as proof.

Browser capture fails but the row is marked passed using a different transport.

Matrix update

Re-run all 20 realtimestt.factory_capture rows.

Expected update:

Clear runner_route_not_implemented by implementing the route.

Pass rows only for the device/transport combinations that actually produce audio plus transcript.

Preserve device-specific failures such as empty browser/Jabra transcripts as failed, with receipt-backed diagnostics.

Must not claim

Do not claim general browser microphone readiness from one passing device. Do not claim physical speaker identity or diarization from ASR transcript alone. This slice proves ingress quality only.

5. Speaker source-audio identity and physical speaker-to-mic gate slice
Subsystem boundary

captured audio segment -> speaker identity/diarization -> memory speaker resolve -> personal-memory gate

The matrix speaker rows are currently passed, but the audit is still partial because source audio identity and physical speaker-to-mic identity gating are not fully proven.

Required endpoint / receipt schema

Required receipt:

YAML
speaker.identity_source_audio_receipt.v1:
  session_id: string
  turn_id: string
  captured_audio_sha256: string
  captured_audio_path: string
  transport: browser_getusermedia|pipewire_physical_microphone|pipewire_monitor_loopback
  enrollment_profile_id: string
  enrollment_independent_from_candidate: true
  candidate_speaker_label: horus|unknown|female_distractor|ambiguous|overlap
  speaker_status: known|unknown|ambiguous
  speaker_id: string|null
  confidence: number
  overlap_detected: boolean
  primary_speaker: true|false|null
  source_audio_identity_proven: true
  physical_speaker_to_microphone_identity_proven: true|false
  personal_memory_allowed: boolean
  memory_query_allowed_namespaces: [string]
  live: true
  mocked: false

Required live action:

Bash
python scripts/run_speaker_identity_source_audio.py \
  --live \
  --cases known_horus,unknown_speaker,ambiguous_low_confidence,female_distractor,overlap \
  --require-independent-enrollment \
  --emit-source-audio-receipt
Pass/fail gates

Pass only if:

Known Horus uses captured source audio and independent enrollment.

Known Horus resolves to speaker_id=horus_lupercal.

Unknown speaker fails closed and gets no personal memory.

Ambiguous speaker fails closed.

Female distractor does not become authoritative.

Overlap produces one-at-a-time or ambiguous policy and disables personal memory.

Every memory query references the speaker gate event that authorized it.

Physical speaker-to-mic proof is explicitly true for rows claiming physical identity.

Fail if:

Enrollment audio is identical to candidate audio.

source_audio_identity_proven=false.

Personal memory is queried after unknown, ambiguous, or overlap gate.

Policy-only /speaker/resolve rows are used to claim raw audio identity.

Matrix update

Do not blindly flip existing memory.speaker.resolve rows; they are already 20/20 passed as policy rows. Add source-audio identity fields to their receipts or create a matrix substatus:

policy_gate_passed=true

source_audio_identity_proven=true|false

physical_identity_gate_proven=true|false

Only update the audit from partial to ready after the source-audio and physical-gate receipts exist.

Must not claim

Do not claim production diarization robustness, generalized speaker enrollment, or browser microphone reliability. This proves speaker identity gating for the tested live source-audio cases only.

6. Interruption, Chatterbox, orb, and replay matrix-link slice
Subsystem boundary

Tau response plan -> Chatterbox audio -> playback telemetry -> interruption manager -> orb state -> replay runner -> matrix receipt

Current evidence has passing narrow live audits for interruption, Chatterbox speech, replay audio, and orb slices. The matrix still has chatterbox.turn_control failures because those proofs are not linked into the 20 turn-control rows with the required receipts.

Required endpoint / receipt schema

Required receipts:

YAML
interruption.receipt.v1:
  session_id: string
  old_turn_id: string
  new_turn_id: string
  playback_event_id: string
  speaker_gate_event_id: string
  interruption_detected: true
  new_turn_wins: true
  stale_audio_stream_bytes_after_cancel: 0
  non_primary_rejected: boolean
  natural_stop_phrase_observed: boolean
  live: true
  mocked: false

audio.playback_orb_receipt.v1:
  session_id: string
  turn_id: string
  audio_artifact_id: string
  audio_artifact_sha256: string
  playback_started: true
  playback_progress_events: integer
  playback_ended_or_cancelled: true
  orb_samples_count: integer
  orb_max_level: number
  orb_state_references_playback_event: true
  live: true
  mocked: false

replay.receipt.v1:
  session_id: string
  source_journal_sha256: string
  artifact_hashes_verified: true
  replay_turn_order_matches_journal: true
  replay_audio_playback_started: true
  memory_trace_replayed: true
  orb_state_replayed: true
  interruption_events_replayed: true
  live: false
  mocked: false
  replay_of_live_session: true

Required live action:

Bash
python scripts/run_turn_control_matrix_link.py \
  --live \
  --route chatterbox.turn_control \
  --cases all \
  --require-interruption-receipt \
  --require-orb-playback-receipt \
  --require-replay-receipt

Browser action:

Start a Chatterbox response from a Tau response plan.

Begin real playback.

Trigger Horus interruption and non-primary interruption cases.

Verify playback cancel or rejection.

Record orb samples from playback telemetry.

Replay the resulting session journal.

Pass/fail gates

Pass only if:

interruption.detected is emitted for Horus barge-in cases.

New Horus turn wins and stale old-turn bytes after cancel are measured.

Non-primary speaker interruption is rejected and does not unlock memory.

Tau tool-wait case emits a natural stop or holding phrase.

Orb state references actual playback event or audio envelope.

Replay uses the real journal and verifies artifact hashes.

All receipt turn IDs line up with the original response plan.

Fail if:

Chatterbox cancel endpoints are called but no interruption receipt is emitted.

Old audio may still stream after cancel and bytes are not measured.

Orb state is timer-driven or DOM-only.

Replay uses a static transcript instead of the event journal.

Narrow passing audit files are copied into matrix rows without re-running or linking the exact case IDs.

Matrix update

Re-run all 20 chatterbox.turn_control rows.

Expected update if gates pass: clear the matrix failures for:

interruption_detected_receipt_not_emitted

new_horus_turn_not_exercised

new_turn_wins_receipt_not_emitted

blessed_qra_cached_response_not_exercised

stale_audio_stream_bytes_not_measured

non_primary_interrupt_rejection_not_exercised

speaker_gate_receipt_not_linked_to_turn_control

natural_stop_phrase_not_observed

tau_tool_wait_not_exercised

Also attach orb/replay receipts to the relevant Chat UX or turn-control rows, but do not inflate pass counts with standalone “orb looks good” screenshots.

Must not claim

Do not claim full live voice/chat loop. This slice proves turn-control, orb, and replay linkage for tested Chatterbox-led sessions. It does not prove browser/device RealtimeSTT ingress or physical speaker identity unless those receipts are part of the same session.

7. Combined voice+chat representative sweep slice
Subsystem boundary

RealtimeSTT ingress -> speaker identity -> memory answerability + memory intent -> Tau route/skill/search -> response plan -> Chatterbox -> shared Chat UX -> orb -> interruption -> replay -> matrix receipt

This is the first slice allowed to approach full-loop language, but only for the selected representative cases.

Required endpoint / receipt schema

One top-level receipt:

YAML
embry.full_loop_stress_receipt.v1:
  session_id: string
  case_id: string
  route: string
  difficulty: string
  live: true
  mocked: false
  event_journal_path: string
  event_journal_sha256: string

  ingress_receipt_id: string
  speaker_identity_receipt_id: string
  answerability_receipt_id: string
  memory_intent_voice_delivery_receipt_id: string
  tau_route_receipt_id: string
  skill_call_receipt_ids: [string]
  brave_source_receipt_ids: [string]
  assistant_response_plan_id: string
  chatterbox_audio_receipt_id: string
  chat_render_receipt_id: string
  orb_receipt_id: string
  interruption_receipt_id: string|null
  replay_receipt_id: string

  conversation_contract:
    conversation_arc_present: true
    steering_strategy_present: true
    interruption_strategy_present: true
    memory_tone_selected: true
    inline_emotion_tags_present: true
    flat_neutral_allowed: false

  verdict:
    result: pass|fail
    failed_gates: [string]

Required command:

Bash
python scripts/run_embry_full_loop_representative_sweep.py \
  --live \
  --cases \
    sparta_qra_compliance-simple-01,\
    persona_memory_recall-simple-01,\
    persona_memory_miss-simple-01,\
    brave_research-simple-01,\
    voice_control_skill-simple-02,\
    chat_ux_sync-simple-03,\
    factory_noise-simple-01,\
    speaker_identity-simple-01,\
    interruption-simple-01 \
  --require-voice-and-chat \
  --require-replay \
  --require-conversation-contract
Pass/fail gates

Pass only if:

Real ingress receipt exists for voice cases.

Speaker identity gate exists before personal memory.

Memory answerability exists before Tau response plan.

Memory intent selects tone and inline emotion tags.

Tau emits skill/source receipts before speaking when tools or search are used.

Chatterbox refuses blocked answers and renders only speakable response plans.

Chat UX render receipt references the same turn_id and audio artifact as Chatterbox.

Orb follows playback telemetry.

Interruption receipt exists for interruption cases.

Replay reconstructs the same event journal and artifacts.

Fail if:

Any component uses mock transcript for live proof.

Any row uses browser screenshot alone.

UI or Chatterbox bypasses Tau.

Any receipt has mismatched turn_id.

Conversation contract is missing or flat/neutral.

Replay does not verify artifact hashes.

Matrix update

Do not run this against all 300 immediately. Start with one representative row from each major route family and update only those rows after pass/fail receipts are written.

After the representative sweep passes, expand to:

all failed tau.skill.embry_voice_control rows,

all failed ux-lab.shared_chat rows,

all failed realtimestt.factory_capture rows,

all failed chatterbox.turn_control rows,

all failed memory.intent.voice_delivery rows.

Must not claim

Do not claim the system is complete. A representative full-loop sweep proves only the selected cases under the tested devices, speakers, skills, and routes.

Immediate implementation order

Implement Tau handoff/DAG/skill receipts for tau.skill.embry_voice_control.

Implement Chat UX response-plan-to-render lineage and extract-entities underline receipts.

Enforce memory intent delivery envelope across all conversation tests.

Implement current RealtimeSTT ingress runner for browser/device/factory rows.

Add source-audio and physical speaker-to-mic identity receipts.

Link existing interruption/Chatterbox/orb/replay narrow proofs into matrix-run receipts.

Run a small full-loop representative sweep, then expand across the remaining failed rows.

Do not spend the next cycle on visual dashboard work. The next useful code is receipt and runner code that changes failed gates in the 300-session matrix.
