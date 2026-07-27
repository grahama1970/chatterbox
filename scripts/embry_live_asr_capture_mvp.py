#!/usr/bin/env python3
"""Prove a Chatterbox-rendered WAV survives a live Linux capture path into ASR.

Two non-mocked routes are supported:

``jabra``
    Play the source WAV through the Jabra speaker and record the Jabra
    microphone. This is the physical acoustic path.

``virtual``
    Play the source WAV into a PipeWire virtual sink whose monitor is exposed
    as a virtual *source* (``embry_virtual_mic``) -- the device RealtimeSTT
    opens as a microphone. A second loopback keeps the Jabra speaker audible so
    the human still hears the utterance.

Both the source WAV and every captured WAV are sent to the same live Whisper
endpoint, and the captured WAV is optionally replayed through the existing
RealtimeSTT listener bridge so the receipt covers the executor RealtimeSTT
actually uses. No browser microphone, no canned transcript, no mocked ASR.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(REPO_ROOT / "src"))

from smoke_realtimestt_listener_bridge import (  # noqa: E402
    sha256_text,
    transcribe_openai_compatible,
    utc_now,
    wav_metrics,
)

from chatterbox.agent.asr_acceptance import normalize_text, word_error_rate  # noqa: E402

DEFAULT_SOURCE_WAV = REPO_ROOT / "logs/physical-hot-mic-20260725T202210Z-agent-jabra-wake-question.wav"
DEFAULT_JABRA_SINK = "alsa_output.usb-0b0e_Jabra_SPEAK_510_USB_501AA5274B1D022000-00.analog-stereo"
DEFAULT_JABRA_SOURCE = "alsa_input.usb-0b0e_Jabra_SPEAK_510_USB_501AA5274B1D022000-00.mono-fallback"
VIRTUAL_SINK = "embry_virtual_speaker"
VIRTUAL_SOURCE = "embry_virtual_mic"
MONITOR_BRIDGE = "embry_monitor_bridge"
SILENCE_FLOOR_DB = -55.0


def run_cmd(cmd: list[str], *, timeout: float) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        completed = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout, check=False)
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


def pw_dump_nodes() -> dict[str, int]:
    """Map PipeWire node.name -> node id for every audio node."""
    proc = subprocess.run(["pw-dump"], text=True, capture_output=True, timeout=30, check=False)
    if proc.returncode != 0:
        return {}
    try:
        objects = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {}
    nodes: dict[str, int] = {}
    for obj in objects:
        if obj.get("type") != "PipeWire:Interface:Node":
            continue
        props = ((obj.get("info") or {}).get("props") or {})
        name = props.get("node.name")
        if name:
            nodes[name] = obj.get("id")
    return nodes


def device_state(node_name: str, nodes: dict[str, int]) -> dict[str, Any]:
    node_id = nodes.get(node_name)
    state: dict[str, Any] = {"node_name": node_name, "node_id": node_id, "present": node_id is not None}
    if node_id is None:
        return state
    volume = run_cmd(["wpctl", "get-volume", str(node_id)], timeout=10)
    raw = (volume["stdout_tail"] or "").strip()
    state["wpctl_raw"] = raw
    match = re.search(r"Volume:\s*([0-9.]+)", raw)
    state["volume"] = float(match.group(1)) if match else None
    state["muted"] = "[MUTED]" in raw
    return state


def alsa_state(card_hint: str) -> dict[str, Any]:
    listing = run_cmd(["amixer", "-c", card_hint, "scontents"], timeout=10)
    return {
        "card": card_hint,
        "returncode": listing["returncode"],
        "available": listing["returncode"] == 0,
        "scontents_tail": (listing["stdout_tail"] or "")[-2000:],
        "capture_switch_off": " [off]" in (listing["stdout_tail"] or ""),
    }


def volume_metrics(path: Path) -> dict[str, Any]:
    probe = run_cmd(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
        timeout=60,
    )
    text = (probe["stderr_tail"] or "") + (probe["stdout_tail"] or "")
    mean = re.search(r"mean_volume:\s*(-?[0-9.]+) dB", text)
    peak = re.search(r"max_volume:\s*(-?[0-9.]+) dB", text)
    return {
        "mean_volume_db": float(mean.group(1)) if mean else None,
        "max_volume_db": float(peak.group(1)) if peak else None,
    }


def start_background(cmd: list[str], log_path: Path) -> dict[str, Any]:
    handle = log_path.open("wb")
    proc = subprocess.Popen(cmd, stdout=handle, stderr=subprocess.STDOUT)
    return {"proc": proc, "cmd": cmd, "pid": proc.pid, "log_path": str(log_path)}


def stop_background(entry: dict[str, Any]) -> dict[str, Any]:
    proc: subprocess.Popen = entry["proc"]
    if proc.poll() is None:
        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
    return {"cmd": entry["cmd"], "pid": entry["pid"], "returncode": proc.returncode, "log_path": entry["log_path"]}


def setup_virtual_route(out_dir: Path, jabra_sink: str, *, mirror_to_jabra: bool) -> dict[str, Any]:
    """Create the virtual sink + virtual source, and mirror playback to the Jabra."""
    started: list[dict[str, Any]] = []
    started.append(
        start_background(
            [
                "pw-loopback",
                "-m",
                "[MONO]",
                "--capture-props",
                f"media.class=Audio/Sink node.name={VIRTUAL_SINK} node.description=EmbryVirtualSpeaker",
                "--playback-props",
                f"media.class=Audio/Source node.name={VIRTUAL_SOURCE} node.description=EmbryVirtualMic",
            ],
            out_dir / "pw-loopback-virtual-mic.log",
        )
    )
    if mirror_to_jabra:
        started.append(
            start_background(
                [
                    "pw-loopback",
                    "-m",
                    "[MONO]",
                    "--capture-props",
                    f"stream.capture.sink=true node.target={VIRTUAL_SINK} node.name={MONITOR_BRIDGE}",
                    "--playback-props",
                    f"node.target={jabra_sink}",
                ],
                out_dir / "pw-loopback-jabra-mirror.log",
            )
        )
    deadline = time.time() + 10
    nodes: dict[str, int] = {}
    while time.time() < deadline:
        nodes = pw_dump_nodes()
        if VIRTUAL_SINK in nodes and VIRTUAL_SOURCE in nodes:
            break
        time.sleep(0.5)
    links = run_cmd(["pw-link", "-l"], timeout=10)
    return {
        "processes": started,
        "virtual_sink_present": VIRTUAL_SINK in nodes,
        "virtual_source_present": VIRTUAL_SOURCE in nodes,
        "jabra_mirror_enabled": mirror_to_jabra,
        "pw_link_embry_lines": [
            line for line in (links["stdout_tail"] or "").splitlines() if "embry" in line or MONITOR_BRIDGE in line
        ][:40],
    }


def play_and_capture(
    *,
    source_wav: Path,
    capture_wav: Path,
    play_target: str,
    record_target: str,
    rate: int,
    lead_in_s: float,
    tail_s: float,
    record_timeout_s: float,
) -> dict[str, Any]:
    recorder = subprocess.Popen(
        [
            "pw-record",
            "--target",
            record_target,
            "--rate",
            str(rate),
            "--channels",
            "1",
            "--format",
            "s16",
            str(capture_wav),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    time.sleep(lead_in_s)
    playback = run_cmd(["pw-play", "--target", play_target, str(source_wav)], timeout=record_timeout_s)
    time.sleep(tail_s)
    if recorder.poll() is None:
        recorder.send_signal(signal.SIGINT)
        try:
            recorder.wait(timeout=5)
        except subprocess.TimeoutExpired:
            recorder.kill()
            recorder.wait(timeout=5)
    return {
        "play_target": play_target,
        "record_target": record_target,
        "record_rate": rate,
        "lead_in_s": lead_in_s,
        "tail_s": tail_s,
        "playback": playback,
        "record_returncode": recorder.returncode,
        "record_output_tail": (recorder.stdout.read() if recorder.stdout else "")[-2000:],
    }


def realtimestt_stage(
    *,
    capture_wav: Path,
    receipt_path: Path,
    expected_text: str,
    max_wer: float,
    args: argparse.Namespace,
    api_key: str,
) -> dict[str, Any]:
    python_bin = Path(args.realtimestt_python)
    if not python_bin.exists():
        return {"ran": False, "reason": f"missing realtimestt python: {python_bin}"}
    env = os.environ.copy()
    env[args.api_key_env] = api_key
    env["PYTHONPATH"] = str(REPO_ROOT)
    cmd = [
        str(python_bin),
        str(SCRIPT_DIR / "smoke_realtimestt_listener_bridge.py"),
        "--audio",
        str(capture_wav),
        "--out",
        str(receipt_path),
        "--expected-transcript",
        expected_text,
        "--max-wer",
        str(max_wer),
        "--realtimestt-root",
        args.realtimestt_root,
        "--asr-openai-base-url",
        args.whisper_base_url,
        "--text-timeout-s",
        "90",
        "--pre-feed-listen-s",
        "0.5",
    ]
    started = time.perf_counter()
    completed = subprocess.run(cmd, text=True, capture_output=True, timeout=args.realtimestt_timeout_s, env=env, check=False)
    receipt: dict[str, Any] | None = None
    if receipt_path.exists():
        try:
            receipt = json.loads(receipt_path.read_text())
        except json.JSONDecodeError:
            receipt = None
    return {
        "ran": True,
        "returncode": completed.returncode,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "receipt_path": str(receipt_path),
        "stderr_tail": completed.stderr[-2000:],
        "ok": bool((receipt or {}).get("ok")),
        "transcript": (receipt or {}).get("transcript", ""),
        "failed_gates": (receipt or {}).get("failed_gates", ["realtimestt_receipt_missing"]),
    }


def evaluate_capture(
    *,
    capture_wav: Path,
    source_transcript: str,
    captured_transcript: str,
    required_substrings: list[str],
    max_wer: float,
    volume: dict[str, Any],
) -> dict[str, Any]:
    failed_gates: list[str] = []
    if not capture_wav.exists() or capture_wav.stat().st_size <= 44:
        failed_gates.append("capture_file_present")
    peak = volume.get("max_volume_db")
    if peak is None or peak <= SILENCE_FLOOR_DB:
        failed_gates.append("capture_above_silence_floor")
    if not captured_transcript.strip():
        failed_gates.append("captured_transcript_present")
    normalized = normalize_text(captured_transcript)
    missing = [needle for needle in required_substrings if normalize_text(needle) not in normalized]
    if missing:
        failed_gates.append("captured_transcript_contains_required_content")
    wer = word_error_rate(source_transcript, captured_transcript)
    if wer > max_wer:
        failed_gates.append("captured_vs_source_wer_within_limit")
    return {
        "ok": not failed_gates,
        "failed_gates": failed_gates,
        "wer_vs_source_transcript": wer,
        "max_wer": max_wer,
        "required_substrings": required_substrings,
        "missing_substrings": missing,
        "silence_floor_db": SILENCE_FLOOR_DB,
    }


def resolve_api_key(args: argparse.Namespace) -> dict[str, Any]:
    if os.getenv(args.api_key_env):
        return {"present": True, "source": "environment", "value": os.environ[args.api_key_env]}
    probe = run_cmd(["docker", "exec", args.whisper_container, "sh", "-lc", f"cat {args.whisper_key_path}"], timeout=20)
    value = (probe["stdout_tail"] or "").strip()
    return {
        "present": bool(value),
        "source": f"docker exec {args.whisper_container}",
        "value": value,
        "returncode": probe["returncode"],
    }


def run_route(
    *,
    route: str,
    args: argparse.Namespace,
    out_dir: Path,
    source_wav: Path,
    source_transcript: str,
    api_key: str,
    required_substrings: list[str],
) -> dict[str, Any]:
    route_dir = out_dir / route
    route_dir.mkdir(parents=True, exist_ok=True)
    capture_wav = route_dir / f"{route}-capture.wav"
    setup: dict[str, Any] = {}
    teardown: list[dict[str, Any]] = []

    if route == "virtual":
        setup = setup_virtual_route(route_dir, args.jabra_sink, mirror_to_jabra=not args.no_jabra_mirror)
        play_target, record_target = VIRTUAL_SINK, VIRTUAL_SOURCE
    else:
        play_target, record_target = args.jabra_sink, args.jabra_source

    nodes = pw_dump_nodes()
    devices = {
        "playback": device_state(play_target, nodes),
        "record": device_state(record_target, nodes),
        "jabra_sink": device_state(args.jabra_sink, nodes),
        "jabra_source": device_state(args.jabra_source, nodes),
        "alsa": alsa_state(args.alsa_card),
    }

    transport = play_and_capture(
        source_wav=source_wav,
        capture_wav=capture_wav,
        play_target=play_target,
        record_target=record_target,
        rate=args.record_rate,
        lead_in_s=args.lead_in_s,
        tail_s=args.tail_s,
        record_timeout_s=args.record_timeout_s,
    )

    if route == "virtual":
        teardown = [stop_background(entry) for entry in setup.get("processes", [])]
        setup = {key: value for key, value in setup.items() if key != "processes"}

    capture_exists = capture_wav.exists() and capture_wav.stat().st_size > 44
    capture_metrics = wav_metrics(capture_wav) if capture_exists else {"path": str(capture_wav), "exists": False}
    volume = volume_metrics(capture_wav) if capture_exists else {"mean_volume_db": None, "max_volume_db": None}

    captured_transcript = ""
    transcribe_error: str | None = None
    if capture_exists:
        try:
            captured_transcript = transcribe_openai_compatible(args.whisper_base_url, api_key, capture_wav)
        except Exception as exc:  # noqa: BLE001
            transcribe_error = f"{type(exc).__name__}: {exc}"

    evaluation = evaluate_capture(
        capture_wav=capture_wav,
        source_transcript=source_transcript,
        captured_transcript=captured_transcript,
        required_substrings=required_substrings,
        max_wer=args.max_wer,
        volume=volume,
    )
    if transcribe_error:
        evaluation["failed_gates"].append("whisper_transcription_call_ok")
        evaluation["ok"] = False
        evaluation["transcribe_error"] = transcribe_error

    realtimestt = {"ran": False, "reason": "disabled"}
    if args.realtimestt and capture_exists:
        realtimestt = realtimestt_stage(
            capture_wav=capture_wav,
            receipt_path=route_dir / f"{route}-realtimestt.json",
            expected_text=source_transcript,
            max_wer=args.max_wer,
            args=args,
            api_key=api_key,
        )

    return {
        "route": route,
        "mocked": False,
        "live": True,
        "playback_target": play_target,
        "record_target": record_target,
        "capture_path": str(capture_wav),
        "capture_metrics": capture_metrics,
        "capture_volume": volume,
        "device_state": devices,
        "route_setup": setup,
        "route_teardown": teardown,
        "transport": transport,
        "captured_transcript": captured_transcript,
        "captured_transcript_sha256": sha256_text(captured_transcript),
        "acceptance": evaluation,
        "realtimestt": realtimestt,
        "pass": bool(evaluation["ok"]),
    }


def build_receipt(args: argparse.Namespace) -> dict[str, Any]:
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    source_wav = Path(args.source_wav).resolve()
    required_substrings = list(args.require_substring)

    receipt: dict[str, Any] = {
        "schema": "embry.live_asr_capture_mvp.v1",
        "mocked": False,
        "live": True,
        "started_at_utc": utc_now(),
        "out_dir": str(out_dir),
        "source_wav": {"path": str(source_wav), "exists": source_wav.exists()},
        "whisper": {"base_url": args.whisper_base_url, "container": args.whisper_container},
        "routes": [],
        "failed_gates": [],
        "claims": {
            "proves": [],
            "does_not_prove": [
                "full_embry_voice_goal",
                "wake_word_detection",
                "sparta_live_turn",
                "orb_cdp_animation",
            ],
        },
    }

    if not source_wav.exists():
        receipt["failed_gates"].append("source_wav_exists")
        receipt["pass"] = False
        receipt["ended_at_utc"] = utc_now()
        return receipt
    receipt["source_wav"] = wav_metrics(source_wav)

    key_info = resolve_api_key(args)
    receipt["whisper"]["api_key_present"] = key_info["present"]
    receipt["whisper"]["api_key_source"] = key_info["source"]
    if not key_info["present"]:
        receipt["failed_gates"].append("whisper_api_key_available")
        receipt["pass"] = False
        receipt["ended_at_utc"] = utc_now()
        return receipt

    try:
        source_transcript = transcribe_openai_compatible(args.whisper_base_url, key_info["value"], source_wav)
    except Exception as exc:  # noqa: BLE001
        receipt["failed_gates"].append("source_wav_transcription_ok")
        receipt["error"] = f"{type(exc).__name__}: {exc}"
        receipt["pass"] = False
        receipt["ended_at_utc"] = utc_now()
        return receipt

    receipt["source_transcript"] = source_transcript
    receipt["source_transcript_sha256"] = sha256_text(source_transcript)
    if not source_transcript.strip():
        receipt["failed_gates"].append("source_transcript_present")

    routes = ["jabra", "virtual"] if args.path == "both" else [args.path]
    for route in routes:
        receipt["routes"].append(
            run_route(
                route=route,
                args=args,
                out_dir=out_dir,
                source_wav=source_wav,
                source_transcript=source_transcript,
                api_key=key_info["value"],
                required_substrings=required_substrings,
            )
        )

    by_route = {entry["route"]: entry for entry in receipt["routes"]}
    passing = [name for name, entry in by_route.items() if entry["pass"]]
    receipt["accepted_routes"] = passing
    receipt["physical_acoustic_path_pass"] = bool(by_route.get("jabra", {}).get("pass"))
    receipt["virtual_loopback_path_pass"] = bool(by_route.get("virtual", {}).get("pass"))
    receipt["pass"] = bool(passing) and not receipt["failed_gates"]
    if not passing:
        receipt["failed_gates"].append("at_least_one_capture_route_accepted")
    if receipt["pass"]:
        receipt["claims"]["proves"] = [
            f"chatterbox_wav_reaches_live_whisper_through_capture_route:{','.join(passing)}",
            "no_browser_microphone_required",
        ]
    receipt["ended_at_utc"] = utc_now()
    return receipt


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source-wav", default=str(DEFAULT_SOURCE_WAV))
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--path", choices=["jabra", "virtual", "both"], default="both")
    parser.add_argument("--jabra-sink", default=DEFAULT_JABRA_SINK)
    parser.add_argument("--jabra-source", default=DEFAULT_JABRA_SOURCE)
    parser.add_argument("--alsa-card", default="Jabra")
    parser.add_argument("--no-jabra-mirror", action="store_true", help="do not mirror virtual playback to the Jabra speaker")
    parser.add_argument("--record-rate", type=int, default=16000)
    parser.add_argument("--lead-in-s", type=float, default=1.0)
    parser.add_argument("--tail-s", type=float, default=1.0)
    parser.add_argument("--record-timeout-s", type=float, default=60.0)
    parser.add_argument("--require-substring", action="append", default=None)
    parser.add_argument("--max-wer", type=float, default=0.35)
    parser.add_argument("--whisper-base-url", default=os.getenv("CHATTERBOX_ASR_OPENAI_BASE_URL", "http://127.0.0.1:9000"))
    parser.add_argument("--whisper-container", default="whisper")
    parser.add_argument("--whisper-key-path", default="/var/lib/whisper/.api_key")
    parser.add_argument("--api-key-env", default="WHISPER_API_KEY")
    parser.add_argument("--realtimestt", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--realtimestt-root", default="/home/graham/workspace/experiments/RealtimeSTT")
    parser.add_argument(
        "--realtimestt-python",
        default="/home/graham/workspace/experiments/RealtimeSTT/.venv-fastapi/bin/python",
    )
    parser.add_argument("--realtimestt-timeout-s", type=float, default=300.0)
    args = parser.parse_args(argv)
    if args.require_substring is None:
        args.require_substring = ["capital of france"]
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    receipt = build_receipt(args)
    out_path = Path(args.out_dir).resolve() / "summary.json"
    out_path.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    print(f"\nreceipt: {out_path}", file=sys.stderr)
    return 0 if receipt.get("pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
