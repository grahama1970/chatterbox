#!/usr/bin/env python3
"""Deterministically audit the Horus/Embry live-loop proof gates.

This script does not run the voice stack. It audits concrete receipts and marks
each requested gate PASS or FAIL from required fields. A producer receipt's
`ok` field is treated as a claim; every gate also checks the specific evidence
fields needed for that gate.
"""

from __future__ import annotations

import argparse
import glob
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULTS = {
    "horus_rung7": "/tmp/chatterbox-fork-agent-out/rung7-horus-factory-stress-youtube-20260702T192914Z/rung7-combined.json",
    "browser_webrtc": "/tmp/chatterbox-fork-agent-out/voice-chat-e2e/browser-current-*/browser-webrtc.json",
    "browser_realtimestt": "/tmp/chatterbox-fork-agent-out/voice-chat-e2e/browser-current-*-continuous-core/02-realtimestt-listener.json",
    "continuous_loop": "/tmp/chatterbox-fork-agent-out/voice-chat-e2e/browser-current-*-continuous-core/continuous-voice-loop.json",
    "listener_memory_tau_qra": "/tmp/chatterbox-fork-agent-out/voice-chat-e2e/voice-chat-e2e-20260703T211546Z-all-current/S01-S02-S08-S09-S12-continuous-core/11-qra-cache-probe/listener-memory-tau-qra.json",
    "tau_voice_render": "/tmp/chatterbox-fork-agent-out/voice-chat-e2e/browser-current-*-continuous-core/09-tau-voice-render.json",
    "stream_cancel": "/tmp/chatterbox-fork-agent-out/voice-chat-e2e/browser-current-*-continuous-core/10-stream-turn-cancel.json",
    "overlap_control": "/tmp/chatterbox-fork-agent-out/voice-chat-e2e/browser-current-*-continuous-core/12-overlap-turn-control/overlap-turn-control.json",
    "chat_ux": "/tmp/embry-voice-controlled-loop-ui-proof-after-live-patch.json",
    "orb_sync": "/tmp/embry_voice_orb_connection_proof.json",
    "replay": "/tmp/codex-ui-verification/pi-mono/embry-voice-dynamic-replay-hardening/dynamic-replay-proof.json",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"__load_error__": f"{type(exc).__name__}: {exc}"}


def resolve_receipt_path(value: str) -> Path:
    if any(ch in value for ch in "*?["):
        matches = [Path(match) for match in glob.glob(value)]
        matches = [match for match in matches if match.exists()]
        if matches:
            return max(matches, key=lambda path: path.stat().st_mtime)
    return Path(value)


def exists_file(path_value: Any) -> bool:
    if not isinstance(path_value, str) or not path_value:
        return False
    path = Path(path_value)
    return path.exists() and path.is_file() and path.stat().st_size > 0


def ok_live_unmocked(receipt: dict[str, Any]) -> bool:
    return (
        receipt.get("ok") is True
        and receipt.get("mocked") is False
        and receipt.get("live") is True
        and not receipt.get("failed_gates")
    )


def get_path(data: Any, *keys: str) -> Any:
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def check(condition: bool, failures: list[str], label: str) -> None:
    if not condition:
        failures.append(label)


def gate(name: str, receipt_paths: list[Path], failures: list[str], evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "status": "PASS" if not failures else "FAIL",
        "failed_checks": failures,
        "receipt_paths": [str(path) for path in receipt_paths],
        "evidence": evidence,
    }


def repo_state(root: Path) -> dict[str, Any]:
    def run(cmd: list[str]) -> str:
        result = subprocess.run(cmd, cwd=root, text=True, capture_output=True, timeout=10, check=False)
        return result.stdout.strip()

    return {
        "path": str(root),
        "head": run(["git", "rev-parse", "--short", "HEAD"]),
        "branch": run(["git", "branch", "--show-current"]),
        "status_short": run(["git", "status", "--short"]),
    }


