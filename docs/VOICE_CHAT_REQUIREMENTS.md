# Embry Voice Chat Requirements And E2E Sanity Matrix

Status date: 2026-07-03

This document defines the acceptance bar for Embry voice chat using
RealtimeSTT/listener input, `$memory` and Tau coordination, and Chatterbox
spoken output. It is a requirements and evidence map, not a product-readiness
claim.

## Readiness Rule

Embry voice chat is ready for a chat interface only when every required row
below has a current non-mocked receipt with `mocked=false`, `live=true`, empty
`failed_gates`, and an inspectable artifact path. Unit tests, patched clients,
fixture-only assertions, and DOM checks are wiring evidence only.

## Current Evidence Baseline

The strongest current full-loop proof-slice receipt is:

`/tmp/chatterbox-fork-agent-out/continuous-voice-loop-20260703T193305Z-full-goal-probes/continuous-voice-loop.json`

That receipt currently covers a captured input WAV through RealtimeSTT external
audio, speaker resolution through enrollment and memory evidence, memory/Tau
routing, Chatterbox output, blessed QRA fast path, overlap one-at-a-time
behavior, and stream cancel child proof. It does not prove all browser,
factory-floor, subjective quality, or chat-interface behaviors.

Other relevant receipts:

- `/tmp/chatterbox-fork-agent-out/overlap-turn-control-20260703T192737Z-live/overlap-turn-control.json`
- `/tmp/chatterbox-fork-agent-out/stream-cancel-20260702T1150/stream-cancel.json`
- `/tmp/chatterbox-fork-agent-out/listener-memory-tau-qra-20260702T140108Z-creation-hook/listener-memory-tau-qra.json`
- `/tmp/chatterbox-fork-agent-out/tau-voice-render-20260702T134405Z.json`

## Required Product Capabilities

