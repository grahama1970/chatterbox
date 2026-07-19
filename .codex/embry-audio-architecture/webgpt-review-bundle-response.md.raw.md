Verdict

Use both browser and local audio, but change the trust hierarchy:

The browser must stop being the proof layer. It can render the timeline, show artifacts, and optionally preview audio, but the authoritative Embry speech path should be a local Embry Audio Authority running beside the UX Lab server. That authority owns Chatterbox WAV identity, PipeWire routing, speaker playback, monitor capture, waveform telemetry, and receipts.

The correct architecture is:

Embry text
  -> Chatterbox backend
  -> WAV artifact + sha256 + duration
  -> Embry Audio Authority
       -> Embry TTS bus / virtual sink
            -> physical speaker sink via loopback
            -> clean Embry-only monitor capture
            -> RealtimeSTT loopback sanity input when enabled
       -> waveform telemetry from monitor capture
       -> receipt ledger
  -> React timeline + orb subscribe to authority events

This directly addresses the failure: audio.paused=false, DOM WAV URLs, and createMediaElementSource() are no longer treated as proof that the human heard anything. Web Audio can create a graph from an existing media element, but that only proves the page owns that element’s audio graph; it does not prove the OS routed audible sound to the intended physical sink. 
MDN Web Docs
+1

1. Embry Audio Authority

Create one server-side abstraction, probably first as a TypeScript service under UX Lab:

packages/ux-lab/server/embryAudioAuthority.ts

Its job is not “play a URL.” Its job is to create a receipt-producing audio transaction.

Core interface:

TypeScript
type EmbrySpeakRequest = {
  text: string;
  voice?: "embry";
  timelineMessageId?: string;
  requestedSinkName?: string;
  loopbackMode?: "off" | "embry-monitor" | "physical-sink-monitor";
};

type EmbryAudioReceipt = {
  playId: string;
  state:
    | "requested"
    | "synthesizing"
    | "artifact-ready"
    | "routing"
    | "playing"
    | "monitor-confirmed"
    | "stt-confirmed"
    | "completed"
    | "failed";

  artifact: {
    wavPath: string;
    publicUrl: string;
    sha256: string;
    durationMs: number;
    sampleRate: number;
    channels: number;
    peakDbfs: number;
  };

  route: {
    backend: "pipewire";
    busSinkName: "embry_tts_bus";
    busMonitorName: "embry_tts_bus.monitor";
    physicalSinkName: string;
    physicalSinkDescription: string;
    physicalSinkId?: string;
    physicalSinkVolume?: string;
    physicalSinkMuted?: boolean;
    loopbackModuleId?: string;
    playerTarget: string;
  };

  playback: {
    player: "pw-play";
    startedAt: string;
    endedAt?: string;
    exitCode?: number;
    mediaName: string;
  };

  waveform: {
    source: "embry_tts_bus.monitor" | "source-pcm-fallback";
    firstNonZeroAt?: string;
    lastSeq?: number;
    peakLevel?: number;
    rmsDbfs?: number;
    visibleFramesSent: number;
  };

  monitorCapture?: {
    wavPath: string;
    sha256: string;
    durationMs: number;
    peakDbfs: number;
    rmsDbfs: number;
    sourceVsCaptureCorrelation?: number;
    estimatedLatencyMs?: number;
  };

  stt?: {
    mode: "loopback-sanity";
    transcript?: string;
    expectedNonce?: string;
    matched?: boolean;
  };

  human?: {
    heardConfirmedByUser?: boolean;
    confirmedAt?: string;
  };
};

The important rule: every Embry utterance has a playId, and every UI visual/audio claim refers to that playId.

Add endpoints:

GET  /api/projects/embry-voice/audio/status
POST /api/projects/embry-voice/audio/select-output
POST /api/projects/embry-voice/audio/speak
POST /api/projects/embry-voice/audio/speaker-check
POST /api/projects/embry-voice/audio/loopback-check
GET  /api/projects/embry-voice/audio/receipts/:playId
GET  /api/projects/embry-voice/audio/events

