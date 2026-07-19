# WebGPT create-architecture request: Embry live voice/chat E2E proof system

## Request

Use `$create-architecture` thinking to define the minimum viable architecture and proof ladder for Embry voice/chat stress testing.

The project agent has been drifting into UI, matrix bookkeeping, and component receipts. The human's actual objective is:

```text
Stress test Embry voice/chat system to identify concrete failures across RealtimeSTT ingress, speaker identity, memory/Tau routing, Chatterbox speech, Chat UX sync, orb sync, replay, and interruption.
```

The human is explicitly frustrated that text-only SPARTA QRA passes were treated as meaningful while the end-to-end voice loop remains unproven.

## Current repo/context, with local paths omitted

Repository: Chatterbox fork, branch `main`.

Latest pushed commit:

```text
2727b223fb4ab57f146fd33ab48b415d0f373911
```

Current checked-in evidence artifacts, summarized:

```text
EMBRY_STRESS_SESSION_MATRIX.json
EMBRY_STRESS_FAILURE_TAXONOMY.json
EMBRY_REALTIMESTT_INGRESS_EVIDENCE_AUDIT.json
EMBRY_HORUS_E2E_STATUS_AUDIT.json
```

Current matrix summary:

```text
300 sessions
255 passed
45 failed
0 not_run
```

This is misleading for the final objective because many `passed` rows are text/memory answerability only.

## Concrete current evidence

### SPARTA QRA

SPARTA QRA answerability rows currently pass:

```text
sparta_qra_compliance: 20 passed / 0 failed / 0 not_run
```

But their receipts prove only memory `/answer` answerability before voice.

Representative receipt claims:

```json
{
  "ok": true,
  "live": true,
  "mocked": false,
  "claims": {
    "proves": [
      "memory_and_brave_routes_return_relevant_answerable_results_before_voice"
    ],
    "does_not_prove": [
      "browser_chat_ui_sync",
      "full_spoken_multiturn_conversation",
      "human_acceptance_of_voice_performance"
    ]
  }
}
```

Therefore these should not count as voice E2E passes.

### RealtimeSTT / physical capture

Fresh Jabra source-62 physical mic receipt summary:

```json
{
  "ok": false,
  "live": false,
  "mocked": false,
  "capture_kind": "physical_microphone",
  "captured_rms": 229,
  "played_source_rms": 542,
  "realtimestt_transcript": "Thank you very much.",
  "expected": "Horus/factory stress speech",
  "failed_gates": [
    "rung7_command_ok",
    "rung7_receipt_ok",
    "speaker_resolution_known_horus",
    "speaker_memory_recall_found"
  ]
}
```

Interpretation: the physical mic path captured non-silent audio, but ASR produced the wrong phrase and the downstream speaker/memory gates failed.

### Speaker identity

Speaker-window evidence on the same captured source-62 audio:

```json
{
  "ok": false,
  "live": false,
  "mocked": false,
  "voiced_segment_count": 6,
  "horus_segment_count": 0,
  "embry_segment_count": 6,
  "horus_ratio": 0.0,
  "mean_primary_margin": -0.1413,
  "failed_gates": [
    "min_primary_ratio",
    "mean_primary_margin"
  ]
}
```

Interpretation: the captured physical-mic waveform does not resemble the Horus enrollment to the current verifier.

### pyannote status

pyannote check did not reach diarization:

```text
Python import of pyannote.audio fails because torchvision is broken against installed torch.
```

Also, shell configuration defines `HF_TOKEN` but does not export it, so child processes do not see it.

## Brave Search findings to incorporate

Raw searches were run with `$brave-search` on 2026-07-08.

### RealtimeSTT external audio

Search: `RealtimeSTT feed_audio external audio websocket examples`

Relevant findings:

- `KoljaB/RealtimeSTT` GitHub and PyPI snippets say to set `use_microphone=False` when audio comes from a file, stream, websocket, or another process.
- RealtimeSTT external audio should feed 16-bit mono PCM chunks at 16 kHz, or pass original sample rate so RealtimeSTT can resample.
- `KoljaB/RealtimeSTT` discussion #17 covers `feed_audio` transcription.

Implication:

```text
The first proof should be a non-browser local audio graph capture feeding RealtimeSTT external-audio mode. Browser UI should not be proof authority.
```

### PipeWire/Pulse monitor capture

Search: `PipeWire PulseAudio null sink monitor capture ffmpeg pulse microphone loopback`

Relevant findings:

- PulseAudio null sink creates a monitor source for the virtual output.
- ArchWiki PulseAudio examples show moving audio to a null sink and recording the monitor, with ffmpeg examples.
- PipeWire docs describe loopback module for linking capture and playback streams.

Implication:

```text
Use a temporary Pulse-compatible null sink under PipeWire, play known Horus speech into it, capture the sink monitor, then feed that captured PCM to RealtimeSTT. This avoids room mic distortion and Chrome autoplay.
```

### pyannote/diarization

