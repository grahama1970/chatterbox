1. Exact existing command or callable for each stage
Managed RealtimeSTT arm/wait

Start one managed listener process for both turns:

Bash
REALTIMESTT=/home/graham/workspace/experiments/RealtimeSTT
REALTIMESTT_PYTHON=/home/graham/workspace/experiments/venv/bin/python
LISTENER_DIR="$CAMPAIGN_DIR/managed-listener"
LISTENER_SOCKET="$LISTENER_DIR/listener.sock"

"$REALTIMESTT_PYTHON" \
  "$REALTIMESTT/proofs/embry_pipewire_ingress/run_physical_hot_mic_listener.py" \
  --run-dir "$LISTENER_DIR" \
  --source-node "$LISTENER_SOURCE_NODE" \
  --event-service-url "$JOURNAL_URL/v1/listener/events" \
  --managed-socket "$LISTENER_SOCKET" \
  --target-cycles 2 \
  --cycles-this-run 2 \
  --max-attempts-this-run 8 \
  --restart-capture-after-cycle 0 \
  --model small.en \
  --realtime-model tiny.en \
  --device cuda \
  --compute-type float16

Arm each turn with the existing callable:

Python
Run
from managed_turn_protocol import send_arm_command

ack = send_arm_command(
    listener_socket,
    {
        "schema": "embry.listener_turn_command.v1",
        "command": "arm",
        "campaign_id": campaign_id,
        "case_id": case_id,
        "attempt_id": attempt_id,
        "session_id": session_id,
        "turn_id": turn_id,
        "source_authority_id": source_authority_id,
        "wake_required": True,
    },
)

The arm packet must contain identifiers only. The existing protocol rejects transcript, expected-transcript, expected-response, Memory-result, and Tau-route fields.

Wait through the existing journal endpoint:

GET /v1/sessions/{session_id}/events?after_sequence={cursor}

The executor must wait for, in order:

listener.turn_armed
listener.final_transcript
listener.turn_completed

filtered by the exact session_id, turn_id, campaign_id, case_id, attempt_id, and source_authority_id. The managed listener already creates a turn-specific publisher and places the managed identifiers in the final transcript payload.

Speaker verification

The existing scoring command is:

Bash
CHATTERBOX=/home/graham/workspace/experiments/chatterbox

uv run --project "$CHATTERBOX" --locked --no-sync \
  python "$CHATTERBOX/scripts/prove_physical_horus_enrollment.py" \
  --enrollment-sample "<enrollment-1.wav>" \
  --enrollment-sample "<enrollment-2.wav>" \
  --enrollment-sample "<enrollment-3.wav>" \
  --held-out-horus "<captured-turn.wav>" \
  --impostor "embry_self=<embry-impostor.wav>" \
  --impostor "non_horus=<non-horus-impostor.wav>" \
  --source-node "$LISTENER_SOURCE_NODE" \
  --threshold 0.75 \
  --min-ambiguity-margin 0.08 \
  --out "$TURN_DIR/speaker-verification-receipt.json"

The enrollment, impostor, threshold, and source paths must come from the named physical-enrollment receipt. The captured turn WAV must come from the exact listener.final_transcript event.

Not currently available as-is: no existing command appends the resulting per-turn candidate to the same journal as speaker.verification.completed. Add the thin speaker_verification.py adapter described in item 2. The existing proof script supplies the physical profile, held-out score, threshold, impostor scores, and profile hash; it should not be reimplemented.

Memory

Use the existing Journal → Memory → Tau controller:

Bash
SKILL_ROOT=/home/graham/workspace/experiments/agent-skills/skills/embry-voice-control
LANE="$SKILL_ROOT/proofs/tau/embry-journal-memory-tau-live"

uv run --project "$SKILL_ROOT" --locked --no-sync \
  python "$LANE/scripts/run_journal_memory_tau_proof.py" \
  --journal-url "$JOURNAL_URL" \
  --consumer-name "embry-audio-e2e:$CAMPAIGN_ID:$CASE_ID" \
  --event-id "$LISTENER_FINAL_EVENT_ID" \
  --speaker-evidence-event-id "$SPEAKER_EVENT_ID" \
  --expected-session-id "$SESSION_ID" \
  --expected-turn-id "$TURN_ID" \
  --expected-sequence "$LISTENER_FINAL_SEQUENCE" \
  --physical-enrollment-receipt "$PHYSICAL_ENROLLMENT_RECEIPT" \
  --memory-url "$MEMORY_URL" \
  --memory-scope sparta_qra \
  --persistent-session-id "$SESSION_ID:tau" \
  --tick-index "$TICK_INDEX" \
  --turn-contract "$TURN_CONTRACT" \
  --tau-repo "$TAU_REPO" \
  --output-dir "$TURN_DIR/memory-tau" \
  --lease-seconds 300

