Recommendation

Make the server-side Chatterbox artifact the Embry Audio Authority, not the browser audio element.

The authority should be:

TypeScript
Chatterbox WAV artifact
+ server-computed envelope from that exact WAV
+ PipeWire playback metadata for that exact WAV
+ chat turn/audio artifact metadata for that exact WAV

The browser should no longer have to prove that Embry is speaking by analyzing a hidden HTMLAudioElement. The browser should render the orb from an explicit voiceEnvelope and a playback start timestamp tied to the pw-play invocation.

That directly matches the human acceptance test:

Acceptance condition	Correct authority
Human hears Embry	pw-play through PipeWire
Orb visibly follows Embry	envelope computed from the same generated WAV
Chat shows live Embry turn	same artifact ID / URL / trace
Proof does not rely on DOM audio	response includes localPlayback + envelope + artifact hash/path
RealtimeSTT later sanity test	capture PipeWire monitor of the selected sink

The current failure shows the problem clearly: activeAudio.currentTime advances, orb.bound=true, and the WAV manually decodes as non-silent, but the orb still reports level=0.000. That means the React/WebAudio analysis path is not a trustworthy authority for this UX.

Answers to the specific architecture questions
1. What should the orb track?

The orb should primarily track a server-emitted waveform envelope computed from the exact Chatterbox WAV.

Use the other candidates only as secondary paths:

Candidate	Role	Reason
Browser HTMLAudioElement	Fallback/debug only	Browser media state is not the same as audible system playback. play() has its own promise/autoplay failure semantics, and browser audio can be blocked or routed differently from PipeWire. 
MDN Web Docs
+1

Decoded WAV timeline in React	Fallback/debug only	It is logically closer than DOM audio, but your evidence already shows the current React decode/orb path can return zero despite a non-silent WAV.
Server-emitted waveform envelope	Primary visual authority	It is deterministic, cheap, permission-free, and derived from the exact WAV that pw-play receives.
PipeWire monitor/capture RMS	Later validation/sanity path	This proves actual audio reached the selected sink/monitor, but it has latency, routing, and environmental coupling. It is excellent for RealtimeSTT sanity tests, not for the first visual authority.

So the model should be:

Chatterbox WAV
   ├─ pw-play -> human hears audio
   ├─ server envelope -> orb moves
   ├─ artifact metadata -> chat timeline
   └─ PipeWire monitor -> later RealtimeSTT sanity capture
2. Should UX Lab server compute waveform envelopes when copying the WAV?

Yes.

Do it immediately after Chatterbox generation and before returning /api/projects/embry-voice/direct-speak.

The server already has the authoritative file path:

/tmp/chatterbox-fork-agent-out/ux-lab-embry-direct/...wav

That is the right place to compute:

TypeScript
{
  durationMs: 13640,
  sampleRate: ...,
  channels: ...,
  sha256: "...",
  envelope: {
    version: 1,
    frameMs: 16,
    level: number[],
    rms: number[],
    peak: number[],
    // optional later:
    bass?: number[],
    mid?: number[],
    treble?: number[]
  }
}

For the first acceptance patch, level, rms, and peak are enough. Bands can be added later. The visible orb should not wait for FFT band correctness.

Normalize the envelope on the server. Your manual decode sample has average amplitudes like 0.0066, 0.0144, 0.0402; raw values mapped directly to CSS or SVG may look like zero. Use percentile normalization, for example:

noiseFloor = p10(rms)
speechCeil = p95(rms)
level = clamp((rms - noiseFloor) / (speechCeil - noiseFloor), 0, 1)

Also include peak so plosives and strong syllables visibly pop even when RMS is modest:

displayLevel = 0.7 * normalizedRms + 0.3 * normalizedPeak
3. Should EmbryVoiceOrb be driven by explicit voiceEnvelope + startedAtMs?

Yes.

EmbryVoiceOrb should become a mostly-presentational component:

TypeScript
<EmbryVoiceOrb
  state="speaking"
  voiceEnvelope={authority.envelope}
  speechStartedAtMs={authority.startedAtPerfMs}
  speechDurationMs={authority.durationMs}
  speechSourceId={authority.artifactId}
  speechAudioUrl={authority.url}
/>

