# WebGPT Architecture Review Request: Embry Chatterbox Audio + Orb Tracking

## Objective

Design the correct architecture and next implementation patch for Embry Voice so:

1. Embry speaks through Chatterbox and the human can hear it on the machine speakers.
2. The Embry orb visibly tracks Embry's actual Chatterbox waveform in real time.
3. The listener stack can capture the same Embry/system audio when needed for loopback sanity tests.
4. The UI at `http://localhost:3002/#embry-voice` does not rely on false proof such as DOM audio tags alone.

## Human Acceptance Failure

The human reported:

- "I did not hear it"
- "I have NEVER seen the embry orb connected to embry audio"

Therefore prior DOM/browser-only proof is insufficient.

## Source-Derived Step Model

1. `EmbryVoiceLabRoute.tsx` calls `/api/projects/embry-voice/direct-speak`.
   - Status: implemented.
   - Evidence: browser generated WAV URLs under `/chatterbox-artifacts/ux-lab-embry-direct/...wav`.

2. UX Lab Express route `/api/projects/embry-voice/direct-speak` calls the Chatterbox backend and copies output WAVs to `/tmp/chatterbox-fork-agent-out/ux-lab-embry-direct`.
   - Status: implemented.
   - Files: `/home/graham/workspace/experiments/pi-mono/packages/ux-lab/server/index.ts`, lines around `10959`.
   - Evidence: files exist under `/tmp/chatterbox-fork-agent-out/ux-lab-embry-direct`.

3. Browser creates a hidden `HTMLAudioElement`, appends it to `document.body`, and calls `.play()`.
   - Status: implemented.
   - Evidence: Surf showed `paused:false`, `currentTime` advancing.
   - Limitation: human did not hear audio, so browser playback does not prove physical speaker output.

4. Orb receives the same `HTMLAudioElement` via `speechAudioElement`.
   - Status: implemented in route props.
   - Evidence: DOM shows `data-embry-speech-bound=true` and `data-embry-speech-source-id=embry-direct-*`.

5. Orb analyser hook uses `AudioContext.createMediaElementSource(audio)` and `AnalyserNode`.
   - Status: implemented.
   - Files: `/home/graham/workspace/experiments/pi-mono/packages/ux-lab/src/hooks/useEmbryPlaybackAudioLevel.ts`.
   - Evidence: Surf samples showed nonzero changing bands such as `level: 0.218 -> 0.438`, `mid: 0.593 -> 1.000`.
   - Limitation: human still did not visually accept the connection.

6. Physical speaker output is not controlled by the browser/React route.
   - Status: missing/fragile.
   - Evidence: `pw-play --target 64 <wav>` showed PipeWire stream to `Jabra SPEAK 510 USB`, but the human still did not hear it.
   - Likely issue: wrong physical sink, muted external device, KDE routing, or route must expose explicit sink selection/test tone.

7. RealtimeSTT listener capture of Embry/system audio is not proven.
   - Status: missing.
   - Required: loopback or monitor source capture from the same speaker sink, then ASR transcript receipt.

## Current Research From Brave Search

- Web Audio analysers can only visualize sources they own; they cannot inspect arbitrary system output.
- MediaElementAudioSource can output zeros if CORS-tainted or lifecycle is wrong.
- Chrome/PipeWire browser routing may need Pulse/PipeWire tooling; browser audio and system speaker routing are separate proof layers.
- PipeWire loopback/monitor routing is likely the right controlled test layer for listener verification.

## Concrete Current Evidence

Commands already run:

```text
Surf generated and played:
http://localhost:3002/chatterbox-artifacts/ux-lab-embry-direct/2026-07-05T18-12-26-414Z-3d17e996a45a.wav

DOM samples during playback:
state=speaking
data-embry-speech-bound=true
data-embry-audio-level varied from 0.218 to 0.438
audio.paused=false
audio.currentTime advanced

PipeWire:
wpctl status listed default sink: Jabra SPEAK 510 Analog Stereo
pw-play --target 64 <wav> created active stream to Jabra SPEAK 510 USB playback_FL/FR
```

Screenshots:

```text
/tmp/embry-orb-waveform-tracking-surf.png
/tmp/codex-ui-verification/chatterbox/embry-orb-waveform-tracking/20260705T181512Z.png
```

## What Needs Review

Please provide a concrete architecture and implementation plan, not general advice, for:

1. A single "Embry Audio Authority" abstraction that owns Chatterbox WAV playback, routes to speakers, feeds the orb analyser, and exposes receipts.
2. Whether playback should stay in browser Web Audio, move to a local audio daemon/service, or use both.
3. How to make the orb visibly and unambiguously track the actual audible Embry waveform.
4. How to prove the human-audible path with deterministic local artifacts without pretending DOM playback is enough.
5. How to connect RealtimeSTT/loopback capture so the system can hear Embry or controlled test audio when needed.
6. The narrow next patch to `#embry-voice` that should be made first.

## Constraints

- Do not use PersonaPlex. Embry speaks through Chatterbox.
- RealtimeSTT listens; Tau and memory reason.
- The shared Chat UX must remain the center timeline.
- Browser-only DOM proof is insufficient.
- The human must be able to hear Embry.
- The orb must visibly track Embry audio, not merely switch labels.
