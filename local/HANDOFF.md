# Handoff Report: Chatterbox / Embry Live Voice

**Timestamp**: 2026-07-17T20:55:00Z
**Active Agent**: Codex

## 1. Project Overview

- **Ecosystem**: Python, FastAPI, Docker, CUDA/PyTorch, PipeWire, RealtimeSTT, SQLite voice journal, Tau/Memory, UX Lab, and Chatterbox.
- **Core Purpose**: This repository is the Chatterbox fork used as Embry's speech renderer. It is not the listener, memory, or UI authority. The current live integration path is:

```text
PipeWire audio source -> RealtimeSTT PCM socket -> SQLite voice-events journal ->
UX Lab listener/latest -> Tau/Memory live-turn -> Chatterbox WAV -> pw-play
```

- **Current human outcome**: Make the human-audible Embry loop work from a spoken wake/request through audible answer, without mocked/unit-test substitutes.

## 2. Current State: Doc-Code Alignment

- `README.md` correctly says the Unix/PipeWire RealtimeSTT path is the listener authority and browser `getUserMedia` is diagnostic only.
- The previous `local/HANDOFF.md` centered on a 200-case mixed-qualified campaign. That is stale for the current blocker. The active problem is a fresh physical human microphone path, not batch campaign retention.
- The project-local handoff runner required by the skill was absent:
  - attempted command: `bash .pi/skills/handoff/run.sh`
  - result: `No such file or directory`
- No `CONTEXT.md` or `0N_TASKS.md` exists in this repo. Supplemental facts came from `README.md`, git state, runtime health, and receipt artifacts under `logs/`.

## 3. What Is Working

- **RealtimeSTT PCM reconnect repair is durable in source**:
  - repo: `/home/graham/workspace/experiments/RealtimeSTT`
  - commit: `0cf2a16 Keep Embry PCM ingress alive across sender reconnects`
  - pushed to `origin/master`
  - current live container was also hotpatched earlier; if the container is recreated from an old image, rebuild/redeploy may still be needed.

- **C920 live PCM sender is currently running**:
  - service: `embry-pcm-sender-c920.service`
  - source: `alsa_input.usb-046d_HD_Pro_Webcam_C920_9947BA2F-02.analog-stereo`
  - restore artifact: `logs/restore-c920-sender-after-alsa-check-20260717T194333Z`
  - health at handoff: `ready=true`, `pcm.connected=true`, `gap_count=0`, `sample_gap_count=0`, `last_error=null`

- **Speaker-to-C920 physical acoustic path can wake and transcribe**:
  - artifact: `logs/live-c920-speaker-wake-request-20260717T191736Z/events_225_352.json`
  - event counts: 1 `listener.wake_detected`, 1 `listener.audio_turn_started`, 124 partial transcripts, 1 `listener.final_transcript`, 1 `listener.receipt_written`
  - final transcript: `What is the capital of France?`
  - final sequence: `351`
  - source node in receipt: C920 PipeWire source

- **Journal final -> Tau/Memory -> Chatterbox -> playback works**:
  - artifact: `logs/live-c920-journal-final-to-playback-20260717T192014Z`
  - listener latest: `mocked=false`, `live=true`, `authority=unix_pipewire_realtimestt_journal`, `wake_detected=true`, final sequence `351`
  - live-turn answer: `The capital of France is Paris.`
  - playback command started by UX Lab: `pw-play --target 65 <generated wav>`
  - generated WAV: `logs/ux-lab-embry-live/2026-07-17T19-20-14-431Z-physical-container-canary-20260717T1531Z-c920-journal-seq-351.wav`

- **UX Lab journal fallback exists in code**:
  - repo: `/home/graham/workspace/experiments/pi-mono`
  - commit object: `9ed10c7ce Read latest Embry listener turn from journal`
  - code present in `packages/ux-lab/server/index.ts`
  - key symbol: `latestJournalListenerReceipt()`
  - endpoint observed returning latest journal final:
    - `/api/projects/embry-voice/listener/latest`
    - `final_sequence=351`
    - `final_transcript=What is the capital of France?`
  - push was rejected earlier because the branch was non-fast-forward. Do not pull/rebase in the dirty pi-mono tree without explicit handling.

## 4. What Is Currently Broken

- **Fresh human speech via C920 is not producing a new listener final transcript**.
  - default gain attempt: `logs/live-human-c920-window-20260717T192158Z`
    - `found_final=0`
    - RMS `814`, max `17906`
    - Whisper text empty
  - boosted gain attempt: `logs/live-human-c920-boosted-window-20260717T193214Z`
    - C920 PipeWire volume `2.00`
    - `found_final=0`
    - RMS `6754`, max `32768`
    - Whisper text garbled and clipped
  - trimmed gain attempt: `logs/live-human-c920-trimmed-window-20260717T193359Z`
    - C920 PipeWire volume `1.35`
    - `found_final=0`
    - RMS `2535`, max `32768`
    - Whisper text empty
  - C920 gain was restored to `1.00` afterward:
    - `logs/restore-c920-known-good-gain-20260717T193512Z`

