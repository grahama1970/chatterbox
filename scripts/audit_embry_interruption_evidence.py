#!/usr/bin/env python3
"""Audit whether Embry interruption evidence proves live barge-in behavior."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_PROOFS = [
    Path("/tmp/chatterbox-fork-agent-out/interruption-current/20260708T034752Z-interrupt-current/final-response.json"),
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

REQUIRED_CHATTERBOX_TURN_CONTROL_FIELDS = [
    "old_turn_id",
    "new_turn_id",
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


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except Exception:
        return []


def normalize_known_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    """Lift known legacy smoke fields into the stricter audit namespace."""

    normalized = dict(receipt)
    events_path = receipt.get("events_path")
    events = read_jsonl(Path(events_path)) if isinstance(events_path, str) else []
    if "old_turn_bytes_after_cancel" in receipt:
        normalized.setdefault("stale_audio", {})["old_turn_bytes_after_cancel"] = receipt.get(
            "old_turn_bytes_after_cancel"
        )
    timeline = receipt.get("interruption_timeline") or {}
    if "post_cancel_old_turn_audio_bytes_emitted" in timeline:
        normalized.setdefault("stale_audio", {})["old_turn_bytes_after_cancel"] = timeline.get(
            "post_cancel_old_turn_audio_bytes_emitted"
        )
    if "turn_id" in receipt:
        normalized.setdefault("turn_id", receipt.get("turn_id"))
        normalized.setdefault("old_turn_id", receipt.get("turn_id"))
    if "old_turn_id" in timeline:
        normalized.setdefault("turn_id", timeline.get("old_turn_id"))
        normalized.setdefault("old_turn_id", timeline.get("old_turn_id"))
    if "new_turn_id" in receipt:
        normalized.setdefault("new_turn_id", receipt.get("new_turn_id"))
    if "new_turn_id" in timeline:
        normalized.setdefault("new_turn_id", timeline.get("new_turn_id"))
    if timeline.get("new_turn_audio_started_after_cancel") is True:
        normalized.setdefault("new_turn", {})["wins"] = True
        normalized.setdefault("new_turn", {})["response_started"] = True
    if any(event.get("type") == "playback.stopped" for event in events):
        normalized.setdefault("turn_control", {})["stopped"] = True
    if receipt.get("stale_skipped_count", 0) > 0 or any(
        event.get("type") == "speech.stale_skipped" for event in events
    ):
        normalized.setdefault("turn_control", {})["stale_chunks_should_skip"] = True
    if any(event.get("type") == "interruption.requested" for event in events):
        normalized.setdefault("turn_control", {})["cancelled"] = True
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
    missing_turn_control_fields = [
        field
        for field in REQUIRED_CHATTERBOX_TURN_CONTROL_FIELDS
        if is_missing(nested_get(normalized, field))
    ]

    old_turn_bytes = nested_get(normalized, "stale_audio.old_turn_bytes_after_cancel")
    if old_turn_bytes not in {None, 0}:
        missing_fields.append("stale_audio.old_turn_bytes_after_cancel_zero")
        missing_turn_control_fields.append("stale_audio.old_turn_bytes_after_cancel_zero")

    primary_speaker = nested_get(normalized, "listener_interruption.speaker_id")
    if primary_speaker not in {None, "horus_lupercal"}:
        missing_fields.append("listener_interruption_primary_horus")

    return {
        "proof_path": str(path),
        "ok": not missing_fields,
        "proof_scope": receipt.get("proof_scope"),
        "missing_fields": sorted(set(missing_fields)),
        "missing_field_count": len(set(missing_fields)),
        "chatterbox_turn_control_ok": not missing_turn_control_fields,
        "chatterbox_turn_control_missing_fields": sorted(set(missing_turn_control_fields)),
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
            "turn_control_stopped": nested_get(normalized, "turn_control.stopped"),
            "turn_control_stale_chunks_should_skip": nested_get(
                normalized, "turn_control.stale_chunks_should_skip"
            ),
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
    turn_control_candidates = [
        candidate for candidate in candidates if candidate["chatterbox_turn_control_ok"]
    ]
    passing_candidates = [candidate for candidate in candidates if candidate["ok"]]
    best_candidates = (
        passing_candidates
        if passing_candidates
        else [
            candidate
            for candidate in candidates
            if candidate["missing_field_count"]
            == min(item["missing_field_count"] for item in candidates)
        ]
        if candidates
        else []
    )
    failed_gates: list[str] = []
    if not existing_paths:
        failed_gates.append("interruption_proof_artifact_present")
    if not passing_candidates:
        failed_gates.append("live_barge_in_receipt_present")
    if not turn_control_candidates:
        failed_gates.append("chatterbox_turn_control_interruption_receipt_present")
    for candidate in best_candidates:
        for field in candidate["missing_fields"]:
            failed_gates.append(f"missing:{field}")

    return {
        "schema": "chatterbox.embry_interruption_evidence_audit.v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mocked": False,
        "live": any(
            candidate["observed"]["live"] is True and candidate["observed"]["mocked"] is False
            for candidate in candidates
        ),
        "ok": not failed_gates,
        "status": "passed" if not failed_gates else "failed",
        "proof_count": len(existing_paths),
        "candidate_count": len(candidates),
        "passing_candidate_count": len(passing_candidates),
        "chatterbox_turn_control_candidate_count": len(turn_control_candidates),
        "best_candidate_paths": [candidate["proof_path"] for candidate in best_candidates],
        "required_barge_in_fields": REQUIRED_BARGE_IN_FIELDS,
        "required_chatterbox_turn_control_fields": REQUIRED_CHATTERBOX_TURN_CONTROL_FIELDS,
        "candidates": candidates,
        "failed_gates": sorted(set(failed_gates)),
        "claims": {
            "proves": [
                "at_least_one_receipt_proves_primary_speaker_barge_in_stops_old_audio_and_new_turn_wins",
            ]
            if not failed_gates
            else [
                "chatterbox_turn_control_interruption_stops_old_audio_and_starts_new_turn",
            ]
            if turn_control_candidates
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