| ID | Requirement | Required non-mocked proof | Current status |
|---|---|---|---|
| VC-01 | Every voice turn has stable `session_id`, `turn_id`, event sequence, text hashes, and renderer request envelope. | Continuous receipt showing listener, coordinator, memory/Tau, and Chatterbox events for the same turn ids. | Partial: current full-loop receipt covers the proof-slice; chat UI path still needs the same ledger. |
| VC-02 | Browser microphone capture can feed usable ASR text. | Browser `getUserMedia` receipt with actual captured audio artifact, ASR final text, WER/quality gate, and device/constraints metadata. | Proven for HD Pro Webcam capture through the full browser -> RealtimeSTT -> memory/Tau -> Chatterbox loop; still device-sensitive because Jabra browser captures produced real WAVs but empty ASR transcripts. |
| VC-03 | PipeWire or loopback capture can be used as a reliable local transport when browser acoustic capture is weak. | Receipt with capture source, device/monitor name, input WAV, ASR transcript, and latency fields. | Partial: captured WAV full-loop path works; transport must be made selectable in the chat interface. |
| VC-04 | Listener emits frame, VAD, partial transcript, final transcript, and heard-text ledger events. | RealtimeSTT/listener receipt with frame counts, speech start/stop, partials, final, ASR backend, and timing. | Partial: Rung 7 style receipts exist; browser UI event parity remains pending. |
| VC-05 | Speaker identity is resolved before personal memory recall. | `/speaker/resolve` evidence using enrollment/memory evidence, not pyannote label assumption. | Partial/proven in proof-slice for Horus; unknown, ambiguous, and non-primary cases still need regression receipts. |
| VC-06 | Horus Lupercal persona is the primary enrolled speaker identity, not Graham. | Receipt and enrollment metadata showing Horus voice/persona maps to `horus_lupercal`. | Partial: proof-slice maps Horus; product enrollment docs and UI labels still need audit. |
| VC-07 | Unknown speaker fails closed and Embry asks who she is speaking with. | Live unknown-speaker receipt with no personal memory recall and one of the approved identity-clarification utterances. | Proven for current receipt; keep in regression matrix. |
| VC-08 | Ambiguous speaker fails closed and asks for clarification. | Live ambiguous-speaker receipt with speaker scores too close, no personal recall, and clarification tone. | Missing. |
| VC-09 | Two non-Embry speakers at once trigger a boundary response such as "Hey, one at a time?" | Pyannote/diarization receipt with `speaker_count >= 2`, overlap seconds, memory intent `CLARIFY`, tone `one_at_a_time_interrupt`, and Chatterbox output. | Proven for one proof-slice; needs noisy-room regression matrix. |
| VC-10 | Factory-floor background noise is filtered so the primary speaker remains intelligible. | Noise-stress receipt with factory noise source, SNR, speaker target, transcript WER, diarization/speaker decision, and false-positive rate. | Missing. |
| VC-11 | Female distractor voice is filtered or classified as non-primary when Horus is the active speaker. | Mixed-speaker receipt with Horus + female distractor audio, speaker decision, ASR final for Horus, and rejected distractor ledger. | Missing. |
| VC-12 | Embry stops or ducks old speech when the user barges in. | End-to-end receipt where playback starts, user speech begins, old turn is cancelled, stale chunks do not play, and new turn wins. | Partial: stream cancel and proof-slice child receipt show zero old-turn bytes after cancel; live browser playback/device flush remains pending. |
| VC-13 | No stale old-turn audio plays after cancel. | Byte-level stream/playback ledger with `old_turn_bytes_after_cancel == 0`. | Proven at stream boundary; physical speaker buffer behavior remains out of scope. |
| VC-14 | `$memory /intent` routes tone and delivery policy for voice turns. | Intent receipt showing selected action, tone, delivery stage, and reason, then Tau/Chatterbox applying that tone. | Partial: tone routing and one-at-a-time intent exist; complete UI tone dropdown to Chatterbox behavior needs proof. |
| VC-15 | Chatterbox receives easy tone controls from coordinator, not hidden UI-only labels. | Chatterbox request/receipt showing `voice_tone`, pause policy, delivery stage, and generated chunks. | Partial: server supports tone metadata; Dream UI dropdown behavior still needs endpoint proof. |
| VC-16 | Near-exact approved QRA memory hits play blessed Embry audio immediately. | Memory recall near-exact QRA gate plus blessed cache hit receipt with selected variant and no live generation. | Proven for current proof-slice; needs speaker-scoped regression cases. |
| VC-17 | Blessed QRA cache can be disabled per request. | Receipt showing same QRA request with fast path disabled and normal Chatterbox generation used. | Proven for current receipts; keep in regression matrix. |
| VC-18 | QRA creation can auto-generate up to five Embry variants with different pause/emotional arcs. | Creation-hook receipt with approved status, variant count, chunk hashes, and ledger update. | Partial/proven for one QRA; needs variant policy regression and human quality review. |
| VC-19 | Embry asks when she does not know who the speaker is. | Unknown-speaker live receipt plus approved utterance bank with about 20 variants. | Proven for current receipt with 20 prompt variants. |
| VC-20 | Embry uses speaker-scoped conversational memory for known speakers. | Receipt where Horus asks a personal question and Embry recalls relevant Horus conversation evidence, or asks if evidence is absent. | Missing. |
| VC-21 | Embry does not hallucinate personal memory when `$memory` has no evidence. | Receipt with memory miss, no unsupported claim, and clarification question. | Missing. |
| VC-22 | Wait/holding utterances prevent long dead air while memory, Tau, or tools run. | Latency receipt with wait decision, spoken/muted wait utterance, and first-audio budget. | Partial in ladder docs/receipts; full loop latency budgets need consolidation. |
| VC-23 | Latency budgets are measured at every boundary. | Receipt fields for mic frame received, VAD start/stop, ASR final, speaker resolve, memory intent, memory recall, Tau request, first audio byte, final chunk. | Partial: proof-slice has several boundaries; browser and playback fields remain pending. |
| VC-24 | Chat interface supports voice input as commonly as text input. | Browser/chat receipt with voice turn entry, transcript display, memory/Tau evidence pointer, Chatterbox playback, interruption, and visible state. | Partial/proven for browser-derived transcript handoff into `#embry-voice`: shared Chat UX shows the ASR text, memory/Tau response, and fresh Chatterbox audio. Live interruption from the browser chat surface still needs a receipt. |
| VC-25 | Subjective voice quality is acceptable for Embry and Horus testing. | Human quality review ledger with audio artifacts, target personas, defects, and accept/reject notes. | Pending human-quality review. |

## Required Non-Mocked E2E Scenario Set

The final sanity runner should produce one index receipt under
`/tmp/chatterbox-fork-agent-out/voice-chat-e2e/<run-id>/index.json` and child
receipts for each scenario.