The orb should not own the primary audio analysis lifecycle.

The current shape has too many places that can silently fail:

speechAudioElement
speechSourceId
speechAudioUrl
speechStartedAtMs
WebAudio analyser
decoded-WAV fallback
overlay

The new rule should be:

TypeScript
if (voiceEnvelope) {
  driveOrbFromEnvelope();
} else if (speechAudioElement) {
  useWebAudioFallback();
} else if (speechAudioUrl) {
  useDecodedWavFallback();
} else {
  idle();
}

The acceptance path must be the first branch.

Browser Web Audio still has value for experiments, but it should not be the claim of success. Web Audio contexts can be suspended and need explicit resume handling, which is another reason not to let that be the primary Embry authority. 
MDN Web Docs
+1

Narrow next patch that should satisfy the human test
Patch objective

When window.embrySpeak(...) runs, the response should prove:

JSON
{
  "authority": "server-chatterbox-wav-envelope-v1",
  "url": "/chatterbox-artifacts/...",
  "path": "/tmp/chatterbox-fork-agent-out/...",
  "sha256": "...",
  "durationMs": 13640,
  "localPlayback": {
    "requested": true,
    "driver": "pipewire",
    "command": "pw-play",
    "target": "auto",
    "pid": 1333856,
    "startedAtEpochMs": 1783291077744
  },
  "envelope": {
    "frameMs": 16,
    "level": [0, 0.02, 0.09, 0.14, "..."],
    "rms": ["..."],
    "peak": ["..."]
  }
}

And the orb debug overlay should show something like:

authority: server-envelope
bound: true
source: /chatterbox-artifacts/...
pid: 1333856
level: 0.318
frame: 142 / 853

Not:

decodedSource: ...
level: 0.000
Implementation plan: implemented vs missing
1. Chatterbox WAV generation

Implemented.

Your evidence shows /api/projects/embry-voice/direct-speak creates real Chatterbox WAVs and returns a URL/path pair:

/chatterbox-artifacts/ux-lab-embry-direct/...wav
/tmp/chatterbox-fork-agent-out/ux-lab-embry-direct/...wav

Manual decode confirms the WAV is non-silent.

Missing.

The response does not yet include a first-class authority object with duration, hash, normalized envelope, and playback timing.

2. PipeWire playback

Partially implemented.

The server returns:

JSON
{
  "playLocal": true,
  "localPlayback": {
    "requested": true,
    "command": "pw-play",
    "target": "default",
    "pid": 1333856
  }
}

Direct pw-play --target <sink> file.wav works when invoked manually.

Missing / likely bug.

Do not use "default" as a fake target unless it is actually a PipeWire node name or object serial. PipeWire’s documented --target values are auto, 0, an object serial/id, or a node name; the default target mode is already auto. 
PipeWire
+1

Narrow fix:

TypeScript
function buildPwPlayArgs(wavPath: string, target?: string) {
  if (!target || target === "default" || target === "auto") {
    return [wavPath]; // let PipeWire session manager pick default/auto
  }

  return ["--target", target, wavPath];
}

Return the resolved playback mode as:

JSON
{
  "target": "auto",
  "targetArgUsed": false
}

For explicit sink testing, only pass real values from pw-play --list-targets, wpctl status, object serials, or node.name.

3. Server-side envelope computation

Missing.

Add a small server helper, for example:

TypeScript
type EmbryVoiceEnvelopeV1 = {
  version: 1;
  frameMs: number;
  durationMs: number;
  sampleRate: number;
  channels: number;
  rms: number[];
  peak: number[];
  level: number[];
  stats: {
    rmsP10: number;
    rmsP95: number;
    peakP95: number;
  };
};

async function computeWavEnvelope(
  wavPath: string,
  frameMs = 16,
): Promise<EmbryVoiceEnvelopeV1> {
  // Decode WAV PCM/float.
  // Slice into frameMs windows.
  // Compute rms and peak per frame.
  // Normalize to visible 0..1 level.
}

Store a JSON sidecar next to the WAV if desired:

2026-07-05T18-37-57-744Z-b8b6a79e51f6.wav
2026-07-05T18-37-57-744Z-b8b6a79e51f6.envelope.json

