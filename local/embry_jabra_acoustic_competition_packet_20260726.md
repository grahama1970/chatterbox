# Embry Jabra Acoustic MVP Competition Packet

Objective:
Find the smallest repair path for the Embry voice blocker at the acoustic/Jabra capture and RealtimeSTT/Whisper boundary, and provide a debugger-ready script/checklist the project agent and human can run.

Immutable goal:
Produce a minimal, deterministic path that turns the fresh Chatterbox answer WAV into ASR-usable captured speech, or proves with receipts that a specific lower-level dependency is unavailable. Do not claim the full Embry voice goal is met. The current full goal still requires wake word -> Jabra capture -> RealtimeSTT final transcript -> SPARTA live-turn -> Chatterbox playback/replay -> orb CDP proof.

Target repo/path:
- Repo: `/home/graham/workspace/experiments/chatterbox`
- Reproducer script: `scripts/debug_embry_jabra_acoustic_mvp.sh`
- Existing bridge under inspection: `scripts/smoke_realtimestt_listener_bridge.py`

Shared context:
The typed MVP now passes:
- Fresh MVP summary: `/tmp/embry-voice-mvp-problem-20260726T2012Z/results-r9-20260726T213537Z/summary.json`
- `pass: true`, `mocked: false`, `live: true`
- SPARTA live-turn returns `answerAuthority=wikipedia_rest`
- Chatterbox renders WAV:
  `/home/graham/workspace/experiments/chatterbox/logs/ux-lab-embry-direct/2026-07-26T21-36-48-714Z-a912bdabfee8.wav`
- Chatterbox receipt:
  `/home/graham/workspace/experiments/chatterbox/logs/ux-lab-embry-direct/2026-07-26T21-36-48-714Z-a912bdabfee8.json`
- Chatterbox envelope has 443 frames, 442 nonzero, and `level/rms/bass/mid/treble` fields for orb animation input.

Memory is not the current blocker:
- Memory `/intent` correctly returns `NO_MATCH`, `outside_memory_domains`.
- Memory `/answer` remains defective/degraded and is tracked separately:
  https://github.com/grahama1970/graph-memory-operator/issues/59
- SPARTA live-turn can currently bypass Memory for this general fact using `wikipedia_rest`.

Current acoustic/ASR evidence:
- Jabra playback attempt:
  `/tmp/embry-voice-mvp-problem-20260726T2012Z/results-r9-20260726T213537Z/jabra-playback-attempt.json`
  - `returncode: 0`
  - target: `alsa_output.usb-0b0e_Jabra_SPEAK_510_USB_501AA5274B1D022000-00.analog-stereo`
- Jabra mic capture during playback:
  `/tmp/embry-voice-mvp-problem-20260726T2012Z/results-r9-20260726T213537Z/jabra-mic-capture-20260726T213849Z.json`
  - record target: `alsa_input.usb-0b0e_Jabra_SPEAK_510_USB_501AA5274B1D022000-00.mono-fallback`
  - capture bytes: 477168
  - duration: 9.940083 seconds
  - mean volume: -50.6 dB
  - max volume: -37.6 dB
  - playback return code: 0
  - record return code: 124, from the bounded `timeout 10` recording window
- RealtimeSTT/Whisper check against that capture:
  `/tmp/embry-voice-mvp-problem-20260726T2012Z/results-r9-20260726T213537Z/jabra-mic-capture-realtimestt-whisper-container-key.json`
  - `ok: false`
  - failed gate: `realtimestt_transcript_present`
  - ASR executor call count: 1
  - ASR transcript: empty string

Fresh debugger-script smoke:
- Command:
  `OUT_DIR=/tmp/embry-jabra-acoustic-debug-smoke-20260726T2257Z scripts/debug_embry_jabra_acoustic_mvp.sh`
- Summary:
  `/tmp/embry-jabra-acoustic-debug-smoke-20260726T2257Z/summary.json`
- Result:
  - playback succeeded
  - Jabra capture existed, 477168 bytes, 9.940083 seconds
  - mean volume improved to -42.4 dB and max volume to -17.1 dB
  - ASR did not run because Docker container `whisper` is currently stopped
  - script failed closed with `failed_gates: ["whisper_container_running"]`

Candidate task:
1. Diagnose the minimum likely cause of the acoustic/ASR failure.
2. Propose the smallest change or command sequence to get an ASR-usable transcript from the Jabra capture path.
3. Improve or validate the debugger script contract if needed.
4. Return a concrete sequence the project agent can run locally.

Judging criteria:
- deterministic proof quality
- minimal scope
- avoids browser microphone
- uses PipeWire/Jabra/Realtimestt/Whisper correctly
- distinguishes service-down from audio-level/capture-route failure
- preserves fail-closed receipts
- provides debugger breakpoint locations and expected live variables

Expected output schema:
- `APPROACH:` concise diagnosis and plan
- `CHANGES:` exact script/source changes or commands
- `PROOF_COMMANDS:` commands the project agent should run
- `DEBUGGER_BREAKPOINTS:` file:line, source statement, expected variables
- `VERIFIED_FEATURE:` only features locally checkable from the provided artifacts
- `RISKS:` remaining failure modes
- `BLOCKERS:` missing credentials, service state, hardware state, or human decision only

Forbidden claims:
- Do not claim the full Embry voice goal is solved.
- Do not claim Memory is the current acoustic blocker.
- Do not use browser microphone as the primary input path.
- Do not propose canned transcripts or mocked ASR as proof.
- Do not bypass Tau/Memory authority for general project architecture; this packet is only the acoustic MVP.

Proof boundary:
Useful candidate output is advisory. Local closure requires a fresh receipt where either:
- Jabra playback -> Jabra mic capture -> RealtimeSTT/Whisper produces non-empty accepted transcript, or
- a focused receipt proves a concrete lower-level blocker such as stopped Whisper service, unavailable Jabra source, muted hardware, or capture route not linked.
