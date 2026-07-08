#!/usr/bin/env python3
"""Build a subsystem failure taxonomy from the Embry stress matrix."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_MATRIX = Path("docs/EMBRY_STRESS_SESSION_MATRIX.json")
DEFAULT_OUT = Path("docs/EMBRY_STRESS_FAILURE_TAXONOMY.json")


SUBSYSTEMS: dict[str, dict[str, Any]] = {
    "memory_answerability": {
        "title": "Memory Answerability",
        "folder_ids": {"sparta_qra_compliance", "persona_memory_recall", "persona_memory_miss"},
        "primary_blocker": "Memory answers still leak unrelated SPARTA/persona records or answer memory misses.",
    },
    "external_research": {
        "title": "External Research",
        "folder_ids": {"brave_research"},
        "primary_blocker": "No current blocker in the matrix rows; source receipt route passes.",
    },
    "tau_skill_routing": {
        "title": "Tau And Direct Skill Routing",
        "folder_ids": {
            "tau_tool_orchestration",
            "skill_create_evidence_case",
            "skill_create_figure",
            "skill_analytics",
            "skill_sparta_validator",
            "voice_control_skill",
        },
        "primary_blocker": "Tau handoff, DAG receipt, and skill.call receipts are not emitted.",
    },
    "shared_chat_ux": {
        "title": "Shared Chat UX",
        "folder_ids": {"chat_ux_sync"},
        "primary_blocker": "Replay and trace basics pass, but turn lineage and entity underline receipts are missing.",
    },
    "interruption_turn_control": {
        "title": "Interruption And Turn Control",
        "folder_ids": {"interruption"},
        "primary_blocker": "Cancel/duck/stop endpoints are exercised, but live interruption decisions and stale-audio byte receipts are missing.",
    },
    "speaker_identity": {
        "title": "Speaker Identity",
        "folder_ids": {"speaker_identity"},
        "primary_blocker": "No current blocker in the matrix rows; memory speaker resolve route passes.",
    },
    "realtimestt_audio_ingress": {
        "title": "RealtimeSTT Audio Ingress",
        "folder_ids": {"factory_noise"},
        "primary_blocker": "Factory/browser capture receipts still show silent/weak capture, empty ASR, or unimplemented runner routes.",
    },
    "tone_emotion_intent": {
        "title": "Tone And Emotion Intent",
        "folder_ids": {"tone_emotion"},
        "primary_blocker": "Only frustrated de-escalation passes; hostile, discouraged, and overlap tone families fail.",
    },
}


DOES_NOT_PROVE = [
    "browser mic/WebRTC is reliable across selected devices and room conditions",
    "full live RealtimeSTT -> speaker/diarization -> memory/Tau -> Chatterbox -> Chat UX loop",
    "real Horus enrollment from a fresh live voice sample in every run",
    "Chatterbox audio generated from a live RealtimeSTT final transcript in every session",
    "Chat UX, orb, and audible playback synchronized from the same live turn event journal",
    "event-sourced replay of an actual live session with original timing",
    "live interruption/barge-in from RealtimeSTT listener input with stale audio suppression",
]


def _empty_status_counts() -> dict[str, int]:
    return {"passed": 0, "failed": 0, "not_run": 0}


def _session_brief(session: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": session["id"],
        "difficulty": session["difficulty"],
        "folder_id": session["folder_id"],
        "route": session["route"],
        "status": session["status"],
        "failed_gates": session.get("failed_gates", []),
        "latest_receipt": session.get("latest_receipt"),
        "observed": session.get("observed"),
    }


def _bucket_for_folder(folder_id: str) -> str:
    for subsystem_id, subsystem in SUBSYSTEMS.items():
        if folder_id in subsystem["folder_ids"]:
            return subsystem_id
    raise KeyError(f"unmapped folder_id: {folder_id}")


def build_taxonomy(matrix: dict[str, Any]) -> dict[str, Any]:
    sessions = matrix["sessions"]
    status_counts = Counter(session["status"] for session in sessions)
    difficulty_counts: dict[str, dict[str, int]] = {}
    folder_counts: dict[str, dict[str, int]] = {}
    route_counts: dict[str, dict[str, int]] = {}
    gate_counts: Counter[str] = Counter()

    subsystems: dict[str, dict[str, Any]] = {}
    for subsystem_id, spec in SUBSYSTEMS.items():
        subsystems[subsystem_id] = {
            "title": spec["title"],
            "primary_blocker": spec["primary_blocker"],
            "status_counts": _empty_status_counts(),
            "session_count": 0,
            "failed_gate_counts": {},
            "failed_sessions": [],
        }

    missing_receipt_sessions: list[str] = []
    not_run_sessions: list[str] = []

    for session in sessions:
        status = session["status"]
        if status in {"passed", "failed"} and not session.get("latest_receipt"):
            missing_receipt_sessions.append(session["id"])
        if status == "not_run":
            not_run_sessions.append(session["id"])

        difficulty_counts.setdefault(session["difficulty"], _empty_status_counts())[status] += 1
        folder_counts.setdefault(session["folder_id"], _empty_status_counts())[status] += 1
        route_counts.setdefault(session["route"], _empty_status_counts())[status] += 1

        subsystem_id = _bucket_for_folder(session["folder_id"])
        subsystem = subsystems[subsystem_id]
        subsystem["status_counts"][status] += 1
        subsystem["session_count"] += 1

        failed_gates = session.get("failed_gates", [])
        gate_counts.update(failed_gates)
        if status == "failed":
            subsystem["failed_sessions"].append(_session_brief(session))
            subsystem_gate_counts = Counter(subsystem["failed_gate_counts"])
            subsystem_gate_counts.update(failed_gates)
            subsystem["failed_gate_counts"] = dict(sorted(subsystem_gate_counts.items()))

    receipt_backed_count = sum(
        1 for session in sessions if session["status"] in {"passed", "failed"} and session.get("latest_receipt")
    )

    for subsystem in subsystems.values():
        subsystem["failed_sessions"] = sorted(
            subsystem["failed_sessions"], key=lambda item: (item["difficulty"], item["folder_id"], item["id"])
        )

    matrix_status_counts = _empty_status_counts()
    for status in matrix_status_counts:
        matrix_status_counts[status] = status_counts[status]

    return {
        "schema": "chatterbox.embry_stress_failure_taxonomy.v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_matrix": str(DEFAULT_MATRIX),
        "session_count": len(sessions),
        "matrix_status_counts": matrix_status_counts,
        "receipt_backed_count": receipt_backed_count,
        "missing_receipt_sessions": missing_receipt_sessions,
        "not_run_sessions": not_run_sessions,
        "difficulty_status_counts": difficulty_counts,
        "folder_status_counts": folder_counts,
        "route_status_counts": route_counts,
        "failed_gate_counts": dict(sorted(gate_counts.items())),
        "top_failed_gates": [
            {"gate": gate, "count": count} for gate, count in gate_counts.most_common()
        ],
        "subsystems": subsystems,
        "does_not_prove": DOES_NOT_PROVE,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    matrix = json.loads(args.matrix.read_text())
    taxonomy = build_taxonomy(matrix)
    taxonomy["source_matrix"] = str(args.matrix)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(taxonomy, indent=2, sort_keys=True) + "\n")
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