- **Brave Search supports investigating PipeWire/C920, but no fix is proven yet**:
  - raw bundle: `logs/brave-search-c920-pipewire-20260717T194035Z`
  - relevant classes found: C920 + PipeWire `spa.alsa` timeout reports, wrong source/profile routing, ALSA capture controls, and stereo-to-mono/remap-source behavior.
  - local C920 ALSA control is already maxed:
    - command: `amixer -c 3 scontents`
    - result: `Mic Capture 15 [100%] [50.00dB] [on]`

- **Stereo downmix was checked and did not explain the failure**:
  - artifact: `logs/live-c920-stereo-channel-check-20260717T194157Z`
  - left channel: RMS `757`, Whisper empty
  - right channel: RMS `709`, Whisper empty
  - averaged mono: RMS `715`, Whisper empty

- **Direct ALSA comparison is still unproven**:
  - artifact: `logs/live-c920-direct-alsa-check-20260717T194314Z`
  - intended command: direct `arecord -D plughw:C920,0`
  - actual error: `arecord: main:834: audio open error: Device or resource busy`
  - PipeWire still owned the C920 device.
  - The transient C920 sender unit was removed by `systemctl stop`; it was recreated successfully at `logs/restore-c920-sender-after-alsa-check-20260717T194333Z`.

- **UX Lab service is unstable right now**:
  - `ux-lab-api.service` was observed in `activating (auto-restart)` with restart counter over 700.
  - The endpoint briefly responded during the restart window, but the service needs its journal checked before relying on it as stable.
  - This may be related to unrelated dirty `pi-mono` work, not the Chatterbox repo.

## 5. Next Steps

1. **Do not create unit tests or mocked deterministic checks for this blocker.** The user explicitly wants non-mocked live/e2e sanity only.
2. Stabilize or inspect `ux-lab-api.service` before another live-turn call:

```bash
systemctl --user --no-pager --full status ux-lab-api.service
journalctl --user -u ux-lab-api.service -n 120 --no-pager
```

3. Run the direct ALSA isolation correctly:
   - stop the RealtimeSTT C920 sender
   - also release PipeWire/WirePlumber ownership of the C920 audio device, or use a method that prevents PipeWire from holding card 3
   - record `plughw:C920,0` directly
   - restore the C920 sender afterward
   - stop condition:
     - if direct ALSA hears intelligible speech, root cause is PipeWire/WirePlumber routing/profile/processing
     - if direct ALSA also fails, root cause is below PipeWire or physical C920 microphone behavior

4. If ALSA works, create a reversible PipeWire remap/mono source for C920 and point `embry_pcm_sender` at that source. Prefer a transient `pw-loopback` experiment before editing persistent WirePlumber config.
5. If ALSA fails, stop spending iterations on C920 PipeWire and switch to a known close-talk microphone for the human-spoken release path.
6. After a fresh human final transcript appears, chain it through:
   - `/api/projects/embry-voice/listener/latest`
   - `/api/projects/embry-voice/live-turn` with `physical_playback=true`
   - `pw-play --target 65`
   - receipt paths must show `mocked=false`, `live=true`.

## 6. Project Context for Success

- **Key Chatterbox files**:
  - `src/chatterbox/agent/server.py`: Chatterbox render API.
  - `scripts/start_agent_server_docker.sh`: Chatterbox container launcher.
  - `logs/ux-lab-embry-live/`: generated UX Lab Chatterbox WAV/JSON receipts.

- **Key cross-repo files**:
  - `/home/graham/workspace/experiments/RealtimeSTT/RealtimeSTT_server/embry_pcm.py`: PCM ingress reconnect behavior.
  - `/home/graham/workspace/experiments/RealtimeSTT/RealtimeSTT_server/embry_pcm_sender.py`: PipeWire source sender into RealtimeSTT socket.
  - `/home/graham/workspace/experiments/pi-mono/packages/ux-lab/server/index.ts`: listener/latest and live-turn endpoints.
  - `/mnt/storage12tb/skills/embry-voice-control/state/voice-events.sqlite3`: authoritative voice event journal.

- **Current Chatterbox git state**:
  - branch: `main`
  - HEAD: `8a7f64a test: preserve live listener playback and replay proof`
  - dirty paths before this handoff update included `.ask/browser-oracles.yaml`, `.codex/ui-verification/latest.json`, `docs/EMBRY_CHAT_UX_SYNC_EVIDENCE_AUDIT.json`, and many untracked `.ask`/`.codex` artifacts.

- **Cross-repo git state**:
  - RealtimeSTT HEAD: `0cf2a16 Keep Embry PCM ingress alive across sender reconnects`
  - RealtimeSTT dirty: untracked `.venv-fastapi/`
  - pi-mono branch: `persona/tim-blazytko-1774553751276`
  - pi-mono audio commit object: `9ed10c7ce Read latest Embry listener turn from journal`
  - pi-mono current HEAD observed later as `055544222 feat(ux-lab): add SPARTA equivalence review queue`
  - pi-mono `packages/ux-lab/server/index.ts` has unrelated unstaged F36/threat-matrix changes on top of the journal fallback. Do not stage or revert them for audio work.

- **Claim boundary**:
  - `mocked: no`
  - `live: yes`
  - Proven: speaker-to-C920 acoustic wake/request, journal final, Tau/Memory answer, Chatterbox render, playback start.
  - Not proven: fresh human-spoken C920 final transcript, direct ALSA C920 quality, persistent PipeWire remap fix, stable UX Lab service after the latest restart cycle.
