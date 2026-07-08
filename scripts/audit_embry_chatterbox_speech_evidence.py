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
DEFAULT_PROOFS = [
    Path("/tmp/chatterbox-fork-agent-out/voice-chat-e2e/20260708T035021Z-qra-disabled-current/S10-qra-disabled/tau-qra-disabled.json"),
    Path("/tmp/chatterbox-fork-agent-out/tau-voice-render-20260702T134405Z.json"),
    Path("/tmp/chatterbox-fork-agent-out/full-live-sanity-20260702T140317Z-creation-hook/listener-memory-tau-qra/qra-creation-audio-hook.json"),
    Path("/tmp/chatterbox-fork-agent-out/full-live-sanity-20260702T140317Z-creation-hook/listener-memory-tau-qra/bless-qra-audio-variants.json"),
    Path("/tmp/chatterbox-fork-agent-out/voice-chat-e2e/personality-audition-20260703T223052Z-scripted/personality-audition.json"),
]

SPEECH_FOLDERS = {"tone_emotion", "interruption"}
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
        "variant_count": receipt.get("variant_count") or _nested_get(receipt, "child_receipt.variant_count") or len(variants),
        "played_variant_count": len(played_variants),
        "voice_delivery_missing_fields": missing_delivery_fields,
        "chunk_voice_delivery_missing_fields": missing_chunk_delivery_fields,
        "failed_gates": receipt.get("failed_gates") or [],
        "claims_proves": (receipt.get("claims") or {}).get("proves") or [],
        "claims_does_not_prove": (receipt.get("claims") or {}).get("does_not_prove") or [],
    }


def build_audit(matrix: dict[str, Any], proof_paths: list[Path]) -> dict[str, Any]:
    speech_matrix = _group_summary(matrix, SPEECH_FOLDERS)
    proof_candidates = [classify_proof(path, read_json(path)) for path in proof_paths if path.exists()]
    live_renders = [candidate for candidate in proof_candidates if candidate["render_audio_ok"]]
    qra_variants = [candidate for candidate in proof_candidates if candidate["qra_variants_ok"]]
    qra_disabled = [candidate for candidate in proof_candidates if candidate["qra_disabled_normal_render_ok"]]
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

    failed_gates: list[str] = []
    if not live_renders:
        failed_gates.append("live_chatterbox_render_receipt_missing")
    if not qra_variants:
        failed_gates.append("blessed_qra_five_variant_generation_missing")
    if not personality:
        failed_gates.append("audible_personality_audition_missing")
    if incomplete_delivery:
        failed_gates.append("delivery_envelope_incomplete")
    if speech_matrix["by_folder"]["tone_emotion"]["status_counts"]["failed"]:
        failed_gates.append("tone_emotion_matrix_has_failures")
    if speech_matrix["by_folder"]["interruption"]["status_counts"]["failed"]:
        failed_gates.append("interruption_matrix_has_failures")
    for gate in sorted(speech_matrix["failed_gate_counts"]):
        failed_gates.append(f"speech_matrix_gate:{gate}")

    ok = not failed_gates
    return {
        "schema": "chatterbox.embry_chatterbox_speech_evidence_audit.v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mocked": False,
        "live": False,
        "ok": ok,
        "status": "passed" if ok else "failed",
        "speech_matrix": speech_matrix,
        "proof_candidate_count": len(proof_candidates),
        "live_render_candidate_count": len(live_renders),
        "qra_variant_candidate_count": len(qra_variants),
        "qra_disabled_normal_render_candidate_count": len(qra_disabled),
        "audible_personality_candidate_count": len(personality),
        "incomplete_delivery_envelope_count": len(incomplete_delivery),
        "proof_candidates": proof_candidates,
        "failed_gates": sorted(set(failed_gates)),
        "claims": {
            "proves": [
                "chatterbox_live_render_qra_variants_personality_tone_and_interruption_are_all_passing",
            ]
            if ok
            else [
                "live_chatterbox_can_render_audio",
                "approved_qra_can_generate_five_embry_audio_variants",
                "personality_audition_variants_can_render_and_play",
            ],
            "does_not_prove": [
                "RealtimeSTT audio ingress",
                "speaker identity",
                "memory/Tau answer correctness",
                "Chat UX synchronization",
                "orb synchronization",
                "event-sourced replay",
                "live barge-in interruption",
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