For the first patch, inline the envelope in the direct-speak response. A 13.64 second clip at 16 ms frames is only about 853 frames, so this is small.

4. Playback start alignment

Missing.

When spawning pw-play, capture the server wall-clock start time:

TypeScript
const startedAtEpochMs = Date.now();
const child = spawn("pw-play", args, {
  detached: true,
  stdio: "ignore",
});

Return:

JSON
{
  "localPlayback": {
    "pid": child.pid,
    "startedAtEpochMs": 1783291077744,
    "target": "auto"
  }
}

On the client, convert server epoch to the browser performance.now() timeline:

TypeScript
function serverEpochToClientPerfMs(startedAtEpochMs: number) {
  const elapsedSinceServerStartMs = Math.max(0, Date.now() - startedAtEpochMs);
  return performance.now() - elapsedSinceServerStartMs;
}

This is good enough for localhost UX. Later, if you need tighter sync, split the flow into prepare-speak and play-prepared-artifact so the UI can arm the orb before the server starts PipeWire playback.

5. Chat timeline

Implemented.

You already insert a visible live Embry chat turn with:

Render Chatterbox audio
Play through system audio
Bind orb to Embry waveform
Live Embry Chatterbox

and audioArtifacts.

Missing.

The chat turn should include the same audioAuthority object used by the orb.

Suggested shape:

TypeScript
type EmbryAudioArtifact = {
  kind: "embry-chatterbox-wav";
  authority: "server-chatterbox-wav-envelope-v1";
  artifactId: string;
  url: string;
  path: string;
  sha256: string;
  durationMs: number;
  localPlayback: {
    driver: "pipewire-pw-play";
    pid: number;
    target: "auto" | string;
    startedAtEpochMs: number;
  };
  envelope: EmbryVoiceEnvelopeV1;
};

The same object should be used for:

chat audio artifact
orb voiceEnvelope
debug overlay
RealtimeSTT sanity metadata later

No duplicate truths.

6. EmbryVoiceLabRoute.tsx

Partially implemented.

It already calls the direct speak route, inserts the live Embry turn, and passes audio-related data toward the orb.

Missing.

It should create a single active authority state:

TypeScript
const [activeEmbryAudio, setActiveEmbryAudio] =
  useState<EmbryAudioAuthority | null>(null);

After direct-speak returns:

TypeScript
const authority = result.audioAuthority;

setActiveEmbryAudio({
  ...authority,
  startedAtPerfMs: serverEpochToClientPerfMs(
    authority.localPlayback.startedAtEpochMs,
  ),
});

upsertEmbryChatTurn({
  role: "embry",
  state: "speaking",
  text,
  audioArtifacts: [authority],
  reasoningTrace: [
    "Render Chatterbox audio",
    "Play through system audio",
    "Bind orb to server envelope",
    "Live Embry Chatterbox",
  ],
});

The route should stop requiring a hidden browser audio element for the success path.

7. IdentityNode.tsx

Partially implemented.

It already wraps the orb and passes speech-related props.

Missing.

Add pass-through props for the new authority:

TypeScript
<EmbryVoiceOrb
  state={embryState}
  voiceEnvelope={activeEmbryAudio?.envelope}
  speechStartedAtMs={activeEmbryAudio?.startedAtPerfMs}
  speechDurationMs={activeEmbryAudio?.durationMs}
  speechSourceId={activeEmbryAudio?.artifactId}
  speechAudioUrl={activeEmbryAudio?.url}
  playbackAuthority={activeEmbryAudio?.localPlayback}
/>

Do not require speechAudioElement for the acceptance path.

8. EmbryVoiceOrb.tsx

Partially implemented.

It already has visible state, speech props, analysis paths, and a ring/meter overlay.

Missing.

Add an explicit envelope-first branch:

TypeScript
const envelopeLevel = useEmbryEnvelopeLevel({
  envelope: voiceEnvelope,
  startedAtMs: speechStartedAtMs,
  durationMs: speechDurationMs,
  enabled: state === "speaking" && !!voiceEnvelope,
});

const level =
  voiceEnvelope ? envelopeLevel.level :
  analyserLevel ? analyserLevel.level :
  decodedLevel ? decodedLevel.level :
  0;

The overlay should expose the authority:

TypeScript
data-embry-orb-authority={
  voiceEnvelope ? "server-envelope" : "browser-analysis"
}
data-embry-orb-level={level.toFixed(3)}
data-embry-orb-source={speechAudioUrl}

The visible ring should move from level, not from DOM audio state.

9. useEmbryPlaybackAudioLevel.ts

Currently failing the acceptance path.

The hook reports zero even though:

orb.state = speaking
orb.bound = true
decodedSource = same WAV URL
manual browser decode = non-silent

Narrow change.

Do not delete it yet. Demote it to fallback/debug.

Add a new hook:

TypeScript
function useEmbryEnvelopeLevel({
  envelope,
  startedAtMs,
  durationMs,
  enabled,
}: {
  envelope?: EmbryVoiceEnvelopeV1;
  startedAtMs?: number;
  durationMs?: number;
  enabled: boolean;
}) {
  const [sample, setSample] = useState({
    level: 0,
    rms: 0,
    peak: 0,
    frameIndex: 0,
  });

  useEffect(() => {
    if (!enabled || !envelope || startedAtMs == null) return;

    let raf = 0;

    const tick = () => {
      const elapsedMs = performance.now() - startedAtMs;
      const frameIndex = Math.max(
        0,
        Math.min(
          envelope.level.length - 1,
          Math.floor(elapsedMs / envelope.frameMs),
        ),
      );

      const active = elapsedMs >= 0 && elapsedMs <= envelope.durationMs + 250;

      setSample({
        level: active ? envelope.level[frameIndex] ?? 0 : 0,
        rms: active ? envelope.rms[frameIndex] ?? 0 : 0,
        peak: active ? envelope.peak[frameIndex] ?? 0 : 0,
        frameIndex,
      });

      if (active) raf = requestAnimationFrame(tick);
    };

    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [enabled, envelope, startedAtMs]);

  return sample;
}

Add smoothing in the visual layer, not in the authority data, so the debug overlay can still show raw envelope values.

10. RealtimeSTT later

Missing, intentionally later.

RealtimeSTT should not be used to drive the orb in the first patch.

Later, add a sanity mode:

direct-speak returns selected PipeWire sink / node
RealtimeSTT captures <sink>.monitor or configured loopback
server computes captured RMS / speech detection
compare captured RMS timing against known envelope

This answers:

Was the same generated Embry audio actually present on the system audio path?

It should not answer:

What should the orb draw this frame?

The orb already has the cleaner answer: the server envelope.

The most important behavioral change

Today, the system effectively says:

PipeWire may be playing,
but the orb only moves if React/WebAudio analysis succeeds.

Change it to:

The server generated one Chatterbox WAV.
The server plays that WAV with PipeWire.
The server returns the envelope of that same WAV.
The chat and orb both bind to that same authority object.

That removes the failed hidden-audio dependency while preserving the exact Embry artifact.

Minimal acceptance test after patch

Run the same Surf trigger:

JavaScript
await window.embrySpeak("Embry voice acceptance test. The orb should move with this generated Chatterbox waveform.");

Expected proof object:

JSON
{
  "result": {
    "url": "/chatterbox-artifacts/ux-lab-embry-direct/....wav",
    "path": "/tmp/chatterbox-fork-agent-out/ux-lab-embry-direct/....wav",
    "audioAuthority": "server-chatterbox-wav-envelope-v1",
    "durationMs": 13640,
    "sha256": "..."
  },
  "localPlayback": {
    "requested": true,
    "command": "pw-play",
    "target": "auto",
    "targetArgUsed": false,
    "pid": 1333856,
    "startedAtEpochMs": 1783291077744
  },
  "orb": {
    "state": "speaking",
    "authority": "server-envelope",
    "bound": "true",
    "source": "/chatterbox-artifacts/ux-lab-embry-direct/....wav",
    "level": "0.318",
    "frame": "142"
  },
  "latestChat": "Live Embry Chatterbox..."
}

The human acceptance is then based on:

human heard PipeWire pw-play
orb moved from server envelope
chat showed the same artifact

not on:

HTMLAudioElement.paused === false

That is the correct next architecture.

<<<WEBGPT_DONE:20260705T184934Z:1150bb46>>>