Search: `pyannote audio realtime diarization overlap detection speaker identification streaming`

Relevant findings:

- `pyannote/pyannote-audio` provides speaker diarization, speaker change detection, overlapped speech detection, and speaker embeddings.
- Hugging Face `pyannote/speaker-diarization-community-1` mentions reconciliation between diarization timestamps and transcription timestamps.
- pyannote.ai advertises realtime API, but local open-source pipeline may not be zero-latency.

Implication:

```text
Do not block Rung 1 on pyannote. Fix pyannote as a separate Rung 3/diarization environment task after RealtimeSTT ingress is clean.
```

### Chrome autoplay/audio replay

Search: `Chrome audio autoplay stops after first fraction of second programmatic play audio element`

Relevant findings:

- Chrome autoplay policy blocks autoplay with sound unless user gesture or engagement criteria are satisfied.
- Chrome Media Engagement Index significant playback events require more than seven seconds of playback.
- Web Audio AudioContext can be subject to the same autoplay policy.

Implication:

```text
Chrome/browser replay is not a valid first proof authority for audible Embry output. Use OS audio/playback authority receipts first, then wire browser controls after a user gesture or explicit playback unlock path.
```

## Human requirements to satisfy

1. Voice E2E is the point. Do not treat text-only answerability as voice success.
2. The human should hear a comprehensive suite of live tests.
3. Embry voice/chat must synchronize:
   - user request
   - Embry spoken response
   - Chat UX text
   - memory reasoning trace
   - tone/emotion tags
   - Chatterbox audio artifact
   - orb envelope tracking
   - replay timing
4. Embry should be `$memory` first through `$tau`, with Chatterbox only as renderer.
5. RealtimeSTT is the listener companion.
6. Speaker identity must identify Horus through enrollment/evidence, not label assumptions.
7. Overlap/interruption must be tested:
   - primary Horus barge-in
   - non-primary suppression
   - two non-Embry speakers overlap: humorous one-at-a-time boundary
   - stale audio skipped
   - natural stops, not robotic instant cutoffs
8. Every conversation test must include:
   - conversation arc
   - steering
   - interruption strategy
   - inline emotion tags such as `[laugh]`
   - tone from `$memory /intent`
   - final spoken text JSON schema
   - pause policy
9. Need at least 200+ stress sessions covering:
   - simple/medium/advanced/adversarial/soak
   - SPARTA QRA compliance questions
   - persona memory recall/miss
   - Brave Search researched questions
   - Tau skill use: create-figure, analytics, create-evidence-case, sparta-validator
   - voice idle hum
   - negative user tone detection and de-escalation
   - factory-floor noise
   - browser mic/WebRTC
   - replayed sessions
10. Deterministic pass/fail per rung:
   - real Horus enrollment
   - browser mic/WebRTC
   - Tau/memory routing
   - Chatterbox from live STT
   - Chat UX sync
   - orb sync
   - replay
   - interruption

## Current architectural concern

The project agent keeps doing bookkeeping/audit updates instead of forcing the live E2E rung to pass. We need an architecture that prevents this:

```text
audio ingress receipt
-> RealtimeSTT event
-> speaker/diarization gate
-> memory/Tau turn decision
-> Chatterbox artifact
-> audio-output authority playback
-> shared Chat UX turn update
-> orb envelope subscriber
-> replayable session journal
```

## What WebGPT should produce

Please create a source-derived architecture plan with:

1. A numbered pipeline model where each step is labeled:
   - implemented
   - partial
   - missing
   - failing
2. A strict proof ladder that starts with the next smallest rung that advances live voice E2E.
3. The exact receipts/schema needed at each boundary.
4. A rule for scoring stress sessions so text-only memory answerability does not count as voice E2E.
5. A plan for turning the 300-session matrix into 200+ true voice/chat stress sessions without masking failures.
6. A recommendation on whether to fix:
   - audio graph/loopback first,
   - browser WebRTC first,
   - pyannote/diarization first,
   - Chatterbox playback/orb first.
7. A fail-closed endpoint architecture:
   - listener endpoints
   - speaker identity endpoints
   - memory/Tau routing endpoints
   - Chatterbox speak endpoints
   - session replay endpoints
   - orb/envelope endpoints
8. Exact next three tasks for the Codex project agent, each with:
   - command/artifact target
   - acceptance criteria
   - what it proves
   - what it does not prove
   - stop condition

Do not produce a generic architecture diagram. The answer must be operational and must prevent the project agent from doing more UI/audit bookkeeping instead of live E2E proof.

## Desired final output shape

Return:

```text
Architecture verdict:
...

Numbered model:
1. ...

Proof ladder:
Rung 1 ...

Receipts:
...

Stress session scoring:
...

Endpoint contracts:
...

Next three Codex tasks:
1. ...
2. ...
3. ...
```

Also include a concise YAML definition compatible with `$create-architecture`:

```yaml
name: embry_live_voice_e2e_truth_architecture
components:
  - id: ...
connections:
  - from: ...
    to: ...
```