Keep the existing /direct-speak route only as a compatibility shim that calls the authority. It should no longer mean “browser should play this WAV.”

2. Browser playback vs local playback

Authoritative playback should move to the local audio authority, not remain in the React route.

The browser path has two problems. First, browser audio device selection is permission- and context-gated: HTMLMediaElement.setSinkId() sets an output device only when the page is allowed to use that device, and the broader Audio Output Devices API requires permission/user activation for non-default outputs. 
MDN Web Docs
+1
 Second, even Chrome’s Web Audio AudioContext.setSinkId() support only routes that browser-owned audio graph; it still does not prove the physical machine emitted sound through the intended PipeWire sink. 
Chrome for Developers

The local authority can control the real Linux audio graph. pw-cat/pw-play can play or capture PCM/WAV through PipeWire, and its --target option accepts a target node id or node.name, which is the right primitive for deterministic routing. 
PipeWire
+1
 WirePlumber/wpctl can inspect and control PipeWire routing, devices, nodes, and volumes, so the server can expose real sink status instead of browser-only state. 
Debian Manpages

Recommended split:

Local authority:
  - synthesize Chatterbox
  - choose PipeWire sink
  - create/maintain virtual Embry bus
  - play WAV
  - capture monitor
  - feed RealtimeSTT sanity input
  - produce receipts and telemetry

Browser:
  - shared Chat UX timeline
  - output device/status controls
  - speaker-check and loopback-check buttons
  - orb visualization from authority telemetry
  - optional non-authoritative WAV preview only

Do not delete Web Audio immediately; demote it. If the browser still creates a hidden HTMLAudioElement, label that path as:

browser-preview-only: true
authoritativeAudibleProof: false
3. PipeWire graph: Embry bus first, speaker second

Do not play directly to Jabra SPEAK 510 as the primary architecture. Create a stable Embry-only bus:

Bash
pactl load-module module-null-sink \
  sink_name=embry_tts_bus \
  sink_properties="device.description=Embry_TTS_Bus" \
  rate=48000 \
  channels=2 \
  channel_map=front-left,front-right

PipeWire’s PulseAudio compatibility supports loading built-in modules through pactl load-module, and module-null-sink exists for creating a named sink with rate/channel options. 
PipeWire
+1

Then loop that bus to the selected physical speaker sink:

Bash
pactl load-module module-loopback \
  source=embry_tts_bus.monitor \
  sink="$PHYSICAL_SINK_NAME" \
  latency_msec=25

PipeWire’s loopback module passes a capture stream to a playback stream and can construct links between sources and sinks or virtual devices; the pw-loopback client and module-backed configuration are official ways to create those loopback nodes. 
PipeWire
+1

Playback becomes:

Bash
pw-play \
  --target=embry_tts_bus \
  --properties="{\"media.name\":\"EmbryVoice:${PLAY_ID}\",\"application.name\":\"Embry Audio Authority\"}" \
  "$WAV_PATH"

Capture for proof and orb telemetry becomes:

Bash
pw-record \
  --target=embry_tts_bus.monitor \
  --raw \
  --format=s16 \
  --rate=16000 \
  --channels=1 \
  -

This gives you a clean Embry-only monitor that is also the signal being looped to the real speakers. It avoids the ambiguity of capturing the physical sink monitor, which may include other desktop audio. For separate “full system output” sanity tests, add an explicit mode that records the selected physical sink’s monitor, but do not use that as the default Embry proof path.

4. Orb tracking: drive it from authority monitor telemetry

The orb should no longer be driven primarily by speechAudioElement.

Replace:

TypeScript
<EmbryOrb speechAudioElement={directSpeechAudioElement} />

with something like:

