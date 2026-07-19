I could not inspect the target ChatGPT tab or the local /home/graham/... checkout from this runtime, so the local status labels below are derived from the source facts in your prompt plus upstream RealtimeSTT, browser media, and PipeWire docs. The key architectural correction is: do not let UX Lab be the proof authority. UX Lab should subscribe to a live session event ledger that is driven first by real RealtimeSTT transcript events.

0. Architecture invariant

The minimum viable live voice loop should have one event spine:

audio ingress receipt
→ RealtimeSTT event
→ speaker gate decision
→ Tau/memory turn decision
→ Chatterbox artifact
→ audio-output authority playback
→ shared Chat UX turn update
→ replayable session journal

A full-loop claim is valid only when a RealtimeSTT final transcript event creates the same turn_id that later receives Tau reasoning, Chatterbox audio, audible playback, orb envelope samples, and Chat UX updates. Direct window.embrySpeak(...) remains useful as a component proof, but it is not the live loop.

RealtimeSTT already exposes the right low-level contract for this: external audio mode uses AudioToTextRecorder(use_microphone=False), accepts feed_audio(...), expects 16-bit mono PCM with 16 kHz as the best input format, can resample other rates, and supports realtime/final callbacks. 
GitHub
 RealtimeSTT’s FastAPI reference server also already models a browser-streaming server with WS /ws/transcribe, per-session recorder state, realtime text, final text, warnings, errors, health, config, metrics, queue depth, and active-speaker limits. 
GitHub

1. Source-derived numbered architecture model

Audio ingress authority — missing
This must be a non-UI process or service that owns input source identity, PCM chunking, timing, session IDs, and capture receipts. It should support three sources: PipeWire monitor/virtual source first, browser microphone later, and controlled file injection for preflight. RealtimeSTT’s external-audio API explicitly supports files, websocket clients, browser streams, telephony/media servers, and other processes, which matches the intended boundary. 
GitHub

PipeWire/Pulse loopback ingress — missing / recommended first proof
Use a virtual source or monitor path to prove actual OS audio enters RealtimeSTT before touching UI. PipeWire’s pw-cat family includes pw-play for playback and pw-record for capture, and its --target can be auto, 0, an object serial, or a node name. 
PipeWire
 PipeWire also has pw-loopback, which creates loopback nodes with explicit capture and playback targets. 
PipeWire

Browser microphone/WebRTC ingress — missing / later
Browser getUserMedia is a real ingress path, but it should not be the first proof authority. It requires a secure context, user permission, top-level permission policy, and the returned promise can fail or even remain unresolved if the user ignores the permission prompt. 
MDN Web Docs
+1
 Browser mic is important after the loopback proof is green.

RealtimeSTT recorder integration — partially implemented upstream, missing in Embry loop
The capability exists in RealtimeSTT: use_microphone=False, feed_audio, realtime transcription, final transcription, VAD callbacks, wake words, and recorded chunk callbacks are documented. 
GitHub
 What is missing is an Embry-owned adapter that emits normalized stt.realtime, stt.final, vad.start, vad.stop, and audio.ingress.receipt events into the shared session ledger.

Speaker identification / diarization gate — missing / unknown needs inspection
There is no proven receipt that a primary speaker, Horus, has been enrolled, recognized, and used to decide whether a transcript is allowed into Tau. This must be a fail-closed gate between RealtimeSTT and memory/Tau, not a display label added after transcription.

Primary-speaker policy — missing
The system needs a deterministic rule: no primary speaker match, no Tau route. Non-primary speech can be logged as rejected ambient speech, but it must not create an Embry response. Two overlapping non-Embry speakers should produce speaker_gate.rejected.overlap, not a conversational turn.

Memory/Tau live-turn router — unknown / needs inspection
The requested loop requires accepted stt.final events to invoke Tau/memory and return an Embry response plan. The prompt lists memory/Tau as unproven in the live loop. Therefore this is not currently claimable.

Chatterbox generation — partially implemented
Proven: Chatterbox direct speak can generate WAV files. Missing: Chatterbox is not yet proven as the result of a live RealtimeSTT event routed through Tau/memory. Direct generation is a component proof, not a loop proof.

Embry audio output authority — partially implemented
Proven: the recent browser proof showed idle -> synthesizing -> speaking, orb authority server-envelope, 363 envelope frames, and max sampled audio level 0.615. Also proven from prior context: Chatterbox WAV generation and local playback can work. Missing: the output authority is not yet bound to a turn_id that originated from RealtimeSTT.

