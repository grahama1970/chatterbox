#!/usr/bin/env python3
"""Audit whether Embry interruption evidence proves live barge-in behavior."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_PROOFS = [
    Path("/tmp/chatterbox-fork-agent-out/stream-cancel-20260702T1150/stream-cancel.json"),
    Path("/tmp/chatterbox-fork-agent-out/overlap-turn-control-20260703T192737Z-live/overlap-turn-control.json"),
    Path("/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260708T013317Z-matrix-interruption-simple/receipt.json"),
]
DEFAULT_OUT = Path("docs/EMBRY_INTERRUPTION_EVIDENCE_AUDIT.json")

REQUIRED_BARGE_IN_FIELDS = [
    "turn_id",
    "old_turn_id",
    "new_turn_id",
    "embry_playback.audio_artifact_id",
    "embry_playback.started_at_epoch_ms",
    "embry_playback.offset_ms_at_interrupt",
    "listener_interruption.detected",
    "listener_interruption.speaker_id",
    "listener_interruption.primary_speaker_match",
    "turn_control.cancelled",
    "turn_control.stopped",
    "turn_control.stale_chunks_should_skip",
    "stale_audio.old_turn_bytes_after_cancel",
    "new_turn.wins",
    "new_turn.response_started",
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


def is_missing(value: Any) -> bool:
    return value is None or value == "" or value is False or value == []


def normalize_known_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    """Lift known legacy smoke fields into the stricter audit namespace."""

    normalized = dict(receipt)
    if "old_turn_bytes_after_cancel" in receipt:
        normalized.setdefault("stale_audio", {})["old_turn_bytes_after_cancel"] = receipt.get(
            "old_turn_bytes_after_cancel"
        )
    if "turn_id" in receipt:
        normalized.setdefault("turn_id", receipt.get("turn_id"))
        normalized.setdefault("old_turn_id", receipt.get("turn_id"))
    if "new_turn_id" in receipt:
        normalized.setdefault("new_turn_id", receipt.get("new_turn_id"))
    final_control = receipt.get("final_control") or {}
    cancel = receipt.get("cancel") or {}
    control = final_control or (cancel.get("control") or {})
    if control:
        normalized.setdefault("turn_control", {})
        for key in ["cancelled", "stopped", "stale_chunks_should_skip", "ducked"]:
            if key in control:
                normalized["turn_control"][key] = control.get(key)
    return normalized


def audit_candidate(path: Path, receipt: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_known_receipt(receipt)
    missing_fields = [
        field for field in REQUIRED_BARGE_IN_FIELDS if is_missing(nested_get(normalized, field))
    ]

    old_turn_bytes = nested_get(normalized, "stale_audio.old_turn_bytes_after_cancel")
    if old_turn_bytes not in {None, 0}:
        missing_fields.append("stale_audio.old_turn_bytes_after_cancel_zero")

    primary_speaker = nested_get(normalized, "listener_interruption.speaker_id")
    if primary_speaker not in {None, "horus_lupercal"}:
        missing_fields.append("listener_interruption_primary_horus")

    return {
        "proof_path": str(path),
        "ok": not missing_fields,
        "proof_scope": receipt.get("proof_scope"),
        "missing_fields": sorted(set(missing_fields)),
        "observed": {
            "ok": receipt.get("ok"),
            "live": receipt.get("live"),
            "mocked": receipt.get("mocked"),
            "turn_id": nested_get(normalized, "turn_id"),
            "old_turn_id": nested_get(normalized, "old_turn_id"),
            "new_turn_id": nested_get(normalized, "new_turn_id"),
            "old_turn_bytes_after_cancel": old_turn_bytes,
            "listener_detected": nested_get(normalized, "listener_interruption.detected"),
            "listener_speaker_id": primary_speaker,
            "primary_speaker_match": nested_get(normalized, "listener_interruption.primary_speaker_match"),
            "playback_offset_ms_at_interrupt": nested_get(
                normalized, "embry_playback.offset_ms_at_interrupt"
            ),
            "new_turn_wins": nested_get(normalized, "new_turn.wins"),
            "action_order": receipt.get("action_order"),
            "failed_gates": receipt.get("failed_gates"),
        },
    }


def build_audit(proof_paths: list[Path]) -> dict[str, Any]:
    existing_paths = [path for path in proof_paths if path.exists()]
    candidates = [audit_candidate(path, read_json(path)) for path in existing_paths]
    failed_gates: list[str] = []
    if not existing_paths:
        failed_gates.append("interruption_proof_artifact_present")
    if not any(candidate["ok"] for candidate in candidates):
        failed_gates.append("live_barge_in_receipt_present")
    for candidate in candidates:
        for field in candidate["missing_fields"]:
            failed_gates.append(f"missing:{field}")

    return {
        "schema": "chatterbox.embry_interruption_evidence_audit.v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mocked": False,
        "live": False,
        "ok": not failed_gates,
        "status": "passed" if not failed_gates else "failed",
        "proof_count": len(existing_paths),
        "candidate_count": len(candidates),
        "passing_candidate_count": sum(1 for candidate in candidates if candidate["ok"]),
        "required_barge_in_fields": REQUIRED_BARGE_IN_FIELDS,
        "candidates": candidates,
        "failed_gates": sorted(set(failed_gates)),
        "claims": {
            "proves": [
                "at_least_one_receipt_proves_primary_speaker_barge_in_stops_old_audio_and_new_turn_wins",
            ]
            if not failed_gates
            else [],
            "does_not_prove": [
                "RealtimeSTT transcription quality",
                "speaker diarization quality",
                "subjective interruption feel",
            ],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proof", action="append", type=Path, default=[])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    audit = build_audit([*DEFAULT_PROOFS, *args.proof])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n")
    print(args.out)
    return 0 if audit["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
