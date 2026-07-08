#!/usr/bin/env python3
"""Prove OS audio graph capture can feed RealtimeSTT external audio.

This runner intentionally avoids browser UI, Chatterbox, Embry output audio,
speaker identity, memory, Tau, orb, and replay. It creates a known input phrase
with a nonce, plays it into a temporary Pulse-compatible null sink, captures the
sink monitor as a real local audio graph artifact, and then feeds that captured
WAV to the existing RealtimeSTT external-audio bridge.
"""

from __future__ import annotations

import argparse
import audioop
import hashlib
import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import time
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_EXPECTED = "Horus factory stress speech"
DEFAULT_OUT = Path("/tmp/embry-live-e2e/rung1")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_text(text: str) -> str:
    digit_words = {
        "zero": "0",
        "one": "1",
        "two": "2",
        "three": "3",
        "four": "4",
        "five": "5",
        "six": "6",
        "seven": "7",
        "eight": "8",
        "nine": "9",
    }
    tokens = "".join(ch.lower() if ch.isalnum() else " " for ch in text).split()
    normalized = [digit_words.get(token, token) for token in tokens]
    return " ".join(normalized)


def compact_alnum(text: str) -> str:
    return "".join(ch for ch in normalize_text(text) if ch.isalnum())


def wav_metrics(path: Path, *, silence_threshold: int = 96) -> dict[str, Any]:
    with wave.open(str(path), "rb") as handle:
        frames = handle.readframes(handle.getnframes())
        frame_count = handle.getnframes()
        sample_rate = handle.getframerate()
        channels = handle.getnchannels()
        sample_width = handle.getsampwidth()
    if frames:
        rms = audioop.rms(frames, sample_width)
        peak = audioop.max(frames, sample_width)
        samples_per_frame = max(1, int(sample_rate * 0.02))
        bytes_per_sample_frame = samples_per_frame * channels * sample_width
        chunks = [
            frames[index : index + bytes_per_sample_frame]
            for index in range(0, len(frames), bytes_per_sample_frame)
            if len(frames[index : index + bytes_per_sample_frame]) >= channels * sample_width
        ]
        non_silent = sum(1 for chunk in chunks if audioop.rms(chunk, sample_width) >= silence_threshold)
        non_silent_ratio = round(non_silent / len(chunks), 4) if chunks else 0.0
    else:
        rms = 0
        peak = 0
        non_silent_ratio = 0.0
    return {
        "path": str(path),
        "exists": path.exists(),
        "bytes": path.stat().st_size if path.exists() else 0,
        "sha256": sha256_file(path) if path.exists() else None,
        "duration_seconds": round(frame_count / sample_rate, 3) if sample_rate else 0,
        "sample_rate": sample_rate,
        "channels": channels,
        "sample_width": sample_width,
        "frame_count": frame_count,
        "rms": rms,
        "peak": peak,
        "non_silent_frame_ratio": non_silent_ratio,
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


def append_event(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"occurred_at_utc": utc_now(), **event}, sort_keys=True) + "\n")


def docker_env_value(container: str, env_name: str) -> str | None:
    result = run_cmd(
        ["docker", "inspect", container, "--format", "{{range .Config.Env}}{{println .}}{{end}}"],
        timeout=5,
    )
    if result["returncode"] != 0:
        return None
    prefix = f"{env_name}="
    for line in (result.get("stdout_tail") or "").splitlines():
        if line.startswith(prefix):
            value = line[len(prefix) :].strip()
            return value or None
    return None


def resolve_api_key(args: argparse.Namespace, env: dict[str, str]) -> dict[str, Any]:
    if env.get(args.api_key_env):
        return {"present": True, "source": "environment", "env_name": args.api_key_env}
    if args.api_key_docker_container:
        value = docker_env_value(args.api_key_docker_container, args.api_key_docker_env)
        if value:
            env[args.api_key_env] = value
            return {
                "present": True,
                "source": "docker_container_env",
                "env_name": args.api_key_env,
                "docker_container": args.api_key_docker_container,
                "docker_env": args.api_key_docker_env,
            }
    return {
        "present": False,
        "source": "missing",
        "env_name": args.api_key_env,
        "docker_container": args.api_key_docker_container,
        "docker_env": args.api_key_docker_env,
    }


