#!/usr/bin/env python3
"""Audit current speaker identity evidence for Embry voice stress testing."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_MATRIX = Path("docs/EMBRY_STRESS_SESSION_MATRIX.json")
DEFAULT_OUT = Path("docs/EMBRY_SPEAKER_IDENTITY_EVIDENCE_AUDIT.json")
DEFAULT_PROOFS = [
    Path("/tmp/chatterbox-fork-agent-out/embry-speaker-identity-ledger/20260708T004440Z-speaker-identity-ledger/receipt.json"),
    Path("/tmp/chatterbox-fork-agent-out/primary-speaker-gate-20260702T150040Z/suite-summary.json"),
    Path("/tmp/chatterbox-fork-agent-out/rung7-horus-factory-stress-youtube-20260702T192914Z/rung7-combined.json"),
    Path("/tmp/chatterbox-speaker-memory-rungs-20260702T1722Z/rung1_unknown_factory_identity.json"),
    Path("/tmp/chatterbox-speaker-memory-rungs-20260702T1800Z/rung5_known_horus_post_writeback_recall.json"),
]


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


def _speaker_matrix_summary(matrix: dict[str, Any]) -> dict[str, Any]:
    sessions = [session for session in matrix["sessions"] if session["folder_id"] == "speaker_identity"]
    gate_counts = Counter(gate for session in sessions for gate in session.get("failed_gates", []))
    return {
        "session_count": len(sessions),
        "status_counts": _status_counts(sessions),
        "failed_gate_counts": dict(sorted(gate_counts.items(), key=lambda item: (-item[1], item[0]))),
        "source_audio_identity_proven_false_count": sum(
            "source_audio_identity_proven=false" in str(session.get("observed", ""))
            for session in sessions
        ),
        "sessions": [
            {
                "id": session["id"],
                "difficulty": session["difficulty"],
                "status": session["status"],
                "latest_receipt": session.get("latest_receipt"),
                "failed_gates": session.get("failed_gates") or [],
                "observed": session.get("observed"),
            }
            for session in sessions
        ],
    }


def _policy_cases_cover_required_statuses(cases: Any) -> bool:
    if not isinstance(cases, list):
        return False
    statuses = {case.get("actual", {}).get("status") for case in cases if isinstance(case, dict)}
    ids = {str(case.get("id") or "") for case in cases if isinstance(case, dict)}
    has_overlap_case = any("overlap" in case_id for case_id in ids)
    return {"known", "unknown", "ambiguous"}.issubset(statuses) and has_overlap_case


def _fixture_gate_ok(cases: Any) -> bool:
    if not isinstance(cases, dict):
        return False
    return (
        cases.get("primary", {}).get("primary_speaker_match") is True
        and cases.get("female_alt", {}).get("primary_speaker_match") is False
        and cases.get("other_male", {}).get("primary_speaker_match") is False
        and cases.get("background_noise", {}).get("primary_speaker_match") is False
    )


def _known_speaker_resolution_ok(receipt: dict[str, Any]) -> bool:
    return (
        _nested_get(receipt, "speaker_resolution.status") == "known"
        and _nested_get(receipt, "speaker_resolution.speaker_id") == "horus_lupercal"
        and _nested_get(receipt, "speaker_resolution.allow_personal_memory") is True
        and "speaker:horus_lupercal" in (_nested_get(receipt, "speaker_resolution.memory_tags") or [])
    )


def _unknown_speaker_resolution_ok(receipt: dict[str, Any]) -> bool:
    return (
        _nested_get(receipt, "speaker_resolution.status") == "unknown"
        and _nested_get(receipt, "speaker_resolution.allow_personal_memory") is False
        and bool(_nested_get(receipt, "speaker_resolution.identity_prompt.text"))
    )


def classify_proof(path: Path, receipt: dict[str, Any]) -> dict[str, Any]:
    schema = str(receipt.get("schema") or "")
    claims = receipt.get("claims") or {}
    does_not_prove = claims.get("does_not_prove") or []

    if receipt.get("proof_scope") == "live_memory_speaker_resolution_policy_not_audio_identity":
        proof_type = "memory_speaker_policy_ledger"
    elif schema == "chatterbox.primary_speaker_gate_suite.v1":
        proof_type = "fixture_primary_speaker_gate"
    elif schema == "chatterbox.conversation_ladder.rung7.listener_contract.v1" and _known_speaker_resolution_ok(receipt):
        proof_type = "known_horus_listener_memory"
    elif schema == "chatterbox.conversation_ladder.rung7.listener_contract.v1" and _unknown_speaker_resolution_ok(receipt):
        proof_type = "unknown_speaker_fail_closed"
    else:
        proof_type = "unknown"

    enrollment_audio = _nested_get(receipt, "primary_speaker_verification.enrollment_audio")
    candidate_audio = _nested_get(receipt, "primary_speaker_verification.candidate_audio")
    enrollment_independent = bool(enrollment_audio and candidate_audio and enrollment_audio != candidate_audio)

    physical_identity_not_proven = any(
        "physical_speaker_to_microphone_identity_gating" in str(item)
        or "physical speaker playback to microphone" in str(item)
        for item in does_not_prove
    )

    return {
        "path": str(path),
        "exists": path.exists(),
        "schema": receipt.get("schema"),
        "proof_type": proof_type,
        "ok": receipt.get("ok"),
        "live": receipt.get("live"),
        "mocked": receipt.get("mocked"),
        "failed_gates": receipt.get("failed_gates") or [],
        "policy_cases_cover_known_unknown_ambiguous_overlap": _policy_cases_cover_required_statuses(receipt.get("cases")),
        "fixture_primary_accepts_and_rejects_non_primary": _fixture_gate_ok(receipt.get("cases")),
        "known_horus_resolution_ok": _known_speaker_resolution_ok(receipt),
        "unknown_speaker_fail_closed_ok": _unknown_speaker_resolution_ok(receipt),
        "source_audio_identity_proven": receipt.get("source_audio_identity_proven"),
        "enrollment_audio": enrollment_audio,
        "candidate_audio": candidate_audio,
        "enrollment_independent_from_candidate": enrollment_independent,
        "primary_speaker_match": _nested_get(receipt, "primary_speaker_verification.primary_speaker_match"),
        "similarity": _nested_get(receipt, "primary_speaker_verification.similarity"),
        "threshold": _nested_get(receipt, "primary_speaker_verification.threshold"),
        "physical_identity_not_proven_by_claims": physical_identity_not_proven,
        "claims_proves": claims.get("proves") or [],
        "claims_does_not_prove": does_not_prove,
    }


def build_audit(matrix: dict[str, Any], proof_paths: list[Path]) -> dict[str, Any]:
    speaker_matrix = _speaker_matrix_summary(matrix)
    proof_candidates = [classify_proof(path, read_json(path)) for path in proof_paths if path.exists()]

    policy_ledgers = [candidate for candidate in proof_candidates if candidate["policy_cases_cover_known_unknown_ambiguous_overlap"]]
    fixture_gates = [candidate for candidate in proof_candidates if candidate["fixture_primary_accepts_and_rejects_non_primary"]]
    known_horus = [candidate for candidate in proof_candidates if candidate["known_horus_resolution_ok"]]
    unknown_fail_closed = [candidate for candidate in proof_candidates if candidate["unknown_speaker_fail_closed_ok"]]
    independent_enrollment = [
        candidate
        for candidate in proof_candidates
        if candidate["known_horus_resolution_ok"] and candidate["enrollment_independent_from_candidate"]
    ]
    physical_identity_proven = [
        candidate
        for candidate in proof_candidates
        if candidate["known_horus_resolution_ok"]
        and candidate["physical_identity_not_proven_by_claims"] is False
        and candidate["source_audio_identity_proven"] is True
    ]

    failed_gates: list[str] = []
    if speaker_matrix["status_counts"]["failed"]:
        failed_gates.append("speaker_identity_matrix_has_failures")
    if not policy_ledgers:
        failed_gates.append("memory_speaker_policy_ledger_missing")
    if not fixture_gates:
        failed_gates.append("primary_speaker_gate_fixture_missing")
    if not known_horus:
        failed_gates.append("known_horus_resolution_receipt_missing")
    if not unknown_fail_closed:
        failed_gates.append("unknown_speaker_fail_closed_receipt_missing")
    if not independent_enrollment:
        failed_gates.append("independent_horus_enrollment_receipt_missing")
    if not physical_identity_proven:
        failed_gates.append("physical_speaker_to_microphone_identity_gating_not_proven")
    if speaker_matrix["source_audio_identity_proven_false_count"]:
        failed_gates.append("matrix_contains_source_audio_identity_unproven_rows")
    failed_gates.append("overlap_diarization_not_proven")

    ok = not failed_gates
    return {
        "schema": "chatterbox.embry_speaker_identity_evidence_audit.v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mocked": False,
        "live": False,
        "ok": ok,
        "status": "passed" if ok else "failed",
        "speaker_matrix": speaker_matrix,
        "proof_candidate_count": len(proof_candidates),
        "policy_ledger_candidate_count": len(policy_ledgers),
        "fixture_gate_candidate_count": len(fixture_gates),
        "known_horus_candidate_count": len(known_horus),
        "unknown_fail_closed_candidate_count": len(unknown_fail_closed),
        "independent_enrollment_candidate_count": len(independent_enrollment),
        "physical_identity_candidate_count": len(physical_identity_proven),
        "proof_candidates": proof_candidates,
        "failed_gates": sorted(set(failed_gates)),
        "claims": {
            "proves": [
                "speaker_identity_matrix_policy_rows_are_passing",
                "memory_speaker_resolve_handles_known_unknown_ambiguous_overlap_policy",
                "fixture_primary_speaker_gate_suppresses_non_primary_audio",
                "known_horus_resolution_can_route_speaker_scoped_memory",
                "unknown_speaker_resolution_fails_closed_to_identity_prompt",
            ],
            "does_not_prove": [
                "RealtimeSTT audio ingress",
                "real multi-sample Horus enrollment",
                "physical speaker-to-microphone identity gating",
                "overlapping-speaker diarization",
                "memory/Tau answer correctness",
                "Chatterbox speech quality",
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
