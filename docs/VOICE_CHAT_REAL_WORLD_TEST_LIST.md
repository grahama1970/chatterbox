# Voice Chat Real-World Non-Mocked Test List

Status date: 2026-07-03

This is the required sanity list for RealtimeSTT/listener plus Chatterbox voice
chat. These tests must use real services and real audio/transport artifacts.
Fixture audio is allowed as an input stimulus; mocked ASR, mocked TTS, mocked
memory, fake browser media devices, and patched service responses are not
acceptable proof.

Latest full-suite receipt:

`/tmp/chatterbox-fork-agent-out/voice-chat-e2e/voice-chat-e2e-20260703T214538Z-audible-all-v2/index.json`

That run reported `mocked=false`, `live=true`, `ok=true`, empty
`failed_gates`, passed eight implemented scenarios, and played scenario WAV
artifacts through PipeWire sink `64`. It is still a sanity suite, not
production certification.

Latest repeat-stress receipt:

`/tmp/chatterbox-fork-agent-out/voice-chat-e2e/stress-20260703T221132Z-audible-repeat/stress-summary.json`

That stress run executed the full audible suite three times. All three index
receipts reported `mocked=false`, `live=true`, `ok=true`, and empty
`failed_gates`.

Latest personality audition receipt:

`/tmp/chatterbox-fork-agent-out/voice-chat-e2e/personality-audition-20260703T223052Z-scripted/personality-audition.json`

That run rendered and audibly played five Embry one-at-a-time boundary variants
through live Tau/Chatterbox. It proves the variants can render and play; it
does not prove the human accepts the performance.

Latest current stress run:

`/tmp/chatterbox-fork-agent-out/voice-chat-e2e/voice-chat-e2e-20260707T232441Z-stress-current/index.json`

That run reported `mocked=false`, `ok=false`, and failed `S06` with
`factory_noise_matrix_ok`. It passed continuous core, stream cancel, QRA
disabled, unknown speaker, ambiguous speaker, female distractor/overlap, and
browser transport. The S06 failure was a real capture/source failure: source
`67` captured RMS `7` while the played stress WAV had RMS `542`.

Latest intelligence stress receipt:

`/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260707T233318Z/receipt.json`

That run reported `mocked=false`, `live=true`, `ok=false`. It found answer
relevance failures: a SPARTA QRA acceptability question returned an unrelated
S0609/deprecated-control answer, Horus persona-memory returned a Horus TTS skill
description instead of Cthonia, and a private-codeword memory miss returned an
unrelated Embry config skill instead of clarifying. The three bad answers were
rendered and audibly played through live Tau/Chatterbox in
`/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260707T233318Z/spoken-failures/spoken-failures.json`.

Latest scripted intelligence stress receipt:

`/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260707T234201Z-scripted/receipt.json`

Command:

```bash
python3 scripts/smoke_embry_intelligence_stress.py \
  --out-dir /tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260707T234201Z-scripted \
  --render-spoken-failures \
  --playback-sink-target 64 \
  --playback-timeout-s 20 \
  --timeout-s 180
```

That run reported `mocked=false`, `live=true`, `ok=false`. It reproduced the
same three answerability failures and passed the Brave Search pyannote route.
It rendered all three bad answers to Chatterbox WAVs, but local playback through
`pw-play --target 64` timed out, so the spoken-failure playback gates failed.
The generated WAV files are valid 24 kHz mono artifacts; playback timeout is a
local command/device failure to investigate separately.

Latest 300-session stress matrix:

`docs/EMBRY_STRESS_SESSION_MATRIX.json`

Latest generated failure taxonomy:

`docs/EMBRY_STRESS_FAILURE_TAXONOMY.json`

Latest generated goal coverage audit:

`docs/EMBRY_GOAL_COVERAGE_AUDIT.json`

The matrix now has 300 receipt-backed sessions: 49 passed, 251 failed, and
0 not-run. The taxonomy converts those rows into subsystem repair blockers:

- Memory answerability: 0 passed, 60 failed. SPARTA/persona-memory answers
  still leak unrelated records or answer memory misses.
- Tau and direct skill routing: 0 passed, 120 failed. The top failures are
  missing `tau.agent_handoff.v1`, `tau.dag_receipt.v1`, and
  `skill.call.receipt.v1`.
- Shared Chat UX: 4 passed, 16 failed. Replay and inline trace basics pass,
  but turn-id lineage and entity underline receipts are missing.
- Interruption and turn control: 0 passed, 20 failed. Cancel/duck/stop
  endpoint paths are exercised, but live interruption decisions, stale-audio
  byte measurements, non-primary rejection, and natural-stop receipts are
  missing.
- RealtimeSTT audio ingress/factory capture: 0 passed, 20 failed in the
  matrix. A separate current S06 PipeWire/Jabra monitor-loopback receipt passes
  and is recorded in the ingress audit, but current matrix rows still show
  weak/silent capture, empty ASR, or unimplemented runner routes.
- Tone and emotion intent: 5 passed, 15 failed. Frustrated de-escalation passes;
  hostile, discouraged, and overlap tone-family expectations fail.
- External research: 20 passed, 0 failed.
- Speaker identity: 20 passed, 0 failed.

The taxonomy is not a full-loop proof. It still does not prove reliable browser
mic/WebRTC across devices, full live RealtimeSTT -> speaker/diarization ->
memory/Tau -> Chatterbox -> Chat UX, Chatterbox generated from every live STT
turn, orb/audio/chat synchronization from one event journal, event-sourced
replay, or live barge-in with stale audio suppression.

The goal coverage audit maps the active objective directly:

- Failing: `realtimestt_ingress`, `memory_tau_routing`, `chat_ux_sync`,
  `interruption`.
- Partial: `speaker_identity`, `chatterbox_speech`, `orb_sync`, `replay`.

The next proof required for `orb_sync` is not another screenshot alone. The
direct Chatterbox/orb receipt now links one generated audio artifact to orb
envelope samples. The remaining proof must emit the same linkage from a full
shared Chat UX or live listener turn where RealtimeSTT, memory/Tau, Chatterbox
playback, and orb state all share one `turn_id`.

Current orb-sync audit receipt:

`docs/EMBRY_ORB_SYNC_EVIDENCE_AUDIT.json`

Current direct orb-sync proof:

`/tmp/chatterbox-fork-agent-out/orb-sync-current/orb-direct-speak/orb-sync-receipt.json`

