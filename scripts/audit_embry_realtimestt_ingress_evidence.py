#!/usr/bin/env python3
"""Audit current RealtimeSTT ingress evidence for Embry voice stress testing."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_MATRIX = Path("docs/EMBRY_STRESS_SESSION_MATRIX.json")
DEFAULT_OUT = Path("docs/EMBRY_REALTIMESTT_INGRESS_EVIDENCE_AUDIT.json")
DEFAULT_PROOFS = [
    Path("/tmp/chatterbox-fork-agent-out/voice-chat-e2e/20260708T061027Z-factory-loopback-auth-auto/S06-factory-noise/rung8-loopback-listener.json"),
    Path("/tmp/chatterbox-fork-agent-out/voice-chat-e2e/20260708T045822Z-factory-loopback-current/S06-factory-noise/rung8-loopback-listener.json"),
    Path("/tmp/chatterbox-fork-agent-out/voice-chat-e2e/20260708T034407Z-factory-current/S06-factory-noise/rung8-loopback-listener.json"),
    Path("/tmp/chatterbox-fork-agent-out/voice-chat-e2e/browser-quality-webcam-20260705T134007Z/continuous-voice-loop.json"),
    Path("/tmp/chatterbox-fork-agent-out/voice-chat-e2e/browser-quality-20260705T132832Z/continuous-voice-loop.json"),
    Path("/tmp/chatterbox-fork-agent-out/voice-chat-e2e/browser-quality-raw-20260705T133055Z/continuous-voice-loop.json"),
    Path("/tmp/chatterbox-fork-agent-out/rung8-loopback-20260702T204049Z/rung8-loopback-listener.json"),
    Path("/tmp/chatterbox-fork-agent-out/rung8-physical-mic-20260702T205201Z/rung8-physical-mic-listener.json"),
]


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"error_type": type(exc).__name__, "error": str(exc), "path": str(path)}


def nested_get(payload: dict[str, Any], dotted: str) -> Any:
    value: Any = payload
    for part in dotted.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def extract_transcript(receipt: dict[str, Any]) -> str:
    candidates = [
        receipt.get("transcript"),
        receipt.get("heard_text"),
        nested_get(receipt, "transcript.text"),
        nested_get(receipt, "children.realtimestt.receipt.transcript.text"),
    ]
    executor_calls = nested_get(receipt, "children.realtimestt.receipt.asr_executor_calls")
    if isinstance(executor_calls, list):
        candidates.extend(call.get("transcript") for call in executor_calls if isinstance(call, dict))
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate
    return ""


def classify_proof(path: Path, receipt: dict[str, Any]) -> dict[str, Any]:
    claims = receipt.get("claims") or {}
    proves = claims.get("proves") or []
    proof_scope = str(receipt.get("proof_scope") or "")
    transcript = extract_transcript(receipt)
    captured_rms = nested_get(receipt, "capture.captured_audio.rms")
    captured_audio_exists = nested_get(receipt, "capture.captured_audio.exists")
    captured_audio_sha256 = nested_get(receipt, "capture.captured_audio.sha256")
    captured_audio_path = nested_get(receipt, "capture.captured_audio.path")
    play_audio_sha256 = nested_get(receipt, "capture.play_audio.sha256")
    pipewire = nested_get(receipt, "capture.pipewire") or {}
    pipewire_identity = {
        "capture_backend": pipewire.get("capture_backend") if isinstance(pipewire, dict) else None,
        "capture_kind": pipewire.get("capture_kind") if isinstance(pipewire, dict) else None,
        "pulse_source": pipewire.get("pulse_source") if isinstance(pipewire, dict) else None,
        "sink_target": pipewire.get("sink_target") if isinstance(pipewire, dict) else None,
        "sink_node_name": pipewire.get("sink_node_name") if isinstance(pipewire, dict) else None,
        "record_target": pipewire.get("record_target") if isinstance(pipewire, dict) else None,
        "record_node_name": pipewire.get("record_node_name") if isinstance(pipewire, dict) else None,
    }
    asr_executor_calls = nested_get(receipt, "children.realtimestt.receipt.asr_executor_calls") or []

    if "browser_getusermedia" in proof_scope:
        transport = "browser_getusermedia"
    elif any("physical_microphone" in str(item) for item in proves):
        transport = "pipewire_physical_microphone"
    elif any("monitor_loopback" in str(item) for item in proves):
        transport = "pipewire_monitor_loopback"
    else:
        transport = "unknown"

    ok = receipt.get("ok") is True and receipt.get("live") is True and receipt.get("mocked") is False
    ingress_proven = ok and (
        bool(transcript.strip())
        or "captured_loopback_audio_feeds_realtimestt_automatic_vad" in proves
        or "browser_getusermedia_audio_can_feed_realtimestt_external_audio_listener" in proves
    )
    source_identity_proven = bool(
        ingress_proven
        and captured_audio_exists
        and captured_audio_sha256
        and pipewire_identity["capture_kind"]
        and (
            pipewire_identity["pulse_source"]
            or pipewire_identity["record_target"]
            or "browser_getusermedia_audio_can_feed_realtimestt_external_audio_listener" in proves
        )
    )

    return {
        "path": str(path),
        "exists": path.exists(),
        "ok": receipt.get("ok"),
        "live": receipt.get("live"),
        "mocked": receipt.get("mocked"),
        "transport": transport,
        "proof_scope": receipt.get("proof_scope"),
        "ingress_proven": ingress_proven,
        "transcript_present": bool(transcript.strip()),
        "transcript": transcript,
        "asr_executor_call_count": len(asr_executor_calls) if isinstance(asr_executor_calls, list) else 0,
        "captured_audio_exists": captured_audio_exists,
        "captured_audio_rms": captured_rms,
        "captured_audio_path": captured_audio_path,
        "captured_audio_sha256": captured_audio_sha256,
        "play_audio_sha256": play_audio_sha256,
        "source_identity_proven": source_identity_proven,
        "pipewire_identity": pipewire_identity,
        "failed_gates": receipt.get("failed_gates") or [],
        "claims_proves": proves,
        "claims_does_not_prove": claims.get("does_not_prove") or [],
    }


def factory_matrix_summary(matrix: dict[str, Any]) -> dict[str, Any]:
    sessions = [session for session in matrix["sessions"] if session["folder_id"] == "factory_noise"]
    status_counts = Counter(session["status"] for session in sessions)
    gate_counts = Counter(gate for session in sessions for gate in session.get("failed_gates", []))
    by_difficulty: dict[str, dict[str, int]] = {}
    for session in sessions:
        counts = by_difficulty.setdefault(session["difficulty"], {"passed": 0, "failed": 0, "not_run": 0})
        counts[session["status"]] += 1
    return {
        "session_count": len(sessions),
        "status_counts": {status: status_counts.get(status, 0) for status in ["passed", "failed", "not_run"]},
        "by_difficulty": by_difficulty,
        "failed_gate_counts": dict(sorted(gate_counts.items())),
        "failed_sessions": [
            {
                "id": session["id"],
                "difficulty": session["difficulty"],
                "latest_receipt": session.get("latest_receipt"),
                "failed_gates": session.get("failed_gates") or [],
                "observed": session.get("observed"),
            }
            for session in sessions
            if session["status"] == "failed"
        ],
    }


def browser_device_ingress_summary(browser_candidates: list[dict[str, Any]]) -> dict[str, Any]:
    failures = [candidate for candidate in browser_candidates if not candidate["ingress_proven"]]
    successes = [candidate for candidate in browser_candidates if candidate["ingress_proven"]]
    failed_gate_counts = Counter(
        gate
        for candidate in failures
        for gate in candidate.get("failed_gates", [])
    )
    return {
        "boundary": "browser_getusermedia_device_to_realtimestt",
        "ready": bool(browser_candidates) and not failures,
        "candidate_count": len(browser_candidates),
        "passing_candidate_count": len(successes),
        "failed_candidate_count": len(failures),
        "failed_gate_counts": dict(sorted(failed_gate_counts.items())),
        "sample_failures": [
            {
                "path": candidate["path"],
                "failed_gates": candidate.get("failed_gates") or [],
                "transcript_present": candidate["transcript_present"],
                "captured_audio_rms": candidate["captured_audio_rms"],
                "claims_does_not_prove": candidate.get("claims_does_not_prove") or [],
            }
            for candidate in failures[:4]
        ],
        "blocking_summary": (
            "browser getUserMedia ingress is device-sensitive: at least one browser capture "
            "receipt failed while another browser capture receipt passed"
        )
        if failures and successes
        else None,
    }


def factory_gate_blocker_summary(factory: dict[str, Any]) -> dict[str, Any]:
    failed_sessions = factory["failed_sessions"]
    receipt_paths = sorted(
        {
            str(session.get("latest_receipt"))
            for session in failed_sessions
            if session.get("latest_receipt")
        }
    )
    return {
        "boundary": "factory_noise_audio_capture_to_realtimestt_rung7",
        "ready": not failed_sessions,
        "failed_session_count": len(failed_sessions),
        "failed_gate_counts": factory["failed_gate_counts"],
        "latest_receipt_paths": receipt_paths,
        "sample_failures": failed_sessions[:6],
        "blocking_summary": (
            "factory/noisy ingress scenarios still fail at capture, ASR transcript, rung7, "
            "speaker resolution, memory recall, or unimplemented runner-route gates"
        )
        if failed_sessions
        else None,
    }


def source_identity_summary(current_factory_loopback_candidates: list[dict[str, Any]]) -> dict[str, Any]:
    missing_identity = [
        candidate
        for candidate in current_factory_loopback_candidates
        if not candidate["source_identity_proven"]
    ]
    return {
        "boundary": "captured_audio_source_identity",
        "ready": bool(current_factory_loopback_candidates) and not missing_identity,
        "candidate_count": len(current_factory_loopback_candidates),
        "source_identity_candidate_count": len(current_factory_loopback_candidates) - len(missing_identity),
        "missing_identity_count": len(missing_identity),
        "sample_missing_identity": [
            {
                "path": candidate["path"],
                "captured_audio_path": candidate["captured_audio_path"],
                "captured_audio_sha256": candidate["captured_audio_sha256"],
                "pipewire_identity": candidate["pipewire_identity"],
            }
            for candidate in missing_identity[:4]
        ],
        "blocking_summary": (
            "at least one current loopback ingress proof lacks replayable captured-audio source identity"
        )
        if missing_identity
        else None,
    }


def is_current_factory_loopback_candidate(candidate: dict[str, Any]) -> bool:
    path = candidate["path"]
    return bool(
        candidate["transport"] == "pipewire_monitor_loopback"
        and "/voice-chat-e2e/" in path
        and "/S06-factory-noise/" in path
    )


def build_audit(matrix: dict[str, Any], proof_paths: list[Path]) -> dict[str, Any]:
    candidates = [classify_proof(path, read_json(path)) for path in proof_paths if path.exists()]
    factory = factory_matrix_summary(matrix)
    passing_candidates = [candidate for candidate in candidates if candidate["ingress_proven"]]
    current_factory_loopback_candidates = [
        candidate
        for candidate in passing_candidates
        if is_current_factory_loopback_candidate(candidate)
    ]
    current_source_identity_candidates = [
        candidate
        for candidate in current_factory_loopback_candidates
        if candidate["source_identity_proven"]
    ]
    browser_candidates = [candidate for candidate in candidates if candidate["transport"] == "browser_getusermedia"]
    browser_failures = [candidate for candidate in browser_candidates if not candidate["ingress_proven"]]
    browser_device_ingress = browser_device_ingress_summary(browser_candidates)
    factory_gate_blockers = factory_gate_blocker_summary(factory)
    source_identity = source_identity_summary(current_factory_loopback_candidates)

    failed_gates: list[str] = []
    if not passing_candidates:
        failed_gates.append("historical_ingress_proof_slice_present")
    if factory["status_counts"]["failed"]:
        failed_gates.append("current_factory_matrix_has_failures")
    if factory["status_counts"]["passed"] == 0 and not current_factory_loopback_candidates:
        failed_gates.append("current_factory_matrix_has_no_passes")
    if browser_failures and any(candidate["ingress_proven"] for candidate in browser_candidates):
        failed_gates.append("browser_device_ingress_inconsistent")
    for gate in factory["failed_gate_counts"]:
        failed_gates.append(f"factory_gate:{gate}")

    return {
        "schema": "chatterbox.embry_realtimestt_ingress_evidence_audit.v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mocked": False,
        "live": bool(passing_candidates),
        "ok": not failed_gates,
        "status": "passed" if not failed_gates else "failed",
        "historical_candidate_count": len(candidates),
        "historical_passing_candidate_count": len(passing_candidates),
        "current_factory_loopback_passing_candidate_count": len(current_factory_loopback_candidates),
        "current_source_identity_candidate_count": len(current_source_identity_candidates),
        "current_factory_loopback_passing_candidates": current_factory_loopback_candidates,
        "current_source_identity_candidates": current_source_identity_candidates,
        "browser_device_ingress": browser_device_ingress,
        "factory_gate_blockers": factory_gate_blockers,
        "source_identity_evidence": source_identity,
        "historical_candidates": candidates,
        "current_factory_matrix": factory,
        "failed_gates": sorted(set(failed_gates)),
        "claims": {
            "proves": [
                "historical_and_current_realtimestt_ingress_evidence_are_all_passing",
            ]
            if not failed_gates
            else [
                "current_factory_loopback_pipewire_monitor_realtimestt_slice_passes",
            ]
            if current_factory_loopback_candidates
            else [],
            "does_not_prove": [
                "speaker identity correctness",
                "memory/Tau answerability",
                "Chatterbox output quality",
                "Chat UX synchronization",
            ],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--proof", action="append", type=Path, default=[])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    matrix = read_json(args.matrix)
    audit = build_audit(matrix, [*DEFAULT_PROOFS, *args.proof])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n")
    print(args.out)
    return 0 if audit["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
