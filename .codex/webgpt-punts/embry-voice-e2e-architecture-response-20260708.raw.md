Architecture verdict:
The current matrix pass count is not a voice E2E truth signal. Treat the current 300 sessions / 255 passed / 45 failed as legacy component status, not Embry voice/chat readiness. SPARTA QRA answerability rows are useful pre-voice evidence, but they explicitly do not prove browser/chat sync, spoken multiturn conversation, Chatterbox playback from live STT, or human-audible voice behavior.

The next proof must not be browser UI, screenshots, pyannote, or matrix bookkeeping. The next smallest rung that advances live voice E2E is:

OS audio graph / loopback capture
-> RealtimeSTT external-audio feed
-> transcript event with nonce
-> source-audio receipt

Use PipeWire/Pulse null-sink monitor capture and RealtimeSTT use_microphone=False external-audio mode first. Browser WebRTC, physical room mic, and pyannote overlap can come later. The Jabra source-62 receipt is a blocker, not a success: it captured non-silent audio, but ok=false, live=false, ASR returned the wrong phrase, and speaker/memory gates failed.

Numbered model:

Stress matrix and scoring layer — implemented but misleading

Current evidence says the matrix has 300 rows and many passes, but many are text/memory preflight passes. This layer must split status into:

legacy_component_status
voice_e2e_status
proof_level
failed_e2e_gates

A row may keep legacy_component_status=passed while voice_e2e_status=not_proven.

Audio graph capture authority — partial / next required proof

Boundary:

OS playback or generated test audio
-> PipeWire/Pulse null sink
-> monitor capture
-> captured PCM/WAV artifact

This avoids Chrome autoplay, room distortion, and browser input instability. It is live service proof when the audio is generated or played during the run with a nonce and captured through the OS audio graph. It is not physical microphone proof.

RealtimeSTT listener companion — failing for current physical mic path

RealtimeSTT must consume external audio with use_microphone=False, using 16-bit mono PCM at 16 kHz or passing original sample rate for resampling. It emits VAD, partial, and final transcript events. It does not authorize speaker identity or memory.

Current blocker: source-62/Jabra physical mic produced "Thank you very much." instead of "Horus/factory stress speech".

Speaker identity / diarization gate — partial and currently failing for source-62

Speaker policy rows may pass, but the source-62 captured waveform did not resemble Horus enrollment: horus_segment_count=0, horus_ratio=0.0, and primary margin failed. Speaker identity must be proven from source audio and independent enrollment, not labels.

Do not block Rung 1 on pyannote. Fix pyannote/torch/torchvision/HF token export later as the diarization environment rung.

Memory-first answerability and intent — partial

Memory owns identity scope, recall, answerability, and /intent tone. Every conversation test must include:

conversation arc
steering strategy
interruption strategy
memory-selected tone
inline emotion tags
final spoken text JSON schema
pause policy

Flat or neutral tests are invalid.

Tau routing and skill authority — partial / failing around receipts

Tau owns route decisions, tool use, work orders, DAG receipts, and skill-call authorization. Chatterbox and UI must not call skills directly.

Current known failure: missing skill_call_receipt, tau.agent_handoff.v1, and Tau DAG receipt.

Chatterbox renderer — implemented partial

Chatterbox has /tau/voice-render and can block block_before_speech. That is useful but downstream only. It does not prove live STT ingress, speaker identity, memory correctness, Chat UX sync, orb sync, replay, or interruption.

Audio-output authority playback — partial

Chatterbox audio artifacts must be played through an auditable output path. Playback receipts must prove actual start/progress/end/cancel. Chrome browser playback is not the first proof authority because autoplay policy can stop or block sound.

Shared Chat UX — failing / not proof authority

Chat UX must render the same event journal as the voice loop. It must prove turn lineage:

assistant.response.plan.v1
-> chat.render.receipt.v1
-> extract_entities.receipt.v1
-> entity underline receipt
-> Chatterbox audio artifact link

Screenshots are supporting evidence only.

Orb envelope subscriber — partial narrow proof only

Orb state must subscribe to actual Chatterbox playback envelope/progress. Timer-driven or DOM-only orb animation is not proof.

Replay — partial narrow proof only

Replay must reconstruct the actual session journal with text, audio artifacts, memory reasoning, tone tags, interruption events, and orb samples. Replay is not new live ingress proof.

Interruption / barge-in — partial narrow proof only

Must test:

primary Horus barge-in
non-primary suppression
two non-Embry speakers overlap
humorous one-at-a-time boundary
stale audio skipped
natural stops rather than robotic instant cutoffs

This comes after clean ingress, speaker gate, and playback authority are proven.

Proof ladder:

Rung 1 — OS audio graph to RealtimeSTT external-audio ingress

Purpose:
Prove a clean, non-browser live audio path into RealtimeSTT before touching UI.

Boundary:

PipeWire/Pulse null sink monitor
-> captured PCM/WAV
-> RealtimeSTT feed_audio / external audio mode
-> realtime_stt.final.v1