def load_null_sink(sink_name: str) -> tuple[str | None, dict[str, Any]]:
    result = run_cmd(
        [
            "pactl",
            "load-module",
            "module-null-sink",
            f"sink_name={sink_name}",
            f"sink_properties=device.description={sink_name}",
        ],
        timeout=10,
    )
    module_id = None
    if result["returncode"] == 0:
        match = re.search(r"\d+", result.get("stdout_tail") or "")
        module_id = match.group(0) if match else (result.get("stdout_tail") or "").strip()
    return module_id, result


def unload_null_sink(module_id: str | None) -> dict[str, Any] | None:
    if not module_id:
        return None
    return run_cmd(["pactl", "unload-module", module_id], timeout=10)


def default_sink_id() -> str | None:
    result = run_cmd(["wpctl", "status"], timeout=5)
    if result["returncode"] != 0:
        return None
    in_sinks = False
    for raw_line in (result.get("stdout_tail") or "").splitlines():
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


def generate_source_wav(*, args: argparse.Namespace, out_dir: Path, phrase: str) -> tuple[Path, dict[str, Any]]:
    source = out_dir / "source.wav"
    if args.source_wav:
        shutil.copy2(args.source_wav, source)
        return source, {
            "strategy": "copied_source_wav",
            "source": str(args.source_wav.resolve()),
            "cmd": None,
            "returncode": 0,
        }
    cmd = ["espeak-ng", "-w", str(source), "-s", str(args.espeak_speed), "-v", args.espeak_voice, phrase]
    result = run_cmd(cmd, timeout=30)
    return source, {"strategy": "espeak_ng", **result}


