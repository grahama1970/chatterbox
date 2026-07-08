#!/usr/bin/env python3
"""Audit current shared Chat UX synchronization evidence for Embry voice."""

from __future__ import annotations

import argparse
import glob
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_MATRIX = Path("docs/EMBRY_STRESS_SESSION_MATRIX.json")
DEFAULT_OUT = Path("docs/EMBRY_CHAT_UX_SYNC_EVIDENCE_AUDIT.json")
DEFAULT_PROOFS = [
    Path("/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260708T013912Z-chat-ux-gate-audit/audit.json"),
    Path("/tmp/codex-ui-verification/pi-mono/embry-voice-dynamic-replay-hardening/dynamic-replay-proof.json"),
]
DEFAULT_MARKER_GLOB = ".codex/ui-verification/*embry-voice*.latest.json"


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


def _chat_matrix_summary(matrix: dict[str, Any]) -> dict[str, Any]:
    sessions = [session for session in matrix["sessions"] if session["folder_id"] == "chat_ux_sync"]
    gate_counts = Counter(gate for session in sessions for gate in session.get("failed_gates", []))
    return {
        "session_count": len(sessions),
        "status_counts": _status_counts(sessions),
        "failed_gate_counts": dict(sorted(gate_counts.items(), key=lambda item: (-item[1], item[0]))),
        "sample_failures": [
            {
                "id": session["id"],
                "difficulty": session["difficulty"],
                "latest_receipt": session.get("latest_receipt"),
                "failed_gates": session.get("failed_gates") or [],
                "observed": session.get("observed"),
            }
            for session in sessions
            if session["status"] == "failed"
        ][:8],
    }


def _gate_by_name(receipt: dict[str, Any], name: str) -> dict[str, Any] | None:
    for gate in receipt.get("gates") or []:
        if isinstance(gate, dict) and gate.get("name") == name:
            return gate
    return None