Required proof action:

Bash
python scripts/rung1_audio_graph_realtimestt.py \
  --transport pipewire_null_sink_monitor \
  --use-microphone false \
  --nonce \
  --expected "Horus factory stress speech <nonce>" \
  --out /tmp/embry-rung1-audio-graph

Pass gates:

live=true
mocked=false
capture_kind=os_audio_graph_loopback
browser_used_as_proof=false
captured_audio_sha256 present
captured_rms above threshold
non_silent_frame_ratio above threshold
RealtimeSTT command exits 0
VAD start/end events present
ASR final transcript present
ASR transcript contains nonce or passes configured WER threshold
events.ndjson and receipt.json produced

Fail gates:

static transcript injected
browser screenshot used as proof
captured audio silent
ASR transcript empty
ASR transcript wrong phrase
fallback to browser or physical mic without marking row failed

Must not claim:
Does not prove physical microphone, speaker identity, memory, Chatterbox, Chat UX, orb, replay, or interruption.

Rung 2 — Source-audio speaker gate on clean captured audio

Purpose:
Prove Horus source-audio identity from independent enrollment after clean STT ingress works.

Boundary:

captured clean audio
-> speaker verifier / source window scorer
-> memory speaker gate
-> personal memory allow/deny decision

Required proof action:

Bash
python scripts/rung2_source_audio_speaker_gate.py \
  --input /tmp/embry-rung1-audio-graph/captured.wav \
  --enrollment horus_independent_enrollment_set \
  --cases known_horus,unknown,distractor,ambiguous \
  --out /tmp/embry-rung2-speaker-gate

Pass gates:

enrollment_independent_from_candidate=true
known Horus resolves speaker_id=horus_lupercal
known Horus personal_memory_allowed=true
unknown speaker personal_memory_allowed=false
distractor personal_memory_allowed=false
ambiguous personal_memory_allowed=false
speaker gate event precedes any personal memory query
source_audio_identity_proven=true

Fail gates:

candidate audio reused as enrollment
speaker label assumed from test case
personal memory queried for unknown/ambiguous/distractor
source-62 style horus_ratio=0.0 accepted as pass

Must not claim:
Does not prove pyannote overlap, physical speaker-to-room-mic identity, browser mic, or live barge-in.

Rung 3 — Live audio transcript to memory/Tau turn decision

Purpose:
Replace text-only SPARTA QRA proof with voice-originated turn proof.

Boundary:

RealtimeSTT final transcript
-> speaker gate
-> memory /answer
-> memory /intent
-> Tau turn decision
-> assistant.response.plan.v1

Required proof action:

Bash
python scripts/rung3_voice_to_memory_tau.py \
  --from-rung1 /tmp/embry-rung1-audio-graph \
  --from-rung2 /tmp/embry-rung2-speaker-gate \
  --cases sparta_qra_compliance-simple-01,persona_memory_miss-simple-01,brave_search-simple-01 \
  --out /tmp/embry-rung3-voice-to-tau

Pass gates:

input_text_source=realtimestt.final.v1
no typed prompt substitution
speaker gate authorizes or blocks memory before memory query
memory.answerability.v1 emitted
memory_intent.voice_delivery_receipt.v1 emitted
conversation_arc present
steering_strategy present
interruption_strategy present
pause_policy present
memory-selected tone present
inline emotion tags present
Tau route decision emitted
assistant.response.plan.v1 emitted

Fail gates:

SPARTA answerability row passed from text-only input
memory answer produced without source speaker gate
generic flat tone accepted
inline emotion tags missing
Tau route decision missing

Must not claim:
Does not prove Chatterbox audio, audible playback, Chat UX, orb, replay, browser mic, or interruption.

Rung 4 — Chatterbox render and OS playback from live STT-derived response plan

Purpose:
Prove Embry speaks only after live audio ingress, speaker gate, memory/Tau answerability, and delivery envelope.

Boundary:

assistant.response.plan.v1
-> /tau/voice-render
-> Chatterbox audio artifact
-> OS playback receipt

Required proof action:

Bash
python scripts/rung4_voice_to_chatterbox_playback.py \
  --from-rung3 /tmp/embry-rung3-voice-to-tau \
  --require-os-playback \
  --out /tmp/embry-rung4-chatterbox-playback

Pass gates:

/tau/voice-render receives response_plan_id
answerability.can_speak=true before render
blocked cases produce no finished_response_audio
speakable cases produce Chatterbox audio artifact
audio artifact sha256 present
playback_started=true
playback_progress_events > 0
playback_ended_or_cancelled=true
spoken text matches final spoken text JSON schema
inline emotion tags carried into render request

Fail gates:

Chatterbox called directly with text outside Tau response plan
Chatterbox speaks blocked answer
audio artifact exists but no playback authority receipt
browser autoplay state used as proof

Must not claim:
Does not prove Chat UX sync, orb sync, browser playback, replay, or interruption.

Rung 5 — Shared Chat UX turn lineage from same event journal