That receipt reported `mocked=false`, `live=true`, `ok=true`, turn/audio
artifact id `0b0d4fe7ea12`, playback start `1783361300926`,
`orb.authority=server-envelope`, 330 envelope frames, max level `0.798`, 20
nonzero audio samples, 21 bound samples, and screenshot
`/tmp/embry-orb-direct-speak-proof.png`.

What it does not prove:

- RealtimeSTT ingress
- speaker identity correctness
- memory/Tau routing
- browser shared Chat UX session replay
- human subjective orb quality

Current replay evidence audit receipt:

`docs/EMBRY_REPLAY_EVIDENCE_AUDIT.json`

That audit now reports `mocked=false`, `ok=true`, `proof_count=5`, and
`passing_candidate_count=1` because
`/tmp/chatterbox-fork-agent-out/event-sourced-replay/20260708T034752Z-interrupt-current/replay-receipt.json`
provides an event journal for the live Chatterbox interruption smoke. This
does not prove browser Chat UX rendering or a full live listener/STT replay.

Current interruption evidence audit receipt:

`docs/EMBRY_INTERRUPTION_EVIDENCE_AUDIT.json`

That audit reported `mocked=false`, `ok=false`, `proof_count=3`, and
`passing_candidate_count=0`. The stream-cancel receipt still proves
`old_turn_bytes_after_cancel=0` for a pre-cancelled turn, but no current
candidate proves live barge-in. The missing receipt fields are old/new turn ids,
Embry playback audio artifact/start/interrupt offset, listener interruption
detection, listener speaker id, primary speaker match, cancelled/stopped/stale
control state, stale old-turn byte measurement, and new-turn response
started/wins.

Current RealtimeSTT ingress evidence audit receipt:

`docs/EMBRY_REALTIMESTT_INGRESS_EVIDENCE_AUDIT.json`

That audit reports `mocked=false`, `live=true`, `ok=false`, 6 proof candidates,
and 4 passing ingress slices. One passing candidate is the current S06
PipeWire/Jabra monitor-loopback receipt from
`/tmp/chatterbox-fork-agent-out/voice-chat-e2e/20260708T034407Z-factory-current/S06-factory-noise/rung8-loopback-listener.json`.
The current factory-noise matrix still remains 0 passed / 20 failed, and
browser device ingress remains inconsistent, so the subsystem is still failing
despite that current loopback slice.

Current memory/Tau routing evidence audit receipt:

`docs/EMBRY_MEMORY_TAU_ROUTING_EVIDENCE_AUDIT.json`

That audit reported `mocked=false`, `ok=false`, 200 audited sessions, 20 passed,
and 180 failed. It separates the green path from the broken paths:

- External research: 20 passed, 0 failed.
- Memory answerability: 0 passed, 60 failed. Current failures are SPARTA QRA
  answers leaking unrelated records, persona-memory answers using unrelated
  source collections or wrong answers, and memory-miss prompts answering
  unrelated records instead of clarifying.
- Tau/direct skill routing: 0 passed, 120 failed. Current failures are missing
  `tau.agent_handoff.v1`, missing `tau.dag_receipt.v1`, and missing
  `skill.call.receipt.v1`.

The audit also records one live mitigation receipt:
`/tmp/chatterbox-fork-agent-out/embry-answerability-runtime-block/20260708T010111Z-answerability-runtime-block/receipt.json`.
That mitigation proves blocked answerability decisions can stop before
Chatterbox synthesis. It does not prove upstream memory answer quality, Tau
agent handoff, Tau DAG execution, direct skill execution, Chat UX sync, or live
voice loop behavior.

Current Chatterbox speech evidence audit receipt:

`docs/EMBRY_CHATTERBOX_SPEECH_EVIDENCE_AUDIT.json`

That audit reported `mocked=false`, `ok=false`, and separates Chatterbox render
capability from speech-policy readiness:

- Live Chatterbox render evidence exists: one `/tau/voice-render` candidate has
  a finished WAV with nonzero bytes and duration.
- Approved QRA audio generation evidence exists: two candidates show five
  Embry audio variants for blessed/approved QRA paths.
- Audible personality evidence exists: one five-variant Embry personality
  audition rendered and played through `pw-play`.
- Delivery envelope evidence is incomplete on the current Tau voice-render
  receipt; required fields such as full delivery policy source, pace, or pause
  strategy are not consistently present.
- Tone/emotion matrix rows are 5 passed / 15 failed. Hostile, discouraged, and
  speaker-overlap prompts still receive the wrong memory intent tone family.
- Interruption matrix rows are 0 passed / 20 failed. Live Horus barge-in,
  new-turn-wins, stale audio byte measurement, non-primary rejection linked to
  turn control, and natural stop phrases remain missing.

This means Chatterbox can speak, but Embry speech is not yet policy-complete for
the active goal.

Current speaker identity evidence audit receipt:

`docs/EMBRY_SPEAKER_IDENTITY_EVIDENCE_AUDIT.json`

That audit reported `mocked=false`, `ok=false`, even though the speaker identity
matrix itself is 20 passed / 0 failed. It separates memory policy from physical
identity proof:

- Live memory `/speaker/resolve` policy coverage exists for known, unknown,
  ambiguous, and overlap-like speaker decisions.
- Fixture primary-speaker gating exists: primary voice accepted, female/other
  male/background noise rejected.
- Known Horus speaker-scoped memory routing exists.
- Unknown speaker fail-closed identity prompting exists.
- One independent enrollment-vs-candidate receipt exists.
- One matrix row still explicitly records `source_audio_identity_proven=false`.
- No committed receipt proves physical speaker-to-microphone identity gating.
- Overlap diarization remains unproven.

This means speaker policy is usable for routing, but the goal-level speaker
identity requirement remains partial until physical identity and overlap
diarization receipts exist.

Current Chat UX sync evidence audit receipt:

`docs/EMBRY_CHAT_UX_SYNC_EVIDENCE_AUDIT.json`

That audit reported `mocked=false`, `ok=false`. It separates basic visual/DOM
evidence from the stronger synchronization receipts the shared Chat UX needs:

- Basic shared Chat text/audio evidence exists: 1 candidate.
- Dynamic replay / inline reasoning trace evidence exists: 2 candidates.
- Screenshot/page-snapshot markers exist: 16 candidates, but they do not prove
  turn lineage by themselves.