| Scenario | Purpose | Minimum pass gates |
|---|---|---|
| S01 simple voice turn | Prove one spoken user request produces one spoken Embry response. | ASR final non-empty, response text non-empty, response WAV exists, output ASR matches response text within WER threshold. |
| S02 known Horus memory | Prove known speaker identity unlocks speaker-scoped memory recall. | Speaker resolves to `horus_lupercal`, memory evidence exists, response uses only returned evidence. |
| S03 unknown speaker | Prove Embry asks who she is speaking with. | Speaker unresolved, personal memory recall skipped, tone `identity_clarification`, approved prompt variant selected. |
| S04 ambiguous speaker | Prove close speaker scores fail closed. | Ambiguous scores recorded, no personal recall, clarification response spoken. |
| S05 Horus plus female distractor | Prove primary speaker focus under competing speech. | Horus accepted as primary or ambiguity triggered; distractor not treated as Horus memory authority. |
| S06 Horus plus factory noise | Prove noisy environment path. | Factory noise source recorded, SNR recorded, WER within threshold or fail-closed reason emitted. |
| S07 two non-Embry speakers overlap | Prove one-at-a-time boundary. | Diarization reports overlap, memory intent selects `one_at_a_time_interrupt`, Chatterbox speaks boundary response. |
| S08 barge-in | Prove interruption during Embry playback. | Old turn cancel event, old-turn stale chunks skipped, zero old-turn bytes after cancel, new turn response starts. |
| S09 blessed QRA hit | Prove immediate known-answer playback. | Near-exact memory QRA gate, cache hit, selected Embry variant, first audio latency below configured budget. |
| S10 blessed QRA disabled | Prove per-request bypass. | Same QRA does not use cache when disabled; normal render path emits fresh chunk hashes. |
| S11 memory miss | Prove no hallucinated memory. | Memory miss recorded, answer asks/clarifies instead of inventing facts. |
| S12 tone steering | Prove conversation tone reaches Chatterbox. | Intent tone selected, Tau request carries tone, Chatterbox receipt records same tone and delivery policy. |
| S13 chat UI voice path | Prove browser/chat integration. | Browser captures voice, transcript appears, evidence pointer appears, audio plays, screenshot and receipt agree. |

## Suggested Runner Contract

Command shape:

```bash
python3 scripts/smoke_voice_chat_e2e.py \
  --base-url http://127.0.0.1:8018 \
  --memory-url http://127.0.0.1:8601 \
  --listener-url http://127.0.0.1:8019 \
  --transport pipewire \
  --include-browser \
  --include-noise-stress \
  --out-dir /tmp/chatterbox-fork-agent-out/voice-chat-e2e/<run-id>
```

Current runner:

```bash
python3 scripts/smoke_voice_chat_e2e.py \
  --out-dir /tmp/chatterbox-fork-agent-out/voice-chat-e2e/<run-id> \
  --scenario continuous_core \
  --scenario stream_cancel \
  --scenario qra_disabled \
  --scenario unknown_speaker \
  --scenario ambiguous_speaker
```

Latest live runner receipts:

- `/tmp/chatterbox-fork-agent-out/voice-chat-e2e/voice-chat-e2e-20260703T214538Z-audible-all-v2/index.json`
  passed all currently implemented scenarios with `mocked=false`, `live=true`,
  empty `failed_gates`, and audible playback ledgers for every scenario through
  PipeWire sink `64`.
- `/tmp/chatterbox-fork-agent-out/voice-chat-e2e/stress-20260703T221132Z-audible-repeat/stress-summary.json`
  repeated the full audible suite three times; all three repeat receipts passed
  with `mocked=false`, `live=true`, and empty `failed_gates`.
- `/tmp/chatterbox-fork-agent-out/voice-chat-e2e/personality-audition-20260703T223052Z-scripted/personality-audition.json`
  rendered and audibly played five Embry boundary/personality variants through
  live Tau/Chatterbox.
- `/tmp/chatterbox-fork-agent-out/voice-chat-e2e/voice-chat-e2e-20260703T222548Z-browser-asr-audible/continuous-voice-loop.json`
  failed the stricter browser getUserMedia -> RealtimeSTT/ASR loop with
  `realtimestt_listener_ok` and `listener_transcript_present`; direct Whisper
  on the browser WAV also returned an empty transcript.
- `/tmp/chatterbox-fork-agent-out/voice-chat-e2e/browser-asr-matrix-20260703T223244Z/browser-asr-matrix.json`
  tested browser audio processing variants; only `jabra_ec_ns_agc` produced any
  direct Whisper text, and that transcript was only `You`.
