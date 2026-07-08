#!/usr/bin/env python3
"""Build goal-level coverage for the Embry voice/chat stress objective."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_REQUIREMENTS = Path("docs/voice_chat_e2e_requirements.json")
DEFAULT_TAXONOMY = Path("docs/EMBRY_STRESS_FAILURE_TAXONOMY.json")
DEFAULT_OUT = Path("docs/EMBRY_GOAL_COVERAGE_AUDIT.json")


GOAL_SUBSYSTEMS: dict[str, dict[str, Any]] = {
    "realtimestt_ingress": {
        "title": "RealtimeSTT Ingress",
        "objective_phrase": "RealtimeSTT ingress",
        "requirement_ids": ["VC-02", "VC-03", "VC-04", "VC-10", "VC-23"],
        "taxonomy_subsystems": ["realtimestt_audio_ingress"],
        "status": "failing",
        "summary": "Browser/loopback proof slices exist, but factory capture matrix rows fail and device behavior is inconsistent.",
        "next_proof": "Run a current single receipt that captures browser or PipeWire audio, emits RealtimeSTT final text, and records device/source identity.",
    },
    "speaker_identity": {
        "title": "Speaker Identity",
        "objective_phrase": "speaker identity",
        "requirement_ids": ["VC-05", "VC-06", "VC-07", "VC-08", "VC-11", "VC-19", "VC-20"],
        "taxonomy_subsystems": ["speaker_identity"],
        "status": "partial",
        "summary": "Matrix speaker-resolution rows pass, but full enrollment, unknown/ambiguous/live distractor identity, and speaker-scoped memory conversations remain incomplete.",
        "next_proof": "Run fresh Horus enrollment, unknown, ambiguous, female distractor, and speaker-scoped recall receipts under one identity ledger.",
    },
    "memory_tau_routing": {
        "title": "Memory And Tau Routing",
        "objective_phrase": "memory/Tau routing",
        "requirement_ids": ["VC-14", "VC-16", "VC-17", "VC-18", "VC-20", "VC-21", "VC-22"],
        "taxonomy_subsystems": ["memory_answerability", "tau_skill_routing", "external_research"],
        "status": "failing",
        "summary": "External research rows pass, but memory answerability and Tau/direct skill routing are the largest current failure classes.",
        "next_proof": "Fix memory answerability gating and emit Tau handoff/DAG/skill.call receipts for direct skill routes.",
    },
    "chatterbox_speech": {
        "title": "Chatterbox Speech",
        "objective_phrase": "Chatterbox speech",
        "requirement_ids": ["VC-12", "VC-13", "VC-15", "VC-16", "VC-17", "VC-18", "VC-25"],
        "taxonomy_subsystems": ["interruption_turn_control", "tone_emotion_intent"],
        "status": "partial",
        "summary": "Chatterbox render and stream-cancel proof slices exist, but tone coverage, interruption behavior, QRA disabled regressions, and subjective voice quality remain open.",
        "next_proof": "Run audible Chatterbox receipts for tone families, QRA disabled generation, and barge-in stale-byte behavior tied to a live turn id.",
    },
    "chat_ux_sync": {
        "title": "Chat UX Sync",
        "objective_phrase": "Chat UX sync",
        "requirement_ids": ["VC-01", "VC-24"],
        "taxonomy_subsystems": ["shared_chat_ux"],
        "status": "failing",
        "summary": "Replay and inline trace basics pass, but turn-id lineage, chat render receipts, and entity underline receipts fail.",
        "next_proof": "Emit assistant.response.plan.v1 and chat.render.receipt.v1 with matching turn_id plus extract-entities underline render receipt.",
    },
    "orb_sync": {
        "title": "Orb Sync",
        "objective_phrase": "orb sync",
        "requirement_ids": [],
        "taxonomy_subsystems": [],
        "status": "insufficient_evidence",
        "summary": "Local UI screenshot markers show the orb route was inspected, but there is no committed receipt proving orb envelope samples are synchronized to the same live Chatterbox turn.",
        "next_proof": "Add a receipt that records turn_id, audio artifact id, playback timestamps, orb authority, envelope frame count, and screenshot path for the same replay/live turn.",
    },
    "replay": {
        "title": "Replay",
        "objective_phrase": "replay",
        "requirement_ids": ["VC-01", "VC-24"],
        "taxonomy_subsystems": ["shared_chat_ux"],
        "status": "partial",
        "summary": "Basic shared Chat UX replay rows pass, but event-sourced replay from a live session journal with original timing is not proven.",
        "next_proof": "Replay from a persisted session event journal containing input, STT, memory/Tau, Chatterbox, playback, and interruption events.",
    },
    "interruption": {
        "title": "Interruption",
        "objective_phrase": "interruption",
        "requirement_ids": ["VC-12", "VC-13"],
        "taxonomy_subsystems": ["interruption_turn_control"],
        "status": "failing",
        "summary": "All 20 matrix interruption rows fail; cancel/duck/stop endpoints are exercised, but live detection and new-turn/stale-audio receipts are missing.",
        "next_proof": "Run live barge-in receipt where primary speech interrupts Embry playback, old audio stops, and a new turn wins.",
    },
}


def _requirements_by_id(requirements: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["id"]: item for item in requirements["requirements"]}


def _taxonomy_summary(taxonomy: dict[str, Any], subsystem_ids: list[str]) -> dict[str, Any]:
    status_counts = {"passed": 0, "failed": 0, "not_run": 0}
    failed_gate_counts: dict[str, int] = {}
    for subsystem_id in subsystem_ids:
        subsystem = taxonomy["subsystems"][subsystem_id]
        for status, count in subsystem["status_counts"].items():
            status_counts[status] += count
        for gate, count in subsystem.get("failed_gate_counts", {}).items():
            failed_gate_counts[gate] = failed_gate_counts.get(gate, 0) + count
    return {
        "status_counts": status_counts,
        "top_failed_gates": [
            {"gate": gate, "count": count}
            for gate, count in sorted(failed_gate_counts.items(), key=lambda item: (-item[1], item[0]))[:10]
        ],
    }


def build_audit(requirements: dict[str, Any], taxonomy: dict[str, Any]) -> dict[str, Any]:
    reqs = _requirements_by_id(requirements)
    subsystems: dict[str, dict[str, Any]] = {}

    for subsystem_id, spec in GOAL_SUBSYSTEMS.items():
        requirement_rows = [reqs[req_id] for req_id in spec["requirement_ids"] if req_id in reqs]
        taxonomy_rows = _taxonomy_summary(taxonomy, spec["taxonomy_subsystems"])
        subsystems[subsystem_id] = {
            "title": spec["title"],
            "objective_phrase": spec["objective_phrase"],
            "status": spec["status"],
            "summary": spec["summary"],
            "next_proof": spec["next_proof"],
            "requirement_ids": spec["requirement_ids"],
            "requirements": requirement_rows,
            "taxonomy_subsystems": spec["taxonomy_subsystems"],
            "taxonomy": taxonomy_rows,
        }

    status_counts: dict[str, int] = {}
    for subsystem in subsystems.values():
        status_counts[subsystem["status"]] = status_counts.get(subsystem["status"], 0) + 1

    return {
        "schema": "chatterbox.embry_goal_coverage_audit.v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "objective": (
            "Stress test Embry voice/chat system to identify concrete failures across "
            "RealtimeSTT ingress, speaker identity, memory/Tau routing, Chatterbox speech, "
            "Chat UX sync, orb sync, replay, and interruption."
        ),
        "source_requirements": str(DEFAULT_REQUIREMENTS),
        "source_taxonomy": str(DEFAULT_TAXONOMY),
        "readiness_rule": requirements["readiness_rule"],
        "matrix_status_counts": taxonomy["matrix_status_counts"],
        "receipt_backed_count": taxonomy["receipt_backed_count"],
        "goal_subsystem_status_counts": status_counts,
        "subsystems": subsystems,
        "overall": {
            "status": "not_ready",
            "reason": "Goal subsystems still include failing, partial, and insufficient-evidence rows.",
            "ready": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requirements", type=Path, default=DEFAULT_REQUIREMENTS)
    parser.add_argument("--taxonomy", type=Path, default=DEFAULT_TAXONOMY)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    requirements = json.loads(args.requirements.read_text())
    taxonomy = json.loads(args.taxonomy.read_text())
    audit = build_audit(requirements, taxonomy)
    audit["source_requirements"] = str(args.requirements)
    audit["source_taxonomy"] = str(args.taxonomy)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n")
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
