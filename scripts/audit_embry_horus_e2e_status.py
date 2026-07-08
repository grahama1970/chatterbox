#!/usr/bin/env python3
"""Build an exact pass/fail audit for the requested Horus voice/chat items."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_GOAL_AUDIT = Path("docs/EMBRY_GOAL_COVERAGE_AUDIT.json")
DEFAULT_OUT = Path("docs/EMBRY_HORUS_E2E_STATUS_AUDIT.json")


ITEMS: dict[str, dict[str, Any]] = {
    "real_horus_enrollment": {
        "title": "Real Horus Enrollment",
        "subsystems": ["speaker_identity"],
        "acceptance": [
            "fresh multi-sample Horus enrollment receipt",
            "primary speaker accepted",
            "female/distractor/non-primary speakers rejected",
            "speaker-scoped memory is unlocked only for resolved Horus",
        ],
        "current_failure": "Speaker identity is only partial: fixture/policy rows and one strict pyannote two-speaker overlap receipt exist, but real multi-sample Horus enrollment and physical speaker-to-mic identity gating are not proven.",
    },
    "browser_mic_webrtc": {
        "title": "Browser Mic / WebRTC To RealtimeSTT",
        "subsystems": ["realtimestt_ingress"],
        "acceptance": [
            "browser getUserMedia permission and device receipt",
            "binary audio packets feed RealtimeSTT",
            "RealtimeSTT realtime and final transcript events emitted",
            "capture source identity and transcript receipt are committed",
        ],
        "current_failure": "RealtimeSTT ingress is failing: loopback/history slices exist, but current browser/device behavior is inconsistent and factory capture rows fail.",
    },
    "tau_memory_routing": {
        "title": "Tau / Memory Routing",
        "subsystems": ["memory_tau_routing"],
        "acceptance": [
            "accepted STT final transcript creates the Tau turn",
            "memory answerability blocks misses",
            "Tau handoff/DAG/skill.call receipts are emitted",
            "Sparta QRA, persona memory, and external research routes are receipt-backed",
        ],
        "current_failure": "Memory/Tau routing is partial: answerability, external research, Tau handoff, DAG, and skill-call matrix rows pass, but they are not yet tied to one live STT -> memory/Tau -> Chatterbox turn ledger.",
    },
    "chatterbox_from_live_stt": {
        "title": "Chatterbox From Live STT",
        "subsystems": ["realtimestt_ingress", "memory_tau_routing", "chatterbox_speech"],
        "acceptance": [
            "RealtimeSTT final event creates a turn_id",
            "same turn_id routes through Tau/memory",
            "same turn_id produces a Chatterbox audio artifact",
            "tone, emotion tags, pause policy, and interruption policy are in the spoken text receipt",
        ],
        "current_failure": "Chatterbox can render audio in slices, but there is no clean same-turn receipt proving live STT -> Tau/memory -> Chatterbox speech.",
    },
    "chat_ux_sync": {
        "title": "Chat UX Sync",
        "subsystems": ["chat_ux_sync"],
        "acceptance": [
            "assistant.response.plan.v1 and chat.render.receipt.v1 share turn_id",
            "chat text, Chatterbox audio, memory trace, and entity underlines share the same turn",
            "session replay emits an audible browser playback receipt that advances and is not cut off",
            "the shared Chat UX emits committed render receipts",
        ],
        "current_failure": "Chat UX sync passes as a shared UI contract; it is not yet tied to a full live RealtimeSTT -> memory/Tau -> Chatterbox turn ledger.",
    },
    "orb_sync": {
        "title": "Orb Sync",
        "subsystems": ["orb_sync"],
        "acceptance": [
            "orb authority is recorded",
            "orb envelope frames are tied to the same Chatterbox audio artifact",
            "turn_id, playback timestamps, max level, and screenshot path are committed",
        ],
        "current_failure": "Orb sync is partial: direct Chatterbox speech is linked to server-envelope orb samples, but the same receipt has not been emitted from a full shared Chat UX or live listener turn.",
    },
    "replay": {
        "title": "Replay",
        "subsystems": ["replay"],
        "acceptance": [
            "actual live session event journal is persisted",
            "replay reconstructs turn order and original timing offsets",
            "chat snapshots and audio offsets match the original session",
        ],
        "current_failure": "Replay is partial: event-sourced Chatterbox interruption replay is proven, but browser shared Chat UX replay from a full live listener session is not proven.",
    },
    "interruption": {
        "title": "Interruption",
        "subsystems": ["interruption"],
        "acceptance": [
            "primary Horus speech interrupts Embry playback",
            "old turn cancels/stops with zero stale audio bytes",
            "new Horus turn wins",
            "non-primary interruption is rejected or fail-closed",
        ],
        "current_failure": "Interruption is partial: live primary-speaker barge-in stops old audio and a new turn wins, and Chatterbox speech evidence covers Tau wait natural-stop and non-primary suppression slices, but these are not yet tied to one live STT -> speaker gate -> Tau/memory -> Chatterbox regression ledger.",
    },
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _artifact_status(path: str) -> dict[str, Any]:
    artifact_path = Path(path)
    if not artifact_path.exists():
        return {
            "path": path,
            "exists": False,
            "ok": False,
            "status": "missing",
            "mocked": None,
            "live": None,
            "failed_gates": ["evidence_artifact_missing"],
        }
    payload = read_json(artifact_path)
    return {
        "path": path,
        "exists": True,
        "ok": payload.get("ok"),
        "status": payload.get("status"),
        "mocked": payload.get("mocked"),
        "live": payload.get("live"),
        "failed_gates": payload.get("failed_gates", []),
        "claims": payload.get("claims", {}),
    }


def _subsystem_artifacts(goal_audit: dict[str, Any], subsystem_id: str) -> list[dict[str, Any]]:
    subsystem = goal_audit["subsystems"][subsystem_id]
    return [_artifact_status(path) for path in subsystem.get("evidence_artifacts", [])]


def _item_status(goal_audit: dict[str, Any], item_id: str, spec: dict[str, Any]) -> dict[str, Any]:
    subsystems = [goal_audit["subsystems"][subsystem_id] for subsystem_id in spec["subsystems"]]
    artifacts = [
        artifact
        for subsystem_id in spec["subsystems"]
        for artifact in _subsystem_artifacts(goal_audit, subsystem_id)
    ]
    subsystem_statuses = {subsystem["status"] for subsystem in subsystems}
    artifact_failures = [
        artifact
        for artifact in artifacts
        if not (
            artifact["exists"]
            and artifact.get("ok") is True
            and artifact.get("mocked") is False
            and artifact.get("live") is True
            and not artifact.get("failed_gates")
        )
    ]
    passed = not artifact_failures and subsystem_statuses == {"passed"}
    failed_reasons: list[str] = []
    if subsystem_statuses != {"passed"}:
        failed_reasons.append(
            "subsystem_status_not_passed:"
            + ",".join(sorted(subsystem_statuses))
        )
    for artifact in artifact_failures:
        failed_reasons.append(f"artifact_not_clean_live_pass:{artifact['path']}")

    return {
        "id": item_id,
        "title": spec["title"],
        "status": "pass" if passed else "fail",
        "mocked": False,
        "live_required": True,
        "acceptance": spec["acceptance"],
        "subsystems": [
            {
                "id": subsystem_id,
                "status": goal_audit["subsystems"][subsystem_id]["status"],
                "summary": goal_audit["subsystems"][subsystem_id]["summary"],
                "next_proof": goal_audit["subsystems"][subsystem_id]["next_proof"],
            }
            for subsystem_id in spec["subsystems"]
        ],
        "evidence_artifacts": artifacts,
        "failed_reasons": failed_reasons,
        "current_failure": None if passed else spec["current_failure"],
    }


def build_audit(goal_audit: dict[str, Any]) -> dict[str, Any]:
    items = {
        item_id: _item_status(goal_audit, item_id, spec)
        for item_id, spec in ITEMS.items()
    }
    counts: dict[str, int] = {"pass": 0, "fail": 0}
    for item in items.values():
        counts[item["status"]] += 1
    failed_gates = []
    for item_id, item in items.items():
        if item["status"] != "fail":
            continue
        failed_gates.append(f"item_failed:{item_id}")
        for reason in item["failed_reasons"]:
            failed_gates.append(f"{item_id}:{reason}")
        for artifact in item["evidence_artifacts"]:
            for gate in artifact.get("failed_gates") or []:
                failed_gates.append(f"{item_id}:{Path(artifact['path']).name}:{gate}")

    return {
        "schema": "chatterbox.embry_horus_e2e_status_audit.v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mocked": False,
        "live": False,
        "ok": counts["fail"] == 0,
        "status": "passed" if counts["fail"] == 0 else "failed",
        "source_goal_audit": str(DEFAULT_GOAL_AUDIT),
        "acceptance_rule": "each item passes only when every mapped subsystem is passed and every mapped evidence artifact is mocked=false, live=true, ok=true, and has no failed_gates",
        "status_counts": counts,
        "failed_gates": sorted(set(failed_gates)),
        "items": items,
        "next_failed_items": [
            {
                "id": item_id,
                "title": item["title"],
                "current_failure": item["current_failure"],
                "next_proof": item["subsystems"][0]["next_proof"],
            }
            for item_id, item in items.items()
            if item["status"] == "fail"
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--goal-audit", type=Path, default=DEFAULT_GOAL_AUDIT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    goal_audit = read_json(args.goal_audit)
    audit = build_audit(goal_audit)
    audit["source_goal_audit"] = str(args.goal_audit)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n")
    print(args.out)
    return 0 if audit["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