- `/tmp/chatterbox-fork-agent-out/voice-chat-e2e/voice-chat-e2e-20260703T223350Z-browser-asr-ec-ns-agc/continuous-voice-loop.json`
  reran the full continuous browser path with the best browser config and still
  failed listener transcript gates.
- `/tmp/chatterbox-fork-agent-out/voice-chat-e2e/browser-quality-20260705T132832Z/continuous-voice-loop.json`
  captured real browser audio from `Jabra SPEAK 510 Mono` with echo
  cancellation, noise suppression, and AGC enabled while playing through
  PipeWire sink `64`; browser transport passed, but RealtimeSTT and direct
  Whisper returned an empty transcript.
- `/tmp/chatterbox-fork-agent-out/voice-chat-e2e/browser-quality-raw-20260705T133055Z/continuous-voice-loop.json`
  captured real browser audio from `Jabra SPEAK 510 Mono` with browser audio
  processing disabled; browser transport passed with higher audio energy, but
  RealtimeSTT and direct Whisper still returned an empty transcript.
- `/tmp/chatterbox-fork-agent-out/voice-chat-e2e/browser-quality-webcam-20260705T134007Z/continuous-voice-loop.json`
  passed the full browser getUserMedia -> RealtimeSTT -> diarization/speaker
  evidence -> memory/Tau -> Chatterbox loop using `HD Pro Webcam` microphone
  capture and Jabra sink `64` playback. It produced non-empty ASR text and
  empty `failed_gates`.
- `/tmp/embry-voice-browser-quality-webcam-ui-proof.json`
  submitted the HD Pro Webcam browser-ASR transcript to
  `http://localhost:3002/#embry-voice`; the shared Chat UX showed the transcript,
  returned HTTP 200 from `/api/projects/embry-voice/live-turn`, and linked a
  fresh `ux-lab-embry-live` Chatterbox WAV. Screenshot:
  `/tmp/embry-voice-browser-quality-webcam-ui-proof.png`.
- `/tmp/chatterbox-fork-agent-out/voice-chat-e2e/voice-chat-e2e-20260703T212337Z-all-realworld-src67/index.json`
  passed all currently implemented simple-to-advanced scenarios with
  `mocked=false`, `live=true`, empty `failed_gates`, source `67` acoustic
  factory capture, and browser getUserMedia transport.
- `/tmp/chatterbox-fork-agent-out/voice-chat-e2e/voice-chat-e2e-20260703T210510Z-core-services/index.json`
  passed `S08`, `S10`, `S03-unknown-speaker`, and
  `S04-ambiguous-speaker` with `mocked=false`, `live=true`, and empty
  `failed_gates`.
- `/tmp/chatterbox-fork-agent-out/voice-chat-e2e/voice-chat-e2e-20260703T210522Z-continuous-core/index.json`
  passed `S01_S02_S08_S09_S12` with `mocked=false`, `live=true`, and empty
  `failed_gates`.

Required top-level fields:

- `schema`: `chatterbox.voice_chat_e2e.index.v1`
- `mocked`: `false`
- `live`: `true`
- `run_id`
- `started_at_utc`, `ended_at_utc`
- `services`
- `transport`
- `scenarios`
- `latency_budgets`
- `artifacts`
- `failed_gates`
- `claims.proves`
- `claims.does_not_prove`

## Implementation Order

1. Convert this matrix into a machine-readable scenario manifest.
2. Add `scripts/smoke_voice_chat_e2e.py` that can run one scenario at a time
   and writes the index/child receipt structure.
3. Start with S01, S02, S08, S09, and S12 because existing scripts already
   cover most of those boundaries.
4. Add missing identity cases S03, S04, S11 before adding new UI work.
5. Add noisy and mixed-speaker cases S05, S06, S07 with pyannote/diarization
   receipts and explicit fail-closed gates.
6. Add browser/chat UI S13 only after the non-browser loop is stable, then
   require screenshot inspection plus receipt agreement.
7. Update `$best-practices-chatterbox-agent`, Embry Chatterbox subagent, and
   RealtimeSTT project knowledge only with lessons backed by receipts from this
   matrix.

## Known Boundaries

- Browser acoustic capture is still weaker than PipeWire/captured WAV proof.
- Pyannote speaker labels such as `SPEAKER_00` are not identity; identity must
  come from enrollment or memory evidence.
- Stream-level cancel proof does not prove every physical speaker buffer has
  flushed.
- Subjective voice quality requires human review of actual audio artifacts.
- A clean UI screenshot does not prove the voice pipeline unless the screenshot
  is tied to the same receipt/run id.