Purpose:
Prove voice and chat are synchronized on the same turn, not separate UI state.

Boundary:

session event journal
-> assistant.response.plan.v1
-> Chatterbox artifact
-> shared Chat UX render
-> chat.render.receipt.v1
-> extract-entities underline receipt

Required proof action:

Bash
python scripts/rung5_chat_ux_lineage.py \
  --from-rung4 /tmp/embry-rung4-chatterbox-playback \
  --browser-user-gesture-required \
  --require-memory-trace-dropdown \
  --require-entity-underlines \
  --out /tmp/embry-rung5-chat-ux-lineage

Pass gates:

chat.render.receipt.v1 emitted
chat turn_id equals assistant.response.plan.v1 turn_id
rendered audio artifact id equals Chatterbox artifact id
memory reasoning trace dropdown linked to memory receipt
extract_entities.receipt.v1 linked
entity underline render receipt emitted
screenshot is supporting artifact only

Fail gates:

visible browser text with no turn_id lineage
DOM marker used as proof authority
entity underlines rendered without extract-entities receipt
audio element not linked to Chatterbox artifact

Must not claim:
Does not prove RealtimeSTT quality beyond the input session, speaker generalization, or browser microphone readiness.

Rung 6 — Orb envelope and replay from actual session journal

Purpose:
Prove orb and replay consume the same truth ledger as voice/chat.

Boundary:

Chatterbox playback events
-> audio envelope stream
-> orb.state.v1
-> session replay

Required proof action:

Bash
python scripts/rung6_orb_replay_from_journal.py \
  --from-rung5 /tmp/embry-rung5-chat-ux-lineage \
  --verify-artifact-hashes \
  --out /tmp/embry-rung6-orb-replay

Pass gates:

orb.state.v1 references playback event ids
orb samples correlate with playback progress/envelope
timer-only orb state absent
replay.receipt.v1 emitted
replay uses original event journal sha256
audio artifact hashes verified
turn order matches original journal
memory trace, tone tags, chat text, audio, and orb state replayed

Fail gates:

orb driven by fake speaking flag
replay uses static transcript
artifact hashes not verified
replay timeline differs from event journal

Must not claim:
Replay is not new live input proof. It proves reconstruction of an already captured session.

Rung 7 — Diarization environment and interruption / barge-in

Purpose:
Prove live turn control after clean ingress, identity, playback, and journal sync are stable.

Boundary:

Embry playback
-> concurrent listener
-> speaker/diarization gate
-> interruption decision
-> playback cancel or suppression
-> new turn or one-at-a-time boundary

Required proof action:

Bash
python scripts/rung7_interruption_barge_in.py \
  --from-rung6 /tmp/embry-rung6-orb-replay \
  --cases primary_horus_barge_in,non_primary_suppression,two_non_embry_overlap,stale_audio_skip,natural_stop \
  --require-pyannote-env-ok false \
  --out /tmp/embry-rung7-interruption

Before advanced overlap cases, fix the pyannote environment separately:

Bash
python scripts/check_diarization_env.py \
  --require-torchvision-compatible \
  --require-hf-token-exported \
  --out /tmp/embry-diarization-env

Pass gates:

primary Horus barge-in stops old audio
new Horus turn wins
non-primary speech does not unlock personal memory
two non-Embry speakers trigger humorous one-at-a-time boundary
stale audio bytes after cancel measured and skipped
natural stop phrase observed for non-emergency interruption
speaker gate receipt linked to interruption receipt

Fail gates:

instant robotic cutoff accepted for all cases
non-primary speaker unlocks personal memory
stale old-turn audio not measured
overlap accepted without diarization/source evidence
pyannote import failure ignored for pyannote-dependent cases

Must not claim:
Does not prove all acoustic environments or all browsers. It proves the tested interruption cases.

Receipts:

Use a common receipt envelope:

YAML
receipt_envelope.v1:
  receipt_id: string
  schema: string
  session_id: string
  turn_id: string|null
  case_id: string
  rung_id: string
  code_version: "2727b223fb4ab57f146fd33ab48b415d0f373911"
  config_hash: string
  generated_at_utc: string
  live: boolean
  mocked: boolean
  proof_class: live_voice_e2e|live_component|text_preflight|replay|mock_dev
  event_journal_path: string
  event_journal_sha256: string
  artifact_paths: [string]
  artifact_sha256: [string]
  failed_gates: [string]
  ok: boolean

Required boundary receipts:

YAML
audio_ingress_receipt.v1:
  capture_kind: os_audio_graph_loopback|physical_microphone|browser_webrtc
  transport: pipewire_null_sink_monitor|pulse_monitor|jabra_physical|browser_getusermedia
  browser_used_as_proof: boolean
  captured_audio_path: string
  captured_audio_sha256: string
  captured_rms: number
  non_silent_frame_ratio: number
  sample_rate: integer
  channels: integer
  duration_ms: integer
  nonce: string
  expected_phrase: string

