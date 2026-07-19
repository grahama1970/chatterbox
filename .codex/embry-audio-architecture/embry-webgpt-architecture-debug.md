# Embry Voice Architecture Debug Request

Target system: `http://localhost:3002/#embry-voice`

Review target: Embry should speak through Chatterbox audibly, and the Embry orb should visibly track that exact Chatterbox audio.

## Current Failure

The human reports:

- "I did not hear it"
- "I have NEVER seen the embry orb connected to embry audio"
- After direct system playback test, the human confirmed all PipeWire sinks played the generated Embry WAV.

Therefore:

- Chatterbox generation works.
- Local PipeWire playback works.
- The problem is the integrated UX path and/or the orb tracking model.

## Relevant Repos / Files

- Chatterbox fork: `/home/graham/workspace/experiments/chatterbox`
- UX Lab route: `/home/graham/workspace/experiments/pi-mono/packages/ux-lab/src/components/embry-voice/EmbryVoiceLabRoute.tsx`
- Orb component: `/home/graham/workspace/experiments/pi-mono/packages/ux-lab/src/components/embry-voice/EmbryVoiceOrb.tsx`
- Orb wrapper: `/home/graham/workspace/experiments/pi-mono/packages/ux-lab/src/components/embry-voice/IdentityNode.tsx`
- Audio hook: `/home/graham/workspace/experiments/pi-mono/packages/ux-lab/src/hooks/useEmbryPlaybackAudioLevel.ts`
- UX Lab server: `/home/graham/workspace/experiments/pi-mono/packages/ux-lab/server/index.ts`
- Embry voice subagent: `/home/graham/workspace/experiments/agent-skills/agents/embry-chatterbox-voice`

## What Is Implemented

1. `/api/projects/embry-voice/direct-speak` generates real Chatterbox WAVs.

Example latest:

```text
/tmp/chatterbox-fork-agent-out/ux-lab-embry-direct/2026-07-05T18-37-57-744Z-b8b6a79e51f6.wav
```

2. Direct system playback works.

Command:

```bash
pw-play --target <sink> /tmp/chatterbox-fork-agent-out/ux-lab-embry-direct/2026-07-05T18-27-59-116Z-5f9d2e157c9d.wav
```

The human confirmed all tested sinks played.

3. Server route was patched to support:

```json
{
  "playLocal": true,
  "localPlayback": {
    "requested": true,
    "command": "pw-play",
    "target": "default",
    "pid": 1333856
  }
}
```

4. UI route inserts a visible live Embry chat turn with `audioArtifacts` and a reasoning trace:

```text
Render Chatterbox audio
Play through system audio
Bind orb to Embry waveform
Live Embry Chatterbox
```

5. Orb has:

- `speechAudioElement`
- `speechSourceId`
- `speechAudioUrl`
- `speechStartedAtMs`
- WebAudio analyser path
- decoded-WAV fallback path
- explicit ring/meter overlay

## Evidence That Still Fails

After triggering `window.embrySpeak(...)` from Surf:

```json
{
  "result": {
    "url": "/chatterbox-artifacts/ux-lab-embry-direct/2026-07-05T18-37-57-744Z-b8b6a79e51f6.wav",
    "path": "/tmp/chatterbox-fork-agent-out/ux-lab-embry-direct/2026-07-05T18-37-57-744Z-b8b6a79e51f6.wav"
  },
  "orb": {
    "state": "speaking",
    "bound": "true",
    "decodedSource": "/chatterbox-artifacts/ux-lab-embry-direct/2026-07-05T18-37-57-744Z-b8b6a79e51f6.wav",
    "level": "0.000",
    "bass": "0.000",
    "mid": "0.000",
    "treble": "0.000"
  },
  "activeAudio": [
    {
      "paused": false,
      "currentTime": 3.002,
      "duration": 13.64
    }
  ],
  "latestChat": "Started pw-play on default pid 1333856..."
}
```

Manual browser decode of the same WAV proves the file is not silent:

```json
{
  "ok": true,
  "bytes": 654798,
  "duration": 13.64,
  "sampleRate": 44100,
  "channels": 1,
  "samples": [
    {"sec": 0.5, "avg": 0.0066, "max": 0.0242},
    {"sec": 1, "avg": 0.0144, "max": 0.0247},
    {"sec": 2, "avg": 0.0102, "max": 0.0664},
    {"sec": 5, "avg": 0.0402, "max": 0.2211}
  ]
}
```

So the WAV has waveform data, but the React hook/orb still reports zero bands.

## Architecture Question

Please design the correct next architecture and patch strategy.

We need one obvious "Embry Audio Authority" where:

1. Chatterbox generates the WAV.
2. The WAV is played audibly through local PipeWire or a controlled browser path.
3. The orb tracks the same exact generated WAV in real time.
4. The chat timeline shows the same turn and audio artifact.
5. RealtimeSTT can later capture the same audio via monitor/loopback for sanity tests.

## Specific Questions

1. Should the orb track:
   - the browser `HTMLAudioElement`,
   - a decoded WAV timeline,
   - a server-emitted waveform envelope,
   - or PipeWire monitor/capture RMS?

2. Since direct `pw-play` is audible and browser hidden audio is unreliable, should UX Lab server compute waveform envelopes when copying the WAV and return them in the `direct-speak` response?

3. Should `EmbryVoiceOrb` be driven by an explicit `voiceEnvelope` + `startedAtMs` instead of trying to own audio analysis in React?

4. What is the narrow next patch that will satisfy the human acceptance test:
   - human hears Embry,
   - orb visibly follows Embry,
   - chat contains visible live Embry turn,
   - proof does not rely on DOM audio alone?

5. Please include a source-derived numbered implementation plan and label implemented vs missing behavior.

## Constraints

- Do not use PersonaPlex.
- Use Chatterbox for Embry voice.
- Use RealtimeSTT for listening later.
- Use shared chat UX as the center timeline.
- Do not claim success from DOM playback only.
- The human must hear Embry.
- The orb must visibly track Embry audio.
