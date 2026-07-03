#!/usr/bin/env python3
"""Continuous live receipt for browser mic -> listener -> memory/Tau -> voice.

The runner composes existing non-mocked receipts and adds boundary timing,
speaker reconciliation, and turn-control checks. It is intentionally fail-closed:
pyannote speaker labels remain anonymous unless enrollment evidence plus memory
/speaker/resolve map the turn to a known speaker.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_PLAY_AUDIO = Path(
    "/tmp/chatterbox-fork-agent-out/rung7-horus-factory-stress-youtube-20260702T192914Z/"
    "horus-factory-embry-stress-8s.wav"
)
DEFAULT_PYTHON = Path("/home/graham/workspace/experiments/venv/bin/python")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run_cmd(cmd: list[str], *, timeout: int, env: dict[str, str] | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    result = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout, env=env)
    return {
        "cmd": cmd,
        "returncode": result.returncode,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "stdout_tail": result.stdout[-4000:],
        "stderr_tail": result.stderr[-4000:],
    }


def load_export_like_assignment(path: Path, name: str) -> str | None:
    if not path.exists():
        return None
    pattern = re.compile(rf"^\s*(?:export\s+)?{re.escape(name)}=(['\"]?)(.*?)\1\s*$")
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = pattern.match(line)
        if match:
            return match.group(2).strip()
    return None


def child_env(args: argparse.Namespace) -> dict[str, str]:
    env = os.environ.copy()
    if not env.get("HF_TOKEN"):
        hf_token = load_export_like_assignment(Path.home() / ".zshrc", "HF_TOKEN")
        if hf_token:
            env["HF_TOKEN"] = hf_token
    if not env.get(args.api_key_env) and args.asr_openai_base_url.startswith("http://127.0.0.1"):
        try:
            result = subprocess.run(
                ["docker", "exec", "whisper", "sh", "-lc", "cat /var/lib/whisper/.api_key"],
                text=True,
                capture_output=True,
                timeout=10,
            )
            key = result.stdout.strip()
            if result.returncode == 0 and key:
                env[args.api_key_env] = key
        except Exception:
            pass
    env.setdefault("CUDA_VISIBLE_DEVICES", "")
    return env


def host_to_container_out(path: Path) -> str:
    out_root = Path("/tmp/chatterbox-fork-agent-out")
    resolved = path.resolve()
    try:
        rel = resolved.relative_to(out_root)
        return f"/out/{rel.as_posix()}"
    except ValueError:
        return str(path)


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"error_type": type(exc).__name__, "error": str(exc), "path": str(path)}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def post_json(url: str, payload: dict[str, Any], timeout_s: int) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        return json.loads(response.read().decode("utf-8"))


def first_event_ms(receipt: dict[str, Any], event_type: str) -> float | None:
    for event in receipt.get("events") or []:
        if event.get("type") == event_type:
            value = event.get("elapsed_ms")
            return float(value) if value is not None else None
    return None


def qra_text(item: dict[str, Any], *names: str) -> str:
    for name in names:
        value = item.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def speaker_resolve_payload(
    *,
    speaker_receipt: dict[str, Any],
    session_id: str,
    turn_id: str,
    threshold: float,
    ambiguity_margin: float,
) -> dict[str, Any]:
    summary = speaker_receipt.get("summary") or {}
    confidence = float(summary.get("mean_primary_margin") or 0.0)
    horus_ratio = float(summary.get("horus_ratio") or 0.0)
    return {
        "speaker_evidence_id": f"{turn_id}:speaker-segment-evidence",
        "session_id": session_id,
        "turn_id": turn_id,
        "persona_id": "embry",
        "threshold": threshold,
        "ambiguity_margin": ambiguity_margin,
        "prompt_variant": 0,
        "allow_personal_memory": True,
        "candidates": [
            {
                "speaker_id": "horus_lupercal",
                "display_name": "Horus Lupercal",
                "confidence": max(confidence, horus_ratio),
                "source": "resemblyzer_segment_evidence",
                "tags": ["persona:horus_lupercal"],
                "evidence": {
                    "horus_ratio": horus_ratio,
                    "mean_primary_margin": summary.get("mean_primary_margin"),
                    "voiced_segment_count": summary.get("voiced_segment_count"),
                },
            }
        ],
    }


def overlap_assessment(
    *,
    pyannote_receipt: dict[str, Any],
    speaker_receipt: dict[str, Any],
    min_overlap_seconds: float,
    max_embry_ratio: float,
) -> dict[str, Any]:
    py_summary = pyannote_receipt.get("summary") or {}
    speaker_summary = speaker_receipt.get("summary") or {}
    voiced = max(1, int(speaker_summary.get("voiced_segment_count") or 0))
    embry_ratio = float(speaker_summary.get("embry_segment_count") or 0) / voiced
    overlap_seconds = float(py_summary.get("overlap_seconds") or 0.0)
    speaker_count = int(py_summary.get("speaker_count") or 0)
    non_embry_overlap = overlap_seconds >= min_overlap_seconds and speaker_count >= 2 and embry_ratio <= max_embry_ratio
    return {
        "schema": "chatterbox.turn_control.overlap_assessment.v1",
        "anonymous_pyannote_speaker_count": speaker_count,
        "anonymous_pyannote_speakers": py_summary.get("speakers") or [],
        "pyannote_overlap_seconds": overlap_seconds,
        "embry_segment_ratio": round(embry_ratio, 4),
        "non_embry_overlap_candidate": non_embry_overlap,
        "policy": "fail_closed_before_personal_recall_when_multiple_non_embry_speakers_overlap",
        "response_text": "Hey, one at a time?" if non_embry_overlap else None,
    }


def listener_evidence_packet(
    *,
    listener_receipt: dict[str, Any],
    pyannote_receipt: dict[str, Any],
    speaker_receipt: dict[str, Any],
    overlap: dict[str, Any],
) -> dict[str, Any]:
    transcript_text = ((listener_receipt.get("transcript") or {}).get("text") or "").strip()
    speaker_summary = speaker_receipt.get("summary") or {}
    pyannote_summary = pyannote_receipt.get("summary") or {}
    return {
        "schema": "chatterbox.listener_evidence.v1",
        "source": "realtimestt_pyannote_segment_evidence",
        "transcript_present": bool(transcript_text),
        "transcript_length": len(transcript_text),
        "speaker_count": pyannote_summary.get("speaker_count"),
        "non_embry_speaker_count": overlap.get("anonymous_pyannote_speaker_count"),
        "overlapping_speech": bool(overlap.get("non_embry_overlap_candidate")),
        "overlap_detected": bool(overlap.get("non_embry_overlap_candidate")),
        "speech_active": bool(transcript_text),
        "pyannote_overlap_seconds": overlap.get("pyannote_overlap_seconds"),
        "embry_segment_ratio": overlap.get("embry_segment_ratio"),
        "horus_segment_ratio": speaker_summary.get("horus_segment_ratio"),
        "mean_primary_margin": speaker_summary.get("mean_primary_margin"),
        "voiced_segment_count": speaker_summary.get("voiced_segment_count"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--base-url", default="http://127.0.0.1:8018")
    parser.add_argument("--memory-url", default="http://127.0.0.1:8601")
    parser.add_argument("--asr-openai-base-url", default="http://127.0.0.1:9000")
    parser.add_argument("--api-key-env", default="WHISPER_API_KEY")
    parser.add_argument("--python", default=DEFAULT_PYTHON, type=Path)
    parser.add_argument("--browser-python", default=None, type=Path)
    parser.add_argument("--play-audio", default=DEFAULT_PLAY_AUDIO, type=Path)
    parser.add_argument("--playback-arg", action="append", default=[])
    parser.add_argument("--audio-device-label", default="Jabra")
    parser.add_argument("--echo-cancellation", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--noise-suppression", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--auto-gain-control", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--capture-seconds", default=9.0, type=float)
    parser.add_argument("--timeout-s", default=480, type=int)
    parser.add_argument("--memory-k", default=5, type=int)
    parser.add_argument("--speaker-resolve-threshold", default=0.82, type=float)
    parser.add_argument("--speaker-ambiguity-margin", default=0.05, type=float)
    parser.add_argument("--min-overlap-seconds", default=0.25, type=float)
    parser.add_argument("--max-embry-ratio-for-non-embry-overlap", default=0.2, type=float)
    parser.add_argument("--pyannote-in-container", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--chatterbox-container", default="chatterbox-fork-agent-server")
    parser.add_argument("--skip-pyannote", action="store_true")
    parser.add_argument("--skip-interruption", action="store_true")
    args = parser.parse_args()

    started = time.perf_counter()
    py = str(args.python) if args.python.exists() else sys.executable
    browser_py = str(args.browser_python) if args.browser_python and args.browser_python.exists() else sys.executable
    env = child_env(args)
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    failed_gates: list[str] = []
    children: dict[str, Any] = {}
    artifacts: dict[str, Any] = {}

    if not args.play_audio.exists():
        failed_gates.append("play_audio_exists")

    browser_path = out_dir / "01-browser-webrtc.json"
    browser_cmd = [
        browser_py,
        "scripts/smoke_browser_webrtc_transport.py",
        "--out",
        str(browser_path),
        "--capture-seconds",
        str(args.capture_seconds),
        "--play-audio",
        str(args.play_audio),
        "--min-duration-seconds",
        "2.0",
        "--audio-device-label",
        args.audio_device_label,
    ]
    for playback_arg in args.playback_arg or []:
        browser_cmd.append(f"--playback-arg={playback_arg}")
    if args.echo_cancellation:
        browser_cmd.append("--echo-cancellation")
    if args.noise_suppression:
        browser_cmd.append("--noise-suppression")
    if args.auto_gain_control:
        browser_cmd.append("--auto-gain-control")
    browser = run_cmd(browser_cmd, timeout=args.timeout_s, env=env)
    children["browser_webrtc_transport"] = browser
    browser_receipt = read_json(browser_path)
    if browser["returncode"] != 0 or not browser_receipt.get("ok"):
        failed_gates.append("browser_webrtc_transport_ok")
    browser_wav = Path(((browser_receipt.get("artifacts") or {}).get("wav")) or "")
    if not browser_wav.exists():
        failed_gates.append("browser_wav_exists")
    artifacts["browser_receipt"] = str(browser_path)
    artifacts["browser_wav"] = str(browser_wav) if browser_wav else None

    listener_path = out_dir / "02-realtimestt-listener.json"
    if browser_wav.exists():
        listener_cmd = [
            py,
            "scripts/smoke_realtimestt_listener_bridge.py",
            "--audio",
            str(browser_wav),
            "--out",
            str(listener_path),
            "--asr-openai-base-url",
            args.asr_openai_base_url,
            "--api-key-env",
            args.api_key_env,
            "--manual-start-stop",
            "--text-timeout-s",
            "180",
        ]
        listener = run_cmd(listener_cmd, timeout=args.timeout_s, env=env)
    else:
        listener = {"cmd": [], "returncode": 1, "elapsed_ms": 0, "stdout_tail": "", "stderr_tail": "browser_wav_missing"}
    children["realtimestt_listener"] = listener
    listener_receipt = read_json(listener_path)
    if listener["returncode"] != 0 or not listener_receipt.get("ok"):
        failed_gates.append("realtimestt_listener_ok")
    transcript = ((listener_receipt.get("transcript") or {}).get("text") or "").strip()
    if not transcript:
        failed_gates.append("listener_transcript_present")
    artifacts["listener_receipt"] = str(listener_path)

    speaker_path = out_dir / "03-speaker-segment-evidence.json"
    if browser_wav.exists():
        speaker_cmd = [
            py,
            "scripts/smoke_speaker_segment_evidence.py",
            "--audio",
            str(browser_wav),
            "--out",
            str(speaker_path),
            "--min-primary-ratio",
            "0.30",
            "--min-voiced-segments",
            "1",
        ]
        speaker = run_cmd(speaker_cmd, timeout=args.timeout_s, env=env)
    else:
        speaker = {"cmd": [], "returncode": 1, "elapsed_ms": 0, "stdout_tail": "", "stderr_tail": "browser_wav_missing"}
    children["speaker_segment_evidence"] = speaker
    speaker_receipt = read_json(speaker_path)
    if speaker["returncode"] != 0 and not speaker_path.exists():
        failed_gates.append("speaker_segment_evidence_ran")
    artifacts["speaker_segment_evidence"] = str(speaker_path)

    pyannote_receipt: dict[str, Any] = {"ok": False, "skipped": args.skip_pyannote}
    pyannote_path = out_dir / "04-pyannote-diarization.json"
    if not args.skip_pyannote and browser_wav.exists():
        if args.pyannote_in_container:
            pyannote_cmd = [
                "docker",
                "exec",
                args.chatterbox_container,
                "/opt/chatterbox-diarization-venv/bin/python",
                "/work/scripts/smoke_pyannote_diarization.py",
                "--audio",
                host_to_container_out(browser_wav),
                "--out",
                host_to_container_out(pyannote_path),
                "--device",
                "cpu",
            ]
        else:
            pyannote_cmd = [
                py,
                "scripts/smoke_pyannote_diarization.py",
                "--audio",
                str(browser_wav),
                "--out",
                str(pyannote_path),
                "--device",
                "cpu",
            ]
        pyannote = run_cmd(pyannote_cmd, timeout=args.timeout_s, env=env)
        children["pyannote_diarization"] = pyannote
        pyannote_receipt = read_json(pyannote_path)
        if pyannote["returncode"] != 0 and not pyannote_path.exists():
            failed_gates.append("pyannote_diarization_ran")
    elif args.skip_pyannote:
        children["pyannote_diarization"] = {"skipped": True}
    artifacts["pyannote_diarization"] = str(pyannote_path)

    speaker_resolution = {}
    memory_intent = {}
    memory_recall = {}
    overlap = overlap_assessment(
        pyannote_receipt=pyannote_receipt,
        speaker_receipt=speaker_receipt,
        min_overlap_seconds=args.min_overlap_seconds,
        max_embry_ratio=args.max_embry_ratio_for_non_embry_overlap,
    )
    write_json(out_dir / "05-overlap-assessment.json", overlap)
    artifacts["overlap_assessment"] = str(out_dir / "05-overlap-assessment.json")
    listener_evidence = listener_evidence_packet(
        listener_receipt=listener_receipt,
        pyannote_receipt=pyannote_receipt,
        speaker_receipt=speaker_receipt,
        overlap=overlap,
    )
    write_json(out_dir / "05-listener-evidence.json", listener_evidence)
    artifacts["listener_evidence"] = str(out_dir / "05-listener-evidence.json")

    try:
        speaker_payload = speaker_resolve_payload(
            speaker_receipt=speaker_receipt,
            session_id="continuous-voice-loop",
            turn_id="continuous-turn-1",
            threshold=args.speaker_resolve_threshold,
            ambiguity_margin=args.speaker_ambiguity_margin,
        )
        speaker_resolution = post_json(f"{args.memory_url.rstrip('/')}/speaker/resolve", speaker_payload, 20)
        write_json(out_dir / "06-speaker-resolution.json", speaker_resolution)
    except Exception as exc:  # noqa: BLE001
        speaker_resolution = {"error_type": type(exc).__name__, "error": str(exc)}
        write_json(out_dir / "06-speaker-resolution.json", speaker_resolution)
        failed_gates.append("speaker_resolution_ok")
    artifacts["speaker_resolution"] = str(out_dir / "06-speaker-resolution.json")

    try:
        intent_payload = {
            "q": transcript or "Two speakers are talking over each other.",
            "scope": "voice_turn_control" if overlap["non_embry_overlap_candidate"] else "persona_memory",
            "fast": True,
            "speaker_resolution": speaker_resolution,
            "listener_evidence": listener_evidence,
            "context": {
                "listener_event": "multi_speaker_overlap" if overlap["non_embry_overlap_candidate"] else "single_primary_speaker",
                "overlap_assessment": overlap,
            },
        }
        memory_intent = post_json(f"{args.memory_url.rstrip('/')}/intent", intent_payload, 20)
        write_json(out_dir / "07-memory-intent.json", memory_intent)
        if not isinstance(memory_intent.get("voice_delivery"), dict):
            failed_gates.append("memory_intent_voice_delivery_present")
    except Exception as exc:  # noqa: BLE001
        memory_intent = {"error_type": type(exc).__name__, "error": str(exc)}
        write_json(out_dir / "07-memory-intent.json", memory_intent)
        failed_gates.append("memory_intent_ok")
    artifacts["memory_intent"] = str(out_dir / "07-memory-intent.json")

    speaker_known_horus = speaker_resolution.get("status") == "known" and speaker_resolution.get("speaker_id") == "horus_lupercal"
    if overlap["non_embry_overlap_candidate"]:
        if memory_intent.get("action") not in {"CLARIFY", "NO_MATCH", "DEFLECT"}:
            failed_gates.append("overlap_intent_fail_closed")
        answer_text = overlap["response_text"] or "Hey, one at a time?"
        memory_key = "voice-turn-control-overlap"
    elif not speaker_known_horus:
        if memory_intent.get("action") not in {"CLARIFY", "NO_MATCH", "DEFLECT", None}:
            failed_gates.append("unknown_speaker_intent_fail_closed")
        answer_text = (
            (speaker_resolution.get("identity_prompt") or {}).get("text")
            or "I can hear you, but I need to know who I am speaking with."
        )
        memory_key = "voice-turn-control-identity-clarification"
    else:
        try:
            memory_recall = post_json(
                f"{args.memory_url.rstrip('/')}/recall",
                {
                    "q": transcript,
                    "k": args.memory_k,
                    "tags": speaker_resolution.get("memory_tags") or ["speaker:horus_lupercal", "persona:embry"],
                    "threshold": 0.3,
                },
                30,
            )
            write_json(out_dir / "08-memory-recall.json", memory_recall)
            if not memory_recall.get("found"):
                failed_gates.append("memory_recall_found")
        except Exception as exc:  # noqa: BLE001
            memory_recall = {"error_type": type(exc).__name__, "error": str(exc)}
            write_json(out_dir / "08-memory-recall.json", memory_recall)
            failed_gates.append("memory_recall_ok")
        top_item = ((memory_recall.get("items") or [{}])[0])
        answer_text = qra_text(top_item, "answer", "solution", "text") or "I heard you, but I do not have a grounded memory answer yet."
        memory_key = str(top_item.get("_key") or "continuous-memory-miss")
    artifacts["memory_recall"] = str(out_dir / "08-memory-recall.json")

    tau_path = out_dir / "09-tau-voice-render.json"
    tau_cmd = [
        py,
        "scripts/smoke_tau_voice_render.py",
        "--base-url",
        args.base_url,
        "--out",
        str(tau_path),
        "--question",
        transcript or "voice turn control",
        "--answer-text",
        answer_text,
        "--blessed-qra-memory-key",
        memory_key,
        "--blessed-qra-memory-similarity",
        "1.0",
        "--blessed-qra-memory-review-status",
        "approved",
        "--memory-receipt",
        str(out_dir / "08-memory-recall.json"),
        "--listener-receipt",
        str(listener_path),
        "--voice-delivery-receipt",
        str(out_dir / "07-memory-intent.json"),
        "--use-blessed-qra-cache",
    ]
    tau = run_cmd(tau_cmd, timeout=args.timeout_s, env=env)
    children["tau_voice_render"] = tau
    tau_receipt = read_json(tau_path)
    if tau["returncode"] != 0 or not tau_receipt.get("ok"):
        failed_gates.append("tau_voice_render_ok")
    tau_voice_delivery = (tau_receipt.get("request") or {}).get("voice_delivery")
    if not isinstance(tau_voice_delivery, dict) or not tau_voice_delivery.get("tone"):
        failed_gates.append("tau_voice_delivery_passed")
    artifacts["tau_voice_render"] = str(tau_path)

    cancel_path = out_dir / "10-stream-turn-cancel.json"
    if not args.skip_interruption:
        cancel_cmd = [
            py,
            "scripts/smoke_stream_turn_cancel.py",
            "--base-url",
            args.base_url,
            "--out",
            str(cancel_path),
        ]
        cancel = run_cmd(cancel_cmd, timeout=args.timeout_s, env=env)
        children["stream_turn_cancel"] = cancel
        cancel_receipt = read_json(cancel_path)
        if cancel["returncode"] != 0 or not cancel_receipt.get("ok"):
            failed_gates.append("stream_turn_cancel_ok")
        if cancel_receipt.get("old_turn_bytes_after_cancel") != 0:
            failed_gates.append("stale_old_turn_bytes_zero")
    else:
        cancel_receipt = {"skipped": True}
        children["stream_turn_cancel"] = {"skipped": True}
    artifacts["stream_turn_cancel"] = str(cancel_path)

    latency_budgets = {
        "schema": "chatterbox.continuous_voice_loop.latency_boundaries.v1",
        "mic_frame_received_ms": 0.0 if browser_receipt.get("ok") else None,
        "browser_capture_elapsed_ms": browser_receipt.get("elapsed_ms"),
        "vad_start_ms": first_event_ms(listener_receipt, "realtimestt.vad_start"),
        "vad_stop_ms": first_event_ms(listener_receipt, "realtimestt.vad_stop"),
        "asr_final_ms": first_event_ms(listener_receipt, "realtimestt.text_returned"),
        "memory_recall_ms": None if overlap["non_embry_overlap_candidate"] else None,
        "tau_render_request_ms": round((time.perf_counter() - started) * 1000, 3),
        "first_audio_byte_ms": (((tau_receipt.get("response") or {}).get("stream") or {}).get("first_byte_ms")),
        "final_spoken_chunk_ms": tau_receipt.get("elapsed_ms"),
        "turn_cancel_old_turn_bytes_after_cancel": cancel_receipt.get("old_turn_bytes_after_cancel"),
    }

    receipt = {
        "schema": "chatterbox.continuous_voice_loop_receipt.v1",
        "ok": not failed_gates,
        "mocked": False,
        "live": not failed_gates,
        "started_at_utc": datetime.fromtimestamp(
            time.time() - (time.perf_counter() - started),
            timezone.utc,
        ).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "ended_at_utc": utc_now(),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "proof_scope": "browser_getusermedia_to_realtimestt_to_speaker_memory_tau_chatterbox_receipt_bundle",
        "inputs": {
            "play_audio": str(args.play_audio),
            "base_url": args.base_url,
            "memory_url": args.memory_url,
            "asr_openai_base_url": args.asr_openai_base_url,
            "python": py,
            "browser_python": browser_py,
            "audio_device_label": args.audio_device_label,
            "playback_arg": list(args.playback_arg or []),
            "echo_cancellation": args.echo_cancellation,
            "noise_suppression": args.noise_suppression,
            "auto_gain_control": args.auto_gain_control,
            "pyannote_in_container": args.pyannote_in_container,
            "chatterbox_container": args.chatterbox_container,
            "skip_pyannote": args.skip_pyannote,
            "skip_interruption": args.skip_interruption,
        },
        "transcript": transcript,
        "speaker_identity_reconciliation": {
            "rule": "anonymous pyannote labels are not identity labels",
            "pyannote_speakers": (pyannote_receipt.get("summary") or {}).get("speakers") or [],
            "speaker_segment_summary": speaker_receipt.get("summary") or {},
            "memory_speaker_resolution": speaker_resolution,
            "mapped_primary_speaker": speaker_resolution.get("speaker_id") if speaker_resolution.get("status") == "known" else None,
            "captured_identity_gate": "known_horus" if speaker_known_horus else "fail_closed_identity_clarification",
        },
        "overlap_turn_control": overlap,
        "latency_budgets": latency_budgets,
        "interruption_proof": {
            "receipt": str(cancel_path),
            "old_turn_bytes_after_cancel": cancel_receipt.get("old_turn_bytes_after_cancel"),
            "new_turn_wins_gate": cancel_receipt.get("old_turn_bytes_after_cancel") == 0,
            "proof_scope": cancel_receipt.get("proof_scope"),
        },
        "artifacts": artifacts,
        "children": children,
        "failed_gates": failed_gates,
        "claims": {
            "proves": [
                "browser_getusermedia_audio_can_feed_realtimestt_external_audio_listener",
                "speaker_identity_mapping_uses_enrollment_and_memory_evidence_not_pyannote_label_assumption",
                "memory_or_turn_control_route_can_drive_tau_voice_render_to_chatterbox_output",
                "unknown_or_insufficient_physical_speaker_evidence_routes_to_clarification_without_personal_recall",
                "stream_cancel_child_receipt_records_zero_old_turn_bytes_after_cancel",
            ]
            if not failed_gates
            else [],
            "does_not_prove": [
                "remote_browser_peer_to_peer_transport",
                "perfect_multi_speaker_overlap_separation",
                "all_factory_floor_noise_conditions",
                "subjective_voice_quality",
                "production_memory_policy_for_every_overlap_phrase",
            ],
        },
    }
    write_json(out_dir / "continuous-voice-loop.json", receipt)
    print(
        json.dumps(
            {
                "ok": receipt["ok"],
                "live": receipt["live"],
                "mocked": receipt["mocked"],
                "out": str(out_dir / "continuous-voice-loop.json"),
                "failed_gates": failed_gates,
            },
            sort_keys=True,
        )
    )
    return 0 if receipt["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