realtimestt_receipt.v1:
  use_microphone: false
  feed_mode: external_audio
  pcm_format: s16le_mono_16khz|original_rate_with_resample
  vad_started: boolean
  vad_ended: boolean
  partial_count: integer
  final_transcript: string
  final_transcript_present: boolean
  transcript_matches_expected: boolean
  wer: number|null

speaker_identity_gate_receipt.v1:
  source_audio_sha256: string
  enrollment_profile_id: string
  enrollment_independent_from_candidate: boolean
  speaker_status: known|unknown|ambiguous|overlap
  speaker_id: string|null
  horus_ratio: number|null
  mean_primary_margin: number|null
  confidence: number
  primary_speaker: boolean
  personal_memory_allowed: boolean
  authorized_memory_namespaces: [string]

memory_tau_turn_receipt.v1:
  input_event_id: string
  input_text_source: realtime_stt.final.v1|chat_text
  speaker_gate_event_id: string
  memory_answerability_event_id: string
  memory_intent_event_id: string
  tau_route_decision_event_id: string
  tau_agent_handoff_event_id: string|null
  tau_dag_receipt_id: string|null
  skill_call_receipt_ids: [string]
  brave_source_receipt_ids: [string]
  assistant_response_plan_id: string
  can_speak: boolean
  block_before_speech: boolean

conversation_delivery_receipt.v1:
  conversation_arc: string
  steering_strategy: string
  interruption_strategy: string
  pause_policy: string
  memory_selected_tone: string
  inline_emotion_tags: [string]
  flat_neutral_allowed: false
  final_spoken_text:
    schema: embry.final_spoken_text.v1
    final_text: string
    tone: string
    inline_emotion_tags: [string]
    pause_policy: string
    interruption_policy: string
    citations_or_receipt_refs: [string]

chatterbox_playback_receipt.v1:
  response_plan_id: string
  voice_render_endpoint: /tau/voice-render
  answerability_receipt_id: string
  render_blocked: boolean
  audio_artifact_path: string|null
  audio_artifact_sha256: string|null
  playback_authority: os_audio|browser_after_user_gesture
  playback_started: boolean
  playback_progress_events: integer
  playback_ended_or_cancelled: boolean
  finished_response_audio: boolean

chat_sync_receipt.v1:
  response_plan_id: string
  chat_render_receipt_id: string
  turn_id_matches_response_plan: boolean
  rendered_audio_artifact_sha256: string
  memory_trace_dropdown_rendered: boolean
  extract_entities_receipt_id: string
  entity_underline_receipt_id: string
  rendered_from_event_journal: boolean
  screenshot_supporting_only: boolean

orb_envelope_receipt.v1:
  playback_event_id: string
  audio_artifact_sha256: string
  envelope_source: playback_progress|audio_amplitude
  orb_state_event_count: integer
  orb_references_playback_events: boolean
  fake_timer_state_detected: boolean

replay_receipt.v1:
  replay_of_live_session: boolean
  source_event_journal_sha256: string
  artifact_hashes_verified: boolean
  turn_order_matches_journal: boolean
  memory_trace_replayed: boolean
  chat_render_replayed: boolean
  audio_replayed: boolean
  orb_state_replayed: boolean
  interruption_events_replayed: boolean

interruption_receipt.v1:
  old_turn_id: string
  new_turn_id: string|null
  playback_event_id: string
  speaker_gate_event_id: string
  interruption_case: primary_horus|non_primary|two_non_embry_overlap|stale_audio|natural_stop
  interruption_detected: boolean
  old_audio_cancelled: boolean
  stale_audio_bytes_after_cancel: integer
  new_turn_wins: boolean
  personal_memory_unlocked: boolean
  natural_stop_phrase_observed: boolean

Stress session scoring:

Do not overwrite current matrix status. Add E2E-specific fields.

YAML
stress_session_scoring.v1:
  legacy_component_status: passed|failed|not_run
  voice_e2e_status: passed|failed|not_proven
  proof_level:
    0: no_receipt
    1: text_preflight_only
    2: audio_ingress_only
    3: voice_to_memory_tau
    4: voice_to_chatterbox_playback
    5: voice_chat_synced
    6: voice_chat_orb_replay_synced
    7: interruption_verified
  required_for_voice_e2e_pass:
    - audio_ingress_receipt.v1
    - realtimestt_receipt.v1
    - speaker_identity_gate_receipt.v1
    - memory_tau_turn_receipt.v1
    - conversation_delivery_receipt.v1
    - chatterbox_playback_receipt.v1
    - chat_sync_receipt.v1
    - orb_envelope_receipt.v1
    - replay_receipt.v1
  optional_by_case:
    - interruption_receipt.v1
    - skill_call_receipt.v1
    - brave_source_receipt.v1

Hard rule:

A text-only SPARTA QRA row may be legacy_component_status=passed and proof_level=1.
It must be voice_e2e_status=not_proven until the same question is spoken through RealtimeSTT, gated by speaker identity, routed through memory/Tau, rendered by Chatterbox, played, synced to Chat UX, orb-tracked, and replayed.