- `assistant.response.plan.v1` -> `chat.render.receipt.v1` lineage candidates:
  0.
- `$extract-entities` underline-render candidates: 0.
- Matrix status remains 4 passed / 16 failed.

The missing proof is explicit: the same `turn_id` must link the assistant
response plan, rendered chat text, Chatterbox audio artifact, memory reasoning
trace, and entity underline rendering. Without that, the Chat UX can look
plausible while still failing the shared voice/chat synchronization contract.

Current exact Horus E2E status audit receipt:

`docs/EMBRY_HORUS_E2E_STATUS_AUDIT.json`

That audit reported `mocked=false`, `ok=false`, with 0 pass / 8 fail. It is the
single deterministic pass/fail index for the eight items that define the current
voice/chat stress goal:

- real Horus enrollment: fail
- browser mic/WebRTC to RealtimeSTT: fail
- Tau/memory routing: fail
- Chatterbox from live STT: fail
- Chat UX sync: fail
- orb sync: fail
- replay: fail
- interruption: fail

The audit passes an item only when every mapped subsystem is `passed` and every
mapped receipt is `mocked=false`, `live=true`, `ok=true`, and has empty
`failed_gates`. Partial receipts, screenshots, UI markers, historical slices,
and direct Chatterbox render proofs do not satisfy the full item gates.

Current factory-loopback S06 receipt:

`/tmp/chatterbox-fork-agent-out/voice-chat-e2e/20260708T034407Z-factory-current/index.json`

Result: `mocked=false`, `live=true`, `ok=true`, scenario `S06` passed.

What it exercised:

- Chatterbox health checked on `http://127.0.0.1:8018`.
- Played the Horus/factory/Embry stress WAV through PipeWire/Jabra sink target
  `64`.
- Captured the monitor loopback into
  `/tmp/chatterbox-fork-agent-out/voice-chat-e2e/20260708T034407Z-factory-current/S06-factory-noise/loopback-captured.wav`.
- Fed the captured audio into RealtimeSTT automatic VAD.
- Produced final ASR text in
  `/tmp/chatterbox-fork-agent-out/voice-chat-e2e/20260708T034407Z-factory-current/S06-factory-noise/realtimestt-loopback.json`.
- Routed the captured loopback audio through the rung7 speaker/memory contract.
- Played three scenario WAV artifacts audibly with `pw-play --target 64`,
  all with return code 0.

What it does not prove:

- browser getUserMedia/WebRTC transport
- physical room microphone capture
- overlapping-speaker diarization
- subjective voice quality
- generalized factory robustness beyond the configured stress WAV and sink

Current Chatterbox interruption sequencing receipt:

`/tmp/chatterbox-fork-agent-out/interruption-current/20260708T034752Z-interrupt-current/final-response.json`

Result: `mocked=false`, `live=true`, `ok=true`.

What it exercised:

- Rendered the first old-turn Chatterbox chunk.
- Issued an interruption request with a new turn id.
- Stopped old playback in the turn event timeline.
- Skipped two stale queued old-turn chunks.
- Recorded `post_cancel_old_turn_audio_bytes_emitted=0`.
- Started new-turn acknowledgement and answer audio after cancel.

What it does not prove:

- RealtimeSTT heard the interrupting user.
- The interrupting speaker was Horus.
- The speaker gate accepted Horus and rejected non-primary speech.
- The playback offset at the exact barge-in moment was measured.
- Subjective human interruption feel.

Current QRA-disabled Chatterbox speech receipt:

`/tmp/chatterbox-fork-agent-out/voice-chat-e2e/20260708T035021Z-qra-disabled-current/index.json`

Result: `mocked=false`, `live=true`, `ok=true`, scenario `S10` passed.

Child receipt:

`/tmp/chatterbox-fork-agent-out/voice-chat-e2e/20260708T035021Z-qra-disabled-current/S10-qra-disabled/tau-qra-disabled.json`

What it exercised:

- Sent a Tau voice render request with `use_blessed_qra_cache=false`.
- Confirmed `response.blessed_qra_cache.enabled=false`.
- Confirmed `response.blessed_qra_cache.hit=false`.
- Rendered a normal Chatterbox WAV instead of a blessed-QRA cache hit.
- Copied the audible render to
  `/tmp/chatterbox-fork-agent-out/voice-chat-e2e/20260708T035021Z-qra-disabled-current/S10-qra-disabled/qra-disabled-render.wav`.

What it does not prove:

- listener ASR
- production memory QRA ranking
- subjective voice quality
- complete voice-delivery metadata, because the receipt still lacks `pace`,
  `pause_strategy`, and `source`

Current full voice-delivery Tau render receipt:

`/tmp/chatterbox-fork-agent-out/tau-voice-render-current/20260708T035831Z-voice-delivery-full-chunks-after-patch/tau-voice-render-full-delivery.json`

Result: `mocked=false`, `live=true`, `ok=true`.

What it exercised:

- Sent a Tau voice render request with `tone`, `delivery_stage`, `pace`,
  `pause_strategy`, `source`, emotion tags, and interruption policy.
- Restarted `chatterbox-fork-agent-server` so the patched server mapping was
  active.
- Confirmed the Chatterbox response and chunk metadata preserved
  `pace=measured`.
- Confirmed the Chatterbox response and chunk metadata preserved
  `pause_strategy=short_answer_no_filler`.
- Confirmed the Chatterbox response and chunk metadata preserved
  `source=memory.intent`.
- Confirmed the response recorded `requested_delivery_stage=answer`.

What it does not prove:

- listener ASR
- production memory recall correctness
- subjective voice quality
- full tone/emotion matrix coverage

Current event-sourced replay receipt:

`/tmp/chatterbox-fork-agent-out/event-sourced-replay/20260708T034752Z-interrupt-current/replay-receipt.json`

Result: `mocked=false`, `live=true`, `ok=true`.

What it exercised:

- Loaded the live Chatterbox interruption receipt and `task-events.jsonl`.
- Wrote an append-only event journal with 10 validated events.
- Included the replay-required event types:
  `listener.audio_frame_received`, `stt.final`, `speaker_gate.accepted`,
  `memory.intent`, `tau.voice_render_request`, `chatterbox.audio_artifact`,
  `audio.playback_started`, and `chat.turn_rendered`.
