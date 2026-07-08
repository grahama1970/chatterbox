#!/usr/bin/env python3
"""Audit whether Embry replay is backed by an event-sourced session journal."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_PROOF_PATHS = [
    Path("/tmp/codex-ui-verification/pi-mono/embry-voice-dynamic-replay-hardening/dynamic-replay-proof.json"),
]
DEFAULT_MARKER_GLOB = ".codex/ui-verification/*replay*.latest.json"
DEFAULT_OUT = Path("docs/EMBRY_REPLAY_EVIDENCE_AUDIT.json")

REQUIRED_REPLAY_FIELDS = [
    "session_id",
    "event_journal.path",
    "event_journal.sha256",
    "event_journal.event_count",
    "replay.turn_ids",
    "replay.audio_artifact_ids",
    "replay.original_timing_offsets_ms",
    "replay.rendered_timing_offsets_ms",
    "replay.chat_snapshots_match",
    "replay.audio_offsets_match",
    "replay.turn_order_matches",
]

REQUIRED_EVENT_TYPES = [
    "listener.audio_frame_received",
    "stt.final",
    "speaker_gate.accepted",
    "memory.intent",
    "tau.voice_render_request",
    "chatterbox.audio_artifact",
    "audio.playback_started",
    "chat.turn_rendered",
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
    return value is None or value == "" or value is False or value == 0 or value == []


def load_journal_events(journal_path: str | None) -> list[dict[str, Any]]:
    if not journal_path:
        return []
    path = Path(journal_path)
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            events.append({"type": "invalid_json_line"})
    return events


def proof_path_candidates(marker_glob: str, explicit_paths: list[Path]) -> list[Path]:
    paths = [path for path in explicit_paths if path.exists()]
    for marker_path in sorted(Path().glob(marker_glob)):
        marker = read_json(marker_path)
        read_json_path = marker.get("read_json")
        replay_receipt = marker.get("replay_receipt") or marker.get("receipt")
        for candidate in [read_json_path, replay_receipt]:
            if candidate and Path(str(candidate)).exists():
                paths.append(Path(str(candidate)))
    seen: set[str] = set()
    deduped: list[Path] = []
    for path in paths:
        key = str(path.resolve())
        if key not in seen:
            seen.add(key)
            deduped.append(path)
    return deduped


def audit_candidate(path: Path, receipt: dict[str, Any]) -> dict[str, Any]:
    missing_fields = [
        field
        for field in REQUIRED_REPLAY_FIELDS
        if is_missing(nested_get(receipt, field))
    ]

    journal_path = nested_get(receipt, "event_journal.path")
    events = load_journal_events(journal_path)
    event_types = [str(event.get("type")) for event in events]
    missing_event_types = [event_type for event_type in REQUIRED_EVENT_TYPES if event_type not in event_types]
    if missing_event_types:
        missing_fields.append("event_journal.required_event_types")

    turn_ids = nested_get(receipt, "replay.turn_ids")
    audio_ids = nested_get(receipt, "replay.audio_artifact_ids")
    original_offsets = nested_get(receipt, "replay.original_timing_offsets_ms")
    rendered_offsets = nested_get(receipt, "replay.rendered_timing_offsets_ms")
    if isinstance(turn_ids, list) and isinstance(audio_ids, list) and len(audio_ids) < len(turn_ids):
        missing_fields.append("replay_audio_artifacts_cover_turns")
    if isinstance(original_offsets, list) and isinstance(rendered_offsets, list) and len(original_offsets) != len(rendered_offsets):
        missing_fields.append("replay_timing_offset_counts_match")

    return {
        "proof_path": str(path),
        "ok": not missing_fields,
        "missing_fields": sorted(set(missing_fields)),
        "observed": {
            "session_id": nested_get(receipt, "session_id"),
            "event_journal_path": journal_path,
            "event_journal_exists": bool(journal_path and Path(str(journal_path)).exists()),
            "event_count": nested_get(receipt, "event_journal.event_count"),
            "loaded_event_count": len(events),
            "event_types": sorted(set(event_types)),
            "missing_event_types": missing_event_types,
            "turn_ids": turn_ids,
            "audio_artifact_ids": audio_ids,
            "original_timing_offsets_ms": original_offsets,
            "rendered_timing_offsets_ms": rendered_offsets,
            "chat_snapshots_match": nested_get(receipt, "replay.chat_snapshots_match"),
            "audio_offsets_match": nested_get(receipt, "replay.audio_offsets_match"),
            "turn_order_matches": nested_get(receipt, "replay.turn_order_matches"),
            "legacy_ui_assertions": receipt.get("assertions"),
            "legacy_audio_count": receipt.get("audioCount"),
            "legacy_screenshot": receipt.get("screenshot"),
        },
    }


def build_audit(proof_paths: list[Path]) -> dict[str, Any]:
    candidates = [audit_candidate(path, read_json(path)) for path in proof_paths]
    failed_gates: list[str] = []
    if not proof_paths:
        failed_gates.append("replay_proof_artifact_present")
    if not any(candidate["ok"] for candidate in candidates):
        failed_gates.append("event_sourced_replay_receipt_present")
    for candidate in candidates:
        for field in candidate["missing_fields"]:
            failed_gates.append(f"missing:{field}")

    return {
        "schema": "chatterbox.embry_replay_evidence_audit.v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mocked": False,
        "live": False,
        "ok": not failed_gates,
        "status": "passed" if not failed_gates else "failed",
        "proof_count": len(proof_paths),
        "candidate_count": len(candidates),
        "passing_candidate_count": sum(1 for candidate in candidates if candidate["ok"]),
        "required_replay_fields": REQUIRED_REPLAY_FIELDS,
        "required_event_types": REQUIRED_EVENT_TYPES,
        "candidates": candidates,
        "failed_gates": sorted(set(failed_gates)),
        "claims": {
            "proves": [
                "at_least_one_replay_receipt_reconstructs_chat_and_audio_from_event_journal",
            ]
            if not failed_gates
            else [],
            "does_not_prove": [
                "RealtimeSTT correctness",
                "speaker identity correctness",
                "Chatterbox synthesis quality",
                "orb synchronization",
            ],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proof", action="append", type=Path, default=[])
    parser.add_argument("--marker-glob", default=DEFAULT_MARKER_GLOB)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    paths = proof_path_candidates(args.marker_glob, [*DEFAULT_PROOF_PATHS, *args.proof])
    audit = build_audit(paths)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n")
    print(args.out)
    return 0 if audit["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