A voice E2E pass requires:

live=true
mocked=false
input_text_source=realtimestt.final.v1
no static transcript
no browser screenshot as proof authority
no UI or Chatterbox skill bypass
all required receipts linked by same session_id and turn_id
conversation delivery contract satisfied

Plan for converting the 300-session matrix into 200+ true voice/chat stress sessions:

Preserve all 300 rows, but relabel current pass/fail as legacy_component_status.

Add voice_e2e_status=not_proven to every row that lacks full boundary receipts.

Add proof_level to every row.

Keep SPARTA QRA, persona, Brave Search, and skill rows as preflight or route cases, but generate corresponding voice cases with nonce phrases and the same oracle.

Create at least 200 required voice/chat E2E cases by selecting:

40 SPARTA QRA compliance cases across simple/medium/advanced/adversarial/soak.

30 persona recall/miss cases.

30 Brave Search researched cases with source receipts.

40 Tau skill cases across create-figure, analytics, create-evidence-case, and sparta-validator.

20 voice idle hum / negative tone / de-escalation cases.

20 factory-floor noise cases.

20 browser mic/WebRTC cases.

20 replay/interruption cases.

Do not mask device failures. If browser WebRTC fails but PipeWire loopback passes, the browser row remains failed.

Do not promote replay to live ingress. Replay rows may pass replay proof only.

Every generated case must include conversation arc, steering, interruption strategy, memory-selected tone, inline emotion tags, final spoken text schema, and pause policy.

Recommendation order:

Fix audio graph / loopback first.

This is the smallest rung that advances live voice E2E. It avoids browser autoplay, Chrome media policy, room mic distortion, and Jabra device instability while still proving live service audio ingress into RealtimeSTT.

Then fix source-audio speaker gate.

The source-62 speaker evidence currently says the waveform does not match Horus. Do not proceed to personal memory E2E until clean source-audio identity is proven.

Then run voice-to-memory/Tau-to-Chatterbox playback.

This turns text-only SPARTA QRA success into actual spoken-turn proof.

Then Chat UX lineage.

Chat UX is important, but it should render the journal after a real voice turn exists. UI cannot be the first truth authority.

Then orb/replay.

Existing narrow orb/replay proofs are useful, but they must attach to the live voice session journal.

Then pyannote/diarization and interruption.

pyannote is currently blocked by torch/torchvision and unexported HF_TOKEN. Fix it before overlap-dependent claims, but do not block the first clean STT rung on it.

Browser WebRTC and physical room mic after loopback.

Browser and Jabra rows are important product tests, not first proof authority.

Endpoint contracts:

Listener endpoints
YAML
POST /listener/sessions:
  input:
    capture_kind: os_audio_graph_loopback|physical_microphone|browser_webrtc
    expected_phrase: string
    nonce: string
  fail_closed:
    - reject missing nonce for live proof
    - reject mocked transcript for live proof
  output:
    session_id: string

POST /listener/feed-audio:
  input:
    session_id: string
    audio_chunk_pcm: bytes
    sample_rate: integer
    channels: integer
    use_microphone: false
  fail_closed:
    - reject typed transcript
    - mark wrong format as failed, not passed
  emits:
    - audio_ingress_receipt.v1
    - realtimestt_receipt.v1

GET /listener/events/{session_id}:
  output:
    - realtime_stt.vad.started.v1
    - realtime_stt.vad.ended.v1
    - realtime_stt.partial.v1
    - realtime_stt.final.v1
Speaker identity endpoints
YAML
POST /speaker/enroll:
  input:
    speaker_id: string
    enrollment_audio_artifacts: [string]
  fail_closed:
    - reject candidate audio reused as enrollment
  output:
    enrollment_profile_id: string

POST /speaker/identify-window:
  input:
    session_id: string
    turn_id: string
    audio_artifact_sha256: string
    enrollment_profile_id: string
  fail_closed:
    - unknown/ambiguous disables personal memory
  emits:
    - speaker_identity_gate_receipt.v1

POST /speaker/gate-turn:
  input:
    speaker_identity_gate_receipt_id: string
  output:
    personal_memory_allowed: boolean
    authorized_namespaces: [string]
Memory/Tau routing endpoints
YAML
POST /memory/answer:
  input:
    transcript_event_id: string
    speaker_gate_receipt_id: string
  fail_closed:
    - no speaker gate means no personal memory
    - unrelated evidence means block_before_speech
  emits:
    - memory.answerability.v1

POST /memory/intent:
  input:
    transcript_event_id: string
    answerability_receipt_id: string
    conversation_context: object
  fail_closed:
    - missing tone blocks speech
    - missing inline emotion tags blocks speech
    - flat_neutral_allowed=false for all stress cases
  emits:
    - memory_intent.voice_delivery_receipt.v1

