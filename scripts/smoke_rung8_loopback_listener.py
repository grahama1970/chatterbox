#!/usr/bin/env python3
"""Run Rung 8 live PipeWire listener capture smoke.

This harness moves beyond file-fed WAVs by playing a configured stress WAV
through PipeWire, recording the selected sink monitor or microphone with pw-record, and
then feeding the captured audio to the existing RealtimeSTT and rung 7 listener
receipts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_HORUS_ENROLLMENT = (
    "/home/graham/workspace/experiments/agent-skills-loop2-shared/skills/"
    "persona-dream/voice_clone_candidates/horus_kling_clone_candidate.wav"
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def wav_metrics(path: Path) -> dict[str, Any]:
    import audioop

    with wave.open(str(path), "rb") as handle:
        frames = handle.readframes(handle.getnframes())
        frame_count = handle.getnframes()
        sample_rate = handle.getframerate()
        channels = handle.getnchannels()
        sample_width = handle.getsampwidth()
    return {
        "path": str(path),
        "exists": path.exists(),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "duration_seconds": round(frame_count / sample_rate, 3) if sample_rate else 0,
        "sample_rate": sample_rate,
        "channels": channels,
        "sample_width": sample_width,
        "frame_count": frame_count,
        "rms": audioop.rms(frames, sample_width) if frames else 0,
    }


def run_cmd(cmd: list[str], *, timeout: float, env: dict[str, str] | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        completed = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout, env=env, check=False)
        return {
            "cmd": cmd,
            "returncode": completed.returncode,
            "stdout_tail": completed.stdout[-4000:],
            "stderr_tail": completed.stderr[-4000:],
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "cmd": cmd,
            "returncode": 124,
            "stdout_tail": (exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else "",
            "stderr_tail": (exc.stderr or "")[-4000:] if isinstance(exc.stderr, str) else "",
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
            "timeout_s": timeout,
        }


def pipewire_status() -> dict[str, Any]:
    status = run_cmd(["wpctl", "status"], timeout=5)
    return {
        "wpctl_status": status,
        "default_sink_id": parse_default_sink_id(status.get("stdout_tail") or ""),
    }


def pipewire_node_name(target: str | None) -> str | None:
    if not target:
        return None
    result = run_cmd(["pw-cli", "ls", "Node"], timeout=5)
    if result["returncode"] != 0:
        return None
    current_id: str | None = None
    current_name: str | None = None
    for raw_line in (result.get("stdout_tail") or "").splitlines():
        id_match = re.search(r"^\s*id\s+(\d+),", raw_line)
        if id_match:
            if current_id == str(target) and current_name:
                return current_name
            current_id = id_match.group(1)
            current_name = None
            continue
        name_match = re.search(r'node\.name = "([^"]+)"', raw_line)
        if name_match:
            current_name = name_match.group(1)
    if current_id == str(target) and current_name:
        return current_name
    return None


def parse_default_sink_id(status_text: str) -> str | None:
    in_sinks = False
    for raw_line in status_text.splitlines():
        line = raw_line.rstrip()
        if "├─ Sinks:" in line:
            in_sinks = True
            continue
        if in_sinks and "├─" in line and "Sinks:" not in line:
            in_sinks = False
        if in_sinks and "*" in line:
            match = re.search(r"\*\s+(\d+)\.", line)
            if match:
                return match.group(1)
    return None


def capture_loopback(args: argparse.Namespace, out_dir: Path) -> dict[str, Any]:
    failed_gates: list[str] = []
    play_audio = args.play_audio.resolve()
    raw_capture = out_dir / "loopback-captured-raw.wav"
    captured_audio = out_dir / "loopback-captured.wav"
    if not play_audio.exists():
        failed_gates.append("play_audio_exists")
        input_metrics = None
    else:
        input_metrics = wav_metrics(play_audio)

    pw = pipewire_status()
    sink_target = args.sink_target or pw.get("default_sink_id")
    record_target = args.record_target or sink_target
    sink_node_name = pipewire_node_name(sink_target)
    record_node_name = pipewire_node_name(record_target)
    pulse_source = args.pulse_source
    if not pulse_source and args.capture_kind == "monitor_loopback" and sink_node_name:
        pulse_source = f"{sink_node_name}.monitor"
    if not pulse_source and args.capture_kind == "physical_microphone" and record_node_name:
        pulse_source = record_node_name
    if not sink_target:
        failed_gates.append("pipewire_default_sink_found")
    if not record_target:
        failed_gates.append("pipewire_record_target_found")
    if args.capture_backend == "ffmpeg-pulse" and not pulse_source:
        failed_gates.append("pulse_source_found")

    receipt: dict[str, Any] = {
        "schema": "chatterbox.rung8.loopback_capture.v1",
        "ok": False,
        "mocked": False,
        "live": False,
        "play_audio": input_metrics,
        "captured_audio": None,
        "pipewire": {
            "capture_kind": args.capture_kind,
            "capture_backend": args.capture_backend,
            "sink_target": sink_target,
            "record_target": record_target,
            "sink_node_name": sink_node_name,
            "record_node_name": record_node_name,
            "pulse_source": pulse_source,
            "status": pw,
        },
        "commands": {},
        "failed_gates": failed_gates,
    }
    if failed_gates:
        return receipt

    captured_audio.unlink(missing_ok=True)
    raw_capture.unlink(missing_ok=True)
    if args.capture_backend == "ffmpeg-pulse":
        record_path = captured_audio
        record_cmd = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "pulse",
            "-i",
            str(pulse_source),
            "-ac",
            "1",
            "-ar",
            str(args.capture_rate),
            "-sample_fmt",
            "s16",
            str(record_path),
        ]
    else:
        record_path = raw_capture
        record_cmd = [
            "pw-record",
            "--target",
            str(record_target),
            "--rate",
            str(args.raw_capture_rate),
            "--channels",
            str(args.raw_capture_channels),
            "--format",
            "s16",
            str(record_path),
        ]
    play_cmd = ["pw-play", "--target", str(sink_target), str(play_audio)]
    record_started = time.perf_counter()
    recorder = subprocess.Popen(record_cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    time.sleep(args.pre_roll_s)
    play = run_cmd(play_cmd, timeout=args.play_timeout_s)
    time.sleep(args.post_roll_s)
    if recorder.poll() is None:
        recorder.send_signal(2)
    try:
        stdout, stderr = recorder.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        recorder.kill()
        stdout, stderr = recorder.communicate(timeout=5)
    record = {
        "cmd": record_cmd,
        "returncode": recorder.returncode,
        "stdout_tail": (stdout or "")[-4000:],
        "stderr_tail": (stderr or "")[-4000:],
        "elapsed_ms": round((time.perf_counter() - record_started) * 1000, 3),
    }
    receipt["commands"] = {"record": record, "play": play}

    if play["returncode"] != 0:
        failed_gates.append("pw_play_returncode_ok")
    if args.capture_backend == "ffmpeg-pulse":
        receipt["commands"] = {"record": record, "play": play}
    if args.capture_backend != "ffmpeg-pulse" and not raw_capture.exists():
        failed_gates.append("raw_captured_audio_exists")
    elif args.capture_backend != "ffmpeg-pulse":
        try:
            raw_metrics = wav_metrics(raw_capture)
            receipt["raw_captured_audio"] = raw_metrics
        except Exception as exc:  # noqa: BLE001
            failed_gates.append("raw_captured_audio_readable")
            receipt["raw_captured_audio_error"] = f"{type(exc).__name__}: {exc}"

    if (
        args.capture_backend != "ffmpeg-pulse"
        and "raw_captured_audio_exists" not in failed_gates
        and "raw_captured_audio_readable" not in failed_gates
    ):
        convert_cmd = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(raw_capture),
            "-ac",
            "1",
            "-ar",
            str(args.capture_rate),
            "-sample_fmt",
            "s16",
            str(captured_audio),
        ]
        convert = run_cmd(convert_cmd, timeout=30)
        receipt["commands"]["convert"] = convert
        if convert["returncode"] != 0:
            failed_gates.append("ffmpeg_convert_returncode_ok")

    if not captured_audio.exists():
        failed_gates.append("captured_audio_exists")
    else:
        try:
            captured_metrics = wav_metrics(captured_audio)
            receipt["captured_audio"] = captured_metrics
            if captured_metrics["duration_seconds"] < args.min_capture_duration_s:
                failed_gates.append("captured_audio_duration")
            if captured_metrics["rms"] < args.min_capture_rms:
                failed_gates.append("captured_audio_rms")
        except Exception as exc:  # noqa: BLE001
            failed_gates.append("captured_audio_readable")
            receipt["captured_audio_error"] = f"{type(exc).__name__}: {exc}"
    allowed_record_codes = {0, 1, -2, 130}
    if args.capture_backend == "ffmpeg-pulse":
        # ffmpeg exits 255 when interrupted after a successful indefinite Pulse capture.
        allowed_record_codes.add(255)
    if record["returncode"] not in allowed_record_codes:
        failed_gates.append("pw_record_returncode_ok")
    elif record["returncode"] == 1 and "raw_captured_audio_exists" in failed_gates:
        failed_gates.append("pw_record_returncode_ok")

    receipt["ok"] = not failed_gates
    receipt["live"] = receipt["ok"]
    receipt["failed_gates"] = failed_gates
    return receipt


def load_receipt(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"error_type": type(exc).__name__, "error": str(exc)}


def run(args: argparse.Namespace) -> dict[str, Any]:
    started = time.perf_counter()
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    capture = capture_loopback(args, out_dir)
    failed_gates: list[str] = [f"capture_{gate}" for gate in capture.get("failed_gates") or []]

    env = os.environ.copy()
    env["PYTHONPATH"] = f"src:{args.realtimestt_root}"
    if not os.getenv(args.api_key_env):
        failed_gates.append(f"api_key_env_present:{args.api_key_env}")

    captured_path = out_dir / "loopback-captured.wav"
    realtime_path = out_dir / "realtimestt-loopback.json"
    rung7_path = out_dir / "rung7-loopback.json"
    children: dict[str, Any] = {}

    if capture.get("ok") and not any(gate.startswith("api_key_env_present") for gate in failed_gates):
        realtime_cmd = [
            str(args.realtimestt_python),
            "scripts/smoke_realtimestt_listener_bridge.py",
            "--audio",
            str(captured_path),
            "--out",
            str(realtime_path),
            "--asr-openai-base-url",
            args.asr_openai_base_url,
            "--api-key-env",
            args.api_key_env,
            "--chunk-ms",
            str(args.chunk_ms),
            "--trailing-silence-ms",
            str(args.trailing_silence_ms),
            "--realtime-feed",
            "--text-timeout-s",
            str(args.text_timeout_s),
            "--pre-feed-listen-s",
            str(args.pre_feed_listen_s),
            "--no-manual-start-stop",
        ]
        realtime_run = run_cmd(realtime_cmd, timeout=args.realtimestt_timeout_s, env=env)
        realtime_receipt = load_receipt(realtime_path)
        children["realtimestt"] = {"run": realtime_run, "receipt": realtime_receipt}
        if realtime_run["returncode"] != 0:
            failed_gates.append("realtimestt_command_ok")
        if realtime_receipt.get("ok") is not True:
            failed_gates.append("realtimestt_receipt_ok")

        rung7_cmd = [
            str(args.rung7_python),
            "scripts/smoke_conversation_ladder.py",
            "--rung",
            "7",
            "--fixture",
            str(captured_path),
            "--fixture-provenance",
            f"pipewire_{args.capture_kind}_capture_of_horus_factory_embry_stress",
            "--primary-speaker-enrollment",
            str(args.primary_speaker_enrollment),
            "--primary-speaker-threshold",
            str(args.primary_speaker_threshold),
            "--expected-primary-speaker",
            "true",
            "--enable-speaker-identity-memory",
            "--enable-speaker-memory-recall",
            "--speaker-confidence",
            "0.0",
            "--speaker-evidence-source",
            f"pipewire_{args.capture_kind}_resemblyzer",
            "--speaker-resolve-threshold",
            str(args.speaker_resolve_threshold),
            "--speaker-memory-recall-collection",
            "persona_memory",
            "--memory-question",
            args.memory_question,
            "--asr-openai-base-url",
            args.asr_openai_base_url,
            "--api-key-env",
            args.api_key_env,
            "--out",
            str(rung7_path),
        ]
        rung7_run = run_cmd(rung7_cmd, timeout=args.rung7_timeout_s, env=env)
        rung7_receipt = load_receipt(rung7_path)
        children["rung7"] = {"run": rung7_run, "receipt": rung7_receipt}
        if rung7_run["returncode"] != 0:
            failed_gates.append("rung7_command_ok")
        if rung7_receipt.get("ok") is not True:
            failed_gates.append("rung7_receipt_ok")

    realtime_receipt = (children.get("realtimestt") or {}).get("receipt") or {}
    rung7_receipt = (children.get("rung7") or {}).get("receipt") or {}
    speaker_resolution = rung7_receipt.get("speaker_resolution") or {}
    speaker_recall = rung7_receipt.get("speaker_memory_recall") or {}
    if children:
        if speaker_resolution.get("status") != "known" or speaker_resolution.get("speaker_id") != "horus_lupercal":
            failed_gates.append("speaker_resolution_known_horus")
        if speaker_recall.get("found") is not True:
            failed_gates.append("speaker_memory_recall_found")

    ok = not failed_gates
    return {
        "schema": "chatterbox.rung8.loopback_listener.v1",
        "ok": ok,
        "mocked": False,
        "live": ok,
        "started_at_utc": datetime.fromtimestamp(
            time.time() - (time.perf_counter() - started),
            timezone.utc,
        ).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "ended_at_utc": utc_now(),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "inputs": {
            "play_audio": str(args.play_audio.resolve()),
            "primary_speaker_enrollment": str(args.primary_speaker_enrollment.resolve()),
            "memory_question": args.memory_question,
        },
        "capture": capture,
        "children": children,
        "failed_gates": failed_gates,
        "claims": {
            "proves": [
                f"pipewire_{args.capture_kind}_captures_played_stress_audio",
                "captured_loopback_audio_feeds_realtimestt_automatic_vad",
                "captured_loopback_audio_routes_through_rung7_speaker_memory_contract",
            ]
            if ok
            else [],
            "does_not_prove": [
                *([] if args.capture_kind == "physical_microphone" else ["physical_room_microphone_capture"]),
                "browser_webrtc_transport",
                "overlapping_speaker_diarization",
                "subjective_voice_quality",
                "generalized_factory_robustness_beyond_configured_audio",
            ],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--play-audio", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--sink-target", default=None)
    parser.add_argument("--record-target", default=None)
    parser.add_argument("--capture-backend", choices=["ffmpeg-pulse", "pw-record"], default="ffmpeg-pulse")
    parser.add_argument("--pulse-source", default=None)
    parser.add_argument("--capture-kind", choices=["monitor_loopback", "physical_microphone"], default="monitor_loopback")
    parser.add_argument("--raw-capture-rate", default=48000, type=int)
    parser.add_argument("--raw-capture-channels", default=2, type=int)
    parser.add_argument("--capture-rate", default=16000, type=int)
    parser.add_argument("--pre-roll-s", default=0.4, type=float)
    parser.add_argument("--post-roll-s", default=0.5, type=float)
    parser.add_argument("--play-timeout-s", default=90.0, type=float)
    parser.add_argument("--min-capture-duration-s", default=5.0, type=float)
    parser.add_argument("--min-capture-rms", default=50, type=int)
    parser.add_argument("--realtimestt-python", default="/tmp/chatterbox-listener-venv/bin/python", type=Path)
    parser.add_argument("--rung7-python", default="/tmp/chatterbox-listener-venv/bin/python", type=Path)
    parser.add_argument("--realtimestt-root", default="/home/graham/workspace/experiments/RealtimeSTT")
    parser.add_argument("--realtimestt-timeout-s", default=180.0, type=float)
    parser.add_argument("--rung7-timeout-s", default=240.0, type=float)
    parser.add_argument("--asr-openai-base-url", default=os.getenv("CHATTERBOX_ASR_OPENAI_BASE_URL", "http://127.0.0.1:9000"))
    parser.add_argument("--api-key-env", default=os.getenv("CHATTERBOX_ASR_API_KEY_ENV", "WHISPER_API_KEY"))
    parser.add_argument("--chunk-ms", default=20, type=int)
    parser.add_argument("--trailing-silence-ms", default=1800, type=int)
    parser.add_argument("--text-timeout-s", default=35.0, type=float)
    parser.add_argument("--pre-feed-listen-s", default=0.25, type=float)
    parser.add_argument("--primary-speaker-enrollment", default=DEFAULT_HORUS_ENROLLMENT, type=Path)
    parser.add_argument("--primary-speaker-threshold", default=0.62, type=float)
    parser.add_argument("--speaker-resolve-threshold", default=0.62, type=float)
    parser.add_argument("--memory-question", default="Where did Horus Lupercal grow up?")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    receipt = run(args)
    out_path = args.out or (args.out_dir / "rung8-loopback-listener.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": receipt["ok"], "live": receipt["live"], "mocked": receipt["mocked"], "failed_gates": receipt["failed_gates"], "out": str(out_path)}, sort_keys=True))
    return 0 if receipt["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