TypeScript
<EmbryOrb
  audioAuthorityPlayId={activePlayId}
  audioLevel={authorityAudioLevel}
  audioBands={authorityAudioBands}
  waveformSource={authorityWaveformSource}
  receiptId={activeReceiptId}
/>

Add a hook:

TypeScript
function useEmbryAudioAuthorityLevel(sessionId: string) {
  const [frame, setFrame] = useState<EmbryAudioFrame | null>(null);

  useEffect(() => {
    const es = new EventSource(
      `/api/projects/embry-voice/audio/events?sessionId=${encodeURIComponent(sessionId)}`
    );

    es.addEventListener("embry-audio-frame", (event) => {
      const parsed = JSON.parse((event as MessageEvent).data);
      setFrame(parsed);
    });

    return () => es.close();
  }, [sessionId]);

  return frame;
}

Telemetry frame:

TypeScript
type EmbryAudioFrame = {
  playId: string;
  seq: number;
  tMs: number;
  source: "embry_tts_bus.monitor" | "source-pcm-fallback";
  rms: number;        // 0..1
  peak: number;       // 0..1
  bands: number[];    // e.g. 8 or 16 bands
  rmsDbfs: number;
  routeVerified: boolean;
  monitorConfirmed: boolean;
};

Orb visual rule:

If source === "embry_tts_bus.monitor" and monitorConfirmed:
  animate orb from monitor RMS/bands
  show badge: "PipeWire monitor: embry_tts_bus.monitor"
  set data-embry-waveform-source="pipewire-monitor"
else if source === "source-pcm-fallback":
  animate but show badge: "source PCM fallback, not monitor proof"
else:
  keep orb idle

Make the connection visually undeniable. Add a small waveform strip or radial oscilloscope behind/around the orb with:

playId
artifact hash short id
sink name
waveform source
monitor peak
route status

Example visible badge:

Embry audio: PLAYING
Source: embry_tts_bus.monitor
Sink: Jabra SPEAK 510 Analog Stereo
Monitor peak: -8.7 dBFS
Receipt: ea_20260705_...

Acceptance DOM attributes should become:

HTML
data-embry-audio-authority="pipewire"
data-embry-waveform-source="embry_tts_bus.monitor"
data-embry-audio-play-id="..."
data-embry-audio-receipt-id="..."
data-embry-monitor-confirmed="true"
data-embry-speech-bound="deprecated-browser-preview"

The old data-embry-speech-bound=true is insufficient and should not be used as the acceptance proof.

5. Deterministic proof that the human-audible path is real

Software can prove “audio reached the selected PipeWire route and monitor.” It cannot honestly prove “a human heard the speaker cone” unless either the human confirms it or an external microphone/acoustic capture confirms it. The UI should distinguish those states.

Add a Speaker Check card in #embry-voice.

When clicked:

Generate a deterministic local WAV:

200 ms silence
880 Hz left
440 Hz right
880 Hz both
spoken Chatterbox phrase: "Embry speaker check <nonce>"

Route it through embry_tts_bus.

Loop embry_tts_bus.monitor to the selected physical sink.

Record the bus monitor and optionally the physical sink monitor.

Compute:

source sha256
monitor sha256
source peak/rms
capture peak/rms
source-vs-capture correlation
estimated latency
sink name/id/volume/mute
player exit code

Write:

/tmp/chatterbox-fork-agent-out/ux-lab-embry-audio-authority/<playId>/source.wav
/tmp/chatterbox-fork-agent-out/ux-lab-embry-audio-authority/<playId>/monitor.wav
/tmp/chatterbox-fork-agent-out/ux-lab-embry-audio-authority/<playId>/receipt.json
/tmp/chatterbox-fork-agent-out/ux-lab-embry-audio-authority/<playId>/pipewire-status.txt

UI status should be honest:

Route verified: yes
Monitor captured Embry audio: yes
Physical sink selected: Jabra SPEAK 510 Analog Stereo
Sink muted: no
Human heard: pending