POST /tau/turn-decision:
  input:
    answerability_receipt_id: string
    memory_intent_receipt_id: string
  fail_closed:
    - no answerability means no response plan
    - skill route requires handoff and DAG
  emits:
    - tau.route_decision.v1
    - assistant.response.plan.v1

POST /tau/skill-handoff:
  input:
    route_decision_id: string
    required_skill: string
  fail_closed:
    - UI caller rejected
    - Chatterbox caller rejected
  emits:
    - tau.agent_handoff.v1
    - tau.dag_receipt.v1
    - skill_call_receipt.v1
Chatterbox speak endpoints
YAML
POST /tau/voice-render:
  input:
    response_plan_id: string
    answerability_receipt_id: string
    memory_intent_receipt_id: string
    skill_call_receipt_ids: [string]
    brave_source_receipt_ids: [string]
  fail_closed:
    - block_before_speech=true returns no finished_response_audio
    - missing response_plan_id returns blocked
    - missing required skill/source receipt returns blocked
  emits:
    - chatterbox_playback_receipt.v1

POST /audio/playback/start:
  input:
    audio_artifact_sha256: string
    session_id: string
    turn_id: string
  emits:
    - audio.playback.started.v1
    - audio.playback.progress.v1
    - audio.playback.ended.v1
Chat UX endpoints
YAML
POST /chat/render-from-journal:
  input:
    session_id: string
    event_journal_sha256: string
  fail_closed:
    - no journal means no render pass
    - no turn_id lineage means failed render receipt
  emits:
    - chat_sync_receipt.v1
Orb/envelope endpoints
YAML
GET /orb/envelope/subscribe:
  input:
    session_id: string
    playback_event_id: string
  fail_closed:
    - no playback event means no orb state
    - timer-only state marked failed
  emits:
    - orb_envelope_receipt.v1
Session replay endpoints
YAML
POST /sessions/{session_id}/replay:
  input:
    event_journal_sha256: string
    verify_artifact_hashes: true
  fail_closed:
    - missing artifact hash fails replay
    - replay cannot count as live ingress
  emits:
    - replay_receipt.v1
Interruption endpoints
YAML
POST /interruptions/evaluate:
  input:
    active_playback_event_id: string
    new_realtime_stt_event_id: string
    speaker_gate_receipt_id: string
  fail_closed:
    - non-primary speaker cannot unlock memory
    - ambiguous overlap uses one-at-a-time boundary
  emits:
    - interruption_receipt.v1

Next three Codex tasks:

Implement Rung 1: OS audio graph to RealtimeSTT external-audio proof

Command/artifact target:

Bash
python scripts/rung1_audio_graph_realtimestt.py \
  --transport pipewire_null_sink_monitor \
  --use-microphone false \
  --nonce \
  --expected "Horus factory stress speech" \
  --out /tmp/embry-live-e2e/rung1

Required artifacts:

/tmp/embry-live-e2e/rung1/captured.wav
/tmp/embry-live-e2e/rung1/events.ndjson
/tmp/embry-live-e2e/rung1/audio_ingress_receipt.json
/tmp/embry-live-e2e/rung1/realtimestt_receipt.json
/tmp/embry-live-e2e/rung1/rung_receipt.json

Acceptance criteria:

rung_receipt.ok=true
live=true
mocked=false
browser_used_as_proof=false
use_microphone=false
captured_rms above threshold
non_silent_frame_ratio above threshold
VAD start/end present
final transcript present
final transcript contains nonce or passes configured WER threshold

What it proves:
Clean live OS audio graph capture can feed RealtimeSTT and produce a correct transcript.

What it does not prove:
Physical mic, browser WebRTC, speaker identity, memory/Tau, Chatterbox, Chat UX, orb, replay, or interruption.

Stop condition:
If this fails, stop all UI/matrix work. Fix audio graph format, PCM chunking, sample rate, RealtimeSTT external feed, or transcript quality first.

Implement Rung 2: source-audio Horus speaker gate on clean captured audio

Command/artifact target:

Bash
python scripts/rung2_source_audio_speaker_gate.py \
  --input /tmp/embry-live-e2e/rung1/captured.wav \
  --enrollment horus_independent_enrollment_set \
  --cases known_horus,unknown,distractor,ambiguous \
  --out /tmp/embry-live-e2e/rung2

Required artifacts:

/tmp/embry-live-e2e/rung2/events.ndjson
/tmp/embry-live-e2e/rung2/speaker_identity_gate_receipt.json
/tmp/embry-live-e2e/rung2/memory_scope_gate_receipt.json
/tmp/embry-live-e2e/rung2/rung_receipt.json

Acceptance criteria:

independent enrollment confirmed
known Horus resolves to horus_lupercal
Horus personal_memory_allowed=true
unknown/distractor/ambiguous personal_memory_allowed=false
no personal memory query before speaker gate
source_audio_identity_proven=true
failed source-62 behavior is not accepted as pass

What it proves:
Clean captured source audio can be gated into Horus or fail-closed memory access.

What it does not prove:
Physical speaker-to-room-mic identity, browser microphone reliability, pyannote overlap, or barge-in.

