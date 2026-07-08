#!/usr/bin/env python3
"""Audit current Chatterbox speech, tone, and interruption evidence."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_MATRIX = Path("docs/EMBRY_STRESS_SESSION_MATRIX.json")
DEFAULT_OUT = Path("docs/EMBRY_CHATTERBOX_SPEECH_EVIDENCE_AUDIT.json")
DEFAULT_INTERRUPTION_AUDIT = Path("docs/EMBRY_INTERRUPTION_EVIDENCE_AUDIT.json")
DEFAULT_SPEAKER_IDENTITY_AUDIT = Path("docs/EMBRY_SPEAKER_IDENTITY_EVIDENCE_AUDIT.json")
DEFAULT_MEMORY_TAU_AUDIT = Path("docs/EMBRY_MEMORY_TAU_ROUTING_EVIDENCE_AUDIT.json")
DEFAULT_PROOFS = [
    Path("/tmp/chatterbox-fork-agent-out/interruption-current/20260708T063142Z-rung4-live-nonprimary-suppressed/rung4-nonprimary-suppressed.json"),
    Path("/tmp/chatterbox-fork-agent-out/full-live-sanity-20260702T140317Z-creation-hook/listener-memory-tau-qra/tau-voice-render.json"),
    Path("/tmp/chatterbox-fork-agent-out/full-live-sanity-20260702T140317Z-creation-hook/listener-memory-tau-qra/listener-memory-tau-qra.json"),
    Path("/tmp/chatterbox-fork-agent-out/tau-voice-render-current/20260708T035831Z-voice-delivery-full-chunks-after-patch/tau-voice-render-full-delivery.json"),
    Path("/tmp/chatterbox-fork-agent-out/tau-voice-render-current/20260708T035428Z-voice-delivery-full-after-patch/tau-voice-render-full-delivery.json"),
    Path("/tmp/chatterbox-fork-agent-out/voice-chat-e2e/20260708T035021Z-qra-disabled-current/S10-qra-disabled/tau-qra-disabled.json"),
    Path("/tmp/chatterbox-fork-agent-out/tau-voice-render-20260702T134405Z.json"),
    Path("/tmp/chatterbox-fork-agent-out/full-live-sanity-20260702T140317Z-creation-hook/listener-memory-tau-qra/qra-creation-audio-hook.json"),
    Path("/tmp/chatterbox-fork-agent-out/full-live-sanity-20260702T140317Z-creation-hook/listener-memory-tau-qra/bless-qra-audio-variants.json"),
    Path("/tmp/chatterbox-fork-agent-out/voice-chat-e2e/personality-audition-20260703T223052Z-scripted/personality-audition.json"),
]

SPEECH_FOLDERS = {"tone_emotion", "interruption"}
INTERRUPTION_AUDIT_COVERED_GATES = {
    "interruption_detected_receipt_not_emitted",
    "new_horus_turn_not_exercised",
    "new_turn_wins_receipt_not_emitted",
    "speaker_gate_receipt_not_linked_to_turn_control",
    "stale_audio_stream_bytes_not_measured",
}
REQUIRED_VOICE_DELIVERY_FIELDS = {
    "tone",
    "delivery_stage",
    "pace",
    "pause_strategy",
    "source",
}


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"error_type": type(exc).__name__, "error": str(exc), "path": str(path)}


def _nested_get(payload: dict[str, Any], dotted: str) -> Any:
    value: Any = payload
    for part in dotted.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def _status_counts(sessions: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(session["status"] for session in sessions)
    return {status: counts.get(status, 0) for status in ["passed", "failed", "not_run"]}


def _gate_counts(sessions: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(gate for session in sessions for gate in session.get("failed_gates", []))
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _sample_failures(sessions: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    failures = []
    for session in sessions:
        if session["status"] != "failed":
            continue
        failures.append(
            {
                "id": session["id"],
                "folder_id": session["folder_id"],
                "difficulty": session["difficulty"],
                "latest_receipt": session.get("latest_receipt"),
                "failed_gates": session.get("failed_gates") or [],
                "observed": session.get("observed"),
            }
        )
        if len(failures) >= limit:
            break
    return failures


def _group_summary(matrix: dict[str, Any], folders: set[str]) -> dict[str, Any]:
    sessions = [session for session in matrix["sessions"] if session["folder_id"] in folders]
    by_folder: dict[str, dict[str, Any]] = {}
    for folder in sorted(folders):
        folder_sessions = [session for session in sessions if session["folder_id"] == folder]
        by_folder[folder] = {
            "session_count": len(folder_sessions),
            "status_counts": _status_counts(folder_sessions),
            "failed_gate_counts": _gate_counts(folder_sessions),
            "sample_failures": _sample_failures(folder_sessions, limit=4),
        }
    return {
        "session_count": len(sessions),
        "status_counts": _status_counts(sessions),
        "failed_gate_counts": _gate_counts(sessions),
        "by_folder": by_folder,
        "sample_failures": _sample_failures(sessions),
    }


def _voice_delivery_missing_fields(voice_delivery: dict[str, Any] | None) -> list[str]:
    if not isinstance(voice_delivery, dict):
        return sorted(REQUIRED_VOICE_DELIVERY_FIELDS)
    return sorted(field for field in REQUIRED_VOICE_DELIVERY_FIELDS if voice_delivery.get(field) in (None, "", []))


def _render_audio_ok(receipt: dict[str, Any]) -> bool:
    metrics = _nested_get(receipt, "artifacts.finished_response_audio_metrics")
    if not isinstance(metrics, dict):
        metrics = _nested_get(receipt, "response.finished_response_metrics")
    return bool(
        receipt.get("ok") is True
        and receipt.get("live") is True
        and receipt.get("mocked") is False
        and isinstance(metrics, dict)
        and metrics.get("exists") is True
        and metrics.get("bytes", 0) > 0
        and metrics.get("duration_seconds", 0) > 0
    )


def classify_proof(path: Path, receipt: dict[str, Any]) -> dict[str, Any]:
    schema = str(receipt.get("schema") or "")
    if schema == "chatterbox.tau_voice_render_smoke.v1":
        proof_type = "tau_voice_render"
    elif schema == "chatterbox.qra_creation_audio_hook.v1":
        proof_type = "qra_creation_audio_hook"
    elif schema == "chatterbox.embry_personality_audition.v1":
        proof_type = "personality_audition"
    elif receipt.get("variant_count") is not None and receipt.get("qra_id"):
        proof_type = "blessed_qra_variant_generation"
    elif schema == "chatterbox.conversation_ladder.rung4.v1":
        proof_type = "conversation_ladder_rung4"
    else:
        proof_type = "unknown"

    variants = receipt.get("variants") or []
    played_variants = [
        variant
        for variant in variants
        if isinstance(variant, dict)
        and _nested_get(variant, "play.returncode") == 0
        and _nested_get(variant, "render.returncode") == 0
    ]

    qra_variants_ok = bool(
        receipt.get("ok") is True
        and receipt.get("live") is True
        and receipt.get("mocked") is False
        and (receipt.get("variant_count") or _nested_get(receipt, "child_receipt.variant_count") or 0) >= 5
    )
    qra_disabled_normal_render_ok = bool(
        receipt.get("ok") is True
        and receipt.get("live") is True
        and receipt.get("mocked") is False
        and _nested_get(receipt, "request.use_blessed_qra_cache") is False
        and _nested_get(receipt, "response.blessed_qra_cache.enabled") is False
        and _nested_get(receipt, "response.blessed_qra_cache.hit") is False
        and _render_audio_ok(receipt)
    )
    blessed_qra_cached_response_ok = bool(
        receipt.get("ok") is True
        and receipt.get("live") is True
        and receipt.get("mocked") is False
        and (
            (
                _nested_get(receipt, "request.use_blessed_qra_cache") is True
                and _nested_get(receipt, "response.blessed_qra_cache.hit") is True
                and _nested_get(receipt, "response.blessed_qra_cache.memory_gate.passed") is True
                and _render_audio_ok(receipt)
            )
            or (
                schema == "chatterbox.listener_memory_tau_qra_smoke.v1"
                and _nested_get(receipt, "tau_voice_render.cache_hit") is True
                and _nested_get(receipt, "tau_voice_render.memory_gate_passed") is True
                and isinstance(_nested_get(receipt, "tau_voice_render.finished_audio_metrics"), dict)
                and _nested_get(receipt, "tau_voice_render.finished_audio_metrics.exists") is True
                and _nested_get(receipt, "tau_voice_render.finished_audio_metrics.bytes") > 0
            )
        )
    )
    non_primary_interrupt_rejection_ok = bool(
        schema == "chatterbox.conversation_ladder.rung4.v1"
        and receipt.get("ok") is True
        and receipt.get("live") is True
        and receipt.get("mocked") is False
        and _nested_get(receipt, "speaker_gate.enabled") is True
        and _nested_get(receipt, "speaker_gate.expected_primary_speaker") is False
        and _nested_get(receipt, "speaker_gate.suppressed") is True
        and _nested_get(receipt, "listener_interruption.speech_detected") is True
        and _nested_get(receipt, "listener_interruption.detected") is False
        and receipt.get("interruption") is None
        and receipt.get("turn_controls") is None
    )

    missing_delivery_fields: list[str] = []
    missing_chunk_delivery_fields: list[list[str]] = []
    if proof_type == "tau_voice_render":
        voice_delivery = _nested_get(receipt, "response.voice_delivery")
        chunks = _nested_get(receipt, "response.chunks") or []
        chunk_voice_delivery = [chunk.get("voice_delivery") for chunk in chunks if isinstance(chunk, dict)]
        missing_delivery_fields = _voice_delivery_missing_fields(voice_delivery)
        missing_chunk_delivery_fields = [
            _voice_delivery_missing_fields(item)
            for item in chunk_voice_delivery
            if _voice_delivery_missing_fields(item)
        ]

    return {
        "path": str(path),
        "exists": path.exists(),
        "schema": receipt.get("schema"),
        "proof_type": proof_type,
        "ok": receipt.get("ok"),
        "live": receipt.get("live"),
        "mocked": receipt.get("mocked"),
        "render_audio_ok": _render_audio_ok(receipt),
        "qra_variants_ok": qra_variants_ok,
        "qra_disabled_normal_render_ok": qra_disabled_normal_render_ok,
        "blessed_qra_cached_response_ok": blessed_qra_cached_response_ok,
        "non_primary_interrupt_rejection_ok": non_primary_interrupt_rejection_ok,
        "variant_count": receipt.get("variant_count") or _nested_get(receipt, "child_receipt.variant_count") or len(variants),
        "played_variant_count": len(played_variants),
        "voice_delivery_missing_fields": missing_delivery_fields,
        "chunk_voice_delivery_missing_fields": missing_chunk_delivery_fields,
        "failed_gates": receipt.get("failed_gates") or [],
        "claims_proves": (receipt.get("claims") or {}).get("proves") or [],
        "claims_does_not_prove": (receipt.get("claims") or {}).get("does_not_prove") or [],
    }


def _interruption_audit_summary(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"path": None, "exists": False, "ok": False, "covered_gates": []}
    receipt = read_json(path)
    ok = bool(
        path.exists()
        and receipt.get("ok") is True
        and receipt.get("live") is True
        and receipt.get("mocked") is False
        and receipt.get("passing_candidate_count", 0) > 0
    )
    return {
        "path": str(path),
        "exists": path.exists(),
        "ok": ok,
        "status": receipt.get("status"),
        "live": receipt.get("live"),
        "mocked": receipt.get("mocked"),
        "passing_candidate_count": receipt.get("passing_candidate_count"),
        "best_candidate_paths": receipt.get("best_candidate_paths") or [],
        "covered_gates": sorted(INTERRUPTION_AUDIT_COVERED_GATES) if ok else [],
    }


def _speaker_identity_audit_summary(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"path": None, "exists": False, "overlap_one_at_a_time_ok": False, "covered_gates": []}
    receipt = read_json(path)
    proves = set((receipt.get("claims") or {}).get("proves") or [])
    overlap_one_at_a_time_ok = bool(
        path.exists()
        and receipt.get("live") is True
        and receipt.get("mocked") is False
        and "pyannote_overlap_detection_routes_to_one_at_a_time_turn_control" in proves
    )
    return {
        "path": str(path),
        "exists": path.exists(),
        "ok": receipt.get("ok"),
        "status": receipt.get("status"),
        "live": receipt.get("live"),
        "mocked": receipt.get("mocked"),
        "overlap_one_at_a_time_ok": overlap_one_at_a_time_ok,
        "covered_gates": ["voice_delivery_tone_expected_firm_boundary_or_one_at_a_time_interrupt"]
        if overlap_one_at_a_time_ok
        else [],
    }


def _memory_tau_audit_summary(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"path": None, "exists": False, "ok": False, "tau_tool_wait_boundary_ready": False}
    receipt = read_json(path)
    failed_gates = receipt.get("failed_gates") or []
    tau_tool_blocking_gates = [
        gate
        for gate in failed_gates
        if gate
        in {
            "skill_call_receipt_missing",
            "skill_tau_agent_handoff_missing",
            "tau_dag_receipt_missing",
            "tau_skill_gate:skill_call_receipt_not_emitted",
            "tau_skill_gate:tau_agent_handoff_not_exercised",
            "tau_skill_gate:tau_dag_receipt_not_created",
            "tau_skill_routing_matrix_has_failures",
        }
    ]
    tau_tool_wait_boundary_ready = bool(
        path.exists()
        and receipt.get("ok") is True
        and receipt.get("live") is True
        and receipt.get("mocked") is False
        and not tau_tool_blocking_gates
    )
    return {
        "path": str(path),
        "exists": path.exists(),
        "ok": receipt.get("ok"),
        "status": receipt.get("status"),
        "live": receipt.get("live"),
        "mocked": receipt.get("mocked"),
        "tau_tool_wait_boundary_ready": tau_tool_wait_boundary_ready,
        "blocking_gates": sorted(tau_tool_blocking_gates),
    }


def _memory_intent_tone_summary(matrix: dict[str, Any], speech_matrix: dict[str, Any]) -> dict[str, Any]:
    tone_failures = [
        failure
        for failure in speech_matrix["by_folder"]["tone_emotion"]["sample_failures"]
        if any(str(gate).startswith("voice_delivery_tone_expected_") for gate in failure.get("failed_gates", []))
    ]
    all_tone_failures = [
        session
        for session in matrix["sessions"]
        if session.get("folder_id") == "tone_emotion"
        and any(str(gate).startswith("voice_delivery_tone_expected_") for gate in session.get("failed_gates", []))
    ]
    failed_gate_counts = {
        gate: count
        for gate, count in speech_matrix["by_folder"]["tone_emotion"]["failed_gate_counts"].items()
        if gate.startswith("voice_delivery_tone_expected_")
    }
    receipt_paths = sorted(
        {
            str(failure.get("latest_receipt"))
            for failure in all_tone_failures
            if failure.get("latest_receipt")
        }
    )
    return {
        "boundary": "memory.intent.voice_delivery",
        "ready": not failed_gate_counts,
        "failed_session_count": len(all_tone_failures),
        "failed_gate_counts": failed_gate_counts,
        "sample_failures": tone_failures,
        "latest_receipt_paths": receipt_paths,
        "blocking_summary": (
            "memory /intent voice_delivery tone routing is still returning an unacceptable tone "
            "for one or more hostile, discouraged, or overlap prompts"
        )
        if failed_gate_counts
        else None,
    }


def build_audit(
    matrix: dict[str, Any],
    proof_paths: list[Path],
    *,
    interruption_audit_path: Path | None = None,
    speaker_identity_audit_path: Path | None = None,
    memory_tau_audit_path: Path | None = None,
) -> dict[str, Any]:
    speech_matrix = _group_summary(matrix, SPEECH_FOLDERS)
    interruption_audit = _interruption_audit_summary(interruption_audit_path)
    speaker_identity_audit = _speaker_identity_audit_summary(speaker_identity_audit_path)
    memory_tau_audit = _memory_tau_audit_summary(memory_tau_audit_path)
    memory_intent_tone = _memory_intent_tone_summary(matrix, speech_matrix)
    interruption_covered_gates = set(interruption_audit["covered_gates"])
    tone_covered_gates = set(speaker_identity_audit["covered_gates"])
    proof_candidates = [classify_proof(path, read_json(path)) for path in proof_paths if path.exists()]
    live_renders = [candidate for candidate in proof_candidates if candidate["render_audio_ok"]]
    qra_variants = [candidate for candidate in proof_candidates if candidate["qra_variants_ok"]]
    qra_disabled = [candidate for candidate in proof_candidates if candidate["qra_disabled_normal_render_ok"]]
    qra_cached = [candidate for candidate in proof_candidates if candidate["blessed_qra_cached_response_ok"]]
    non_primary_interrupt_rejections = [
        candidate for candidate in proof_candidates if candidate["non_primary_interrupt_rejection_ok"]
    ]
    personality = [
        candidate
        for candidate in proof_candidates
        if candidate["proof_type"] == "personality_audition" and candidate["played_variant_count"] >= 5
    ]
    incomplete_delivery = [
        candidate
        for candidate in proof_candidates
        if candidate["voice_delivery_missing_fields"] or candidate["chunk_voice_delivery_missing_fields"]
    ]
    complete_delivery = [
        candidate
        for candidate in live_renders
        if not candidate["voice_delivery_missing_fields"] and not candidate["chunk_voice_delivery_missing_fields"]
    ]

    failed_gates: list[str] = []
    if not live_renders:
        failed_gates.append("live_chatterbox_render_receipt_missing")
    if not qra_variants:
        failed_gates.append("blessed_qra_five_variant_generation_missing")
    if not personality:
        failed_gates.append("audible_personality_audition_missing")
    if not complete_delivery:
        failed_gates.append("delivery_envelope_incomplete")
    dynamic_covered_gates = set(interruption_covered_gates)
    if non_primary_interrupt_rejections:
        dynamic_covered_gates.add("non_primary_interrupt_rejection_not_exercised")
    if qra_cached:
        dynamic_covered_gates.add("blessed_qra_cached_response_not_exercised")
    effective_interruption_failed_gates = {
        gate
        for gate in speech_matrix["by_folder"]["interruption"]["failed_gate_counts"]
        if gate not in dynamic_covered_gates
    }
    if speech_matrix["by_folder"]["tone_emotion"]["status_counts"]["failed"]:
        tone_remaining_gates = {
            gate
            for gate in speech_matrix["by_folder"]["tone_emotion"]["failed_gate_counts"]
            if gate not in tone_covered_gates
        }
        if tone_remaining_gates:
            failed_gates.append("tone_emotion_matrix_has_failures")
    if effective_interruption_failed_gates:
        failed_gates.append("interruption_matrix_has_failures")
    for gate in sorted(speech_matrix["failed_gate_counts"]):
        if gate in dynamic_covered_gates or gate in tone_covered_gates:
            continue
        failed_gates.append(f"speech_matrix_gate:{gate}")

    ok = not failed_gates
    live_evidence_present = any(
        candidate["live"] is True and candidate["mocked"] is False
        for candidate in proof_candidates
    )
    partial_proves = []
    if live_renders:
        partial_proves.append("live_chatterbox_can_render_audio")
    if qra_variants:
        partial_proves.append("approved_qra_can_generate_five_embry_audio_variants")
    if qra_disabled:
        partial_proves.append("qra_disabled_requests_render_normal_chatterbox_audio_without_cache_hit")
    if qra_cached:
        partial_proves.append("blessed_qra_cached_response_can_render_preapproved_audio")
    if personality:
        partial_proves.append("personality_audition_variants_can_render_and_play")
    if complete_delivery:
        partial_proves.append("complete_voice_delivery_envelope_can_reach_chatterbox_chunks")
    if interruption_audit["ok"]:
        partial_proves.append("live_primary_speaker_interruption_barge_in_receipt_present")
    if non_primary_interrupt_rejections:
        partial_proves.append("live_non_primary_interrupt_audio_is_suppressed_before_turn_control")
    if speaker_identity_audit["overlap_one_at_a_time_ok"]:
        partial_proves.append("pyannote_overlap_routes_to_one_at_a_time_voice_delivery")
    does_not_prove = [
        "RealtimeSTT audio ingress",
        "general speaker identity outside the linked interruption receipt",
        "memory/Tau answer correctness",
        "Chat UX synchronization",
        "orb synchronization",
        "event-sourced replay",
    ]
    if not interruption_audit["ok"]:
        does_not_prove.append("live primary-speaker barge-in interruption")
    return {
        "schema": "chatterbox.embry_chatterbox_speech_evidence_audit.v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mocked": False,
        "live": live_evidence_present,
        "ok": ok,
        "status": "passed" if ok else "failed",
        "speech_matrix": speech_matrix,
        "proof_candidate_count": len(proof_candidates),
        "interruption_evidence_audit": interruption_audit,
        "interruption_matrix_remaining_failed_gates": sorted(effective_interruption_failed_gates),
        "speaker_identity_evidence_audit": speaker_identity_audit,
        "memory_tau_routing_evidence_audit": memory_tau_audit,
        "memory_intent_tone_evidence": memory_intent_tone,
        "tone_emotion_matrix_remaining_failed_gates": sorted(
            gate
            for gate in speech_matrix["by_folder"]["tone_emotion"]["failed_gate_counts"]
            if gate not in tone_covered_gates
        ),
        "live_render_candidate_count": len(live_renders),
        "qra_variant_candidate_count": len(qra_variants),
        "qra_disabled_normal_render_candidate_count": len(qra_disabled),
        "blessed_qra_cached_response_candidate_count": len(qra_cached),
        "non_primary_interrupt_rejection_candidate_count": len(non_primary_interrupt_rejections),
        "audible_personality_candidate_count": len(personality),
        "incomplete_delivery_envelope_count": len(incomplete_delivery),
        "complete_delivery_envelope_candidate_count": len(complete_delivery),
        "proof_candidates": proof_candidates,
        "failed_gates": sorted(set(failed_gates)),
        "claims": {
            "proves": [
                "chatterbox_live_render_qra_variants_personality_tone_and_interruption_are_all_passing",
            ]
            if ok
            else partial_proves,
            "does_not_prove": does_not_prove,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--proof", action="append", type=Path, default=[])
    parser.add_argument("--interruption-audit", type=Path, default=DEFAULT_INTERRUPTION_AUDIT)
    parser.add_argument("--speaker-identity-audit", type=Path, default=DEFAULT_SPEAKER_IDENTITY_AUDIT)
    parser.add_argument("--memory-tau-audit", type=Path, default=DEFAULT_MEMORY_TAU_AUDIT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    matrix = read_json(args.matrix)
    audit = build_audit(
        matrix,
        [*DEFAULT_PROOFS, *args.proof],
        interruption_audit_path=args.interruption_audit,
        speaker_identity_audit_path=args.speaker_identity_audit,
        memory_tau_audit_path=args.memory_tau_audit,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n")
    print(args.out)
    return 0 if audit["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