The currently committed controller already performs /speaker/resolve, /intent, /answer, writes immutable call receipts, appends the three Memory events, builds the Tau input packet, and then launches Tau.

The four new arguments above are required because the current code hard-codes Memory scope and does not preserve a case-wide persistent-session identity or a dynamic tick index.

Persistent Tau tick

The Memory controller above already invokes the existing Tau command internally:

Bash
uv run tau dag-run \
  "$TURN_DIR/memory-tau/dag-contract.json" \
  --receipt-dir "$TURN_DIR/memory-tau/tau-run" \
  --no-resume

The existing adapter is:

proofs/tau/embry-journal-memory-tau-live/
  scripts/run_embry_journal_memory_tau_handoff.py

It must retain:

tick_budget=1
unbounded_autonomy_allowed=false
session_mode=persistent
tau_control=bounded_receipt_gated_ticks

For this case it must additionally emit:

persistent_session_id = <same value for both turns>
tick_index             = 1, then 2
tick_budget            = 1 for both turns

The current adapter always emits tick_index=1; that must be parameterized before two turns can constitute one persistent logical Tau session.

Causal Chatterbox render

Use the existing render command:

Bash
uv run --project "$SKILL_ROOT" --locked --no-sync \
  python "$LANE/scripts/render_tau_turn_plan.py" \
  --tau-step-receipt \
    "$TURN_DIR/memory-tau/tau-run/command-loop/command-loop-step-001.receipt.json" \
  --expected-event-id "$LISTENER_FINAL_EVENT_ID" \
  --expected-sequence "$LISTENER_FINAL_SEQUENCE" \
  --expected-session-id "$SESSION_ID" \
  --expected-turn-id "$TURN_ID" \
  --chatterbox-url "$CHATTERBOX_URL" \
  --output-dir "$TURN_DIR/render"

It already loads the plan only from the Tau handoff, hash-checks the plan, verifies the source/session/turn lineage, calls /tau/voice-render, and verifies live non-mocked nonempty audio plus the echoed plan hash.

It is not composable for SPARTA unchanged because its final acceptance currently requires:

memory_miss_irrelevant_answer
static_answer

Those France-specific checks are at the end of the script and must be replaced with generic plan/hash/lineage assertions.

After render, invoke the existing journalization command:

Bash
uv run --project "$SKILL_ROOT" --locked --no-sync \
  python \
  "$SKILL_ROOT/proofs/chat-ux/embry-journal-chat-projection-live/journalize_projection_inputs.py" \
  --journal "$JOURNAL_DB" \
  --render-receipt "$TURN_DIR/render/receipt.json" \
  --output-dir "$TURN_DIR/projection-inputs"

That command already appends the accepted chatterbox.voice_render.completed event. Its entity-input portion must be changed to consume the Memory intent receipt rather than launching $extract-entities directly.

Jabra playback

Use the existing executable:

Bash
uv run --project "$SKILL_ROOT" --locked --no-sync \
  python "$SKILL_ROOT/scripts/prove_pipewire_playback.py" \
  --journal-db "$JOURNAL_DB" \
  --journal-url "$JOURNAL_URL" \
  --session-id "$SESSION_ID" \
  --turn-id "$TURN_ID" \
  --source-event-id "$LISTENER_FINAL_EVENT_ID" \
  --source-sequence "$LISTENER_FINAL_SEQUENCE" \
  --tau-plan-event-id "$TAU_PLAN_EVENT_ID" \
  --render-event-id "$RENDER_EVENT_ID" \
  --tau-plan-sha256 "$TAU_PLAN_SHA256" \
  --tts-text-sha256 "$TTS_TEXT_SHA256" \
  --audio-sha256 "$AUDIO_SHA256" \
  --audio-bytes "$AUDIO_BYTES" \
  --sink-node-name \
    "alsa_output.usb-0b0e_Jabra_SPEAK_510_USB_501AA5274B1D022000-00.analog-stereo" \
  --expected-current-node-id "$JABRA_CURRENT_NODE_ID" \
  --expected-sink-description "Jabra SPEAK 510 Analog Stereo" \
  --expected-sink-volume 0.70 \
  --sink-volume-tolerance 0.02 \
  --duplicate-probe \
  --output-dir "$TURN_DIR/playback"

This calls the existing embry_voice_control.pipewire_playback.run_playback() callable. It resolves the artifact from the render event, verifies the Jabra sink, appends playback.requested, observes the running PipeWire route before appending playback.started, appends playback.ended only after plausible successful completion, and ACKs the render event.

