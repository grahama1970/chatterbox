#!/usr/bin/env python3
"""Audit current memory/Tau routing evidence for Embry voice stress testing."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_MATRIX = Path("docs/EMBRY_STRESS_SESSION_MATRIX.json")
DEFAULT_OUT = Path("docs/EMBRY_MEMORY_TAU_ROUTING_EVIDENCE_AUDIT.json")
DEFAULT_PROOFS = [
    Path("/tmp/chatterbox-fork-agent-out/embry-memory-answerability-ledger/20260708T004951Z-memory-answerability-ledger/receipt.json"),
    Path("/tmp/chatterbox-fork-agent-out/embry-answerability-runtime-block/20260708T010111Z-answerability-runtime-block/receipt.json"),
    Path("/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260708T002830Z-matrix-tau-simple/receipt.json"),
    Path("/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260708T051042Z-matrix-tau-simple-dag-batch/receipt.json"),
    Path("/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260708T051253Z-matrix-tau-all-dag-current/receipt.json"),
    Path("/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260708T052215Z-skill-analytics-all-live/receipt.json"),
    Path("/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260708T052948Z-skill-create-figure-all-live/receipt.json"),
    Path("/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260708T014152Z-matrix-medium-memory-search/receipt.json"),
    Path("/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260708T014802Z-matrix-medium-routes-16-31/receipt.json"),
]

MEMORY_FOLDERS = {
    "sparta_qra_compliance",
    "persona_memory_recall",
    "persona_memory_miss",
}
TAU_SKILL_FOLDERS = {
    "tau_tool_orchestration",
    "skill_create_evidence_case",
    "skill_create_figure",
    "skill_analytics",
    "skill_sparta_validator",
    "voice_control_skill",
}
EXTERNAL_RESEARCH_FOLDERS = {"brave_research"}
AUDITED_FOLDERS = MEMORY_FOLDERS | TAU_SKILL_FOLDERS | EXTERNAL_RESEARCH_FOLDERS


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"error_type": type(exc).__name__, "error": str(exc), "path": str(path)}


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


def classify_proof(path: Path, receipt: dict[str, Any]) -> dict[str, Any]:
    claims = receipt.get("claims") or {}
    proves = claims.get("proves") or []
    failed_gates = receipt.get("failed_gates") or []
    schema = str(receipt.get("schema") or "")

    cases = receipt.get("cases") if isinstance(receipt.get("cases"), list) else []

    if "answerability_runtime_block" in schema:
        proof_type = "answerability_runtime_block"
    elif "memory-answerability-ledger" in str(path) or "answerability" in str(receipt.get("proof_scope") or ""):
        proof_type = "memory_answerability_ledger"
    elif (
        "tau" in str(path)
        or any("tau" in str(gate) for gate in failed_gates)
        or any(isinstance(case, dict) and str(case.get("route") or "").startswith("tau.") for case in cases)
    ):
        proof_type = "tau_or_skill_routing"
    else:
        proof_type = "unknown"

    ok = receipt.get("ok") is True and receipt.get("live") is True and receipt.get("mocked") is False
    runtime_block_proven = ok and proof_type == "answerability_runtime_block" and {
        "tau_voice_render_rejects_blocked_memory_answerability",
        "blocked_memory_answers_do_not_create_chatterbox_finished_audio",
    }.issubset(set(proves))
    tau_dag_handoff_proven = (
        ok
        and proof_type == "tau_or_skill_routing"
        and bool(cases)
        and all(
            isinstance(case, dict)
            and case.get("route") == "tau.agent_handoff"
            and case.get("ok") is True
            and bool(case.get("tau_dag_receipt"))
            and bool(case.get("tau_command_loop_receipt"))
            for case in cases
        )
    )
    direct_skill_call_proven = (
        ok
        and proof_type == "tau_or_skill_routing"
        and bool(cases)
        and all(
            isinstance(case, dict)
            and str(case.get("route") or "").startswith("tau.skill.")
            and case.get("ok") is True
            and bool(case.get("tau_dag_receipt"))
            and bool(case.get("tau_command_loop_receipt"))
            and bool(case.get("skill_call_receipt"))
            and bool(case.get("analytics_stdout_sha256") or case.get("skill_call_receipt_sha256"))
            for case in cases
        )
    )

    return {
        "path": str(path),
        "exists": path.exists(),
        "schema": receipt.get("schema"),
        "proof_type": proof_type,
        "ok": receipt.get("ok"),
        "live": receipt.get("live"),
        "mocked": receipt.get("mocked"),
        "case_count": receipt.get("case_count") or len(receipt.get("cases") or receipt.get("results") or []),
        "runtime_block_proven": runtime_block_proven,
        "tau_dag_handoff_proven": tau_dag_handoff_proven,
        "direct_skill_call_proven": direct_skill_call_proven,
        "failed_gates": failed_gates,
        "claims_proves": proves,
        "claims_does_not_prove": claims.get("does_not_prove") or [],
        "journal": receipt.get("journal"),
    }


def build_audit(matrix: dict[str, Any], proof_paths: list[Path]) -> dict[str, Any]:
    relevant_sessions = [session for session in matrix["sessions"] if session["folder_id"] in AUDITED_FOLDERS]
    memory = _group_summary(matrix, MEMORY_FOLDERS)
    tau_skill = _group_summary(matrix, TAU_SKILL_FOLDERS)
    external_research = _group_summary(matrix, EXTERNAL_RESEARCH_FOLDERS)
    proof_candidates = [classify_proof(path, read_json(path)) for path in proof_paths if path.exists()]
    runtime_blocks = [candidate for candidate in proof_candidates if candidate["runtime_block_proven"]]
    tau_dag_handoffs = [candidate for candidate in proof_candidates if candidate["tau_dag_handoff_proven"]]
    direct_skill_calls = [candidate for candidate in proof_candidates if candidate["direct_skill_call_proven"]]
    live_unmocked_candidates = [
        candidate
        for candidate in proof_candidates
        if candidate.get("live") is True and candidate.get("mocked") is False
    ]

    failed_gates: list[str] = []
    if memory["status_counts"]["failed"]:
        failed_gates.append("memory_answerability_matrix_has_failures")
    if tau_skill["status_counts"]["failed"]:
        failed_gates.append("tau_skill_routing_matrix_has_failures")
    if external_research["status_counts"]["failed"] or external_research["status_counts"]["passed"] == 0:
        failed_gates.append("external_research_not_all_passing")
    for gate in sorted(memory["failed_gate_counts"]):
        failed_gates.append(f"memory_gate:{gate}")
    for gate in sorted(tau_skill["failed_gate_counts"]):
        failed_gates.append(f"tau_skill_gate:{gate}")
    if "tau_agent_handoff_not_exercised" in tau_skill["failed_gate_counts"]:
        tau_tool_gates = tau_skill["by_folder"].get("tau_tool_orchestration", {}).get("failed_gate_counts", {})
        if "tau_agent_handoff_not_exercised" in tau_tool_gates:
            failed_gates.append("tau_agent_handoff_missing")
        skill_folder_gates = [
            folder_summary.get("failed_gate_counts", {})
            for folder, folder_summary in tau_skill["by_folder"].items()
            if folder != "tau_tool_orchestration"
        ]
        if any("tau_agent_handoff_not_exercised" in gates for gates in skill_folder_gates):
            failed_gates.append("skill_tau_agent_handoff_missing")
    if "skill_call_receipt_not_emitted" in tau_skill["failed_gate_counts"]:
        failed_gates.append("skill_call_receipt_missing")
    if "tau_dag_receipt_not_created" in tau_skill["failed_gate_counts"]:
        failed_gates.append("tau_dag_receipt_missing")
    if not runtime_blocks:
        failed_gates.append("answerability_runtime_block_receipt_missing")

    ok = not failed_gates
    return {
        "schema": "chatterbox.embry_memory_tau_routing_evidence_audit.v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mocked": False,
        "live": bool(live_unmocked_candidates),
        "ok": ok,
        "status": "passed" if ok else "failed",
        "audited_session_count": len(relevant_sessions),
        "audited_status_counts": _status_counts(relevant_sessions),
        "memory_answerability": memory,
        "tau_skill_routing": tau_skill,
        "external_research": external_research,
        "proof_candidate_count": len(proof_candidates),
        "live_unmocked_candidate_count": len(live_unmocked_candidates),
        "runtime_block_candidate_count": len(runtime_blocks),
        "tau_dag_handoff_candidate_count": len(tau_dag_handoffs),
        "direct_skill_call_candidate_count": len(direct_skill_calls),
        "proof_candidates": proof_candidates,
        "failed_gates": sorted(set(failed_gates)),
        "claims": {
            "proves": [
                "memory_answerability_tau_skill_routing_and_external_research_are_all_passing",
            ]
            if ok
            else [
                "blocked_memory_answerability_can_be_suppressed_before_chatterbox"
            ]
            if runtime_blocks
            else [],
            "does_not_prove": [
                "RealtimeSTT audio ingress",
                "speaker identity",
                "Chatterbox output quality",
                "Chat UX synchronization",
                "orb synchronization",
                "replay",
                "interruption",
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