Embry orb tracking — partially implemented
Proven: the orb can bind to Chatterbox browser playback after the playing event, and recent proof used server-envelope. Missing: orb tracking is not yet tied to an Embry response generated from live input. The orb should remain an output subscriber, not a proof authority.

Shared Chat UX timeline — partially implemented
Proven: UX Lab route exists and can show Embry voice state. Missing: Chat UX does not yet prove simultaneous text/audio from the same event-sourced turn record. The shared Chat UX must render the ledger used by Watch, Sparta, Persona Dream, and Embry, not maintain an Embry-only side path.

Replay system — missing
Static replay or prerecorded demos do not count. Replay must reconstruct an actual live session from a journal containing input audio receipts, STT events, speaker decisions, Tau/memory events, Chatterbox artifacts, playback timestamps, orb envelope samples, and interruption events.

Interruption / barge-in controller — missing
The system must know when Embry is speaking, prevent Embry’s own TTS from being interpreted as user speech, and stop or duck Embry only when the primary speaker interrupts. This belongs in the event spine and audio authorities, not in UI polish.

Current UX Lab route EmbryVoiceLabRoute.tsx — partially implemented, not the next place to work
The recent commit e54aafd9f Sync Embry orb to browser audio playback changed only the route. That is useful component work, but further UI work would keep proving adjacent pieces. The next proof must be non-UI audio ingress into RealtimeSTT.

2. Minimum non-mocked proof ladder
Rung 1 — OS audio ingress into RealtimeSTT

Goal: prove real audio bytes enter RealtimeSTT and produce transcript events.

Recommended source: a known spoken WAV injected through a PipeWire/Pulse virtual source or monitor, captured as PCM, then fed to RealtimeSTT. This is not a final live demo; it is the first real ingress proof.

Required receipts:

JSON
{
  "rung": "01_pipewire_monitor_to_realtimestt",
  "run_id": "...",
  "source_audio": {
    "path": "...wav",
    "sha256": "...",
    "expected_phrase": "..."
  },
  "pipewire": {
    "playback_command": "...",
    "capture_command": "...",
    "source_node": "...",
    "monitor_node": "...",
    "sample_rate": 16000,
    "channels": 1,
    "format": "s16le"
  },
  "realtimestt": {
    "use_microphone": false,
    "engine": "...",
    "model": "...",
    "vad_start_ms": 123,
    "realtime_updates": ["..."],
    "final_transcript": "...",
    "vad_stop_ms": 456
  },
  "acceptance": {
    "captured_audio_non_silent": true,
    "transcript_matches_expected": true,
    "no_typed_text_path": true
  }
}

Pass condition: the final transcript comes from RealtimeSTT callbacks fed by captured PCM, not from the file name, expected text, a mock event, or UI input.

Rung 2 — Browser microphone ingress into the same RealtimeSTT event contract

Goal: prove browser mic/WebRTC can feed the same adapter.

Required receipts:

JSON
{
  "rung": "02_browser_getusermedia_to_realtimestt",
  "browser": {
    "origin": "http://localhost:3002",
    "permission_state": "granted",
    "device_id_hash": "...",
    "sample_rate": 48000,
    "packet_count": 123
  },
  "websocket": {
    "session_id": "...",
    "binary_audio_packets": 123,
    "dropped_packets": 0
  },
  "realtimestt": {
    "final_transcript": "...",
    "realtime_updates": ["..."]
  }
}

Pass condition: a live spoken phrase enters RealtimeSTT through browser audio packets. Browser permission and packet receipts are required because getUserMedia is permission-gated and can fail or remain unresolved. 
MDN Web Docs
+1

Rung 3 — Primary-speaker gate

Goal: prove that only the enrolled primary speaker can create a routable user turn.

Required receipts:

JSON
{
  "rung": "03_primary_speaker_gate",
  "enrollment": {
    "speaker_id": "horus_primary",
    "sample_count": 3,
    "sample_sha256": ["...", "...", "..."],
    "threshold": 0.82
  },
  "test_segments": [
    {
      "segment_id": "primary_001",
      "speaker_score": 0.91,
      "decision": "accepted"
    },
    {
      "segment_id": "distractor_001",
      "speaker_score": 0.41,
      "decision": "rejected_non_primary"
    },
    {
      "segment_id": "overlap_001",
      "speaker_score": null,
      "decision": "rejected_overlap"
    }
  ]
}

