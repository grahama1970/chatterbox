#!/usr/bin/env bash
set -euo pipefail

OUT_DIR="${OUT_DIR:-/tmp/embry-jabra-acoustic-debug-$(date -u +%Y%m%dT%H%M%SZ)}"
REPO_ROOT="${REPO_ROOT:-/home/graham/workspace/experiments/chatterbox}"
SCILLM_ROOT="${SCILLM_ROOT:-/home/graham/workspace/experiments/scillm}"
REALTIMESTT_PYTHON="${REALTIMESTT_PYTHON:-/home/graham/workspace/experiments/RealtimeSTT/.venv-fastapi/bin/python}"
REALTIME_ROOT="${REALTIME_ROOT:-/home/graham/workspace/experiments/RealtimeSTT}"
PLAY_TARGET="${PLAY_TARGET:-alsa_output.usb-0b0e_Jabra_SPEAK_510_USB_501AA5274B1D022000-00.analog-stereo}"
RECORD_TARGET="${RECORD_TARGET:-alsa_input.usb-0b0e_Jabra_SPEAK_510_USB_501AA5274B1D022000-00.mono-fallback}"
DEFAULT_EXPECTED_TEXT="Wikipedia's List of capitals of France result says: The capital of France has been Paris since its liberation in 1944."
EXPECTED_TEXT="${EXPECTED_TEXT:-$DEFAULT_EXPECTED_TEXT}"
SOURCE_WAV="${SOURCE_WAV:-/home/graham/workspace/experiments/chatterbox/logs/ux-lab-embry-direct/2026-07-26T21-36-48-714Z-a912bdabfee8.wav}"

mkdir -p "$OUT_DIR"

CAPTURE_WAV="$OUT_DIR/jabra-mic-capture.wav"
PLAYBACK_RECEIPT="$OUT_DIR/jabra-playback.json"
CAPTURE_RECEIPT="$OUT_DIR/jabra-capture.json"
ASR_RECEIPT="$OUT_DIR/realtimestt-asr.json"
FFPROBE_JSON="$OUT_DIR/jabra-capture-ffprobe.json"
VOLUME_TXT="$OUT_DIR/jabra-capture-volumedetect.txt"

printf 'Running acoustic MVP into %s\n' "$OUT_DIR"

timeout 10 pw-record \
  --target "$RECORD_TARGET" \
  --rate 24000 \
  --channels 1 \
  --format s16 \
  "$CAPTURE_WAV" &
record_pid=$!

sleep 1
pw-play --target "$PLAY_TARGET" "$SOURCE_WAV"
play_rc=$?
wait "$record_pid" || record_rc=$?
record_rc="${record_rc:-0}"

jq -n \
  --arg target "$PLAY_TARGET" \
  --arg wav "$SOURCE_WAV" \
  --argjson returncode "$play_rc" \
  '{schema:"embry.debug_jabra_playback.v1", mocked:false, live:true, target:$target, wav:$wav, returncode:$returncode}' \
  > "$PLAYBACK_RECEIPT"

ffprobe -hide_banner -v error \
  -show_entries format=duration,size \
  -show_entries stream=codec_name,sample_rate,channels \
  -of json "$CAPTURE_WAV" > "$FFPROBE_JSON" || true

ffmpeg -hide_banner -nostats -i "$CAPTURE_WAV" \
  -af volumedetect -f null - > "$VOLUME_TXT" 2>&1 || true

mean_volume_db="$(sed -n 's/.*mean_volume: \([-0-9.]*\) dB.*/\1/p' "$VOLUME_TXT" | tail -1)"
max_volume_db="$(sed -n 's/.*max_volume: \([-0-9.]*\) dB.*/\1/p' "$VOLUME_TXT" | tail -1)"
capture_bytes="$(stat -c %s "$CAPTURE_WAV" 2>/dev/null || printf 0)"
capture_sha256="$(sha256sum "$CAPTURE_WAV" 2>/dev/null | awk '{print $1}')"
duration_seconds="$(jq -r '.format.duration // empty' "$FFPROBE_JSON" 2>/dev/null)"

