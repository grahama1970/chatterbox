#!/usr/bin/env python3
"""Embry workstation voice-control CLI and Unix-socket service scaffold.

This is intentionally a thin authority layer. It orchestrates existing Linux
packages and existing proof runners, then writes an Embry session journal and
receipt bundle. It does not implement STT, speaker identity, memory, Tau, TTS,
audio routing, or browser UI behavior itself.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import socket
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.embry_event_journal import EventJournal, sha256_file


DEFAULT_SESSION_ROOT = Path.home() / ".local/share/embry/voice/sessions"
DEFAULT_RUNTIME_DIR = Path(os.getenv("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")) / "embry"
DEFAULT_SOCKET = DEFAULT_RUNTIME_DIR / "voice-control.sock"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"error_type": type(exc).__name__, "error": str(exc), "path": str(path)}


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def run_cmd(cmd: list[str], *, timeout: float, env: dict[str, str] | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        result = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout, env=env, check=False)
        return {
            "argv": cmd,
            "returncode": result.returncode,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
            "stdout_tail": result.stdout[-6000:],
            "stderr_tail": result.stderr[-6000:],
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "argv": cmd,
            "returncode": 124,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
            "stdout_tail": (exc.stdout or "")[-6000:] if isinstance(exc.stdout, str) else "",
            "stderr_tail": (exc.stderr or "")[-6000:] if isinstance(exc.stderr, str) else "",
            "timeout_s": timeout,
        }
    except FileNotFoundError as exc:
        return {
            "argv": cmd,
            "returncode": 127,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
            "stdout_tail": "",
            "stderr_tail": str(exc),
            "error_type": "FileNotFoundError",
        }


def command_version(command: str, *args: str) -> str | None:
    result = run_cmd([command, *args], timeout=8)
    if result["returncode"] != 0:
        return None
    return (result.get("stdout_tail") or result.get("stderr_tail") or "").strip().splitlines()[0:1][0]


def command_versions() -> dict[str, str | None]:
    return {
        "pactl": command_version("pactl", "--version"),
        "wpctl": command_version("wpctl", "--version"),
        "pw-record": command_version("pw-record", "--version"),
        "pw-play": command_version("pw-play", "--version"),
        "ffmpeg": command_version("ffmpeg", "-version"),
        "sox": command_version("sox", "--version"),
        "python": sys.version.split()[0],
    }


def resolve_whisper_api_key(env: dict[str, str], *, env_name: str = "WHISPER_API_KEY") -> dict[str, Any]:
    if env.get(env_name):
        return {"present": True, "source": "environment", "env_name": env_name}
    for cmd in (
        ["docker", "exec", "whisper", "whisper_manage", "--getkey"],
        ["docker", "exec", "chatterbox-fork-agent-server", "printenv", env_name],
    ):
        result = run_cmd(cmd, timeout=10)
        value = (result.get("stdout_tail") or "").strip().splitlines()
        if result["returncode"] == 0 and value and value[-1]:
            env[env_name] = value[-1].strip()
            return {"present": True, "source": " ".join(cmd[:3]), "env_name": env_name}
    return {"present": False, "source": "missing", "env_name": env_name}


def new_session(root: Path, *, session_id: str | None = None) -> dict[str, Any]:
    sid = session_id or "ses_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + secrets.token_hex(3)
    session_dir = (root / sid).resolve()
    for subdir in ("receipts", "artifacts/audio", "artifacts/json", "commands"):
        (session_dir / subdir).mkdir(parents=True, exist_ok=True)
    events_path = session_dir / "events.ndjson"
    events_path.write_text("", encoding="utf-8")
    receipt = {
        "schema": "embry.voice_control_session.v1",
        "ok": True,
        "live": True,
        "mocked": False,
        "session_id": sid,
        "session_dir": str(session_dir),
        "events_path": str(events_path),
        "receipts_dir": str(session_dir / "receipts"),
        "artifacts_dir": str(session_dir / "artifacts"),
        "created_at_utc": utc_now(),
    }
    write_json(session_dir / "receipts/session_start_receipt.json", receipt)
    return receipt


def artifact_entry(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "exists": path.exists(),
        "sha256": sha256_file(path) if path.exists() and path.is_file() else None,
        "bytes": path.stat().st_size if path.exists() and path.is_file() else 0,
    }


def child_status(receipt: dict[str, Any], *, path: Path) -> dict[str, Any]:
    return {
        "ok": receipt.get("ok") is True,
        "live": receipt.get("live") is True,
        "mocked": receipt.get("mocked") is True,
        "path": str(path),
        "failed_gates": receipt.get("failed_gates") or [],
        "schema": receipt.get("schema"),
    }


def check_os_loopback_core(args: argparse.Namespace) -> dict[str, Any]:
    started = time.perf_counter()
    session = new_session(args.session_root, session_id=args.session_id)
    session_dir = Path(session["session_dir"])
    events_path = Path(session["events_path"])
    journal = EventJournal(events_path, session_id=session["session_id"], trace_id=f"trace_{uuid.uuid4().hex}", repo=Path.cwd())
    env = os.environ.copy()
    asr_auth = resolve_whisper_api_key(env)
    failed_gates: list[str] = []
    child_receipts: dict[str, Any] = {}
    commands: list[dict[str, Any]] = []
    nonce = args.nonce or secrets.token_hex(4)
    python = str(args.child_python)
    speaker_gate_python = str(args.speaker_gate_python)

    journal.append(
        "voice_control.check.started",
        component="embry-voice-control",
        payload={"check": "os-loopback-core", "nonce_sha256": sha256_text(nonce)},
        source={"live": True, "mocked": False, "transport": "unix_socket_or_cli"},
    )

    rung1_dir = session_dir / "artifacts/json/rung1"
    rung1_cmd = [
        python,
        "scripts/rung1_audio_graph_realtimestt.py",
        "--out",
        str(rung1_dir),
        "--expected",
        args.expected_phrase,
        "--nonce",
        nonce,
        "--realtimestt-timeout-s",
        str(args.realtimestt_timeout_s),
    ]
    rung1_run = run_cmd(rung1_cmd, timeout=args.stage_timeout_s, env=env)
    commands.append(rung1_run)
    write_json(session_dir / "commands/rung1_command.json", rung1_run)
    rung1_path = rung1_dir / "rung_receipt.json"
    rung1 = read_json(rung1_path)
    child_receipts["audio_graph_realtimestt"] = child_status(rung1, path=rung1_path)
    if rung1_run["returncode"] != 0 or rung1.get("ok") is not True:
        failed_gates.append("audio_graph_realtimestt_ok")
    journal.append(
        "voice_control.child_receipt",
        component="rung1_audio_graph_realtimestt",
        payload=child_receipts["audio_graph_realtimestt"],
        source={"live": rung1.get("live") is True, "mocked": rung1.get("mocked") is True, "transport": "pipewire_pulse_monitor"},
        artifacts=[artifact_entry(rung1_path), artifact_entry(rung1_dir / "captured.wav")],
    )

    captured_wav = rung1_dir / "captured.wav"
    if args.with_speaker_gate and captured_wav.exists():
        rung2_run_id = f"rung2-{session['session_id']}"
        rung2_cmd = [
            speaker_gate_python,
            "scripts/rung2_source_audio_speaker_gate.py",
            "--run-id",
            rung2_run_id,
            "--out-root",
            str(session_dir / "artifacts/json"),
            "--generic-non-horus-audio",
            str(captured_wav),
        ]
        rung2_run = run_cmd(rung2_cmd, timeout=args.stage_timeout_s, env=env)
        commands.append(rung2_run)
        write_json(session_dir / "commands/rung2_command.json", rung2_run)
        rung2_path = session_dir / "artifacts/json" / rung2_run_id / "rung2_source_audio_speaker_gate_receipt.json"
        rung2 = read_json(rung2_path)
        child_receipts["speaker_gate"] = child_status(rung2, path=rung2_path)
        if rung2_run["returncode"] != 0 or rung2.get("ok") is not True:
            failed_gates.append("speaker_gate_ok")
        journal.append(
            "voice_control.child_receipt",
            component="rung2_source_audio_speaker_gate",
            payload=child_receipts["speaker_gate"],
            source={"live": rung2.get("live") is True, "mocked": rung2.get("mocked") is True, "transport": "source_audio_embedding"},
            artifacts=[artifact_entry(rung2_path)],
        )
    elif args.with_speaker_gate:
        failed_gates.append("speaker_gate_input_captured_wav_exists")

    if args.with_memory_tau:
        core_dir = session_dir / "artifacts/json/listener_memory_tau_qra"
        core_cmd = [
            python,
            "scripts/smoke_listener_memory_tau_qra.py",
            "--out-dir",
            str(core_dir),
            "--timeout-s",
            str(int(args.core_timeout_s)),
        ]
        core_run = run_cmd(core_cmd, timeout=args.core_timeout_s + 20, env=env)
        commands.append(core_run)
        write_json(session_dir / "commands/memory_tau_command.json", core_run)
        core_path = core_dir / "listener-memory-tau-qra.json"
        core = read_json(core_path)
        child_receipts["memory_tau_chatterbox"] = child_status(core, path=core_path)
        if core_run["returncode"] != 0 or core.get("ok") is not True:
            failed_gates.append("memory_tau_chatterbox_ok")
        journal.append(
            "voice_control.child_receipt",
            component="smoke_listener_memory_tau_qra",
            payload=child_receipts["memory_tau_chatterbox"],
            source={"live": core.get("live") is True, "mocked": core.get("mocked") is True, "transport": "service_http_and_realtimestt"},
            artifacts=[artifact_entry(core_path)],
        )

    commands_path = session_dir / "commands.jsonl"
    with commands_path.open("w", encoding="utf-8") as handle:
        for command in commands:
            handle.write(json.dumps(command, sort_keys=True) + "\n")

    if asr_auth["present"] is not True:
        failed_gates.append("asr_api_key_available")
    if journal.validation_failures:
        failed_gates.extend(f"event_journal:{gate}" for gate in journal.validation_failures)

    all_children_live = all(status.get("live") is True for status in child_receipts.values()) if child_receipts else False
    no_child_mocked = all(status.get("mocked") is not True for status in child_receipts.values()) if child_receipts else False
    ok = not failed_gates and bool(child_receipts) and all(status["ok"] for status in child_receipts.values())
    journal.append(
        "voice_control.check.ended",
        component="embry-voice-control",
        payload={"ok": ok, "failed_gates": failed_gates},
        source={"live": all_children_live, "mocked": not no_child_mocked, "transport": "unix_socket_or_cli"},
    )
    event_hash = journal.hash()
    receipt = {
        "schema": "embry.voice_control.os_loopback_core_receipt.v1",
        "ok": ok,
        "status": "pass" if ok else "fail",
        "live": ok and all_children_live,
        "mocked": not no_child_mocked,
        "session_id": session["session_id"],
        "session_dir": str(session_dir),
        "events_path": str(events_path),
        "event_journal_sha256": event_hash,
        "commands_path": str(commands_path),
        "command_versions": command_versions(),
        "asr_auth": asr_auth,
        "child_receipts": child_receipts,
        "artifact_hashes": [artifact_entry(path) for path in (rung1_path, captured_wav, commands_path, events_path) if path.exists()],
        "failed_gates": failed_gates,
        "proof_scope": [
            "embry_voice_control_session_directory",
            "embry_voice_control_event_journal",
            "orchestrates_pipewire_pulse_capture_to_realtimestt",
            "orchestrates_source_audio_speaker_gate" if args.with_speaker_gate else "speaker_gate_not_requested",
            "orchestrates_memory_tau_chatterbox_component_check" if args.with_memory_tau else "memory_tau_chatterbox_not_requested",
        ],
        "does_not_prove": [
            "browser_or_react_is_voice_authority",
            "single_turn_id_across_all_voice_services",
            "physical_room_microphone_capture",
            "production_pyannote_overlap_diarization",
            "shared_chat_ux_rendering",
            "orb_visual_quality",
            "human_heard_audio",
        ],
        "claims": {
            "proves": [
                "embry_voice_control_can_create_a_receipted_session_and_run_live_package_backed_voice_checks",
            ]
            if ok
            else [],
            "does_not_prove": [
                "final_unified_browser_to_chat_voice_loop",
                "react_chat_ux_sync",
                "human_audible_speaker_output",
            ],
        },
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "ended_at_utc": utc_now(),
    }
    receipt_path = session_dir / "receipts/os_loopback_core_receipt.json"
    receipt["receipt_path"] = str(receipt_path)
    write_json(receipt_path, receipt)
    return receipt


def serve(args: argparse.Namespace) -> int:
    """Tiny JSON-over-UDS endpoint for smokeable local control."""
    socket_path = args.socket
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    socket_path.unlink(missing_ok=True)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        server.bind(str(socket_path))
        os.chmod(socket_path, 0o600)
        server.listen(1)
        while True:
            conn, _ = server.accept()
            with conn:
                raw = conn.recv(1024 * 1024)
                try:
                    request = json.loads(raw.decode("utf-8"))
                    endpoint = request.get("endpoint")
                    if endpoint == "/sessions/start":
                        response = new_session(args.session_root, session_id=request.get("session_id"))
                    elif endpoint == "/checks/os-loopback-core":
                        ns = argparse.Namespace(**vars(args))
                        ns.nonce = request.get("nonce")
                        ns.expected_phrase = request.get("expected_phrase") or "Horus workstation loopback check"
                        ns.with_speaker_gate = bool(request.get("with_speaker_gate", True))
                        ns.with_memory_tau = bool(request.get("with_memory_tau", False))
                        response = check_os_loopback_core(ns)
                    else:
                        response = {"ok": False, "live": True, "mocked": False, "failed_gates": ["unknown_endpoint"], "endpoint": endpoint}
                except Exception as exc:  # noqa: BLE001
                    response = {"ok": False, "live": False, "mocked": False, "error_type": type(exc).__name__, "error": str(exc)}
                conn.sendall((json.dumps(response, sort_keys=True) + "\n").encode("utf-8"))
                if getattr(args, "one_shot", False):
                    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Embry workstation voice-control authority")
    parser.add_argument("--session-root", type=Path, default=DEFAULT_SESSION_ROOT)
    sub = parser.add_subparsers(dest="command", required=True)

    session_parser = sub.add_parser("sessions")
    session_sub = session_parser.add_subparsers(dest="session_command", required=True)
    start = session_sub.add_parser("start")
    start.add_argument("--session-id")

    check_parser = sub.add_parser("check")
    check_sub = check_parser.add_subparsers(dest="check_command", required=True)
    os_loop = check_sub.add_parser("os-loopback-core")
    os_loop.add_argument("--session-id")
    os_loop.add_argument("--nonce")
    os_loop.add_argument("--expected-phrase", default="Horus workstation loopback check")
    os_loop.add_argument("--stage-timeout-s", type=float, default=240.0)
    os_loop.add_argument("--realtimestt-timeout-s", type=float, default=180.0)
    os_loop.add_argument("--core-timeout-s", type=float, default=420.0)
    os_loop.add_argument("--with-speaker-gate", action=argparse.BooleanOptionalAction, default=True)
    os_loop.add_argument("--with-memory-tau", action=argparse.BooleanOptionalAction, default=False)
    os_loop.add_argument("--child-python", type=Path, default=Path(sys.executable))
    os_loop.add_argument(
        "--speaker-gate-python",
        type=Path,
        default=Path("/tmp/chatterbox-listener-venv/bin/python"),
    )

    serve_parser = sub.add_parser("serve")
    serve_parser.add_argument("--socket", type=Path, default=DEFAULT_SOCKET)
    serve_parser.add_argument("--one-shot", action="store_true")
    serve_parser.add_argument("--session-id")
    serve_parser.add_argument("--nonce")
    serve_parser.add_argument("--expected-phrase", default="Horus workstation loopback check")
    serve_parser.add_argument("--stage-timeout-s", type=float, default=240.0)
    serve_parser.add_argument("--realtimestt-timeout-s", type=float, default=180.0)
    serve_parser.add_argument("--core-timeout-s", type=float, default=420.0)
    serve_parser.add_argument("--with-speaker-gate", action=argparse.BooleanOptionalAction, default=True)
    serve_parser.add_argument("--with-memory-tau", action=argparse.BooleanOptionalAction, default=False)
    serve_parser.add_argument("--child-python", type=Path, default=Path(sys.executable))
    serve_parser.add_argument(
        "--speaker-gate-python",
        type=Path,
        default=Path("/tmp/chatterbox-listener-venv/bin/python"),
    )

    args = parser.parse_args()
    if args.command == "sessions" and args.session_command == "start":
        receipt = new_session(args.session_root, session_id=args.session_id)
    elif args.command == "check" and args.check_command == "os-loopback-core":
        receipt = check_os_loopback_core(args)
    elif args.command == "serve":
        return serve(args)
    else:
        parser.error("unsupported command")
    print(json.dumps(receipt, sort_keys=True))
    return 0 if receipt.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