Pass condition: non-primary and overlapping speech do not reach Tau, even when RealtimeSTT can transcribe them.

Rung 4 — Accepted STT event drives Tau/memory

Goal: prove the live input event, not a typed prompt, creates the Embry response plan.

Required receipts:

JSON
{
  "rung": "04_stt_final_to_tau_memory",
  "turn_id": "...",
  "input_event_id": "stt.final....",
  "speaker_gate_event_id": "speaker_gate.accepted....",
  "memory": {
    "retrieval_ids": ["..."],
    "tau_route": "...",
    "trace_summary": ["..."]
  },
  "embry_response": {
    "text": "...",
    "source": "tau_live_turn"
  }
}

Pass condition: Tau receives only the accepted transcript event and returns the text that will be spoken by Chatterbox.

Rung 5 — Tau response drives Chatterbox and shared Chat UX simultaneously

Goal: prove one turn record produces both visible text and audible Embry voice.

Required receipts:

JSON
{
  "rung": "05_tau_to_chatterbox_chat_audio",
  "turn_id": "...",
  "chat": {
    "turn_created_event_id": "...",
    "text_visible_at_ms": 1234,
    "audio_artifact_id": "..."
  },
  "chatterbox": {
    "wav_path": "...",
    "wav_sha256": "...",
    "duration_ms": 13640
  },
  "audio_output": {
    "driver": "pipewire",
    "playback_pid": 12345,
    "started_at_epoch_ms": 1783291077744
  },
  "orb": {
    "authority": "server-envelope",
    "envelope_frames": 363,
    "max_level": 0.615
  }
}

Pass condition: Chat UX and Chatterbox audio share the same turn_id. DOM audio alone does not count.

Rung 6 — Embry interruption

Goal: prove barge-in without self-triggering from Embry’s own voice.

Required receipts:

JSON
{
  "rung": "06_primary_barge_in",
  "embry_output": {
    "turn_id": "...",
    "audio_artifact_id": "...",
    "playing": true,
    "offset_ms_at_interrupt": 2410
  },
  "ingress": {
    "detected_speech_during_embry_output": true,
    "self_audio_suppressed": true,
    "speaker_id": "horus_primary"
  },
  "action": {
    "event": "embry.interrupted",
    "playback_stopped": true,
    "new_user_turn_created": true
  }
}

Pass condition: primary speaker speech interrupts Embry; non-primary speech does not.

Rung 7 — Replay actual live session

Goal: prove the session can be reconstructed exactly.

Required receipts:

JSON
{
  "rung": "07_event_sourced_replay",
  "session_id": "...",
  "event_count": 123,
  "artifact_sha256": ["...", "..."],
  "replay": {
    "turn_order_matches": true,
    "audio_offsets_match": true,
    "interruptions_match": true,
    "chat_snapshots_match": true
  }
}

Pass condition: replay consumes the session journal and audio artifacts from the live run. No fixture-only replay, no static demo.

3. Recommended ingress path to prove first

Prove PipeWire/Pulse virtual source or monitor → RealtimeSTT first.

Reason:

It proves the real local audio stack, not just a file parser.

It avoids browser permission and device-selection instability at the first rung.

It directly supports later loopback sanity checks for Embry’s own output.

It can be made deterministic by injecting a known spoken WAV while still passing through OS audio capture.

It aligns with RealtimeSTT’s documented external-audio boundary: other processes can emit PCM chunks that are fed into AudioToTextRecorder(use_microphone=False). 
GitHub

Do not prove browser getUserMedia first. Browser mic is important, but it has user-permission and secure-context rules that make it a poor foundation proof. 
MDN Web Docs
+1

Do not use a pure file-to-RealtimeSTT runner as closure. A pure file runner is acceptable as a 5-minute codec preflight because RealtimeSTT documents direct file/external feed support, but it does not prove the requested browser-or-loopback ingress path. 
GitHub

4. Fail-closed strategy for noisy factory-floor operation
Primary speaker enrollment

Enrollment should create a speaker_profile_id only after multiple clean samples from Horus/primary speaker. Store sample hashes, embedding model version, threshold, SNR, and enrollment timestamp. A live segment should be accepted only when both speech activity and speaker match exceed thresholds. Low SNR, missing embedding, or ambiguous score means speaker_gate.rejected, not “best guess.”

Non-primary filtering

