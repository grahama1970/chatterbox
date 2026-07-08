#!/usr/bin/env python3
"""Audit whether Embry orb screenshots are linked to live audio-turn evidence."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_MARKER_GLOB = ".codex/ui-verification/*orb*.latest.json"
DEFAULT_RECEIPT_PATHS = [
    Path("/tmp/chatterbox-fork-agent-out/orb-sync-current/orb-direct-speak/orb-sync-receipt.json"),
]
DEFAULT_OUT = Path("docs/EMBRY_ORB_SYNC_EVIDENCE_AUDIT.json")


REQUIRED_LINKAGE_FIELDS = [
    "turn_id",
    "audio_artifact_id",
    "playback.started_at_epoch_ms",
    "playback.audio_artifact_id",
    "orb.authority",
    "orb.envelope_frame_count",
    "orb.max_level",
    "screenshot.path",
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


def normalized_marker(marker_path: Path, marker: dict[str, Any]) -> dict[str, Any]:
    screenshot = marker.get("screenshot")
    if isinstance(screenshot, dict):
        screenshot = screenshot.get("path")
    return {
        "marker_path": str(marker_path),
        "name": marker.get("name"),
        "url": marker.get("url"),
        "verified_at": marker.get("verified_at"),
        "screenshot": screenshot,
        "screenshot_exists": bool(screenshot and Path(str(screenshot)).exists()),
        "read_json": marker.get("read_json"),
    }


def audit_candidate(marker_path: Path, marker: dict[str, Any]) -> dict[str, Any]:
    # Current UI verification markers store screenshot/read_json paths at top
    # level. Future passing receipts may embed the full linkage contract under
    # the same marker or point to an external orb_sync_receipt.
    receipt_path = marker.get("orb_sync_receipt") or marker.get("receipt")
    receipt: dict[str, Any] = marker
    if receipt_path:
        receipt = read_json(Path(str(receipt_path)))
    elif marker_path.name.endswith(".json") and marker.get("schema") == "chatterbox.embry_orb_sync_receipt.v1":
        receipt_path = str(marker_path)

    missing_fields = [
        field
        for field in REQUIRED_LINKAGE_FIELDS
        if nested_get(receipt, field) in {None, "", 0, False}
    ]
    if receipt.get("mocked") is not False:
        missing_fields.append("mocked_false")
    if receipt.get("live") is not True:
        missing_fields.append("live_true")

    audio_artifact_id = nested_get(receipt, "audio_artifact_id")
    playback_audio_artifact_id = nested_get(receipt, "playback.audio_artifact_id")
    if audio_artifact_id and playback_audio_artifact_id and audio_artifact_id != playback_audio_artifact_id:
        missing_fields.append("audio_artifact_id_matches_playback")

    screenshot_path = nested_get(receipt, "screenshot.path") or marker.get("screenshot")
    screenshot_exists = bool(screenshot_path and Path(str(screenshot_path)).exists())
    if not screenshot_exists:
        missing_fields.append("screenshot_file_exists")

    envelope_frame_count = nested_get(receipt, "orb.envelope_frame_count")
    if isinstance(envelope_frame_count, int | float) and envelope_frame_count <= 0:
        missing_fields.append("orb_envelope_frame_count_positive")

    max_level = nested_get(receipt, "orb.max_level")
    if isinstance(max_level, int | float) and max_level <= 0:
        missing_fields.append("orb_max_level_positive")

    return {
        "marker": normalized_marker(marker_path, marker),
        "linked_receipt_path": str(receipt_path) if receipt_path else None,
        "ok": not missing_fields,
        "missing_fields": sorted(set(missing_fields)),
        "observed": {
            "turn_id": nested_get(receipt, "turn_id"),
            "audio_artifact_id": audio_artifact_id,
            "playback_audio_artifact_id": playback_audio_artifact_id,
            "orb_authority": nested_get(receipt, "orb.authority"),
            "orb_envelope_frame_count": envelope_frame_count,
            "orb_max_level": max_level,
            "screenshot_path": screenshot_path,
            "screenshot_exists": screenshot_exists,
            "mocked": receipt.get("mocked"),
            "live": receipt.get("live"),
        },
    }


def build_audit(marker_paths: list[Path]) -> dict[str, Any]:
    candidates = [audit_candidate(path, read_json(path)) for path in marker_paths]
    has_passing_candidate = any(candidate["ok"] for candidate in candidates)
    failed_gates: list[str] = []
    if not marker_paths:
        failed_gates.append("orb_ui_marker_present")
    if not has_passing_candidate:
        failed_gates.append("orb_sync_turn_audio_envelope_receipt_present")
        for candidate in candidates:
            for field in candidate["missing_fields"]:
                failed_gates.append(f"missing:{field}")

    return {
        "schema": "chatterbox.embry_orb_sync_evidence_audit.v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mocked": False,
        "live": has_passing_candidate,
        "ok": not failed_gates,
        "status": "passed" if not failed_gates else "failed",
        "marker_count": len(marker_paths),
        "candidate_count": len(candidates),
        "passing_candidate_count": sum(1 for candidate in candidates if candidate["ok"]),
        "required_linkage_fields": REQUIRED_LINKAGE_FIELDS,
        "candidates": candidates,
        "failed_gates": sorted(set(failed_gates)),
        "claims": {
            "proves": [
                "at_least_one_orb_receipt_links_turn_audio_playback_envelope_and_screenshot",
            ]
            if not failed_gates
            else [],
            "does_not_prove": [
                "RealtimeSTT ingress",
                "memory/Tau routing",
                "Chatterbox generation correctness",
                "human subjective orb quality",
            ],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--marker-glob", default=DEFAULT_MARKER_GLOB)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    marker_paths = [path for path in DEFAULT_RECEIPT_PATHS if path.exists()]
    marker_paths.extend(sorted(Path().glob(args.marker_glob)))
    audit = build_audit(marker_paths)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n")
    print(args.out)
    return 0 if audit["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