def audit(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(__file__).resolve().parents[1]
    paths = {key: resolve_receipt_path(str(getattr(args, key) or value)) for key, value in DEFAULTS.items()}
    receipts = {key: load_json(path) if path.exists() else {"__missing__": True} for key, path in paths.items()}

    gates: list[dict[str, Any]] = []

    horus = receipts["horus_rung7"]
    verification = horus.get("primary_speaker_verification") or {}
    resolution = horus.get("speaker_resolution") or {}
    failures: list[str] = []
    check(paths["horus_rung7"].exists(), failures, "receipt_exists")
    check(ok_live_unmocked(horus), failures, "rung7_receipt_ok_live_unmocked")
    check(verification.get("schema") == "chatterbox.listener.primary_speaker_verification.v1", failures, "primary_verification_schema")
    check(verification.get("ok") is True, failures, "primary_verification_ok")
    check(verification.get("primary_speaker_match") is True, failures, "primary_speaker_match_true")
    check(str(verification.get("enrollment_audio") or "").lower().find("horus") >= 0, failures, "enrollment_audio_names_horus")
    check(exists_file(verification.get("enrollment_audio")), failures, "enrollment_audio_exists")
    check(exists_file(verification.get("candidate_audio")), failures, "candidate_audio_exists")
    check(float(verification.get("similarity") or 0) >= float(verification.get("threshold") or 1), failures, "similarity_meets_threshold")
    check(resolution.get("status") == "known", failures, "memory_speaker_status_known")
    check(resolution.get("speaker_id") == "horus_lupercal", failures, "speaker_id_horus_lupercal")
    gates.append(gate(
        "real Horus enrollment",
        [paths["horus_rung7"]],
        failures,
        {
            "enrollment_audio": verification.get("enrollment_audio"),
            "candidate_audio": verification.get("candidate_audio"),
            "similarity": verification.get("similarity"),
            "threshold": verification.get("threshold"),
            "speaker_resolution_status": resolution.get("status"),
            "speaker_id": resolution.get("speaker_id"),
        },
    ))

    browser = receipts["browser_webrtc"]
    browser_rstt = receipts["browser_realtimestt"]
    failures = []
    check(paths["browser_webrtc"].exists(), failures, "receipt_exists")
    check(ok_live_unmocked(browser), failures, "browser_transport_ok_live_unmocked")
    check((browser.get("transport") or {}).get("chunks_received", 0) > 0, failures, "chunks_received_positive")
    check((browser.get("transport") or {}).get("binary_bytes_received", 0) > 0, failures, "binary_bytes_received_positive")
    check((browser.get("transport") or {}).get("duration_seconds", 0) >= 2.0, failures, "duration_at_least_2s")
    check(exists_file((browser.get("artifacts") or {}).get("wav")), failures, "captured_wav_exists")
    check(paths["browser_realtimestt"].exists(), failures, "browser_realtimestt_receipt_exists")
    check(ok_live_unmocked(browser_rstt), failures, "browser_realtimestt_ok_live_unmocked")
    check((browser_rstt.get("transcript") or {}).get("text") not in {None, ""}, failures, "browser_realtimestt_transcript_present")
    gates.append(gate(
        "browser mic/WebRTC",
        [paths["browser_webrtc"], paths["browser_realtimestt"]],
        failures,
        {
            "chunks_received": get_path(browser, "transport", "chunks_received"),
            "binary_bytes_received": get_path(browser, "transport", "binary_bytes_received"),
            "duration_seconds": get_path(browser, "transport", "duration_seconds"),
            "captured_wav": get_path(browser, "artifacts", "wav"),
            "audio_device_label": get_path(browser, "inputs", "audio_device_label"),
            "echo_cancellation": get_path(browser, "inputs", "echo_cancellation"),
            "noise_suppression": get_path(browser, "inputs", "noise_suppression"),
            "auto_gain_control": get_path(browser, "inputs", "auto_gain_control"),
            "realtimestt_transcript": get_path(browser_rstt, "transcript", "text"),
        },
    ))

    qra = receipts["listener_memory_tau_qra"]
    rung7_path = Path(str(get_path(qra, "artifacts", "rung7_receipt") or ""))
    rung7 = load_json(rung7_path) if rung7_path.exists() else {}
    failures = []
    check(paths["listener_memory_tau_qra"].exists(), failures, "receipt_exists")
    check(ok_live_unmocked(qra), failures, "listener_memory_tau_qra_ok_live_unmocked")
    check((rung7.get("asr_transcript") or {}).get("text") not in {None, ""}, failures, "asr_text_present")
    check((rung7.get("tau_voice_render_request") or {}).get("schema") == "tau.voice_render_request.v1", failures, "tau_request_schema")
    memory_gate_passed = get_path(qra, "tau_voice_render", "memory_gate_passed") is True
    check(
        (qra.get("memory_recall") or {}).get("found") is True
        or (qra.get("runtime_memory_recall") or {}).get("found") is True
        or memory_gate_passed,
        failures,
        "memory_recall_or_gate_found",
    )
    gates.append(gate(
        "Tau/memory routing",
        [paths["listener_memory_tau_qra"], rung7_path],
        failures,
        {
            "rung7_receipt": str(rung7_path),
            "asr_text": (rung7.get("asr_transcript") or {}).get("text"),
            "tau_request_schema": (rung7.get("tau_voice_render_request") or {}).get("schema"),
            "memory_gate_passed": memory_gate_passed,
        },
    ))

    continuous = receipts["continuous_loop"]
    tau = receipts["tau_voice_render"]
    listener_path = Path(str(get_path(continuous, "artifacts", "listener_receipt") or ""))
    listener = load_json(listener_path) if listener_path.exists() else {}
    failures = []
    check(paths["continuous_loop"].exists(), failures, "continuous_loop_receipt_exists")
    check(ok_live_unmocked(continuous), failures, "continuous_loop_ok_live_unmocked")
    check(listener_path.exists(), failures, "continuous_listener_receipt_exists")
    check(ok_live_unmocked(listener), failures, "continuous_listener_ok_live_unmocked")
    check((listener.get("transcript") or {}).get("text") not in {None, ""}, failures, "continuous_listener_transcript_present")
    check(ok_live_unmocked(tau), failures, "tau_voice_render_ok_live_unmocked")
    check(exists_file(get_path(tau, "artifacts", "finished_response_audio_host")), failures, "chatterbox_finished_wav_exists")
    check((tau.get("request") or {}).get("schema") == "tau.voice_render_request.v1", failures, "tau_request_schema")
    gates.append(gate(
        "Chatterbox from live STT",
        [paths["continuous_loop"], listener_path, paths["tau_voice_render"]],
        failures,
        {
            "continuous_loop_ok": continuous.get("ok"),
            "continuous_listener_ok": listener.get("ok"),
            "continuous_listener_transcript": get_path(listener, "transcript", "text"),
            "tau_voice_render_ok": tau.get("ok"),
            "finished_response_audio_host": get_path(tau, "artifacts", "finished_response_audio_host"),
            "lineage_rule": "PASS requires one continuous-loop receipt with live STT transcript plus Tau/Chatterbox render artifacts.",
        },
    ))

    chat = receipts["chat_ux"]
    failures = []
    check(paths["chat_ux"].exists(), failures, "receipt_exists")
    check(chat.get("audioCount", 0) >= 1, failures, "audio_elements_present")
    check("Shared chat UX with synchronized Chatterbox audio" in str(chat.get("finalText") or ""), failures, "shared_chat_text_visible")
    check("What did we last talk about?" in str(chat.get("finalText") or ""), failures, "conversation_text_visible")
    check("RENDER CHATTERBOX AUDIO" in str(chat.get("finalText") or ""), failures, "chatterbox_audio_status_visible")
    check(len(chat.get("audioSrcs") or []) >= 1, failures, "audio_srcs_present")
    gates.append(gate(
        "Chat UX sync",
        [paths["chat_ux"]],
        failures,
        {
            "audio_count": chat.get("audioCount"),
            "audio_src_count": len(chat.get("audioSrcs") or []),
            "proof_type": "UI DOM/text/audio-src proof, not full browser microphone loop.",
        },
    ))

    orb = receipts["orb_sync"]
    samples = orb.get("samples") or []
    nonzero_samples = [sample for sample in samples if float(sample.get("audioLevel") or 0) > 0]
    bound_samples = [sample for sample in samples if str(sample.get("speechBound")).lower() == "true"]
    canvas_hashes = {sample.get("canvasHash") for sample in samples if sample.get("canvasHash") is not None}
    failures = []
    check(paths["orb_sync"].exists(), failures, "receipt_exists")
    check(str(orb.get("mocked")).lower() in {"no", "false"}, failures, "mocked_false")
    check(str(orb.get("live")).lower() in {"yes", "true"}, failures, "live_true")
    check(len(nonzero_samples) >= 3, failures, "nonzero_audio_samples")
    check(len(bound_samples) >= 3, failures, "speech_bound_samples")
    check(len(canvas_hashes) >= 2, failures, "canvas_hash_changes")
    gates.append(gate(
        "orb sync",
        [paths["orb_sync"]],
        failures,
        {
            "sample_count": len(samples),
            "nonzero_audio_sample_count": len(nonzero_samples),
            "speech_bound_sample_count": len(bound_samples),
            "canvas_hash_count": len(canvas_hashes),
        },
    ))

    replay = receipts["replay"]
    assertions = replay.get("assertions") or {}
    failures = []
    check(paths["replay"].exists(), failures, "receipt_exists")
    check(assertions.get("dynamicReplayReducedToCurrentTurn") is True, failures, "dynamic_replay_reduced_to_current_turn")
    check(assertions.get("audioArtifactsEmbeddedInSharedChat") is True, failures, "audio_artifacts_embedded")
    check(assertions.get("liveReasoningTraceVisibleDuringReplay") is True, failures, "reasoning_trace_visible")
    check(assertions.get("replayCompletesWithoutStaticReset") is True, failures, "replay_completes")
    check(int(replay.get("audioCount") or 0) >= 1, failures, "audio_count_positive")
    gates.append(gate(
        "replay",
        [paths["replay"]],
        failures,
        {
            "assertions": assertions,
            "audio_count": replay.get("audioCount"),
            "final_phase": replay.get("finalPhase"),
            "screenshot": replay.get("screenshot"),
        },
    ))

    cancel = receipts["stream_cancel"]
    overlap = receipts["overlap_control"]
    failures = []
    check(paths["stream_cancel"].exists(), failures, "stream_cancel_receipt_exists")
    check(ok_live_unmocked(cancel), failures, "stream_cancel_ok_live_unmocked")
    check(cancel.get("old_turn_bytes_after_cancel") == 0, failures, "old_turn_bytes_after_cancel_zero")
    check(paths["overlap_control"].exists(), failures, "overlap_receipt_exists")
    check(ok_live_unmocked(overlap), failures, "overlap_ok_live_unmocked")
    check(exists_file(get_path(overlap, "artifacts", "tau_voice_render")), failures, "overlap_tau_voice_render_receipt_exists")
    gates.append(gate(
        "interruption",
        [paths["stream_cancel"], paths["overlap_control"]],
        failures,
        {
            "old_turn_bytes_after_cancel": cancel.get("old_turn_bytes_after_cancel"),
            "stream_cancel_failed_gates": cancel.get("failed_gates"),
            "overlap_failed_gates": overlap.get("failed_gates"),
            "overlap_tau_voice_render": get_path(overlap, "artifacts", "tau_voice_render"),
        },
    ))

    pass_count = sum(1 for item in gates if item["status"] == "PASS")
    fail_count = sum(1 for item in gates if item["status"] == "FAIL")
    receipt = {
        "schema": "chatterbox.horus_live_loop_gate_audit.v1",
        "created_at_utc": utc_now(),
        "ok": fail_count == 0,
        "mocked": False,
        "live": fail_count == 0,
        "status": "PASS" if fail_count == 0 else "FAIL",
        "pass_count": pass_count,
        "fail_count": fail_count,
        "gate_count": len(gates),
        "gates": gates,
        "repo": repo_state(root),
        "claims": {
            "proves": [
                "Each requested Horus/Embry live-loop item is deterministically classified PASS or FAIL from local receipt fields."
            ],
            "does_not_prove": [
                "A PASS in this audit does not create new live evidence; it validates existing receipts.",
                "The strict Chatterbox-from-live-STT gate fails unless browser/WebRTC RealtimeSTT transcript and Chatterbox render both pass.",
            ],
        },
    }
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    for key, value in DEFAULTS.items():
        parser.add_argument(f"--{key.replace('_', '-')}", default=value)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    receipt = audit(args)
    out = args.out or Path("/tmp/chatterbox-fork-agent-out") / f"horus-live-loop-gate-audit-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(str(out))
    print(json.dumps({
        "status": receipt["status"],
        "pass_count": receipt["pass_count"],
        "fail_count": receipt["fail_count"],
        "gates": [{ "name": gate["name"], "status": gate["status"], "failed_checks": gate["failed_checks"] } for gate in receipt["gates"]],
    }, indent=2, sort_keys=True))
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