RealtimeSTT may transcribe non-primary speech, but the speaker gate owns routing. Non-primary transcripts can be stored as ambient diagnostics with redaction rules, but they must not enter Tau and must not create Embry responses. The event name should be explicit:

speaker_gate.rejected.non_primary
Two non-Embry speakers talking at once

Overlapping non-primary speech should fail closed:

vad.start
diarization.overlap_detected
speaker_gate.rejected.overlap
no_tau_route
no_chatterbox_output

The UI may show “unverified speech ignored,” but the system must not answer.

Primary + non-primary overlap

If Horus is present but overlap is high, prefer rejection over risky routing. A reasonable rule is:

accept only when primary_score >= threshold
and overlap_ratio <= threshold
and transcript_confidence >= threshold
and speech_segment_snr >= threshold

Otherwise produce:

speaker_gate.rejected.ambiguous_primary_overlap
Embry interruption behavior

Embry output must be tagged as self-audio with known artifact ID, start time, envelope, and playback node. The ingress gate must avoid treating Embry’s Chatterbox voice as user speech. During Embry playback:

Primary speaker detected with high confidence → stop or duck Embry, emit embry.interrupted, create new user turn.

Non-primary speech detected → do not interrupt and do not route to Tau.

Ambiguous overlap → fail closed; optionally stop Embry only for safety, but do not route content.

Embry’s own loopback audio detected → classify as self_audio and suppress.

This requires the input authority and output authority to share session timing, artifact IDs, and playback state.

5. create-architecture-ready YAML
YAML
name: embry_live_voice_loop_minimum_viable_architecture

components:
  - id: ingress_audio_authority
    name: Ingress Audio Authority
    color: blue
    status: missing
    purpose: Owns browser, loopback, or controlled audio input; emits capture receipts and ordered PCM chunks.
    files:
      - /home/graham/workspace/experiments/agent-skills/skills/embry-voice-control

  - id: pipewire_virtual_ingress
    name: PipeWire/Pulse Virtual Source Or Monitor
    color: blue
    status: missing
    purpose: First reliable non-UI audio ingress proof path into RealtimeSTT.
    files: []

  - id: browser_mic_ingress
    name: Browser getUserMedia Ingress
    color: amber
    status: missing
    purpose: Later live browser microphone path using websocket audio packets.
    files:
      - /home/graham/workspace/experiments/pi-mono/packages/ux-lab/src/components/embry-voice/EmbryVoiceLabRoute.tsx

  - id: realtime_stt_adapter
    name: RealtimeSTT Embry Adapter
    color: blue
    status: missing
    purpose: Feeds PCM into RealtimeSTT and emits vad, realtime transcript, and final transcript events.
    files: []

  - id: speaker_gate
    name: Primary Speaker And Diarization Gate
    color: red
    status: missing
    purpose: Accepts only enrolled primary speaker turns; rejects ambient, non-primary, and overlap.
    files:
      - /home/graham/workspace/experiments/agent-skills/skills/embry-voice-control

  - id: tau_memory_router
    name: Tau Memory Router
    color: purple
    status: unknown
    purpose: Converts accepted user transcript events into Embry response plans with memory trace.
    files: []

  - id: chatterbox_synth
    name: Chatterbox Embry Voice Synth
    color: green
    status: partially_implemented
    purpose: Generates Embry WAV artifacts from response text.
    files:
      - /home/graham/workspace/experiments/chatterbox
      - /home/graham/workspace/experiments/agent-skills/agents/embry-chatterbox-voice
      - /home/graham/workspace/experiments/agent-skills/skills/best-practices-chatterbox-agent

  - id: audio_output_authority
    name: Embry Audio Output Authority
    color: green
    status: partially_implemented
    purpose: Plays Chatterbox audio audibly and emits artifact, playback, and envelope receipts.
    files:
      - /home/graham/workspace/experiments/pi-mono/packages/ux-lab/server/index.ts
      - /home/graham/workspace/experiments/pi-mono/packages/ux-lab/src/hooks/useEmbryPlaybackAudioLevel.ts

  - id: shared_chat_turn_ledger
    name: Shared Chat UX Turn Ledger
    color: purple
    status: partially_implemented
    purpose: Central event-sourced timeline used by Watch, Sparta, Persona Dream, Embry, and replay.
    files:
      - /home/graham/workspace/experiments/pi-mono/packages/ux-lab/src/components/embry-voice/EmbryVoiceLabRoute.tsx

  - id: embry_orb
    name: Embry Orb Subscriber
    color: green
    status: partially_implemented
    purpose: Visualizes the output authority envelope for the same Embry turn audio artifact.
    files:
      - /home/graham/workspace/experiments/pi-mono/packages/ux-lab/src/components/embry-voice/EmbryVoiceOrb.tsx
      - /home/graham/workspace/experiments/pi-mono/packages/ux-lab/src/components/embry-voice/IdentityNode.tsx

  - id: replay_engine
    name: Event-Sourced Replay Engine
    color: amber
    status: missing
    purpose: Reconstructs actual live sessions from event journal and artifact hashes.
    files: []

  - id: interruption_controller
    name: Embry Interruption Controller
    color: red
    status: missing
    purpose: Prevents self-triggering and allows primary-speaker barge-in to stop Embry output.
    files:
      - /home/graham/workspace/experiments/agent-skills/skills/embry-voice-control