Record the explicit human witness with:

Bash
uv run --project "$SKILL_ROOT" --locked --no-sync \
  python "$SKILL_ROOT/scripts/record_pipewire_playback_witness.py" \
  --machine-receipt "$TURN_DIR/playback/machine-receipt.json" \
  --human-reply-file "$TURN_DIR/playback/human-reply.txt" \
  --verdict heard_exactly \
  --output "$TURN_DIR/playback/receipt.json"

The machine receipt’s expected sentence is currently hard-coded to the France answer and must instead be read from the accepted Tau-plan locator.

Chat projection

Existing callable:

Python
Run
from embry_voice_control.chat_projection import build_turn_chat_projection

projection = build_turn_chat_projection(
    journal_db,
    session_id=session_id,
    turn_id=turn_id,
)

Existing HTTP command:

Bash
curl --fail --silent --show-error \
  "$JOURNAL_URL/v1/sessions/$SESSION_ID/turns/$TURN_ID/chat-projection" \
  --output "$TURN_DIR/chat-projection.json"

The existing projection endpoint is read-only and the projection already validates the complete requested → started → ended playback chain when those events are present.

Orb projection

No currently composable command exists.

The current public orb helper derives speaking from a replay phase named response, not from the exact playback.started journal event.

The unavoidable missing adapter is:

pi-mono/packages/ux-lab/src/components/embry-voice/
  EmbryJournalTurnRuntime.tsx

It must subscribe to exact session events and map:

listener.turn_armed or listener.recording_started -> listening
Tau tick start/completion                         -> processing
chatterbox.voice_render.completed                 -> audio_ready
playback.started                                  -> speaking
playback.ended                                    -> idle

It must emit a browser receipt containing the event ID and sequence that caused every state change.

Replay

No currently composable journal-only replay command exists.

The current public route constructs static voiceTurns, static receipt paths, timer-driven reasoning steps, and DOM audio playback; those artifacts cannot be reused for the new case.

The same EmbryJournalTurnRuntime.tsx adapter must expose:

replay(session_id, frozen_through_sequence, frozen_journal_sha256)

and reconstruct both turns without Memory, Tau, Chatterbox, or RealtimeSTT requests.

2. Minimal agent-skills files to add or modify
Existing audio_e2e runtime

Modify:

skills/embry-voice-control/src/embry_voice_control/audio_e2e/runner.py
skills/embry-voice-control/src/embry_voice_control/audio_e2e/case_executor.py
skills/embry-voice-control/src/embry_voice_control/audio_e2e/receipts.py
skills/embry-voice-control/src/embry_voice_control/audio_e2e/__main__.py

Add:

skills/embry-voice-control/src/embry_voice_control/audio_e2e/event_waiter.py
skills/embry-voice-control/src/embry_voice_control/audio_e2e/speaker_verification.py
skills/embry-voice-control/tests/audio_e2e/test_live_executor.py

Required behavior:

Python
Run
# runner.py
with ManagedListenerProcess(config) as listener:
    result = CaseExecutor(config, state, listener).execute_case(case)

# case_executor.py
for turn_index, turn_contract in enumerate(case["turns"], start=1):
    arm_listener()
    wait_for_final_and_completed()
    write_physical_source_receipt()
    verify_and_journal_speaker()
    run_memory_tau(tick_index=turn_index)
    render_tau_plan()
    journalize_render_and_entities()
    load_chat_projection()
    wait_for_orb_runtime_ready()
    run_jabra_playback()
    record_human_witness()
    finalize_chat_orb_turn_receipt()

run_journal_only_replay()
finalize_case_receipt()

run_audio_e2e_rung.sh should remain a package wrapper. The execution plan must call:

run_audio_e2e_rung.sh run ...

rather than passing run-only options without the run subcommand.

Existing proof lane

Modify:

skills/embry-voice-control/proofs/tau/embry-journal-memory-tau-live/
  scripts/run_journal_memory_tau_proof.py

skills/embry-voice-control/proofs/tau/embry-journal-memory-tau-live/
  scripts/run_embry_journal_memory_tau_handoff.py

skills/embry-voice-control/proofs/tau/embry-journal-memory-tau-live/
  scripts/render_tau_turn_plan.py

Required changes:

run_journal_memory_tau_proof.py:
  add --memory-scope
  add --persistent-session-id
  add --tick-index
  add --turn-contract
  use source.payload.request_text before source.payload.text
  record Tau step-receipt path/hash in final receipt