- Preserved old/new turn ids from the interruption session.
- Linked three Chatterbox WAV artifacts into the replay receipt.
- Recorded matching original/rendered timing offsets.
- Marked chat snapshot, audio offset, and turn order replay checks as matching.

What it does not prove:

- RealtimeSTT live microphone correctness
- speaker identity correctness
- browser Chat UX rendering
- subjective replay timing quality

Latest memory answerability ledger receipt:

`/tmp/chatterbox-fork-agent-out/embry-memory-answerability-ledger/20260708T004951Z-memory-answerability-ledger/receipt.json`

That run migrated the twelve simple SPARTA/persona/memory-miss cases into the
canonical event-journal shape. It reported `mocked=false`, `live=true`, and
`ok=false` with `74` journal events and `14` failed gates. All twelve cases
computed `block_before_speech`: SPARTA QRA questions still leaked unrelated
S0609/deprecated-control answers, persona-memory recall still used unrelated
source collections, and memory-miss prompts still answered unrelated records
instead of clarifying or no-answer. The proof scope is
`live_memory_answerability_gate_not_runtime_speech_block`, so it does not prove
that Tau or Chatterbox are already suppressing failed answers at runtime.

Latest runtime answerability block receipt:

`/tmp/chatterbox-fork-agent-out/embry-answerability-runtime-block/20260708T010111Z-answerability-runtime-block/receipt.json`

That run replayed all twelve blocked answerability cases against the live
`/tau/voice-render` endpoint. It reported `mocked=false`, `live=true`,
`ok=true`, `case_count=12`, and `failed_gates=[]`. Each child response returned
server `ok=false` with `answerability_blocks_speech` and
`answerability_failed_gates_present`, and no child produced a
`finished_response_audio` file. This proves the voice-render boundary now
suppresses blocked memory answers before Chatterbox audio; it does not prove the
memory service chose the right answer in the first place.

Latest matrix memory/search subset receipt:

`/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260708T000144Z-matrix-simple-memory-search-v2/receipt.json`

That run executed `16` simple sessions from
`docs/EMBRY_STRESS_SESSION_MATRIX.json` with `mocked=false`, `live=true`, and
`ok=false`. It passed the four Brave Search research sessions and failed all
four SPARTA QRA sessions, all four persona-memory recall sessions, and all four
persona-memory miss sessions. The failures show that Embry currently needs a
stricter answerability gate before speaking memory answers.

Latest matrix medium memory/search subset receipt:

`/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260708T014152Z-matrix-medium-memory-search/receipt.json`

That run executed `16` medium sessions from the same matrix with `mocked=false`,
`live=true`, and `ok=false`. The four Brave Search research sessions passed.
All twelve medium SPARTA/persona-memory sessions failed answerability gates:
SPARTA QRA prompts still leaked S0609/deprecated-control or missing-acceptance
answers, persona-memory recall still used unrelated source collections, and
persona-memory miss prompts still answered unrelated records instead of
clarifying. These failures are now receipt-backed medium cases rather than
`not_run`.

Latest matrix advanced memory/search subset receipt:

`/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260708T015631Z-matrix-advanced-memory-search/receipt.json`

That run executed `16` advanced sessions with `mocked=false`, `live=true`, and
`ok=false`. The four Brave Search research sessions passed. The twelve advanced
SPARTA/persona-memory cases failed the same answerability classes as the simple
and medium runs: S0609/deprecated-control leakage, unrelated persona-memory
source collections, and memory-miss prompts answering unrelated records instead
of clarifying.

Latest matrix advanced Tau/direct-skill subset receipt:

`/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260708T020325Z-matrix-advanced-routes-16-31/receipt.json`

That run executed `16` advanced Tau/direct-skill sessions with `mocked=false`,
`live=true`, and `ok=false`. The four advanced Tau orchestration sessions
reached the Tau wrapper but still produced no `tau.agent_handoff.v1` work order
or DAG receipt. The twelve advanced direct-skill sessions for
create-evidence-case, create-figure, and analytics confirmed the required skill
files exist, but no Tau handoff, `tau.dag_receipt.v1`, or
`skill.call.receipt.v1` was emitted. The matrix now records `26` passed, `126`
failed, and `148` not-run sessions.

Latest matrix advanced route subset receipt:

`/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260708T020917Z-matrix-advanced-routes-32-47/receipt.json`

That run executed the next `16` advanced sessions with `mocked=false` and
`ok=false`. Overall `live=false` because the four advanced Chat UX rows still
hit `runner_route_not_implemented`. The eight SPARTA-validator and Embry
voice-control direct-skill rows were live preflight failures: Tau found the
required skills but emitted no Tau handoff, DAG, or `skill.call.receipt.v1`.
The four interruption rows exercised live cancel/duck/stop endpoint paths but
still lack interruption-detection, new-turn, stale-audio, non-primary rejection,
and Tau-wait natural-stop receipts. The matrix now records `26` passed, `142`
failed, and `132` not-run sessions.

Latest matrix advanced speaker/factory/tone subset receipt:

`/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260708T021302Z-matrix-advanced-routes-48-63/receipt.json`

That run selected the remaining `12` advanced sessions with `mocked=false` and
`ok=false`. Overall `live=false` because the four factory-noise rows still hit
`runner_route_not_implemented`. Four speaker-identity rows passed live
`memory.speaker.resolve` policy checks. Tone/emotion passed only the frustrated
de-escalation case; hostile, discouraged, and speaker-overlap inputs failed
their expected tone-family gates. The matrix now records `31` passed, `149`
failed, and `120` not-run sessions.

Latest matrix adversarial memory/search subset receipt:

`/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260708T021629Z-matrix-adversarial-memory-search/receipt.json`

That run executed `16` adversarial memory/search sessions with `mocked=false`,
`live=true`, and `ok=false`. The four Brave Search research sessions passed.
All twelve adversarial SPARTA/persona-memory sessions failed answerability
gates: SPARTA QRA prompts still leaked S0609/deprecated-control or
missing-acceptance answers, persona-memory recall still used unrelated source
collections, and persona-memory miss prompts still answered unrelated records
instead of clarifying. The matrix now records `35` passed, `161` failed, and
`104` not-run sessions.

Latest matrix adversarial Tau/direct-skill subset receipt:

`/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260708T022326Z-matrix-adversarial-routes-16-31/receipt.json`

