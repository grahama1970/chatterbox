#!/usr/bin/env python3
"""Run a simple-to-advanced non-mocked voice chat sanity suite.

This is an index runner. It does not replace the lower-level smokes; it calls
them as live child processes and writes one receipt that records which voice
chat requirements were exercised by each scenario.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_PYTHON = Path("/home/graham/workspace/experiments/venv/bin/python")
DEFAULT_INPUT_WAV = Path(
    "/tmp/chatterbox-fork-agent-out/rung7-horus-factory-stress-youtube-20260702T192914Z/"
    "horus-factory-embry-stress-8s.wav"
)

SUPPORTED_SCENARIOS = [
    "continuous_core",
    "stream_cancel",
    "qra_disabled",
    "unknown_speaker",
    "ambiguous_speaker",
    "female_distractor",
    "factory_noise_matrix",
    "browser_chat_ui",
]

PENDING_ADVANCED_SCENARIOS = {
    "physical_room_microphone_matrix": "requires repeated live room captures across devices and positions",
    "browser_chat_ui_screenshot_agreement": "requires production chat UI route plus screenshot-to-receipt agreement",
}


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


def child_env(api_key_env: str) -> dict[str, str]:
    env = os.environ.copy()
    repo_root = str(Path(__file__).resolve().parents[1])
    env["PYTHONPATH"] = (
        repo_root
        if not env.get("PYTHONPATH")
        else f"{repo_root}{os.pathsep}{env['PYTHONPATH']}"
    )
    if not env.get("HF_TOKEN"):
        hf_token = load_export_like_assignment(Path.home() / ".zshrc", "HF_TOKEN")
        if hf_token:
            env["HF_TOKEN"] = hf_token
    if not env.get(api_key_env):
        api_key = load_export_like_assignment(Path.home() / ".zshrc", api_key_env)
        if api_key:
            env[api_key_env] = api_key
    if not env.get(api_key_env):
        try:
            result = subprocess.run(
                ["docker", "exec", "whisper", "sh", "-lc", "cat /var/lib/whisper/.api_key"],
                text=True,
                capture_output=True,
                timeout=10,
                check=False,
            )
            key = result.stdout.strip()
            if result.returncode == 0 and key:
                env[api_key_env] = key
        except Exception:
            pass
    return env


def pipewire_status_text() -> str:
    result = run_cmd(["wpctl", "status"], timeout=5)
    return str(result.get("stdout_tail") or "")


def pipewire_id_by_label(status_text: str, section: str, label: str) -> str | None:
    in_section = False
    section_marker = f"├─ {section}:"
    for raw_line in status_text.splitlines():
        line = raw_line.rstrip()
        if section_marker in line:
            in_section = True
            continue
        if in_section and "├─" in line and section_marker not in line:
            in_section = False
        if in_section and label.lower() in line.lower():
            match = re.search(r"(?:\*?\s*)(\d+)\.", line)
            if match:
                return match.group(1)
    return None


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


def scenario_result(
    *,
    scenario_id: str,
    name: str,
    status: str,
    receipt_path: Path,
    child: dict[str, Any] | None = None,
    receipt: dict[str, Any] | None = None,
    failed_gates: list[str] | None = None,
    proves: list[str] | None = None,
    does_not_prove: list[str] | None = None,
    requirements: list[str] | None = None,
) -> dict[str, Any]:
    gates = failed_gates if failed_gates is not None else list((receipt or {}).get("failed_gates") or [])
    ok = status == "passed" and not gates
    return {
        "id": scenario_id,
        "name": name,
        "status": "passed" if ok else status,
        "ok": ok,
        "mocked": False,
        "live": bool(receipt.get("live")) if isinstance(receipt, dict) else status != "pending",
        "receipt": str(receipt_path),
        "requirements": requirements or [],
        "child": child or {},
        "failed_gates": gates,
        "claims": {
            "proves": proves if ok and proves is not None else ((receipt or {}).get("claims") or {}).get("proves", []),
            "does_not_prove": does_not_prove
            if does_not_prove is not None
            else ((receipt or {}).get("claims") or {}).get("does_not_prove", []),
        },
    }


def collect_wav_artifacts(root: Path) -> list[Path]:
    if not root.exists():
        return []
    wavs: list[Path] = []
    for path in sorted(root.rglob("*.wav")):
        if path.is_file() and path.stat().st_size > 44:
            wavs.append(path)
    return wavs


def wav_paths_from_json(value: Any) -> list[Path]:
    paths: list[Path] = []
    if isinstance(value, dict):
        for nested in value.values():
            paths.extend(wav_paths_from_json(nested))
    elif isinstance(value, list):
        for nested in value:
            paths.extend(wav_paths_from_json(nested))
    elif isinstance(value, str) and value.endswith(".wav"):
        path = Path(value)
        if path.exists() and path.is_file() and path.stat().st_size > 44:
            paths.append(path)
    return paths


def collect_scenario_wavs(scenario: dict[str, Any]) -> list[Path]:
    receipt_path = Path(str(scenario.get("receipt") or ""))
    root_wavs = collect_wav_artifacts(receipt_path.parent)
    receipt_wavs = wav_paths_from_json(read_json(receipt_path))
    seen: set[str] = set()
    deduped: list[Path] = []
    for wav in [*root_wavs, *receipt_wavs]:
        key = str(wav.resolve())
        if key not in seen:
            seen.add(key)
            deduped.append(wav)
    return deduped


def copy_tau_finished_audio(tau_receipt: dict[str, Any], dest: Path) -> str | None:
    source = Path(str(((tau_receipt.get("artifacts") or {}).get("finished_response_audio_host")) or ""))
    if not source.exists():
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)
    return str(dest)


def play_scenario_audio(
    *,
    scenario: dict[str, Any],
    playback_cmd: str,
    sink_target: str | None,
    timeout_s: int,
    env: dict[str, str],
) -> dict[str, Any]:
    wavs = collect_scenario_wavs(scenario)
    plays: list[dict[str, Any]] = []
    failed_gates: list[str] = []
    if not wavs:
        failed_gates.append("audible_playback_wav_artifact_present")
    for wav in wavs:
        cmd = [playback_cmd]
        if sink_target:
            cmd.extend(["--target", sink_target])
        cmd.append(str(wav))
        played = run_cmd(cmd, timeout=timeout_s, env=env)
        played["wav"] = str(wav)
        plays.append(played)
        if played["returncode"] != 0:
            failed_gates.append(f"audible_playback_ok:{wav.name}")
    return {
        "schema": "chatterbox.voice_chat_e2e.audible_playback.v1",
        "requested": True,
        "sink_target": sink_target,
        "playback_cmd": playback_cmd,
        "wav_count": len(wavs),
        "wavs": [str(path) for path in wavs],
        "plays": plays,
        "failed_gates": failed_gates,
        "claims": {
            "proves": [
                "scenario_wav_artifacts_were_played_through_configured_audio_sink",
            ]
            if not failed_gates
            else [],
            "does_not_prove": [
                "human_subjective_acceptance",
                "microphone_recapture_of_every_played_artifact",
            ],
        },
    }


def run_continuous_core(args: argparse.Namespace, out_dir: Path, py: str, env: dict[str, str]) -> dict[str, Any]:
    scenario_dir = out_dir / "S01-S02-S08-S09-S12-continuous-core"
    receipt_path = scenario_dir / "continuous-voice-loop.json"
    cmd = [
        py,
        "scripts/smoke_continuous_voice_loop.py",
        "--out-dir",
        str(scenario_dir),
        "--base-url",
        args.base_url,
        "--memory-url",
        args.memory_url,
        "--asr-openai-base-url",
        args.asr_openai_base_url,
        "--api-key-env",
        args.api_key_env,
        "--input-wav",
        str(args.input_wav),
        "--input-wav-source",
        args.input_wav_source,
        "--speaker-resolve-threshold",
        str(args.speaker_resolve_threshold),
        "--include-qra-cache-probe",
        "--include-overlap-probe",
        "--timeout-s",
        str(args.timeout_s),
    ]
    child = run_cmd(cmd, timeout=args.timeout_s, env=env)
    receipt = read_json(receipt_path)
    return scenario_result(
        scenario_id="S01_S02_S08_S09_S12",
        name="continuous voice core: simple turn, known Horus memory, barge-in, QRA hit, tone steering",
        status="passed" if child["returncode"] == 0 and receipt.get("ok") else "failed",
        receipt_path=receipt_path,
        child=child,
        receipt=receipt,
        requirements=["VC-01", "VC-03", "VC-04", "VC-05", "VC-06", "VC-09", "VC-12", "VC-13", "VC-14", "VC-15", "VC-16", "VC-23"],
    )


def run_stream_cancel(args: argparse.Namespace, out_dir: Path, py: str, env: dict[str, str]) -> dict[str, Any]:
    scenario_dir = out_dir / "S08-stream-cancel"
    receipt_path = scenario_dir / "stream-cancel.json"
    cmd = [
        py,
        "scripts/smoke_stream_turn_cancel.py",
        "--base-url",
        args.base_url,
        "--out",
        str(receipt_path),
        "--stream-timeout-s",
        str(args.timeout_s),
    ]
    child = run_cmd(cmd, timeout=args.timeout_s, env=env)
    receipt = read_json(receipt_path)
    failed = list(receipt.get("failed_gates") or [])
    if receipt.get("old_turn_bytes_after_cancel") != 0:
        failed.append("old_turn_bytes_after_cancel_zero")
    witness_path = scenario_dir / "stream-cancel-audible-witness.json"
    witness_cmd = [
        py,
        "scripts/smoke_tau_voice_render.py",
        "--base-url",
        args.base_url,
        "--out",
        str(witness_path),
        "--question",
        "What did the stream cancellation smoke test?",
        "--answer-text",
        "Stream cancellation check. The old turn emitted zero bytes after cancel.",
        "--blessed-qra-memory-key",
        "voice-turn-control-stream-cancel",
        "--blessed-qra-memory-similarity",
        "1.0",
        "--blessed-qra-memory-review-status",
        "approved",
        "--voice-delivery-json",
        json.dumps({"tone": "firm_boundary", "delivery_stage": "status", "pause_after_ms": 0}),
        "--no-use-blessed-qra-cache",
        "--timeout-s",
        str(args.timeout_s),
    ]
    witness_child = run_cmd(witness_cmd, timeout=args.timeout_s, env=env)
    witness_receipt = read_json(witness_path)
    witness_wav = copy_tau_finished_audio(witness_receipt, scenario_dir / "stream-cancel-audible-witness.wav")
    if witness_child["returncode"] != 0 or not witness_receipt.get("ok"):
        failed.append("stream_cancel_audible_witness_render_ok")
    if not witness_wav:
        failed.append("stream_cancel_audible_witness_wav")
    receipt["audible_witness"] = {
        "receipt": str(witness_path),
        "wav": witness_wav,
        "child": witness_child,
    }
    write_json(receipt_path, receipt)
    return scenario_result(
        scenario_id="S08",
        name="stream cancellation suppresses old-turn audio bytes",
        status="passed" if child["returncode"] == 0 and receipt.get("ok") and not failed else "failed",
        receipt_path=receipt_path,
        child={"stream_cancel": child, "audible_witness": witness_child},
        receipt=receipt,
        failed_gates=failed,
        proves=["cancelled turn stream emits zero old-turn bytes after cancel"],
        does_not_prove=["physical speaker buffer flush", "live microphone barge-in detection"],
        requirements=["VC-12", "VC-13"],
    )


def run_qra_disabled(args: argparse.Namespace, out_dir: Path, py: str, env: dict[str, str]) -> dict[str, Any]:
    receipt_path = out_dir / "S10-qra-disabled" / "tau-qra-disabled.json"
    voice_delivery = json.dumps({"tone": "memory_confident", "delivery_stage": "answer", "pause_after_ms": 0})
    cmd = [
        py,
        "scripts/smoke_tau_voice_render.py",
        "--base-url",
        args.base_url,
        "--out",
        str(receipt_path),
        "--question",
        args.qra_question,
        "--answer-text",
        args.qra_answer,
        "--blessed-qra-memory-key",
        args.qra_memory_key,
        "--blessed-qra-memory-similarity",
        "1.0",
        "--blessed-qra-memory-review-status",
        "approved",
        "--voice-delivery-json",
        voice_delivery,
        "--no-use-blessed-qra-cache",
        "--timeout-s",
        str(args.timeout_s),
    ]
    child = run_cmd(cmd, timeout=args.timeout_s, env=env)
    receipt = read_json(receipt_path)
    copied = copy_tau_finished_audio(receipt, receipt_path.parent / "qra-disabled-render.wav")
    response = receipt.get("response") or {}
    cache = response.get("blessed_qra_cache") or {}
    failed = list(receipt.get("failed_gates") or [])
    if receipt.get("request", {}).get("use_blessed_qra_cache") is not False:
        failed.append("request_cache_disabled")
    if cache.get("hit"):
        failed.append("cache_hit_false_when_disabled")
    if not copied:
        failed.append("qra_disabled_render_wav_copied")
    receipt["audible_wav"] = copied
    write_json(receipt_path, receipt)
    return scenario_result(
        scenario_id="S10",
        name="blessed QRA cache disabled path forces normal render",
        status="passed" if child["returncode"] == 0 and receipt.get("ok") and not failed else "failed",
        receipt_path=receipt_path,
        child=child,
        receipt=receipt,
        failed_gates=failed,
        proves=["Tau can request Chatterbox rendering with blessed QRA cache disabled"],
        does_not_prove=["listener ASR", "memory QRA ranking", "subjective voice quality"],
        requirements=["VC-17"],
    )


def speaker_resolution_scenario(
    *,
    args: argparse.Namespace,
    out_dir: Path,
    py: str,
    env: dict[str, str],
    scenario_id: str,
    name: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    scenario_dir = out_dir / scenario_id
    resolution_path = scenario_dir / "speaker-resolution.json"
    tau_path = scenario_dir / "identity-clarification-render.json"
    failed: list[str] = []
    try:
        resolution = post_json(f"{args.memory_url.rstrip('/')}/speaker/resolve", payload, 20)
    except Exception as exc:  # noqa: BLE001
        resolution = {"error_type": type(exc).__name__, "error": str(exc)}
        failed.append("speaker_resolve_ok")
    write_json(resolution_path, resolution)
    if resolution.get("status") != "unknown":
        failed.append("speaker_status_unknown")
    if resolution.get("allow_personal_memory") is not False:
        failed.append("personal_memory_disallowed")
    identity_prompt = resolution.get("identity_prompt") or {}
    answer_text = identity_prompt.get("text") or "I need to know who I am speaking with."
    if not identity_prompt.get("text"):
        failed.append("identity_prompt_present")
    if int(identity_prompt.get("count") or 0) < 20:
        failed.append("identity_prompt_bank_count_20")

    voice_delivery = json.dumps({"tone": "identity_clarification", "delivery_stage": "clarify", "pause_after_ms": 0})
    cmd = [
        py,
        "scripts/smoke_tau_voice_render.py",
        "--base-url",
        args.base_url,
        "--out",
        str(tau_path),
        "--question",
        "Who are you speaking with?",
        "--answer-text",
        answer_text,
        "--blessed-qra-memory-key",
        "voice-turn-control-identity-clarification",
        "--blessed-qra-memory-similarity",
        "1.0",
        "--blessed-qra-memory-review-status",
        "approved",
        "--voice-delivery-json",
        voice_delivery,
        "--no-use-blessed-qra-cache",
        "--timeout-s",
        str(args.timeout_s),
    ]
    child = run_cmd(cmd, timeout=args.timeout_s, env=env)
    tau = read_json(tau_path)
    copied = copy_tau_finished_audio(tau, scenario_dir / "identity-clarification-render.wav")
    if child["returncode"] != 0 or not tau.get("ok"):
        failed.append("identity_clarification_render_ok")
    if not copied:
        failed.append("identity_clarification_render_wav_copied")
    tau_delivery = (tau.get("request") or {}).get("voice_delivery") or {}
    if tau_delivery.get("tone") != "identity_clarification":
        failed.append("tau_identity_clarification_tone")

    receipt = {
        "schema": "chatterbox.voice_chat_e2e.identity_resolution.v1",
        "ok": not failed,
        "mocked": False,
        "live": bool(resolution and tau.get("live")),
        "speaker_resolution": resolution,
        "tau_voice_render": {
            "ok": tau.get("ok"),
            "live": tau.get("live"),
            "failed_gates": tau.get("failed_gates"),
            "voice_delivery": tau_delivery,
            "finished_audio_metrics": (tau.get("artifacts") or {}).get("finished_response_audio_metrics"),
            "audible_wav": copied,
        },
        "artifacts": {
            "speaker_resolution": str(resolution_path),
            "tau_voice_render": str(tau_path),
        },
        "children": {"tau_voice_render": child},
        "failed_gates": failed,
        "claims": {
            "proves": [
                "live_memory_speaker_resolution_fails_closed_without_personal_memory",
                "identity_clarification_prompt_bank_is_available",
                "tau_chatterbox_renders_identity_clarification_tone",
            ]
            if not failed
            else [],
            "does_not_prove": [
                "raw_audio_identity_embedding_correctness",
                "live_microphone_capture",
                "speaker_diarization_correctness",
            ],
        },
    }
    write_json(scenario_dir / "identity-resolution.json", receipt)
    return scenario_result(
        scenario_id=scenario_id,
        name=name,
        status="passed" if receipt["ok"] else "failed",
        receipt_path=scenario_dir / "identity-resolution.json",
        child={"speaker_resolution_http": {"returncode": 0 if "speaker_resolve_ok" not in failed else 1}, "tau_voice_render": child},
        receipt=receipt,
        failed_gates=failed,
        requirements=["VC-07", "VC-08" if "ambiguous" in scenario_id else "VC-19"],
    )


def run_unknown_speaker(args: argparse.Namespace, out_dir: Path, py: str, env: dict[str, str]) -> dict[str, Any]:
    payload = {
        "speaker_evidence_id": "voice-chat-e2e-unknown",
        "session_id": "voice-chat-e2e",
        "turn_id": "unknown-speaker-turn",
        "persona_id": "embry",
        "threshold": args.speaker_resolve_threshold,
        "ambiguity_margin": args.speaker_ambiguity_margin,
        "allow_personal_memory": True,
        "candidates": [],
    }
    return speaker_resolution_scenario(
        args=args,
        out_dir=out_dir,
        py=py,
        env=env,
        scenario_id="S03-unknown-speaker",
        name="unknown speaker fails closed and Embry asks who she is speaking with",
        payload=payload,
    )


def run_ambiguous_speaker(args: argparse.Namespace, out_dir: Path, py: str, env: dict[str, str]) -> dict[str, Any]:
    payload = {
        "speaker_evidence_id": "voice-chat-e2e-ambiguous",
        "session_id": "voice-chat-e2e",
        "turn_id": "ambiguous-speaker-turn",
        "persona_id": "embry",
        "threshold": args.speaker_resolve_threshold,
        "ambiguity_margin": args.speaker_ambiguity_margin,
        "allow_personal_memory": True,
        "candidates": [
            {
                "speaker_id": "horus_lupercal",
                "display_name": "Horus Lupercal",
                "confidence": max(0.0, args.speaker_resolve_threshold - 0.02),
                "source": "voice_chat_e2e_low_confidence_probe",
                "tags": ["persona:horus_lupercal"],
            },
            {
                "speaker_id": "unknown_other",
                "display_name": "Unknown Other",
                "confidence": max(0.0, args.speaker_resolve_threshold - 0.04),
                "source": "voice_chat_e2e_low_confidence_probe",
                "tags": [],
            },
        ],
    }
    return speaker_resolution_scenario(
        args=args,
        out_dir=out_dir,
        py=py,
        env=env,
        scenario_id="S04-ambiguous-speaker",
        name="ambiguous speaker fails closed instead of using Horus memory",
        payload=payload,
    )


def run_female_distractor(args: argparse.Namespace, out_dir: Path, py: str, env: dict[str, str]) -> dict[str, Any]:
    receipt_path = out_dir / "S05-female-distractor" / "overlap-turn-control.json"
    cmd = [
        py,
        "scripts/smoke_overlap_turn_control.py",
        "--base-url",
        args.base_url,
        "--memory-url",
        args.memory_url,
        "--out-dir",
        str(receipt_path.parent),
        "--timeout-s",
        str(args.timeout_s),
    ]
    child = run_cmd(cmd, timeout=args.timeout_s, env=env)
    receipt = read_json(receipt_path)
    failed = list(receipt.get("failed_gates") or [])
    py_summary = receipt.get("pyannote_summary") or {}
    memory_intent = receipt.get("memory_intent") or {}
    if int(py_summary.get("speaker_count") or 0) < 2:
        failed.append("distractor_two_speakers_detected")
    if memory_intent.get("clarify_kind") != "turn_taking":
        failed.append("distractor_routes_to_turn_taking")
    if ((memory_intent.get("voice_delivery") or {}).get("tone")) != "one_at_a_time_interrupt":
        failed.append("distractor_one_at_a_time_tone")
    return scenario_result(
        scenario_id="S05",
        name="male plus female distractor routes to turn-taking boundary instead of personal memory",
        status="passed" if child["returncode"] == 0 and receipt.get("ok") and not failed else "failed",
        receipt_path=receipt_path,
        child=child,
        receipt=receipt,
        failed_gates=failed,
        proves=[
            "live pyannote detects two anonymous speakers in a male/female overlap fixture",
            "memory intent routes the overlap to turn-taking clarification",
            "Tau/Chatterbox renders the one-at-a-time boundary",
        ],
        does_not_prove=[
            "Horus enrollment identity under a female distractor",
            "real factory-room microphone capture",
            "word-level speaker separation",
        ],
        requirements=["VC-11", "VC-09"],
    )


def run_factory_noise_matrix(args: argparse.Namespace, out_dir: Path, py: str, env: dict[str, str]) -> dict[str, Any]:
    receipt_path = out_dir / "S06-factory-noise" / "rung8-loopback-listener.json"
    pw_status = pipewire_status_text()
    sink_target = args.factory_sink_target or pipewire_id_by_label(pw_status, "Sinks", args.factory_sink_label)
    record_target = args.factory_record_target or pipewire_id_by_label(pw_status, "Sources", args.factory_record_label)
    cmd = [
        py,
        "scripts/smoke_rung8_loopback_listener.py",
        "--play-audio",
        str(args.input_wav),
        "--out-dir",
        str(receipt_path.parent),
        "--out",
        str(receipt_path),
        "--asr-openai-base-url",
        args.asr_openai_base_url,
        "--api-key-env",
        args.api_key_env,
        "--capture-kind",
        args.factory_capture_kind,
        "--realtimestt-timeout-s",
        str(args.timeout_s),
        "--rung7-timeout-s",
        str(args.timeout_s),
    ]
    if sink_target:
        cmd.extend(["--sink-target", sink_target])
    if record_target:
        cmd.extend(["--record-target", record_target])
    child = run_cmd(cmd, timeout=args.timeout_s + 120, env=env)
    receipt = read_json(receipt_path)
    failed = list(receipt.get("failed_gates") or [])
    capture = receipt.get("capture") or {}
    if not capture.get("captured_audio"):
        failed.append("factory_capture_audio_present")
    return scenario_result(
        scenario_id="S06",
        name="Horus factory-stress audio through PipeWire loopback listener",
        status="passed" if child["returncode"] == 0 and receipt.get("ok") and not failed else "failed",
        receipt_path=receipt_path,
        child={**child, "pipewire_target_selection": {"sink_target": sink_target, "record_target": record_target}},
        receipt=receipt,
        failed_gates=failed,
        proves=[
            "configured factory-stress audio can be captured through PipeWire and fed to RealtimeSTT/rung7",
        ],
        does_not_prove=[
            "all factory floor noise conditions",
            "physical microphone placement robustness",
            "female distractor separation",
        ],
        requirements=["VC-10", "VC-23"],
    )


def run_browser_chat_ui(args: argparse.Namespace, out_dir: Path, py: str, env: dict[str, str]) -> dict[str, Any]:
    receipt_path = out_dir / "S13-browser-transport" / "browser-webrtc.json"
    cmd = [
        py,
        "scripts/smoke_browser_webrtc_transport.py",
        "--out",
        str(receipt_path),
        "--capture-seconds",
        str(args.browser_capture_seconds),
        "--min-duration-seconds",
        "1.0",
        "--play-audio",
        str(args.input_wav),
        "--noise-suppression",
        "--auto-gain-control",
    ]
    if args.browser_audio_device_label:
        cmd.extend(["--audio-device-label", args.browser_audio_device_label])
    child = run_cmd(cmd, timeout=args.timeout_s, env=env)
    receipt = read_json(receipt_path)
    failed = list(receipt.get("failed_gates") or [])
    artifacts = receipt.get("artifacts") or {}
    if not artifacts.get("wav"):
        failed.append("browser_transport_wav_present")
    return scenario_result(
        scenario_id="S13",
        name="browser getUserMedia transport captures audio for voice chat path",
        status="passed" if child["returncode"] == 0 and receipt.get("ok") and not failed else "failed",
        receipt_path=receipt_path,
        child=child,
        receipt=receipt,
        failed_gates=failed,
        proves=[
            "browser getUserMedia captured real microphone audio and sent PCM frames to Python listener",
        ],
        does_not_prove=[
            "production chat UI transcript/playback state",
            "screenshot agreement",
            "ASR accuracy",
        ],
        requirements=["VC-02", "VC-24"],
    )


def pending_scenario(scenario_id: str, name: str, reason: str, out_dir: Path) -> dict[str, Any]:
    receipt_path = out_dir / scenario_id / "pending.json"
    receipt = {
        "schema": "chatterbox.voice_chat_e2e.pending_scenario.v1",
        "ok": False,
        "mocked": False,
        "live": False,
        "status": "pending",
        "reason": reason,
        "failed_gates": ["scenario_not_implemented_with_live_artifacts"],
        "claims": {
            "proves": [],
            "does_not_prove": ["the scenario has not been exercised by this runner"],
        },
    }
    write_json(receipt_path, receipt)
    return scenario_result(
        scenario_id=scenario_id,
        name=name,
        status="pending",
        receipt_path=receipt_path,
        receipt=receipt,
        failed_gates=["scenario_not_implemented_with_live_artifacts"],
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--base-url", default="http://127.0.0.1:8018")
    parser.add_argument("--memory-url", default="http://127.0.0.1:8601")
    parser.add_argument("--asr-openai-base-url", default="http://127.0.0.1:9000")
    parser.add_argument("--api-key-env", default="WHISPER_API_KEY")
    parser.add_argument("--python", default=DEFAULT_PYTHON, type=Path)
    parser.add_argument("--input-wav", default=DEFAULT_INPUT_WAV, type=Path)
    parser.add_argument("--input-wav-source", default="pipewire_or_physical_capture")
    parser.add_argument("--timeout-s", default=600, type=int)
    parser.add_argument("--speaker-resolve-threshold", default=0.82, type=float)
    parser.add_argument("--speaker-ambiguity-margin", default=0.05, type=float)
    parser.add_argument("--scenario", action="append", choices=SUPPORTED_SCENARIOS + ["all", "pending_advanced"], default=[])
    parser.add_argument("--require-pending-advanced", action="store_true")
    parser.add_argument("--qra-question", default="Which control family should I use when the answer says SI?")
    parser.add_argument("--qra-answer", default="Use system and communications protection.")
    parser.add_argument("--qra-memory-key", default="qra-smoke-si")
    parser.add_argument("--browser-capture-seconds", default=6.0, type=float)
    parser.add_argument("--browser-audio-device-label", default="Jabra")
    parser.add_argument("--factory-capture-kind", choices=["monitor_loopback", "physical_microphone"], default="physical_microphone")
    parser.add_argument("--factory-sink-label", default="Jabra")
    parser.add_argument("--factory-record-label", default="Jabra")
    parser.add_argument("--factory-sink-target", default=None)
    parser.add_argument("--factory-record-target", default=None)
    parser.add_argument("--audible-playback", action="store_true")
    parser.add_argument("--playback-cmd", default="pw-play")
    parser.add_argument("--playback-sink-target", default=None)
    parser.add_argument("--playback-timeout-s", default=120, type=int)
    args = parser.parse_args()

    started = time.perf_counter()
    py = str(args.python) if args.python.exists() else sys.executable
    env = child_env(args.api_key_env)
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    requested = list(args.scenario or [])
    if not requested:
        requested = ["all"]
    if "all" in requested:
        scenarios_to_run = list(SUPPORTED_SCENARIOS)
    else:
        scenarios_to_run = [item for item in requested if item in SUPPORTED_SCENARIOS]

    scenario_receipts: list[dict[str, Any]] = []
    failed_gates: list[str] = []

    runners = {
        "continuous_core": run_continuous_core,
        "stream_cancel": run_stream_cancel,
        "qra_disabled": run_qra_disabled,
        "unknown_speaker": run_unknown_speaker,
        "ambiguous_speaker": run_ambiguous_speaker,
        "female_distractor": run_female_distractor,
        "factory_noise_matrix": run_factory_noise_matrix,
        "browser_chat_ui": run_browser_chat_ui,
    }
    for scenario_name in scenarios_to_run:
        result = runners[scenario_name](args, out_dir, py, env)
        if args.audible_playback:
            playback_sink = args.playback_sink_target or args.factory_sink_target
            audible = play_scenario_audio(
                scenario=result,
                playback_cmd=args.playback_cmd,
                sink_target=playback_sink,
                timeout_s=args.playback_timeout_s,
                env=env,
            )
            result["audible_playback"] = audible
            if audible["failed_gates"]:
                result["failed_gates"] = list(result.get("failed_gates") or []) + [
                    f"audible:{gate}" for gate in audible["failed_gates"]
                ]
                result["ok"] = False
                result["status"] = "failed"
        scenario_receipts.append(result)
        if not result["ok"]:
            failed_gates.append(f"{scenario_name}_ok")

    pending_requested = "pending_advanced" in requested or args.require_pending_advanced
    if pending_requested:
        for key, reason in PENDING_ADVANCED_SCENARIOS.items():
            result = pending_scenario(key, key.replace("_", " "), reason, out_dir)
            scenario_receipts.append(result)
            if args.require_pending_advanced:
                failed_gates.append(f"{key}_implemented")

    passed = [item["id"] for item in scenario_receipts if item["ok"]]
    failed = [item["id"] for item in scenario_receipts if item["status"] == "failed"]
    pending = [item["id"] for item in scenario_receipts if item["status"] == "pending"]
    receipt = {
        "schema": "chatterbox.voice_chat_e2e.index.v1",
        "ok": not failed_gates,
        "mocked": False,
        "live": bool(scenario_receipts) and not failed_gates,
        "started_at_utc": datetime.fromtimestamp(
            time.time() - (time.perf_counter() - started),
            timezone.utc,
        ).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "ended_at_utc": utc_now(),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "inputs": {
            "base_url": args.base_url,
            "memory_url": args.memory_url,
            "asr_openai_base_url": args.asr_openai_base_url,
            "input_wav": str(args.input_wav),
            "input_wav_source": args.input_wav_source,
            "scenarios": scenarios_to_run,
            "pending_advanced_included": pending_requested,
            "audible_playback": args.audible_playback,
            "playback_sink_target": args.playback_sink_target or args.factory_sink_target,
        },
        "summary": {
            "scenario_count": len(scenario_receipts),
            "passed": passed,
            "failed": failed,
            "pending": pending,
        },
        "scenarios": scenario_receipts,
        "pending_advanced_scenarios": PENDING_ADVANCED_SCENARIOS,
        "failed_gates": failed_gates,
        "claims": {
            "proves": [
                "selected_voice_chat_scenarios_were_exercised_through_live_services",
                "one_index_receipt_links_child_receipts_for_simple_to_advanced_voice_chat_checks",
            ]
            if not failed_gates
            else [],
            "does_not_prove": [
                "scenarios_not_requested_or_marked_pending",
                "subjective_voice_quality_without_human_review",
                "production_browser_chat_readiness_without_browser_chat_ui_scenario",
            ],
        },
    }
    write_json(out_dir / "index.json", receipt)
    print(
        json.dumps(
            {
                "ok": receipt["ok"],
                "mocked": receipt["mocked"],
                "live": receipt["live"],
                "out": str(out_dir / "index.json"),
                "passed": passed,
                "failed": failed,
                "pending": pending,
                "failed_gates": failed_gates,
            },
            sort_keys=True,
        )
    )
    return 0 if receipt["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