run_embry_journal_memory_tau_handoff.py:
  preserve persistent_session_id
  accept tick_index 1 or 2
  keep tick_budget=1
  include input_text and input_text_sha256 in tau.turn_plan.v1

render_tau_turn_plan.py:
  use plan input_text rather than raw wake transcript
  remove France-specific acceptance checks
  validate generic plan route, display/TTS hashes, delivery policy,
  one bounded tick, echoed plan hash, and nonempty live audio
Production planner

Modify:

skills/embry-voice-control/src/embry_voice_control/embry_chat.py

Required ordering:

Python
Run
if intent_action in {"CLARIFY", "IDENTITY_CLARIFICATION", "DEFLECT"}:
    fail_closed()
elif grounded_memory_answer:
    use_memory_answer()
elif intent_action == "COMPLIANCE":
    block_for_missing_grounded_compliance_answer()
elif controlled_static_fact:
    use_static_answer()
else:
    memory_miss()

Also accept the compiled turn’s delivery requirements and preserve its tone, arc, emotion tags, pause policy, and interruption policy.

Projection journalization

Modify:

skills/embry-voice-control/proofs/chat-ux/
  embry-journal-chat-projection-live/
  journalize_projection_inputs.py

Replace the direct $extract-entities subprocess with:

user spans:
  exact Memory intent receipt -> response.entity_context

assistant spans:
  Tau-plan assistant spans when supplied
  otherwise deterministic zero-span result

The current direct $extract-entities invocation would be an extra unplanned skill call.

Playback witness

Modify:

skills/embry-voice-control/src/embry_voice_control/pipewire_playback.py

Replace the fixed expected sentence with:

render event
-> Tau plan locator
-> plan.tts_render_text
-> plan.tts_render_text_sha256

No new --expected-text CLI argument should be added.

3. Exact one-case CLI arguments and receipt checks
Bash
set -euo pipefail

SKILL_ROOT=/home/graham/workspace/experiments/agent-skills/skills/embry-voice-control
REALTIMESTT=/home/graham/workspace/experiments/RealtimeSTT
CHATTERBOX=/home/graham/workspace/experiments/chatterbox
TAU=/home/graham/workspace/experiments/tau
OUT=/tmp/embry-audio-e2e-sparta-two-turn

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
      else error("expected_one_jabra_input")
      end
  '
)"

SINK_NODE='alsa_output.usb-0b0e_Jabra_SPEAK_510_USB_501AA5274B1D022000-00.analog-stereo'

SINK_ID="$(
  pw-dump --no-colors |
  jq -er --arg node "$SINK_NODE" '
    [
      .[]
      | select(.type == "PipeWire:Interface:Node")
      | select(.info.props["node.name"] == $node)
      | select(.info.props["media.class"] == "Audio/Sink")
      | .id
    ]
    | if length == 1 then .[0]
      else error("expected_one_jabra_output")
      end
  '
)"

rm -rf "$OUT"
mkdir -p "$OUT"

Run:

Bash
"$SKILL_ROOT/run_audio_e2e_rung.sh" run \
  --manifest "$OUT/manifest.json" \
  --campaign-dir "$OUT/run" \
  --case-id sparta_qra_compliance-simple-01 \
  --source-class physical_live_horus \
  --journal-db \
    /mnt/storage12tb/skills/embry-voice-control/state/voice-events.sqlite3 \
  --journal-url http://127.0.0.1:8032 \
  --realtimestt-repo "$REALTIMESTT" \
  --realtimestt-python /home/graham/workspace/experiments/venv/bin/python \
  --managed-listener-socket "$OUT/run/managed-listener.sock" \
  --listener-source-node "$SOURCE_NODE" \
  --physical-enrollment-receipt \
    /tmp/embry-horus-enrollment-physical/physical-enrollment-receipt.json \
  --chatterbox-repo "$CHATTERBOX" \
  --memory-url http://127.0.0.1:8601 \
  --memory-scope sparta_qra \
  --tau-repo "$TAU" \
  --chatterbox-url http://127.0.0.1:8018 \
  --response-sink-node-name "$SINK_NODE" \
  --response-sink-current-node-id "$SINK_ID" \
  --response-sink-description "Jabra SPEAK 510 Analog Stereo" \
  --response-sink-volume 0.70 \
  --ux-url http://127.0.0.1:3002 \
  --browser-oracle-project embry \
  --browser-oracle-tab 837357645 \
  --require-human-playback-witness

The manifest must contain exactly:

case: sparta_qra_compliance-simple-01
session: one case-level session ID
turn 1: ...:turn-001
turn 2: ...:turn-002
source class: physical_live_horus
Memory scope: sparta_qra
persistent Tau session: <session-id>:tau
Tau tick indices: [1, 2]

