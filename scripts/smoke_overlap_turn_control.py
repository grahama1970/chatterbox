#!/usr/bin/env python3
"""Live overlap -> memory intent -> Chatterbox boundary smoke.

This smoke proves the policy path for "two non-Embry speakers are talking at
once". It generates an overlapping two-voice WAV, runs pyannote diarization,
passes listener overlap evidence to memory /intent, and renders the boundary
response through Tau/Chatterbox with memory-provided voice_delivery metadata.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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


def host_to_container_out(path: Path) -> str:
    default_out_root = Path(__file__).resolve().parents[1] / "logs"
    out_root = Path(os.getenv("CHATTERBOX_OUT_DIR_HOST", str(default_out_root))).resolve()
    resolved = path.resolve()
    try:
        rel = resolved.relative_to(out_root)
        return f"/out/{rel.as_posix()}"
    except ValueError:
        return str(path)


def make_overlap_wav(out_dir: Path, *, timeout_s: int) -> dict[str, Any]:
    male = out_dir / "male.wav"
    female = out_dir / "female.wav"
    overlap = out_dir / "overlap.wav"
    children: dict[str, Any] = {}
    children["male_espeak"] = run_cmd(
        [
            "espeak-ng",
            "-w",
            str(male),
            "-v",
            "en-us+m3",
            "-s",
            "135",
            "Horus is asking Embry a question about memory recall under factory noise.",
        ],
        timeout=timeout_s,
    )
    children["female_espeak"] = run_cmd(
        [
            "espeak-ng",
            "-w",
            str(female),
            "-v",
            "en-us+f3",
            "-s",
            "150",
            "Another person is speaking at the same time and should not be treated as Horus.",
        ],
        timeout=timeout_s,
    )
    children["sox_mix"] = run_cmd(
        [
            "sox",
            "-m",
            "-v",
            "0.9",
            str(male),
            "-v",
            "0.9",
            str(female),
            "-r",
            "16000",
            "-c",
            "1",
            str(overlap),
        ],
        timeout=timeout_s,
    )
    return {"audio": {"male": str(male), "female": str(female), "overlap": str(overlap)}, "children": children}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--base-url", default="http://127.0.0.1:8018")
    parser.add_argument("--memory-url", default="http://127.0.0.1:8601")
    parser.add_argument("--python", default=DEFAULT_PYTHON, type=Path)
    parser.add_argument("--timeout-s", default=420, type=int)
    parser.add_argument("--chatterbox-container", default="chatterbox-fork-agent-server")
    parser.add_argument("--pyannote-in-container", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--min-overlap-seconds", default=0.25, type=float)
    args = parser.parse_args()

    started = time.perf_counter()
    py = str(args.python) if args.python.exists() else sys.executable
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    failed_gates: list[str] = []
    children: dict[str, Any] = {}

    generated = make_overlap_wav(out_dir, timeout_s=args.timeout_s)
    children.update(generated["children"])
    overlap_audio = Path(generated["audio"]["overlap"])
    if not overlap_audio.exists():
        failed_gates.append("overlap_audio_generated")

    pyannote_path = out_dir / "pyannote-overlap.json"
    if args.pyannote_in_container:
        pyannote_cmd = [
            "docker",
            "exec",
            args.chatterbox_container,
            "/opt/chatterbox-diarization-venv/bin/python",
            "/work/scripts/smoke_pyannote_diarization.py",
            "--audio",
            host_to_container_out(overlap_audio),
            "--out",
            host_to_container_out(pyannote_path),
            "--device",
            "cpu",
            "--num-speakers",
            "2",
            "--min-speakers",
            "2",
        ]
    else:
        pyannote_cmd = [
            py,
            "scripts/smoke_pyannote_diarization.py",
            "--audio",
            str(overlap_audio),
            "--out",
            str(pyannote_path),
            "--device",
            "cpu",
            "--num-speakers",
            "2",
            "--min-speakers",
            "2",
        ]
    pyannote = run_cmd(pyannote_cmd, timeout=args.timeout_s)
    children["pyannote_diarization"] = pyannote
    pyannote_receipt = read_json(pyannote_path)
    py_summary = pyannote_receipt.get("summary") or {}
    if pyannote["returncode"] != 0 or not pyannote_receipt.get("ok"):
        failed_gates.append("pyannote_overlap_ok")
    if int(py_summary.get("speaker_count") or 0) < 2:
        failed_gates.append("pyannote_two_speakers")
    if float(py_summary.get("overlap_seconds") or 0.0) < args.min_overlap_seconds:
        failed_gates.append("pyannote_overlap_seconds")

    listener_evidence = {
        "schema": "chatterbox.listener_evidence.v1",
        "source": "pyannote_overlap_smoke",
        "speaker_count": py_summary.get("speaker_count"),
        "non_embry_speaker_count": py_summary.get("speaker_count"),
        "overlapping_speech": True,
        "overlap_detected": True,
        "speech_active": True,
        "pyannote_overlap_seconds": py_summary.get("overlap_seconds"),
        "anonymous_pyannote_speakers": py_summary.get("speakers") or [],
    }
    write_json(out_dir / "listener-evidence.json", listener_evidence)

    intent_payload = {
        "q": "Two people are speaking at the same time.",
        "scope": "voice_turn_control",
        "fast": True,
        "speaker_resolution": {
            "schema": "memory.speaker_resolution.v1",
            "status": "known",
            "speaker_id": "horus_lupercal",
            "confidence": 0.94,
        },
        "listener_evidence": listener_evidence,
        "context": {"listener_event": "multi_speaker_overlap"},
    }
    intent = {}
    try:
        intent = post_json(f"{args.memory_url.rstrip('/')}/intent", intent_payload, 20)
        write_json(out_dir / "memory-intent.json", intent)
    except Exception as exc:  # noqa: BLE001
        intent = {"error_type": type(exc).__name__, "error": str(exc)}
        write_json(out_dir / "memory-intent.json", intent)
        failed_gates.append("memory_intent_ok")
    if intent.get("action") != "CLARIFY":
        failed_gates.append("memory_intent_clarify")
    if intent.get("clarify_kind") != "turn_taking":
        failed_gates.append("memory_intent_turn_taking")
    if ((intent.get("voice_delivery") or {}).get("tone")) != "one_at_a_time_interrupt":
        failed_gates.append("memory_intent_one_at_a_time_tone")

    tau_path = out_dir / "tau-overlap-boundary.json"
    tau_cmd = [
        py,
        "scripts/smoke_tau_voice_render.py",
        "--base-url",
        args.base_url,
        "--out",
        str(tau_path),
        "--question",
        "Two people are speaking at the same time.",
        "--answer-text",
        "Hey, one at a time?",
        "--blessed-qra-memory-key",
        "voice-turn-control-overlap",
        "--blessed-qra-memory-similarity",
        "1.0",
        "--blessed-qra-memory-review-status",
        "approved",
        "--listener-receipt",
        str(out_dir / "listener-evidence.json"),
        "--voice-delivery-receipt",
        str(out_dir / "memory-intent.json"),
        "--no-use-blessed-qra-cache",
    ]
    tau = run_cmd(tau_cmd, timeout=args.timeout_s)
    children["tau_voice_render"] = tau
    tau_receipt = read_json(tau_path)
    if tau["returncode"] != 0 or not tau_receipt.get("ok"):
        failed_gates.append("tau_overlap_boundary_ok")
    tau_delivery = (tau_receipt.get("request") or {}).get("voice_delivery") or {}
    if tau_delivery.get("tone") != "one_at_a_time_interrupt":
        failed_gates.append("tau_one_at_a_time_tone")

    receipt = {
        "schema": "chatterbox.overlap_turn_control_smoke.v1",
        "ok": not failed_gates,
        "mocked": False,
        "live": not failed_gates,
        "started_at_utc": datetime.fromtimestamp(
            time.time() - (time.perf_counter() - started),
            timezone.utc,
        ).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "ended_at_utc": utc_now(),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "artifacts": {
            "male_wav": generated["audio"]["male"],
            "female_wav": generated["audio"]["female"],
            "overlap_wav": generated["audio"]["overlap"],
            "pyannote": str(pyannote_path),
            "listener_evidence": str(out_dir / "listener-evidence.json"),
            "memory_intent": str(out_dir / "memory-intent.json"),
            "tau_voice_render": str(tau_path),
        },
        "pyannote_summary": py_summary,
        "listener_evidence": listener_evidence,
        "memory_intent": {
            "action": intent.get("action"),
            "clarify_kind": intent.get("clarify_kind"),
            "classifier_source": intent.get("classifier_source"),
            "voice_delivery": intent.get("voice_delivery"),
        },
        "tau_voice_render": {
            "ok": tau_receipt.get("ok"),
            "live": tau_receipt.get("live"),
            "failed_gates": tau_receipt.get("failed_gates"),
            "voice_delivery": tau_delivery,
            "finished_audio_metrics": (tau_receipt.get("artifacts") or {}).get("finished_response_audio_metrics"),
        },
        "children": children,
        "failed_gates": failed_gates,
        "claims": {
            "proves": [
                "pyannote_detected_two_anonymous_overlapping_speakers",
                "memory_intent_maps_overlap_to_turn_taking_clarification",
                "memory_intent_emits_one_at_a_time_interrupt_voice_delivery",
                "tau_chatterbox_renders_overlap_boundary_with_memory_tone",
            ]
            if not failed_gates
            else [],
            "does_not_prove": [
                "real_time_streaming_overlap_diarization",
                "word_level_speaker_attribution",
                "all_factory_floor_overlap_conditions",
                "subjective_boundary_delivery_quality",
            ],
        },
    }
    write_json(out_dir / "overlap-turn-control.json", receipt)
    print(
        json.dumps(
            {
                "ok": receipt["ok"],
                "mocked": receipt["mocked"],
                "live": receipt["live"],
                "out": str(out_dir / "overlap-turn-control.json"),
                "failed_gates": failed_gates,
            },
            sort_keys=True,
        )
    )
    return 0 if receipt["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