Stop condition:
If Horus cannot be verified from clean audio, stop. Do not proceed to memory/Tau E2E or Chat UX. Fix enrollment, speaker verifier thresholds, source-windowing, or audio preprocessing.

Implement Rung 3/4 combined: live STT-derived turn through memory/Tau to Chatterbox OS playback

Command/artifact target:

Bash
python scripts/rung3_4_voice_to_tau_chatterbox.py \
  --from-rung1 /tmp/embry-live-e2e/rung1 \
  --from-rung2 /tmp/embry-live-e2e/rung2 \
  --cases sparta_qra_compliance-simple-01,persona_memory_miss-simple-01,brave_search-simple-01 \
  --require-memory-intent \
  --require-conversation-delivery-contract \
  --require-os-playback \
  --out /tmp/embry-live-e2e/rung3_4

Required artifacts:

/tmp/embry-live-e2e/rung3_4/events.ndjson
/tmp/embry-live-e2e/rung3_4/memory_tau_turn_receipt.json
/tmp/embry-live-e2e/rung3_4/conversation_delivery_receipt.json
/tmp/embry-live-e2e/rung3_4/chatterbox_playback_receipt.json
/tmp/embry-live-e2e/rung3_4/rung_receipt.json
/tmp/embry-live-e2e/rung3_4/audio/*.wav

Acceptance criteria:

input_text_source=realtimestt.final.v1
no typed prompt substitution
speaker gate receipt linked
memory.answerability.v1 emitted
memory /intent tone emitted
conversation arc present
steering strategy present
interruption strategy present
pause policy present
inline emotion tags present
assistant.response.plan.v1 emitted
/tau/voice-render called only with response_plan_id
blocked cases produce no finished_response_audio
answerable cases produce Chatterbox audio artifact
OS playback receipt proves actual playback

What it proves:
Minimum live voice E2E core: audio ingress to RealtimeSTT, speaker-gated memory/Tau reasoning, delivery envelope, Chatterbox render, and real playback.

What it does not prove:
Shared Chat UX sync, browser WebRTC, physical mic, orb sync, replay, pyannote overlap, or interruption.

Stop condition:
If any receipt is missing or text is injected downstream of STT, stop. Do not update matrix pass counts or add UI screenshots. Fix the broken service boundary.

YAML
name: embry_live_voice_e2e_truth_architecture
version: 2026-07-08
objective: >
  Prove Embry live voice/chat E2E behavior by forcing every pass through
  audio ingress, RealtimeSTT, speaker gate, memory/Tau, Chatterbox playback,
  Chat UX sync, orb envelope, replay, and interruption receipts.

truth_rules:
  - id: text_only_not_voice_e2e
    rule: "Text-only memory answerability can be proof_level=1 only; it cannot set voice_e2e_status=passed."
  - id: no_mock_live_proof
    rule: "Live proof requires live=true, mocked=false, and real artifact hashes."
  - id: browser_screenshot_not_authority
    rule: "Browser screenshots may support but never decide pass/fail."
  - id: memory_first_tau_authority
    rule: "Memory answers and intent precede Tau route decision; Tau alone authorizes skills."
  - id: chatterbox_renderer_only
    rule: "Chatterbox renders response plans and must not reason, retrieve, or call skills."
  - id: no_flat_tests
    rule: "Every conversation test requires arc, steering, interruption strategy, memory-selected tone, inline emotion tags, final spoken text schema, and pause policy."

components:
  - id: stress_matrix
    status: implemented_misleading
    owner: tau
    responsibilities:
      - "Track legacy_component_status separately from voice_e2e_status"
      - "Preserve 300 rows without promoting text-only passes to voice E2E"

  - id: os_audio_graph_capture
    status: next_required
    owner: RealtimeSTT
    responsibilities:
      - "Create PipeWire/Pulse null sink monitor capture"
      - "Capture non-browser audio with nonce"
      - "Emit audio_ingress_receipt.v1"

  - id: realtimestt_listener
    status: failing_physical_partial_loopback_next
    owner: RealtimeSTT
    responsibilities:
      - "Consume external audio with use_microphone=false"
      - "Emit VAD and final transcript events"
      - "Reject static transcripts for live proof"

  - id: speaker_gate
    status: partial_failing_source62
    owner: memory
    responsibilities:
      - "Verify Horus from independent enrollment"
      - "Disable personal memory for unknown, ambiguous, distractor, or overlap"
      - "Emit speaker_identity_gate_receipt.v1"

  - id: memory_answer_intent
    status: partial
    owner: memory
    responsibilities:
      - "Answerability"
      - "Memory-scoped retrieval"
      - "Conversation delivery intent"
      - "Tone and inline emotion tag selection"

  - id: tau_router
    status: partial_skill_receipts_failing
    owner: tau
    responsibilities:
      - "Turn decision"
      - "Skill handoff"
      - "DAG receipt"
      - "Assistant response plan"

  - id: agent_skills
    status: partial
    owner: agent-skills
    responsibilities:
      - "create-figure"
      - "analytics"
      - "create-evidence-case"
      - "sparta-validator"
      - "Emit skill call receipts only for Tau-authorized calls"

  - id: brave_search_route
    status: partial
    owner: tau
    responsibilities:
      - "Real external research route"
      - "Source receipts before speech"

  - id: chatterbox_renderer
    status: implemented_partial
    owner: chatterbox
    endpoint: "/tau/voice-render"
    responsibilities:
      - "Render only Tau response plans"
      - "Block unanswerable responses"
      - "Emit audio artifact and playback receipt"

  - id: audio_playback_authority
    status: partial
    owner: chatterbox
    responsibilities:
      - "Prove playback started/progressed/ended/cancelled"
      - "Avoid Chrome autoplay as first proof authority"

  - id: shared_chat_ux
    status: failing
    owner: ux-lab
    responsibilities:
      - "Render event journal"
      - "Prove response-plan-to-chat turn lineage"
      - "Render memory trace and entity underlines from receipts"

  - id: orb_envelope
    status: partial
    owner: ux-lab
    responsibilities:
      - "Subscribe to actual playback envelope"
      - "Reject timer-only speaking state"

  - id: replay_runner
    status: partial
    owner: ux-lab
    responsibilities:
      - "Replay actual session journal"
      - "Verify artifact hashes"
      - "Label replay as replay, not new live proof"

  - id: interruption_manager
    status: partial
    owner: tau
    responsibilities:
      - "Primary Horus barge-in"
      - "Non-primary suppression"
      - "Overlap boundary"
      - "Stale audio skip"
      - "Natural stop behavior"

connections:
  - from: os_audio_graph_capture
    to: realtimestt_listener
    carries:
      - "16-bit mono PCM or original sample rate audio chunks"
      - "audio_ingress_receipt.v1"

  - from: realtimestt_listener
    to: speaker_gate
    carries:
      - "realtime_stt.final.v1"
      - "captured audio artifact hash"

  - from: speaker_gate
    to: memory_answer_intent
    carries:
      - "speaker_identity_gate_receipt.v1"
      - "authorized memory namespaces"

  - from: memory_answer_intent
    to: tau_router
    carries:
      - "memory.answerability.v1"
      - "memory_intent.voice_delivery_receipt.v1"

  - from: tau_router
    to: agent_skills
    condition: "skill_required"
    carries:
      - "tau.agent_handoff.v1"
      - "tau.dag_receipt.v1"

  - from: tau_router
    to: brave_search_route
    condition: "external_research_required"
    carries:
      - "tau.route_decision.v1"

  - from: tau_router
    to: chatterbox_renderer
    condition: "assistant.response.plan.can_speak == true"
    carries:
      - "assistant.response.plan.v1"
      - "answerability receipt id"
      - "memory intent receipt id"
      - "skill/source receipt ids"

  - from: chatterbox_renderer
    to: audio_playback_authority
    carries:
      - "Chatterbox audio artifact"
      - "chatterbox_playback_receipt.v1"

  - from: audio_playback_authority
    to: orb_envelope
    carries:
      - "playback progress"
      - "audio envelope"

  - from: audio_playback_authority
    to: shared_chat_ux
    carries:
      - "audio artifact id"
      - "turn id"

  - from: tau_router
    to: shared_chat_ux
    carries:
      - "assistant.response.plan.v1"
      - "memory trace"
      - "tone and emotion tags"

  - from: shared_chat_ux
    to: replay_runner
    carries:
      - "chat render receipt"

  - from: os_audio_graph_capture
    to: interruption_manager
    condition: "speech during Embry playback"
    carries:
      - "new live audio segment"

  - from: speaker_gate
    to: interruption_manager
    carries:
      - "speaker gate for barge-in candidate"

  - from: interruption_manager
    to: audio_playback_authority
    carries:
      - "cancel or continue decision"

proof_ladder:
  - rung: 1
    name: "OS audio graph to RealtimeSTT"
    required_receipts:
      - audio_ingress_receipt.v1
      - realtimestt_receipt.v1

  - rung: 2
    name: "Source-audio speaker gate"
    required_receipts:
      - speaker_identity_gate_receipt.v1

  - rung: 3
    name: "Voice transcript to memory/Tau"
    required_receipts:
      - memory_tau_turn_receipt.v1
      - conversation_delivery_receipt.v1

  - rung: 4
    name: "Chatterbox render and OS playback"
    required_receipts:
      - chatterbox_playback_receipt.v1

  - rung: 5
    name: "Shared Chat UX lineage"
    required_receipts:
      - chat_sync_receipt.v1

  - rung: 6
    name: "Orb and replay"
    required_receipts:
      - orb_envelope_receipt.v1
      - replay_receipt.v1

  - rung: 7
    name: "Interruption and barge-in"
    required_receipts:
      - interruption_receipt.v1

<<<WEBGPT_DONE:20260708T103554Z:3fc3939a>>>