jq -n \
  --arg capture "$CAPTURE_WAV" \
  --arg record_target "$RECORD_TARGET" \
  --arg playback "$SOURCE_WAV" \
  --arg playback_target "$PLAY_TARGET" \
  --arg sha "$capture_sha256" \
  --arg mean "$mean_volume_db" \
  --arg max "$max_volume_db" \
  --arg duration "$duration_seconds" \
  --arg ffprobe "$FFPROBE_JSON" \
  --arg volumedetect "$VOLUME_TXT" \
  --argjson bytes "$capture_bytes" \
  --argjson playback_returncode "$play_rc" \
  --argjson record_returncode "$record_rc" \
  '{
    schema:"embry.debug_jabra_capture.v1",
    mocked:false,
    live:true,
    playback_wav:$playback,
    playback_target:$playback_target,
    record_target:$record_target,
    capture_path:$capture,
    capture_bytes:$bytes,
    capture_sha256:$sha,
    duration_seconds:$duration,
    mean_volume_db:$mean,
    max_volume_db:$max,
    ffprobe_path:$ffprobe,
    volumedetect_path:$volumedetect,
    playback_returncode:$playback_returncode,
    record_returncode:$record_returncode
  }' > "$CAPTURE_RECEIPT"

whisper_state="$(docker inspect -f '{{.State.Running}}' whisper 2>/dev/null || printf missing)"
if [[ "$whisper_state" == "true" ]]; then
  whisper_key="$(docker exec whisper sh -lc 'cat /var/lib/whisper/.api_key')"
  WHISPER_API_KEY="$whisper_key" \
  PYTHONPATH="$REPO_ROOT:/home/graham/workspace/experiments/agent-skills/skills/embry-voice-control/src" \
  timeout 180 "$REALTIMESTT_PYTHON" "$REPO_ROOT/scripts/smoke_realtimestt_listener_bridge.py" \
    --audio "$CAPTURE_WAV" \
    --out "$ASR_RECEIPT" \
    --expected-transcript "$EXPECTED_TEXT" \
    --max-wer 0.40 \
    --realtimestt-root "$REALTIME_ROOT" \
    --text-timeout-s 60 \
    --pre-feed-listen-s 0.5 || true
else
  jq -n \
    --arg state "$whisper_state" \
    --arg capture "$CAPTURE_WAV" \
    '{
      schema:"chatterbox.realtimestt.listener_bridge.v1",
      ok:false,
      mocked:false,
      live:false,
      failed_gates:["whisper_container_running"],
      error_type:"ServiceUnavailable",
      error:"whisper container is not running",
      services:{asr_executor:{kind:"openai_compatible", container:"whisper", running_state:$state}},
      artifacts:{input_audio:{path:$capture}},
      claims:{proves:[], does_not_prove:["realtimestt_external_audio_path"]}
    }' > "$ASR_RECEIPT"
fi

jq -n \
  --arg out_dir "$OUT_DIR" \
  --arg playback "$PLAYBACK_RECEIPT" \
  --arg capture "$CAPTURE_RECEIPT" \
  --arg asr "$ASR_RECEIPT" \
  --slurpfile capture_data "$CAPTURE_RECEIPT" \
  --slurpfile asr_data "$ASR_RECEIPT" \
  '{
    schema:"embry.debug_jabra_acoustic_mvp.summary.v1",
    mocked:false,
    live:true,
    out_dir:$out_dir,
    playback_receipt:$playback,
    capture_receipt:$capture,
    asr_receipt:$asr,
    capture: $capture_data[0],
    asr: $asr_data[0],
    pass: (($asr_data[0].ok // false) == true),
    debugger_breakpoints:[
      "scripts/smoke_realtimestt_listener_bridge.py:401 feed_wav_to_recorder call",
      "scripts/smoke_realtimestt_listener_bridge.py:411 recorder.start(frames=recorded_frames)",
      "scripts/smoke_realtimestt_listener_bridge.py:435 recorder_text_with_timeout",
      "scripts/smoke_realtimestt_listener_bridge.py:441 text_returned event"
    ]
  }' | tee "$OUT_DIR/summary.json"