Each turn receipt must pass:

source:
  physical_live_horus
  synthetic=false
  physical_human=true
  captured WAV exists
  captured WAV and PCM hashes present
  non-silent

listener:
  listener.turn_armed exists
  listener.final_transcript exists
  listener.turn_completed exists
  managed identifiers match exactly
  request_text passes transcript oracle

speaker:
  speaker.verification.completed causation == listener final
  accepted=true
  top candidate == horus_lupercal
  audio hash == listener capture hash
  profile hash == physical enrollment profile hash

memory:
  /speaker/resolve known Horus
  allow_personal_memory=true
  /intent scope == sparta_qra
  /answer scope == sparta_qra
  request query == listener request_text

tau:
  same persistent_session_id for both turns
  tick indices == [1, 2]
  each tick_budget == 1
  each source event and turn unchanged
  tau.turn_plan.v1 hash valid

render:
  causal render receipt PASS
  live=true
  mocked=false
  plan hash echoed
  audio bytes > 44
  render event journaled

playback:
  requested -> started -> ended
  exact render causation
  exact audio hash
  exact Jabra node.name
  process exit zero
  human witness heard_exactly

chat:
  projection schema embry.chat_projection.v1
  exact session and turn
  two messages per turn
  correct user/assistant hashes
  playback authority present

orb:
  speaking caused by playback.started only
  idle caused by playback.ended only

replay:
  four messages
  two input audio artifacts
  two Embry audio artifacts
  zero Memory/Tau/Chatterbox/RealtimeSTT calls

Final case assertion:

Bash
jq -e '
  .schema == "embry.audio_e2e_case_receipt.v1"
  and .case_id == "sparta_qra_compliance-simple-01"
  and .status == "PASS"
  and .counted == true
  and .live == true
  and .mocked == false
  and .source_class == "physical_live_horus"
  and .turn_count == 2
  and .passed_turn_count == 2
  and [.turns[].tau.tick_index] == [1, 2]
  and ([.turns[].tau.tick_budget] | all(. == 1))
  and ([.turns[].speaker.speaker_id] | all(. == "horus_lupercal"))
  and ([.turns[].playback.status] | all(. == "PASS"))
  and ([.turns[].chat.status] | all(. == "PASS"))
  and ([.turns[].orb.status] | all(. == "PASS"))
  and .replay.status == "PASS"
  and (.failed_gates | length) == 0
' "$OUT/run/cases/sparta_qra_compliance-simple-01/receipt.json"

On failure, the executor must set:

status=FAIL
counted=false
failed_stage=<exact stage>

freeze the bundle, and leave later stages unexecuted. resume must restart at that failed stage rather than rearming an already completed physical turn.

4. Stages that cannot currently be composed
Per-turn speaker verification event

The existing physical enrollment/scoring command can score the managed capture, but no existing adapter writes that result as the exact same-turn speaker.verification.completed event expected by the Memory/Tau controller.

Missing adapter:

agent-skills/skills/embry-voice-control/src/
  embry_voice_control/audio_e2e/speaker_verification.py
Two-turn SPARTA Memory/Tau

The existing controller currently uses fixed Memory scope and the current handoff adapter emits tick 1 for every invocation. It cannot prove a two-turn SPARTA session unchanged.

Required modifications:

run_journal_memory_tau_proof.py
run_embry_journal_memory_tau_handoff.py
embry_chat.py

No separate harness is required.

SPARTA causal render

The existing render command is executable, but its receipt is hard-coded to require the France-specific static route.

Required modification:

render_tau_turn_plan.py

Replace static-answer assertions with generic plan/hash/lineage assertions.

Journal entity projection

The existing journalizer invokes $extract-entities directly rather than consuming the Memory intent entity context.

Required modification:

journalize_projection_inputs.py
Playback human witness

The existing playback controller can play any journaled artifact, but its machine receipt names the France sentence.

Required modification:

pipewire_playback.py
Orb and replay

No current command can bind a newly created two-turn journal session to live orb transitions and journal-only replay. The public route remains fixture- and timer-driven.

Exact unavoidable missing adapter:

pi-mono/packages/ux-lab/src/components/embry-voice/
  EmbryJournalTurnRuntime.tsx

It must serve both functions:

live journal events -> orb state with causal event IDs
frozen journal snapshot -> replay without provider reruns

Until that adapter emits a same-session browser receipt, the case must stop at:

BLOCKED_UI_JOURNAL_RUNTIME
counted=false

<<<WEBGPT_DONE:20260711T172717Z:091db26d>>>