Then provide a button:

I heard Embry

Only after that button should the receipt say:

JSON
"human": {
  "heardConfirmedByUser": true
}

Optional stronger proof: add “acoustic proof” mode that records from the actual room microphone while playing the speaker check. That is the only software-side way to approach “the human could hear it” without a manual confirmation.

6. RealtimeSTT loopback capture

Use the Embry bus monitor for deterministic listener sanity tests:

embry_tts_bus.monitor
  -> PCM chunks
  -> RealtimeSTT(use_microphone=false)
  -> transcript
  -> receipt
  -> timeline diagnostic card

RealtimeSTT supports external audio by disabling microphone input and feeding 16-bit mono PCM chunks at 16 kHz, or passing the original sample rate for resampling. 
GitHub
+1
 That fits the authority design exactly: pw-record captures raw PCM from the Embry monitor, and the listener stack receives that as controlled external audio.

Add loopback modes:

TypeScript
type LoopbackMode =
  | "off"                  // normal human listening only
  | "embry-sanity"          // capture only Embry bus monitor
  | "system-sanity";        // capture selected physical sink monitor

For embry-sanity, generate a nonce phrase:

"Embry loopback sanity alpha seven four"

Receipt requires:

monitor captured nonzero audio
RealtimeSTT transcript received
transcript contains expected phrase or nonce tokens

Important safety/architecture boundary: loopback sanity transcripts should be marked as self/system audio, not user speech. Tau and memory should not treat them as human input. Add metadata:

JSON
{
  "speaker": "embry",
  "source": "loopback-sanity",
  "eligibleForMemory": false,
  "eligibleForUserIntent": false
}
7. Narrow next patch to make first

The first patch should not try to build the perfect daemon. It should make the acceptance failure impossible to hide.

Patch name
embry-audio-authority-pipewire-monitor-v1
Files
packages/ux-lab/server/embryAudioAuthority.ts          new
packages/ux-lab/server/index.ts                        add routes
packages/ux-lab/src/hooks/useEmbryAudioAuthority.ts    new
packages/ux-lab/src/hooks/useEmbryPlaybackAudioLevel.ts keep but mark fallback
packages/ux-lab/src/routes/EmbryVoiceLabRoute.tsx      switch speak path
packages/ux-lab/src/components/EmbryOrb.tsx            accept authority telemetry
Server patch

Implement:

TypeScript
class EmbryAudioAuthority {
  async getStatus(): Promise<AudioAuthorityStatus>;

  async ensureEmbryBus(physicalSinkName?: string): Promise<RouteStatus>;

  async speak(req: EmbrySpeakRequest): Promise<EmbryAudioReceipt>;

  async speakerCheck(req: {
    physicalSinkName?: string;
  }): Promise<EmbryAudioReceipt>;

  async loopbackCheck(req: {
    physicalSinkName?: string;
    expectedPhrase?: string;
  }): Promise<EmbryAudioReceipt>;

  events(): EventEmitter;
}

Minimum implementation details:

- Reuse existing Chatterbox direct-speak code to create WAV.
- Copy WAV to the existing artifact area.
- Compute sha256 + duration + peak.
- Ensure embry_tts_bus exists.
- Ensure module-loopback from embry_tts_bus.monitor to selected physical sink.
- Start pw-record on embry_tts_bus.monitor before playback.
- Spawn pw-play --target embry_tts_bus <wav>.
- While pw-record emits PCM, compute RMS/peak/bands and SSE them.
- Stop recording when playback exits plus small tail, e.g. 300 ms.
- Save receipt.json.

SSE route:

TypeScript
app.get("/api/projects/embry-voice/audio/events", (req, res) => {
  res.writeHead(200, {
    "Content-Type": "text/event-stream",
    "Cache-Control": "no-cache",
    Connection: "keep-alive",
  });

  const onFrame = (frame: EmbryAudioFrame) => {
    res.write(`event: embry-audio-frame\n`);
    res.write(`data: ${JSON.stringify(frame)}\n\n`);
  };

  embryAudioAuthority.events().on("frame", onFrame);

  req.on("close", () => {
    embryAudioAuthority.events().off("frame", onFrame);
  });
});