def _marker_candidates(marker_glob: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for marker_name in sorted(glob.glob(marker_glob)):
        marker_path = Path(marker_name)
        marker = read_json(marker_path)
        screenshot = marker.get("screenshot")
        read_json_path = marker.get("read_json")
        read_json_exists = bool(read_json_path and Path(str(read_json_path)).exists())
        candidates.append(
            {
                "marker_path": str(marker_path),
                "url": marker.get("url"),
                "name": marker.get("name"),
                "screenshot": screenshot,
                "screenshot_exists": bool(screenshot and Path(str(screenshot)).exists()),
                "read_json": read_json_path,
                "read_json_exists": read_json_exists,
                "proof_scope": "screenshot_or_page_snapshot_only",
            }
        )
    return candidates


def classify_proof(path: Path, receipt: dict[str, Any]) -> dict[str, Any]:
    schema = receipt.get("schema")
    chat_gate = _gate_by_name(receipt, "Chat UX sync")
    replay_gate = _gate_by_name(receipt, "replay")
    assertions = receipt.get("assertions") or _nested_get(replay_gate or {}, "evidence.assertions") or {}

    assistant_plan = receipt.get("assistant_response_plan") or receipt.get("assistant.response.plan.v1")
    chat_render = receipt.get("chat_render_receipt") or receipt.get("chat.render.receipt.v1")
    extract_entities = receipt.get("extract_entities_receipt") or receipt.get("extract_entities")
    underline_render = receipt.get("entity_underline_render_receipt") or receipt.get("entity_underlines")

    plan_turn_id = _nested_get(assistant_plan or {}, "turn_id")
    render_turn_id = _nested_get(chat_render or {}, "turn_id")
    text_audio_same_turn = bool(
        plan_turn_id
        and render_turn_id
        and plan_turn_id == render_turn_id
        and (_nested_get(chat_render or {}, "audio_artifact_id") or _nested_get(chat_render or {}, "audio_artifact_ids"))
    )
    entities_underlined = bool(
        extract_entities
        and underline_render
        and (
            _nested_get(underline_render or {}, "rendered_entity_count")
            or len(_nested_get(underline_render or {}, "entities") or [])
        )
    )

    chat_gate_pass = bool(
        chat_gate
        and chat_gate.get("status") == "PASS"
        and _nested_get(chat_gate, "evidence.audio_count")
        and _nested_get(chat_gate, "evidence.audio_src_count")
    )
    dynamic_replay_basic = bool(
        assertions.get("dynamicReplayReducedToCurrentTurn")
        and assertions.get("audioArtifactsEmbeddedInSharedChat")
        and assertions.get("liveReasoningTraceVisibleDuringReplay")
        and assertions.get("replayCompletesWithoutStaticReset")
    )

    return {
        "path": str(path),
        "exists": path.exists(),
        "schema": schema,
        "chat_gate_pass": chat_gate_pass,
        "dynamic_replay_basic": dynamic_replay_basic,
        "inline_reasoning_trace_basic": bool(assertions.get("liveReasoningTraceVisibleDuringReplay")),
        "response_plan_to_chat_render_lineage": text_audio_same_turn,
        "extract_entities_underlines": entities_underlined,
        "observed": {
            "chat_gate_evidence": (chat_gate or {}).get("evidence"),
            "replay_assertions": assertions,
            "plan_turn_id": plan_turn_id,
            "render_turn_id": render_turn_id,
            "audio_artifact_id": _nested_get(chat_render or {}, "audio_artifact_id"),
            "audio_artifact_ids": _nested_get(chat_render or {}, "audio_artifact_ids"),
            "extract_entities_present": bool(extract_entities),
            "underline_render_present": bool(underline_render),
        },
    }


def build_audit(matrix: dict[str, Any], proof_paths: list[Path], marker_glob: str = DEFAULT_MARKER_GLOB) -> dict[str, Any]:
    chat_matrix = _chat_matrix_summary(matrix)
    proof_candidates = [classify_proof(path, read_json(path)) for path in proof_paths if path.exists()]
    markers = _marker_candidates(marker_glob)

    chat_gate_candidates = [candidate for candidate in proof_candidates if candidate["chat_gate_pass"]]
    replay_candidates = [candidate for candidate in proof_candidates if candidate["dynamic_replay_basic"]]
    lineage_candidates = [candidate for candidate in proof_candidates if candidate["response_plan_to_chat_render_lineage"]]
    underline_candidates = [candidate for candidate in proof_candidates if candidate["extract_entities_underlines"]]

    failed_gates: list[str] = []
    if chat_matrix["status_counts"]["failed"]:
        failed_gates.append("chat_ux_matrix_has_failures")
    if not chat_gate_candidates:
        failed_gates.append("shared_chat_audio_text_basic_gate_missing")
    if not replay_candidates:
        failed_gates.append("dynamic_replay_inline_trace_basic_missing")
    if not lineage_candidates:
        failed_gates.append("assistant_response_plan_to_chat_render_lineage_missing")
    if not underline_candidates:
        failed_gates.append("extract_entities_underline_render_receipt_missing")
    if markers and not lineage_candidates:
        failed_gates.append("screenshot_markers_do_not_prove_turn_lineage")
    for gate in sorted(chat_matrix["failed_gate_counts"]):
        failed_gates.append(f"chat_matrix_gate:{gate}")

    ok = not failed_gates
    return {
        "schema": "chatterbox.embry_chat_ux_sync_evidence_audit.v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mocked": False,
        "live": False,
        "ok": ok,
        "status": "passed" if ok else "failed",
        "chat_matrix": chat_matrix,
        "proof_candidate_count": len(proof_candidates),
        "chat_gate_candidate_count": len(chat_gate_candidates),
        "dynamic_replay_candidate_count": len(replay_candidates),
        "lineage_candidate_count": len(lineage_candidates),
        "entity_underline_candidate_count": len(underline_candidates),
        "screenshot_marker_count": len(markers),
        "proof_candidates": proof_candidates,
        "screenshot_markers": markers,
        "failed_gates": sorted(set(failed_gates)),
        "claims": {
            "proves": [
                "shared_chat_basic_audio_text_and_dynamic_replay_evidence_exists",
            ]
            if chat_gate_candidates and replay_candidates
            else [],
            "does_not_prove": [
                "RealtimeSTT audio ingress",
                "speaker identity correctness",
                "memory/Tau answer correctness",
                "Chatterbox speech quality",
                "orb synchronization",
                "event-sourced replay",
                "interruption",
            ],
        },
    }


def proof_path_candidates(explicit_paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    result: list[Path] = []
    for path in explicit_paths:
        if not path.exists():
            continue
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--proof", action="append", type=Path, default=[])
    parser.add_argument("--marker-glob", default=DEFAULT_MARKER_GLOB)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    matrix = read_json(args.matrix)
    paths = proof_path_candidates([*DEFAULT_PROOFS, *args.proof])
    audit = build_audit(matrix, paths, marker_glob=args.marker_glob)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n")
    print(args.out)
    return 0 if audit["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