That run executed `16` adversarial Tau/direct-skill sessions with
`mocked=false`, `live=true`, and `ok=false`. The four adversarial Tau
orchestration sessions reached the Tau wrapper but still produced no
`tau.agent_handoff.v1` work order or DAG receipt. The twelve adversarial
direct-skill sessions for create-evidence-case, create-figure, and analytics
confirmed the required skill files exist, but no Tau handoff,
`tau.dag_receipt.v1`, or `skill.call.receipt.v1` was emitted. The matrix now
records `35` passed, `177` failed, and `88` not-run sessions.

Latest matrix adversarial route subset receipt:

`/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260708T022636Z-matrix-adversarial-routes-32-47/receipt.json`

That run executed the next `16` adversarial sessions with `mocked=false` and
`ok=false`. Overall `live=false` because the four adversarial Chat UX rows
still hit `runner_route_not_implemented`. The SPARTA validator and Embry
voice-control direct-skill cases reached Tau and found the required skill files
but emitted no Tau handoff, DAG, or `skill.call.receipt.v1`. The interruption
cases exercised live cancel/duck/stop endpoint paths but still lack
interruption-detection, new-turn, stale-audio, non-primary rejection, and
Tau-wait natural-stop receipts. The matrix now records `35` passed, `193`
failed, and `72` not-run sessions.

Latest matrix adversarial speaker/factory/tone subset receipt:

`/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260708T023001Z-matrix-adversarial-routes-48-63/receipt.json`

That run selected the remaining `12` adversarial sessions with `mocked=false`
and `ok=false`. Overall `live=false` because the four factory-noise rows still
hit `runner_route_not_implemented`. Four speaker-identity rows passed live
`memory.speaker.resolve` policy checks. Tone/emotion passed only the frustrated
de-escalation case; hostile, discouraged, and speaker-overlap inputs failed
their expected tone-family gates. All adversarial rows are now receipt-backed.
The matrix now records `40` passed, `200` failed, and `60` not-run sessions;
the remaining not-run rows are all soak.

Latest matrix soak memory/search subset receipt:

`/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260708T023312Z-matrix-soak-memory-search/receipt.json`

That run executed `16` soak memory/search sessions with `mocked=false`,
`live=true`, and `ok=false`. The four Brave Search research sessions passed.
All twelve soak SPARTA/persona-memory sessions failed answerability gates:
SPARTA QRA prompts still leaked S0609/deprecated-control or missing-acceptance
answers, persona-memory recall still used unrelated source collections, and
persona-memory miss prompts still answered unrelated records instead of
clarifying. The matrix now records `44` passed, `212` failed, and `44` not-run
sessions.

Latest matrix soak Tau/direct-skill subset receipt:

`/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260708T024031Z-matrix-soak-routes-16-31/receipt.json`

That run executed `16` soak Tau/direct-skill sessions with `mocked=false`,
`live=true`, and `ok=false`. The four soak Tau orchestration sessions reached
the Tau wrapper but still produced no `tau.agent_handoff.v1` work order or DAG
receipt. The twelve soak direct-skill sessions for create-evidence-case,
create-figure, and analytics confirmed the required skill files exist, but no
Tau handoff, `tau.dag_receipt.v1`, or `skill.call.receipt.v1` was emitted. The
matrix now records `44` passed, `228` failed, and `28` not-run sessions.

Latest matrix soak route subset receipt:

`/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260708T024412Z-matrix-soak-routes-32-47/receipt.json`

That run executed the next `16` soak sessions with `mocked=false` and
`ok=false`. Overall `live=false` because the four soak Chat UX rows still hit
`runner_route_not_implemented`. The SPARTA validator and Embry voice-control
direct-skill cases reached Tau and found the required skill files but emitted
no Tau handoff, DAG, or `skill.call.receipt.v1`. The interruption cases
exercised live cancel/duck/stop endpoint paths but still lack
interruption-detection, new-turn, stale-audio, non-primary rejection, and
Tau-wait natural-stop receipts. The matrix now records `44` passed, `244`
failed, and `12` not-run sessions.

Latest matrix soak speaker/factory/tone subset receipt:

`/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260708T024716Z-matrix-soak-routes-48-63/receipt.json`

That run selected the final `12` soak sessions with `mocked=false` and
`ok=false`. Overall `live=false` because the four factory-noise rows still hit
`runner_route_not_implemented`. Four speaker-identity rows passed live
`memory.speaker.resolve` policy checks. Tone/emotion passed only the frustrated
de-escalation case; hostile, discouraged, and speaker-overlap inputs failed
their expected tone-family gates. All `300` matrix sessions are now
receipt-backed: `49` passed, `251` failed, and `0` not-run. This proves matrix
coverage, not the full live RealtimeSTT -> memory/Tau -> Chatterbox -> Chat UX
loop.

Latest matrix medium Tau/direct-skill subset receipt:

`/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260708T014802Z-matrix-medium-routes-16-31/receipt.json`

That run executed `16` medium Tau/direct-skill sessions with `mocked=false`,
`live=true`, and `ok=false`. The four medium Tau orchestration sessions reached
the Tau wrapper but still produced no `tau.agent_handoff.v1` work order or DAG
receipt. The twelve medium direct-skill sessions for create-evidence-case,
create-figure, and analytics confirmed the required skill files exist, but no
Tau handoff, `tau.dag_receipt.v1`, or `skill.call.receipt.v1` was emitted.

Latest matrix medium route subset receipt:

`/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260708T015035Z-matrix-medium-routes-32-47/receipt.json`

That run executed the next `16` medium sessions with `mocked=false` and
`ok=false`. The SPARTA validator and Embry voice-control direct-skill cases
reached Tau and found the required skill files but emitted no Tau handoff, DAG,
or `skill.call.receipt.v1`. The interruption cases exercised live
cancel/duck/stop endpoints but still lack interruption-detection, new-turn,
non-primary rejection, stale-audio, and Tau-wait natural-stop receipts. The Chat
UX medium rows are mapped to the deterministic Chat UX gate audit: replay and
inline reasoning trace pass; turn-id lineage and `$extract-entities` underline
rendering remain failed.

Latest matrix medium speaker/factory/tone subset receipt:

`/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260708T015351Z-matrix-medium-routes-48-63/receipt.json`