Speak route:

TypeScript
app.post("/api/projects/embry-voice/audio/speak", async (req, res) => {
  try {
    const receipt = await embryAudioAuthority.speak({
      text: req.body.text,
      voice: "embry",
      timelineMessageId: req.body.timelineMessageId,
      requestedSinkName: req.body.sinkName,
      loopbackMode: "embry-monitor",
    });

    res.json({ ok: true, receipt });
  } catch (error) {
    res.status(500).json({
      ok: false,
      error: error instanceof Error ? error.message : String(error),
    });
  }
});

Status route should expose:

JSON
{
  "ok": true,
  "backend": "pipewire",
  "selectedSink": {
    "name": "...",
    "description": "Jabra SPEAK 510 Analog Stereo",
    "muted": false,
    "volume": "..."
  },
  "embryBus": {
    "sink": "embry_tts_bus",
    "monitor": "embry_tts_bus.monitor",
    "loopedToPhysicalSink": true
  }
}
React patch

In EmbryVoiceLabRoute.tsx:

- Replace direct DOM audio playback as the default path.
- POST to /audio/speak.
- Store active playId / receiptId.
- Subscribe to /audio/events.
- Pass authority RMS/bands to the orb.
- Add a receipt card to the shared Chat UX timeline.

Add UI controls:

[Output device: Jabra SPEAK 510 Analog Stereo]
[Speaker Check]
[Loopback Check]

Receipt card example:

Embry audio receipt
Artifact: 3d17e996a45a.wav
Route: embry_tts_bus -> Jabra SPEAK 510 Analog Stereo
Waveform source: embry_tts_bus.monitor
Monitor: confirmed, peak -8.7 dBFS
Human heard: pending
Acceptance criteria for this patch

Do not accept the patch because a DOM audio element played.

Accept only when the UI can show all of these for one playId:

1. Chatterbox artifact exists and has sha256.
2. Authority selected a physical PipeWire sink by stable name/description.
3. WAV was played through pw-play --target embry_tts_bus.
4. embry_tts_bus.monitor produced nonzero captured PCM during playback.
5. Orb was driven by monitor telemetry for that same playId.
6. Receipt JSON exists with artifact, route, playback, waveform, and monitor fields.
7. Speaker Check asks the human to confirm hearing; until then, human heard is not claimed.
8. What to avoid

Do not make HTMLAudioElement.play() the default success condition.

Do not use browser setSinkId() as the primary fix. It can be a convenience feature later, but the browser output-device API is permission/user-activation constrained and still stays inside the browser proof layer. 
MDN Web Docs
+1

Do not animate the orb from state=speaking. The orb should animate from either monitor PCM frames or a clearly labeled fallback.

Do not configure the physical sink by ephemeral numeric node id alone. pw-cat accepts either object serial or node.name; use stable names/descriptions for config and include the runtime numeric id only in receipts. 
PipeWire

Do not let loopback sanity transcripts enter memory or Tau as user intent.

Final architecture decision

Use a server-side/local Embry Audio Authority backed by PipeWire as the source of truth. Keep browser Web Audio only as optional preview/fallback. Route Chatterbox WAVs into a stable Embry virtual sink, loop that sink to the selected physical speaker, capture the bus monitor for orb telemetry and RealtimeSTT sanity tests, and write receipts for every utterance.

The narrow first patch is: replace #embry-voice direct DOM playback with /audio/speak authority playback, add embry_tts_bus monitor telemetry, drive the orb from that telemetry, and show a receipt card plus Speaker Check.

<<<WEBGPT_DONE:20260705T182302Z:32cc38f3>>>