def capture_monitor(*, args: argparse.Namespace, source_wav: Path, out_dir: Path, events_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    if shutil.which("pactl"):
        return capture_pulse_null_sink(args=args, source_wav=source_wav, out_dir=out_dir, events_path=events_path)
    return capture_pipewire_sink_target(args=args, source_wav=source_wav, out_dir=out_dir, events_path=events_path)


def capture_pulse_null_sink(*, args: argparse.Namespace, source_wav: Path, out_dir: Path, events_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    failed_gates: list[str] = []
    sink_name = f"embry_rung1_{secrets.token_hex(4)}"
    monitor_name = f"{sink_name}.monitor"
    module_id: str | None = None
    commands: dict[str, Any] = {}
    capture_receipt: dict[str, Any] = {
        "schema": "embry.audio_ingress_receipt.v1",
        "ok": False,
        "mocked": False,
        "live": False,
        "capture_kind": "os_audio_graph_loopback",
        "transport": "pipewire_pulse_null_sink_monitor",
        "sink_name": sink_name,
        "monitor_name": monitor_name,
        "module_id": None,
        "source_wav": str(source_wav),
        "captured_wav": str(out_dir / "captured.wav"),
        "failed_gates": failed_gates,
        "commands": commands,
    }
    try:
        module_id, load = load_null_sink(sink_name)
        commands["load_null_sink"] = load
        capture_receipt["module_id"] = module_id
        append_event(events_path, {"type": "audio_graph.null_sink_loaded", "sink_name": sink_name, "module_id": module_id})
        if load["returncode"] != 0 or not module_id:
            failed_gates.append("null_sink_loaded")
            return capture_receipt, {"failed_gates": failed_gates}

        captured = out_dir / "captured.wav"
        captured.unlink(missing_ok=True)
        record_cmd = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "pulse",
            "-i",
            monitor_name,
            "-ac",
            "1",
            "-ar",
            str(args.capture_rate),
            "-sample_fmt",
            "s16",
            str(captured),
        ]
        record_started = time.perf_counter()
        recorder = subprocess.Popen(record_cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        time.sleep(args.pre_roll_s)
        play_cmd = ["paplay", f"--device={sink_name}", str(source_wav)]
        if not shutil.which("paplay"):
            play_cmd = ["pw-play", "--target", sink_name, str(source_wav)]
        play = run_cmd(play_cmd, timeout=args.play_timeout_s)
        time.sleep(args.post_roll_s)
        if recorder.poll() is None:
            recorder.send_signal(signal.SIGINT)
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
        commands["record_monitor"] = record
        commands["play_source"] = play
        append_event(events_path, {"type": "audio_graph.source_played", "returncode": play["returncode"]})
        append_event(events_path, {"type": "audio_graph.monitor_recorded", "returncode": record["returncode"]})
        if play["returncode"] != 0:
            failed_gates.append("source_played_to_null_sink")
        if record["returncode"] not in {0, 1, -2, 130, 255}:
            failed_gates.append("monitor_record_returncode_ok")
        if not captured.exists():
            failed_gates.append("captured_wav_exists")
        else:
            metrics = wav_metrics(captured, silence_threshold=args.silence_threshold)
            capture_receipt["captured_audio"] = metrics
            if metrics["duration_seconds"] < args.min_capture_duration_s:
                failed_gates.append("captured_duration")
            if metrics["rms"] < args.min_capture_rms:
                failed_gates.append("captured_rms")
            if metrics["non_silent_frame_ratio"] < args.min_non_silent_ratio:
                failed_gates.append("captured_non_silent_ratio")
    finally:
        unload = unload_null_sink(module_id)
        if unload:
            commands["unload_null_sink"] = unload
            append_event(events_path, {"type": "audio_graph.null_sink_unloaded", "module_id": module_id, "returncode": unload["returncode"]})

    capture_receipt["ok"] = not failed_gates
    capture_receipt["live"] = capture_receipt["ok"]
    capture_receipt["failed_gates"] = failed_gates
    return capture_receipt, {"failed_gates": failed_gates}


def capture_pipewire_sink_target(*, args: argparse.Namespace, source_wav: Path, out_dir: Path, events_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    failed_gates: list[str] = []
    sink_target = args.sink_target or default_sink_id()
    commands: dict[str, Any] = {}
    captured = out_dir / "captured.wav"
    capture_receipt: dict[str, Any] = {
        "schema": "embry.audio_ingress_receipt.v1",
        "ok": False,
        "mocked": False,
        "live": False,
        "capture_kind": "os_audio_graph_loopback",
        "transport": "pipewire_pw_record_sink_target",
        "sink_target": sink_target,
        "source_wav": str(source_wav),
        "captured_wav": str(captured),
        "failed_gates": failed_gates,
        "commands": commands,
        "note": "Pulse pactl unavailable; using pw-record against the PipeWire sink target.",
    }
    if not sink_target:
        failed_gates.append("pipewire_default_sink_found")
        return capture_receipt, {"failed_gates": failed_gates}
    captured.unlink(missing_ok=True)
    record_cmd = [
        "pw-record",
        "--target",
        str(sink_target),
        "--rate",
        str(args.capture_rate),
        "--channels",
        "1",
        "--format",
        "s16",
        str(captured),
    ]
    play_cmd = ["pw-play", "--target", str(sink_target), str(source_wav)]
    record_started = time.perf_counter()
    recorder = subprocess.Popen(record_cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    time.sleep(args.pre_roll_s)
    play = run_cmd(play_cmd, timeout=args.play_timeout_s)
    time.sleep(args.post_roll_s)
    if recorder.poll() is None:
        recorder.send_signal(signal.SIGINT)
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
    commands["record_sink_target"] = record
    commands["play_source"] = play
    append_event(events_path, {"type": "audio_graph.source_played", "returncode": play["returncode"], "sink_target": sink_target})
    append_event(events_path, {"type": "audio_graph.sink_target_recorded", "returncode": record["returncode"], "sink_target": sink_target})
    if play["returncode"] != 0:
        failed_gates.append("source_played_to_sink_target")
    if record["returncode"] not in {0, 1, -2, 130, 255}:
        failed_gates.append("sink_target_record_returncode_ok")
    if not captured.exists():
        failed_gates.append("captured_wav_exists")
    else:
        metrics = wav_metrics(captured, silence_threshold=args.silence_threshold)
        capture_receipt["captured_audio"] = metrics
        if metrics["duration_seconds"] < args.min_capture_duration_s:
            failed_gates.append("captured_duration")
        if metrics["rms"] < args.min_capture_rms:
            failed_gates.append("captured_rms")
        if metrics["non_silent_frame_ratio"] < args.min_non_silent_ratio:
            failed_gates.append("captured_non_silent_ratio")
    capture_receipt["ok"] = not failed_gates
    capture_receipt["live"] = capture_receipt["ok"]
    capture_receipt["failed_gates"] = failed_gates
    return capture_receipt, {"failed_gates": failed_gates}


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"error_type": type(exc).__name__, "error": str(exc)}


def run(args: argparse.Namespace) -> dict[str, Any]:
    started = time.perf_counter()
    out_dir = args.out.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    events_path = out_dir / "events.ndjson"
    events_path.unlink(missing_ok=True)
    nonce = args.nonce or secrets.token_hex(3)
    expected_phrase = f"{args.expected} nonce {nonce}" if args.include_nonce else args.expected
    failed_gates: list[str] = []
    env = os.environ.copy()
    api_key = resolve_api_key(args, env)
    append_event(events_path, {"type": "rung1.started", "expected_phrase_sha256": sha256_text(expected_phrase), "nonce": nonce})

    source_wav, source_generation = generate_source_wav(args=args, out_dir=out_dir, phrase=expected_phrase)
    source_metrics = wav_metrics(source_wav, silence_threshold=args.silence_threshold) if source_wav.exists() else None
    if source_generation.get("returncode") != 0:
        failed_gates.append("source_wav_generated")
    if not source_wav.exists():
        failed_gates.append("source_wav_exists")

    capture_receipt, capture_status = capture_monitor(args=args, source_wav=source_wav, out_dir=out_dir, events_path=events_path)
    (out_dir / "audio_ingress_receipt.json").write_text(json.dumps(capture_receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    failed_gates.extend(f"audio_ingress:{gate}" for gate in capture_status["failed_gates"])

    realtimestt_path = out_dir / "realtimestt_receipt.json"
    realtimestt_run: dict[str, Any] | None = None
    if capture_receipt.get("ok") and api_key["present"]:
        bridge_cmd = [
            str(args.realtimestt_python),
            "scripts/smoke_realtimestt_listener_bridge.py",
            "--audio",
            str(out_dir / "captured.wav"),
            "--out",
            str(realtimestt_path),
            "--realtimestt-root",
            str(args.realtimestt_root),
            "--asr-openai-base-url",
            args.asr_openai_base_url,
            "--api-key-env",
            args.api_key_env,
            "--chunk-ms",
            str(args.chunk_ms),
            "--trailing-silence-ms",
            str(args.trailing_silence_ms),
            "--realtime-feed",
            "--manual-start-stop",
        ]
        realtimestt_run = run_cmd(bridge_cmd, timeout=args.realtimestt_timeout_s, env=env)
        append_event(events_path, {"type": "realtimestt.bridge_completed", "returncode": realtimestt_run["returncode"]})
        if realtimestt_run["returncode"] != 0:
            failed_gates.append("realtimestt_command_ok")
    else:
        if not api_key["present"]:
            failed_gates.append(f"api_key_env_present:{args.api_key_env}")
    realtimestt_receipt = load_json(realtimestt_path) if realtimestt_path.exists() else {}
    if not realtimestt_receipt:
        failed_gates.append("realtimestt_receipt_exists")
    elif realtimestt_receipt.get("ok") is not True:
        failed_gates.append("realtimestt_receipt_ok")

    transcript_text = ((realtimestt_receipt.get("transcript") or {}).get("text") or "") if isinstance(realtimestt_receipt, dict) else ""
    normalized_expected = normalize_text(expected_phrase)
    normalized_transcript = normalize_text(transcript_text)
    nonce_present = compact_alnum(nonce) in compact_alnum(transcript_text)
    if args.include_nonce and not nonce_present:
        failed_gates.append("transcript_nonce_present")
    if not transcript_text:
        failed_gates.append("transcript_present")

    ok = not failed_gates
    receipt = {
        "schema": "embry.rung1.audio_graph_realtimestt.v1",
        "ok": ok,
        "status": "pass" if ok else "fail",
        "live": ok,
        "mocked": False,
        "browser_used_as_proof": False,
        "used_chatterbox_audio_as_input": False,
        "started_at_utc": datetime.fromtimestamp(
            time.time() - (time.perf_counter() - started),
            timezone.utc,
        ).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "ended_at_utc": utc_now(),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "inputs": {
            "expected_phrase": expected_phrase,
            "expected_phrase_sha256": sha256_text(expected_phrase),
            "normalized_expected": normalized_expected,
            "nonce": nonce,
            "source_wav": str(source_wav),
            "source_generation": source_generation,
            "source_audio": source_metrics,
        },
        "audio_ingress": {
            "receipt_path": str(out_dir / "audio_ingress_receipt.json"),
            "receipt": capture_receipt,
        },
        "realtimestt": {
            "receipt_path": str(realtimestt_path),
            "run": realtimestt_run,
            "receipt": realtimestt_receipt,
            "use_microphone": False,
            "final_transcript": transcript_text,
            "normalized_final_transcript": normalized_transcript,
            "nonce_present": nonce_present,
        },
        "asr_auth": api_key,
        "events_path": str(events_path),
        "failed_gates": failed_gates,
        "claims": {
            "proves": [
                "os_audio_graph_null_sink_monitor_capture_feeds_realtimestt_external_audio",
                "known_nonce_input_reaches_realtimestt_final_transcript",
            ]
            if ok
            else [],
            "does_not_prove": [
                "physical_microphone_capture",
                "browser_webrtc_capture",
                "speaker_identity",
                "memory_tau_routing",
                "chatterbox_from_live_stt",
                "chat_ux_sync",
                "orb_sync",
                "replay",
                "interruption",
            ],
        },
    }
    append_event(events_path, {"type": "rung1.ended", "ok": ok, "failed_gates": failed_gates})
    (out_dir / "rung_receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--expected", default=DEFAULT_EXPECTED)
    parser.add_argument("--nonce", default=None)
    parser.add_argument("--include-nonce", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--source-wav", type=Path, default=None)
    parser.add_argument("--sink-target", default=None)
    parser.add_argument("--espeak-speed", type=int, default=135)
    parser.add_argument("--espeak-voice", default="en-us")
    parser.add_argument("--capture-rate", type=int, default=16000)
    parser.add_argument("--silence-threshold", type=int, default=96)
    parser.add_argument("--min-capture-duration-s", type=float, default=1.0)
    parser.add_argument("--min-capture-rms", type=int, default=50)
    parser.add_argument("--min-non-silent-ratio", type=float, default=0.05)
    parser.add_argument("--pre-roll-s", type=float, default=0.35)
    parser.add_argument("--post-roll-s", type=float, default=0.5)
    parser.add_argument("--play-timeout-s", type=float, default=60.0)
    parser.add_argument("--realtimestt-python", type=Path, default=Path("/tmp/chatterbox-listener-venv/bin/python"))
    parser.add_argument("--realtimestt-root", type=Path, default=Path("/home/graham/workspace/experiments/RealtimeSTT"))
    parser.add_argument("--realtimestt-timeout-s", type=float, default=180.0)
    parser.add_argument("--asr-openai-base-url", default=os.getenv("CHATTERBOX_ASR_OPENAI_BASE_URL", "http://127.0.0.1:9000"))
    parser.add_argument("--api-key-env", default=os.getenv("CHATTERBOX_ASR_API_KEY_ENV", "WHISPER_API_KEY"))
    parser.add_argument("--api-key-docker-container", default="chatterbox-fork-agent-server")
    parser.add_argument("--api-key-docker-env", default="WHISPER_API_KEY")
    parser.add_argument("--chunk-ms", type=int, default=20)
    parser.add_argument("--trailing-silence-ms", type=int, default=1600)
    parser.add_argument("--max-wer", type=float, default=0.35)
    args = parser.parse_args()

    receipt = run(args)
    print(
        json.dumps(
            {
                "ok": receipt["ok"],
                "live": receipt["live"],
                "mocked": receipt["mocked"],
                "browser_used_as_proof": receipt["browser_used_as_proof"],
                "failed_gates": receipt["failed_gates"],
                "receipt": str(args.out.resolve() / "rung_receipt.json"),
            },
            sort_keys=True,
        )
    )
    return 0 if receipt["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
