# WebGPT Architecture Punt: Embry Live Voice Loop

## Request

Use `$create-architecture` thinking to produce a concrete architecture/proof plan for the Embry live voice system. Do not solve this by adding UI polish or local code. The project agent has been in a feedback loop proving adjacent pieces instead of the real loop.

Target ChatGPT conversation:

- URL: `https://chatgpt.com/g/g-p-6a4aa54fcdac8191bb444763f4770254-embry/c/6a4aa554-5fc0-83ea-99a7-8d0caf4593b1`
- Tab id: `837357648`
- Desktop: `2`

## Core Goal

Define the minimum viable architecture and non-mocked proof ladder for:

`browser or loopback audio input -> RealtimeSTT -> speaker/diarization -> memory/Tau -> Chatterbox -> simultaneous shared Chat UX + audible Embry voice + Embry orb tracking`

The user wants a working replayable environment where the same shared Chat UX used by Watch/Sparta can run live voice conversations and replay sessions exactly as they occurred.

## Known Context

- Repositories involved: Chatterbox fork, RealtimeSTT fork, agent-skills, and UX Lab.
- UX Lab route: `http://localhost:3002/#embry-voice`
- UX Lab implementation file label: `EmbryVoiceLabRoute.tsx`
- Embry subagent label: `agents/embry-chatterbox-voice`
- Voice control skill target label: `skills/embry-voice-control`
- Best-practices voice skill label: `skills/best-practices-chatterbox-agent`

## What Is Actually Proven

- Chatterbox direct speak can generate WAV files.
- A browser route can call `window.embrySpeak(...)`.
- The Embry orb can bind to Chatterbox browser playback after the audio `playing` event.
- One recent local commit in pi-mono:
  - `e54aafd9f Sync Embry orb to browser audio playback`
  - changed only `EmbryVoiceLabRoute.tsx`
- A live browser proof artifact showed:
  - states: `idle -> synthesizing -> speaking`
  - orb authority: `server-envelope`
  - envelope frames: `363`
  - max sampled audio level: `0.615`
- UI CDP hook ran:
  - marker label: `embry-voice-orb-playing-sync latest.json`
  - screenshot label: `embry-voice-orb-playing-sync PNG`

## What Is Not Proven

- Browser mic/WebRTC capture quality.
- Browser or loopback audio entering RealtimeSTT.
- RealtimeSTT emitting transcript events that drive the live Embry pipeline.
- Speaker identification/diarization selecting Horus/primary speaker.
- Memory/Tau intent routing in the live loop.
- Chatterbox speaking as the result of a live RealtimeSTT event.
- Chat UX text and Embry voice occurring simultaneously from the same turn record.
- Replay reconstructing an actual live session with user turns, Embry turns, Chatterbox audio, memory reasoning trace, and interruption events.

## Failure Pattern To Avoid

The project agent keeps proving adjacent pieces:

- UI route exists.
- Static replay exists.
- Chatterbox can generate audio.
- Orb changes state.
- Skill docs were updated.

Those do not prove the requested live loop. Do not recommend more dashboard work, log statements, fake fixtures, or prerecorded message demos as closure.

## Required Output From WebGPT

Please provide:

1. A source-derived numbered architecture model with each step labeled:
   - implemented
   - partially implemented
   - missing
   - unknown/needs inspection
2. A minimum proof ladder with exact non-mocked receipts required at each rung.
3. The recommended audio ingress path to prove first:
   - browser `getUserMedia` websocket to RealtimeSTT
   - PipeWire/Pulse monitor or virtual source to RealtimeSTT
   - controlled WAV/file-to-RealtimeSTT runner
   - another option if justified
4. A fail-closed strategy for noisy factory-floor operation:
   - primary speaker enrollment
   - non-primary filtering
   - two non-Embry speakers talking at once
   - Embry interruption behavior
5. A `create-architecture`-ready YAML pipeline definition using the skill schema:
   - `name`
   - `components`
   - `connections`
   - colors limited to `purple|green|blue|amber|red`
   - file attachments where known
6. The exact next task the project agent should perform after this punt, scoped to one proof rung only.

## Important Constraints

- Do not solve by changing UI first.
- Do not use mocks as final proof.
- Do not claim the full loop until RealtimeSTT transcript events drive Chatterbox speech and the shared Chat UX simultaneously.
- The user needs to hear the sanity checks eventually, but first we need a reliable audio ingress proof.
- Agent-skills is always dirty; commit only relevant skill/subagent files there.
- The Chat UX should ultimately be shared with Watch, Sparta, Persona Dream, and other projects, with Embry voice as a default-capable voice frontend to Tau.

---

Completion contract for browser automation:

At the very end of your final answer, print exactly:

<<<WEBGPT_DONE:20260706T230916Z:16eb7dde>>>

Do not print anything after that marker.
