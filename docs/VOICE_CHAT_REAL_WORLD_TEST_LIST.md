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

Browser-ASR failure receipt:

`/tmp/chatterbox-fork-agent-out/voice-chat-e2e/voice-chat-e2e-20260703T222548Z-browser-asr-audible/continuous-voice-loop.json`

The browser transport captured a real WAV, but RealtimeSTT and direct Whisper
both returned an empty transcript. The direct Whisper receipt is:

`/tmp/chatterbox-fork-agent-out/voice-chat-e2e/voice-chat-e2e-20260703T222548Z-browser-asr-audible/direct-whisper-browser-capture.json`

## Tests Still Needed For Higher Confidence

These are not closed by the latest suite:

- repeated factory-noise runs across multiple source positions and volume
  levels
- Horus plus female distractor with identity reconciliation, not only overlap
  boundary behavior
- browser chat UI screenshot agreement against the same receipt/run id
- browser microphone capture that is ASR-usable; current browser capture writes
  a real WAV but produced an empty transcript under RealtimeSTT and direct
  Whisper
- physical playback buffer flush after cancel
- subjective human voice quality review for Embry and Horus
- stronger Embry personality arcs for boundary lines such as
  `one_at_a_time_interrupt`; the current audio can be intelligible while still
  lacking character
- longer multi-turn memory conversations with memory miss, memory hit, and
  identity changes in the same session

## Failure Handling Rule

Do not weaken gates to make this suite pass. If a real-world source is silent,
as Jabra source `62` was for S06, preserve the failure receipt and either fix
the routing or select a source that produces non-silent real capture with its
source id recorded in the receipt.