That run selected the remaining `12` medium cases. Four speaker identity cases
passed against live memory `/speaker/resolve` policy. Tone/emotion repeated the
simple pattern: the warm/frustrated case passed, while hostile, discouraged, and
two-speaker-overlap prompts still returned `memory_confident` instead of the
required boundary/support/one-at-a-time tones. Factory-noise medium rows are
mapped to concrete current capture receipts, not the runner's generic gap:
current source 67 and webcam paths fail at RMS/capture, while source 62 fails
RealtimeSTT/rung7 and Horus speaker-resolution/memory gates.

Latest matrix simple-rest receipt:

`/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260708T000951Z-matrix-simple-rest/receipt.json`

That run executed the next `24` simple sessions with `mocked=false`,
`live=false`, and `ok=false`. Every selected route failed with
`runner_route_not_implemented`: Tau tool orchestration, Chat UX sync,
interruption, speaker identity, factory noise, and tone/emotion. The per-case
event ledger is
`/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260708T000951Z-matrix-simple-rest/matrix-case-events.jsonl`
with `24` completed case events. This is useful failure evidence: the Sessions
matrix now distinguishes answerability failures from route families that do not
yet have executable live sanity implementations.

Latest speaker identity ledger receipt:

`/tmp/chatterbox-fork-agent-out/embry-speaker-identity-ledger/20260708T004440Z-speaker-identity-ledger/receipt.json`

That run migrated the four simple `memory.speaker.resolve` cases into the
canonical event-journal shape. It reported `mocked=false`, `live=true`, and
`ok=true` with `17` journal events: known Horus resolved to
`horus_lupercal` with personal memory allowed, unknown speaker failed closed,
ambiguous low-confidence failed closed, and Horus/female overlap returned
`ambiguous` with no authoritative speaker. The proof scope is explicitly
`live_memory_speaker_resolution_policy_not_audio_identity`, so it does not prove
RealtimeSTT audio identity, diarization correctness, or raw voice embedding
quality.

Latest matrix tone/emotion receipt:

`/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260708T001850Z-matrix-tone-simple/receipt.json`

That run re-executed the four simple `memory.intent.voice_delivery` sessions
with an executable live `/intent` route. It reported `mocked=false`,
`live=true`, and `ok=false`: one prompt passed, while hostile, discouraged, and
two-speaker-overlap prompts all returned `memory_confident`/`satisfied` instead
of the expected conversational tones. This converts the prior generic
`runner_route_not_implemented` tone failures into concrete `$memory` intent
tone-selection failures.

Latest matrix Tau preflight receipt:

`/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260708T002830Z-matrix-tau-simple/receipt.json`

That run re-executed the four simple `tau.agent_handoff` sessions with a live
read-only Tau doctor preflight. It reported `mocked=false`, `live=true`, and
`ok=false`: Tau itself was reachable (`doctor` return code `0` for each case),
but no `tau.agent_handoff.v1` work order or DAG receipt was created for the
Embry session prompts. These are now concrete missing-handoff failures, not
generic runner gaps.

Latest matrix direct-skill preflight receipts:

- `/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260708T012426Z-skill-create-evidence-simple/receipt.json`
- `/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260708T012426Z-skill-create-figure-simple/receipt.json`
- `/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260708T012426Z-skill-analytics-simple/receipt.json`
- `/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260708T012426Z-skill-sparta-validator-simple/receipt.json`
- `/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260708T012426Z-skill-voice-control-simple/receipt.json`

Those five runs covered the twenty simple direct-skill sessions with
`mocked=false`. Each run reached the live Tau wrapper (`doctor` return code `0`)
and confirmed the required skill file exists in `agent-skills`, but every case
failed because no `tau.agent_handoff.v1`, `tau.dag_receipt.v1`, or
`skill.call.receipt.v1` was emitted. These are concrete missing Tau skill
gateway failures, not proof that the skills executed.

Latest matrix interruption preflight receipt:

`/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260708T013317Z-matrix-interruption-simple/receipt.json`

That run covered the four simple `chatterbox.turn_control` interruption cases
with `mocked=false`, `live=true`, and `ok=false`. Each case exercised the live
Chatterbox cancel/duck/stop endpoints and observed action order
`cancel -> duck -> stop`, but the cases still fail because the live suite has
not emitted interruption-detection receipts, linked audio playback/stale-byte
measurements, new-turn-wins evidence, non-primary rejection evidence, or Tau
tool-wait natural-stop evidence for those prompts. This replaces the old
generic `runner_route_not_implemented` label for simple interruption cases.

Latest matrix factory-noise receipts:

- `/tmp/chatterbox-fork-agent-out/voice-chat-e2e/voice-chat-e2e-20260707T232441Z-stress-current/S06-factory-noise/rung8-loopback-listener.json`
- `/tmp/chatterbox-fork-agent-out/voice-chat-e2e/factory-source-matrix-20260707T232938Z/source-62/S06-factory-noise/rung8-loopback-listener.json`
- `/tmp/chatterbox-fork-agent-out/voice-chat-e2e/factory-source-matrix-20260707T232938Z/source-67/S06-factory-noise/rung8-loopback-listener.json`
- `/tmp/chatterbox-fork-agent-out/voice-chat-e2e/fresh-s06-webcam-20260707T143939Z/S06-factory-noise/rung8-loopback-listener.json`

Those receipts now back the four simple `realtimestt.factory_capture` matrix
cases. Current failures are concrete audio/ASR boundaries: the latest stress
capture from source 67 had RMS `7`, current source 67 had RMS `6`, the webcam
path recorded zero-RMS audio, and source 62 captured non-silent audio but failed
RealtimeSTT/rung7 and Horus speaker-resolution/memory recall gates. These cases
remain failed; they are no longer generic runner gaps.

Latest matrix Chat UX gate audit:

`/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260708T013912Z-chat-ux-gate-audit/audit.json`

That deterministic audit reads existing UI and voice receipts. It lets the
matrix mark the simple replay and inline-reasoning Chat UX cases as passed:
dynamic replay reduced the chat to the current turn, embedded audio artifacts
in the shared Chat UX, completed without static reset, and showed the reasoning
trace during replay. Two simple Chat UX cases remain failed: there is still no
linked `assistant.response.plan.v1` -> `chat.render.receipt.v1` lineage proof
that chat text and Chatterbox audio share the same `turn_id`, and there is no
linked `$extract-entities` receipt proving faint underline entity rendering in
the spoken transcript.

Current Sessions matrix artifact:

`docs/EMBRY_STRESS_SESSION_MATRIX.json`

Generated by:

```bash
python3 scripts/build_embry_stress_session_matrix.py --out docs/EMBRY_STRESS_SESSION_MATRIX.json
```

The matrix contains `300` labeled sessions across `15` route families and `5`
difficulty levels. It marks only receipt-backed cases as pass/fail: currently
`26` passed, `110` failed, and `164` are `not_run`. This is the intended source
for the Embry Voice Sessions pane; unrun cases must not be shown as passing.

The current matrix is now a generated case contract, not just a session list.
Every row is `embry.stress_case.v1` with an oracle type, required receipts,
required gates, expected route policy, and expected answerability policy. The
direct-skill route families are:

- `tau.skill.create_evidence_case`
- `tau.skill.create_figure`
- `tau.skill.analytics`
- `tau.skill.sparta_validator`
- `tau.skill.embry_voice_control`

Those 100 direct-skill cases require `tau.agent_handoff.v1` and
`skill.call.receipt.v1`; they explicitly forbid UI or Chatterbox direct skill
calls. They are not marked passing until a live Tau skill gateway and receipt
path exists.

Every generated case also carries `conversation_requirements` because Embry
must not answer in a flat or neutral style. The matrix currently has
`flat_neutral_allowed=false` for all `300` cases, `15` route-specific
conversation arcs, required `$memory` intent voice delivery, required inline
emotion tags, required pause strategy, and a required interruption strategy.
The generated metadata is a contract for the runner and Chat UX; it does not
prove that `$memory` or Tau already satisfy the delivery policy at runtime.

## Required Receipt Fields

Every scenario receipt must include:

- `mocked=false`
- `live=true`
- `failed_gates=[]`
- audio artifact paths and hashes where audio is involved
- service URLs or command invocations
- transcript, speaker, memory, Tau, or Chatterbox evidence appropriate to the
  boundary
- audible playback ledger when `--audible-playback` is used
- `claims.proves`
- `claims.does_not_prove`

## Current Test List

| ID | Test | Real-world stimulus | Required proof | Latest status |
|---|---|---|---|---|
| S01 | Simple voice turn | Real captured WAV into RealtimeSTT/listener | ASR final, Tau request, Chatterbox output audio | Passed in latest full-suite receipt. |
| S02 | Known Horus memory | Horus stress WAV and speaker evidence | `$memory /speaker/resolve` maps to `horus_lupercal`, memory/Tau path proceeds | Passed in latest full-suite receipt. |
| S03 | Unknown speaker | Live `$memory /speaker/resolve` with no candidates | personal memory disabled, identity clarification prompt selected, Chatterbox renders clarification | Passed in latest full-suite receipt. |
| S04 | Ambiguous speaker | Live `$memory /speaker/resolve` with low/close candidates | personal memory disabled, clarification response rendered | Passed in latest full-suite receipt. |
| S05 | Male plus female distractor / overlap | Generated male/female overlapping WAV through live pyannote, memory intent, Tau, Chatterbox | two anonymous speakers detected, turn-taking clarification, `one_at_a_time_interrupt` tone | Passed in latest full-suite receipt; does not prove word-level separation. |
| S06 | Horus plus factory/noisy acoustic path | Horus factory-stress WAV played through speaker and captured by real source `67` | captured WAV RMS > gate, RealtimeSTT/rung7 speaker memory path, Horus speaker resolution | Passed in latest full-suite receipt with source `67`; Jabra source `62` was silent and failed earlier. |
| S08 | Barge-in / stale turn cancellation | Live Chatterbox stream and turn cancel endpoint | old-turn stream emits zero bytes after cancel | Passed in latest full-suite receipt; physical speaker buffer flush remains separate. |
| S09 | Blessed QRA hit | Listener-memory-Tau-QRA child smoke | near-exact memory gate, blessed cache hit, selected Embry variant | Passed inside continuous core scenario. |
| S10 | Blessed QRA disabled | Tau request with `use_blessed_qra_cache=false` | request bypasses cache and renders through normal Chatterbox path | Passed in latest full-suite receipt. |
| S12 | Tone steering | `$memory /intent` voice delivery into Tau/Chatterbox | tone and delivery stage are present in Tau/Chatterbox receipt | Passed inside continuous core scenario. |
| S13 | Browser getUserMedia transport | Real browser microphone capture with no fake media flags | browser sends PCM frames to Python listener and writes captured WAV | Passed in latest full-suite receipt; production chat UI screenshot agreement remains separate. |
| P01 | Embry boundary personality audition | Five one-at-a-time boundary variants through live Tau/Chatterbox | each variant renders a WAV and plays through sink `64` | Passed in latest personality audition receipt; human acceptance remains open. |
| I01 | SPARTA QRA answer relevance | Live `$memory /intent` and `/answer` for a SPARTA QRA acceptability question | answer must discuss acceptable QRA evidence, not an unrelated control-exclusion record | Failed in latest scripted intelligence stress receipt. |
| I02 | Horus persona-memory recall relevance | Live `$memory /intent` and `/answer` for "Where did Horus Lupercal grow up?" | answer must include Cthonia or fail closed | Failed in latest scripted intelligence stress receipt. |
| I03 | Persona-memory miss fail-closed | Live `$memory /intent` and `/answer` for an unsupported private codeword question | answer must clarify/no-answer, not return unrelated records | Failed in latest scripted intelligence stress receipt. |
| I04 | External research route | `$brave-search` query for pyannote diarization/overlap support | search command returns relevant pyannote sources as source-bearing evidence | Passed in latest scripted intelligence stress receipt. |

## Current Command

The current full run command is:

```bash
python3 scripts/smoke_voice_chat_e2e.py \
  --out-dir /tmp/chatterbox-fork-agent-out/voice-chat-e2e/<run-id> \
  --scenario all \
  --factory-record-target 67 \
  --factory-sink-target 64 \
  --playback-sink-target 64 \
  --audible-playback \
  --timeout-s 1200
```

The current intelligence stress command is:

```bash
python3 scripts/smoke_embry_intelligence_stress.py \
  --out-dir /tmp/chatterbox-fork-agent-out/embry-intelligence-stress/<run-id> \
  --render-spoken-failures \
  --playback-sink-target 64 \
  --playback-timeout-s 20 \
  --timeout-s 180
```

The current session-matrix command is:

```bash
python3 scripts/build_embry_stress_session_matrix.py \
  --out docs/EMBRY_STRESS_SESSION_MATRIX.json
```

Latest audible playback counts:

- `S01_S02_S08_S09_S12`: 6 WAV artifacts played.
- `S08`: 1 WAV artifact played.
- `S10`: 2 WAV artifacts played.
- `S03-unknown-speaker`: 2 WAV artifacts played.
- `S04-ambiguous-speaker`: 2 WAV artifacts played.
- `S05`: 4 WAV artifacts played.
- `S06`: 4 WAV artifacts played.
- `S13`: 2 WAV artifacts played.

Source `67` was selected because live source probing showed non-silent capture:

- source `67`: RMS `517`
- source `68`: RMS `236`
- source `62` / Jabra mic: RMS `0`

Follow-up source tests:

- `/tmp/chatterbox-fork-agent-out/voice-chat-e2e/voice-chat-e2e-20260703T212255Z-factory-acoustic-src67/index.json`
  passed S06 with source `67`.
- `/tmp/chatterbox-fork-agent-out/voice-chat-e2e/voice-chat-e2e-20260703T222756Z-factory-src68/index.json`
  failed S06. It captured non-silent audio, RMS `227`, but RealtimeSTT/VAD and
  Horus speaker resolution failed.
- `/tmp/chatterbox-fork-agent-out/voice-chat-e2e/voice-chat-e2e-20260703T212038Z-factory-acoustic/index.json`
  failed S06 with Jabra source `62` because captured RMS was `0`.

Current source matrix follow-up:

`/tmp/chatterbox-fork-agent-out/voice-chat-e2e/factory-source-matrix-20260707T232938Z`

Observed current results:

- source `34`: failed because the harness could not resolve a Pulse source.
- source `62`: captured RMS `214`, but RealtimeSTT returned an empty transcript
  and speaker resolution stayed unknown at confidence `0.5374` below threshold
  `0.62`.
- source `67`: failed capture RMS with RMS `6`.
- source `68`: failed capture RMS with RMS `5`.

Browser-ASR failure receipt:

`/tmp/chatterbox-fork-agent-out/voice-chat-e2e/voice-chat-e2e-20260703T222548Z-browser-asr-audible/continuous-voice-loop.json`

The browser transport captured a real WAV, but RealtimeSTT and direct Whisper
both returned an empty transcript. The direct Whisper receipt is:

`/tmp/chatterbox-fork-agent-out/voice-chat-e2e/voice-chat-e2e-20260703T222548Z-browser-asr-audible/direct-whisper-browser-capture.json`

Browser-ASR configuration matrix:

`/tmp/chatterbox-fork-agent-out/voice-chat-e2e/browser-asr-matrix-20260703T223244Z/browser-asr-matrix.json`

Observed results:

- `jabra_ns_agc`: browser captured audio, direct Whisper transcript was empty.
- `jabra_ec_ns_agc`: browser captured louder audio and direct Whisper returned
  only `You`, which is not sufficient for the listener path.
- `jabra_raw`: browser captured audio, direct Whisper transcript was empty.
- `default_ns_agc`: browser capture failed audio gates with zero RMS.

Best browser config follow-up:

`/tmp/chatterbox-fork-agent-out/voice-chat-e2e/voice-chat-e2e-20260703T223350Z-browser-asr-ec-ns-agc/continuous-voice-loop.json`

That run still failed the full browser getUserMedia -> RealtimeSTT loop with
`realtimestt_listener_ok` and `listener_transcript_present`.

Fresh browser capture quality follow-up:

- `/tmp/chatterbox-fork-agent-out/voice-chat-e2e/browser-quality-20260705T132832Z/continuous-voice-loop.json`
  selected `Jabra SPEAK 510 Mono` with echo cancellation, noise suppression, and
  AGC enabled while playing the fixture through PipeWire sink `64`. Browser
  transport passed and wrote a valid WAV, but RealtimeSTT and direct Whisper
  returned an empty transcript.
- `/tmp/chatterbox-fork-agent-out/voice-chat-e2e/browser-quality-raw-20260705T133055Z/continuous-voice-loop.json`
  selected `Jabra SPEAK 510 Mono` with browser audio processing disabled.
  Browser transport passed with higher audio energy, but RealtimeSTT and direct
  Whisper still returned an empty transcript.
- `/tmp/chatterbox-fork-agent-out/voice-chat-e2e/browser-quality-webcam-20260705T134007Z/continuous-voice-loop.json`
  selected `HD Pro Webcam` with browser audio processing disabled and played
  through Jabra sink `64`. This passed the full browser getUserMedia ->
  RealtimeSTT -> diarization/speaker evidence -> memory/Tau -> Chatterbox loop
  with `mocked=false`, `live=true`, empty `failed_gates`, and transcript:
  `He saw tracked weapon carried, automated artillery, nests with more or even
  eight automatic cannons shackled together on power path.`
- `/tmp/embry-voice-browser-quality-webcam-ui-proof.json` submitted that
  browser-ASR transcript to `http://localhost:3002/#embry-voice`; the shared
  Chat UX rendered the user turn, memory/Tau response, and a fresh
  `ux-lab-embry-live` Chatterbox WAV. Screenshot:
  `/tmp/embry-voice-browser-quality-webcam-ui-proof.png`.

## Tests Still Needed For Higher Confidence

These are not closed by the latest suite:

- repeated factory-noise runs across multiple source positions and volume
  levels
- Horus plus female distractor with identity reconciliation, not only overlap
  boundary behavior
- browser chat UI screenshot agreement against the same receipt/run id for live
  interruption and barge-in behavior
- browser microphone device-selection policy: HD Pro Webcam capture is
  ASR-usable in the latest run, while Jabra browser capture still writes real
  WAVs that transcribe as empty text
- physical playback buffer flush after cancel
- subjective human voice quality review for Embry and Horus
- stronger Embry personality arcs for boundary lines such as
  `one_at_a_time_interrupt`; the current audio can be intelligible while still
  lacking character
- longer multi-turn memory conversations with memory miss, memory hit, and
  identity changes in the same session
- upstream answerability quality for SPARTA QRA and persona-memory questions,
  because live `/answer` can return unrelated records; the voice-render boundary
  now blocks `block_before_speech` decisions before Chatterbox audio

## Failure Handling Rule

Do not weaken gates to make this suite pass. If a real-world source is silent,
as Jabra source `62` was for S06, preserve the failure receipt and either fix
the routing or select a source that produces non-silent real capture with its
source id recorded in the receipt.