connections:
  - from: pipewire_virtual_ingress
    to: ingress_audio_authority
    color: blue
    status: missing
    label: Captured PCM chunks plus source and monitor node receipts.

  - from: browser_mic_ingress
    to: ingress_audio_authority
    color: amber
    status: missing
    label: getUserMedia MediaStream packets over websocket.

  - from: ingress_audio_authority
    to: realtime_stt_adapter
    color: blue
    status: missing
    label: Ordered 16-bit mono PCM chunks with session and source ids.

  - from: realtime_stt_adapter
    to: speaker_gate
    color: blue
    status: missing
    label: VAD, realtime transcript, final transcript, chunk timing events.

  - from: speaker_gate
    to: tau_memory_router
    color: red
    status: missing
    label: Accepted primary-speaker final transcript only.

  - from: tau_memory_router
    to: shared_chat_turn_ledger
    color: purple
    status: unknown
    label: User turn and Embry response plan with memory trace.

  - from: tau_memory_router
    to: chatterbox_synth
    color: purple
    status: missing
    label: Embry response text to synthesize.

  - from: chatterbox_synth
    to: audio_output_authority
    color: green
    status: partially_implemented
    label: Chatterbox WAV artifact with sha256, duration, and envelope.

  - from: audio_output_authority
    to: shared_chat_turn_ledger
    color: green
    status: partially_implemented
    label: Playback start, audio artifact, and audible output receipt for same turn id.

  - from: audio_output_authority
    to: embry_orb
    color: green
    status: partially_implemented
    label: Server envelope and playback timing for visible orb tracking.

  - from: audio_output_authority
    to: interruption_controller
    color: red
    status: missing
    label: Current Embry playback artifact, offset, and self-audio suppression data.

  - from: interruption_controller
    to: shared_chat_turn_ledger
    color: red
    status: missing
    label: Barge-in, stop, duck, cancel, and partial-playback events.

  - from: shared_chat_turn_ledger
    to: replay_engine
    color: purple
    status: missing
    label: Append-only session events and artifact references for exact replay.
6. Exact next task for the project agent

Task: implement and run only Rung 1: PipeWire/Pulse virtual source or monitor → RealtimeSTT ingress receipt.

Scope:

Do not touch EmbryVoiceLabRoute.tsx.
Do not add UI.
Do not call Chatterbox.
Do not route to Tau.
Do not claim live loop.

The project agent should create a non-UI proof runner that:

Creates or selects a PipeWire/Pulse virtual source or monitor.

Plays a known spoken WAV into that audio path.

Captures the monitor/source as real PCM.

Feeds captured chunks into AudioToTextRecorder(use_microphone=False, enable_realtime_transcription=True).

Emits a JSON receipt containing source WAV hash, captured audio hash, PipeWire node/source names, sample format, RealtimeSTT config, VAD events, realtime updates, final transcript, and pass/fail.

Saves the captured audio artifact so silence, clipping, and wrong-device capture can be independently checked.

Commits only the relevant proof runner and skill/subagent documentation if placed under agent-skills; leave unrelated dirty files alone.

Acceptance for this one task:

A real RealtimeSTT final transcript event is produced from captured PipeWire/Pulse audio,
the captured audio artifact is non-silent,
the transcript matches the expected spoken phrase,
and the proof receipt contains enough data to replay the ingress test without UX Lab.

That is the next move because every higher rung depends on this one. Without this receipt, more orb, dashboard, route, or replay work would continue proving adjacent pieces instead of the live Embry voice loop.

<<<WEBGPT_DONE:20260706T230916Z:16eb7dde>>>
