from pathlib import Path

from scripts.audit_embry_memory_tau_routing_evidence import build_audit, classify_proof


def _session(folder_id: str, status: str, gates: list[str] | None = None) -> dict:
    return {
        "id": f"{folder_id}-{status}",
        "folder_id": folder_id,
        "difficulty": "simple",
        "status": status,
        "latest_receipt": f"/tmp/{folder_id}-{status}.json",
        "failed_gates": gates or [],
        "observed": "fixture row",
    }


def _passing_matrix() -> dict:
    return {
        "sessions": [
            _session("sparta_qra_compliance", "passed"),
            _session("persona_memory_recall", "passed"),
            _session("persona_memory_miss", "passed"),
            _session("tau_tool_orchestration", "passed"),
            _session("skill_create_evidence_case", "passed"),
            _session("skill_create_figure", "passed"),
            _session("skill_analytics", "passed"),
            _session("skill_sparta_validator", "passed"),
            _session("voice_control_skill", "passed"),
            _session("brave_research", "passed"),
        ]
    }


def test_classify_runtime_block_receipt_as_mitigation() -> None:
    receipt = {
        "schema": "embry.answerability_runtime_block.v1",
        "ok": True,
        "live": True,
        "mocked": False,
        "case_count": 12,
        "claims": {
            "proves": [
                "tau_voice_render_rejects_blocked_memory_answerability",
                "blocked_memory_answers_do_not_create_chatterbox_finished_audio",
            ],
        },
    }

    candidate = classify_proof(Path("/tmp/receipt.json"), receipt)

    assert candidate["proof_type"] == "answerability_runtime_block"
    assert candidate["runtime_block_proven"] is True
    assert candidate["case_count"] == 12


def test_classify_tau_dag_handoff_receipt_as_tau_evidence() -> None:
    receipt = {
        "schema": "embry.intelligence_stress.v1",
        "ok": True,
        "live": True,
        "mocked": False,
        "cases": [
            {
                "id": "tau_tool_orchestration-simple-01",
                "route": "tau.agent_handoff",
                "ok": True,
                "tau_dag_receipt": "/tmp/run/dag-receipt.json",
                "tau_command_loop_receipt": "/tmp/run/command-loop-receipt.json",
            }
        ],
        "failed_gates": [],
    }

    candidate = classify_proof(Path("/tmp/matrix-tau-simple-dag-batch/receipt.json"), receipt)

    assert candidate["proof_type"] == "tau_or_skill_routing"
    assert candidate["tau_dag_handoff_proven"] is True
    assert candidate["case_count"] == 1


def test_classify_direct_skill_call_receipt_as_tau_skill_evidence() -> None:
    receipt = {
        "schema": "embry.intelligence_stress.v1",
        "ok": True,
        "live": True,
        "mocked": False,
        "cases": [
            {
                "id": "skill_analytics-simple-01",
                "route": "tau.skill.analytics",
                "ok": True,
                "tau_dag_receipt": "/tmp/run/dag-receipt.json",
                "tau_command_loop_receipt": "/tmp/run/command-loop-receipt.json",
                "skill_call_receipt": "/tmp/run/skill-call-receipt.json",
                "analytics_stdout_sha256": "sha256:" + "a" * 64,
            }
        ],
        "failed_gates": [],
    }

    candidate = classify_proof(Path("/tmp/skill-analytics-all-live/receipt.json"), receipt)

    assert candidate["proof_type"] == "tau_or_skill_routing"
    assert candidate["direct_skill_call_proven"] is True
    assert candidate["tau_dag_handoff_proven"] is False
    assert candidate["case_count"] == 1


def test_audit_fails_when_memory_and_tau_rows_fail(tmp_path: Path) -> None:
    runtime_block = tmp_path / "runtime-block.json"
    runtime_block.write_text(
        """
{
  "schema": "embry.answerability_runtime_block.v1",
  "ok": true,
  "live": true,
  "mocked": false,
  "claims": {
    "proves": [
      "tau_voice_render_rejects_blocked_memory_answerability",
      "blocked_memory_answers_do_not_create_chatterbox_finished_audio"
    ]
  }
}
"""
    )
    matrix = _passing_matrix()
    matrix["sessions"].extend(
        [
            _session("sparta_qra_compliance", "failed", ["sparta_qra_answer_missing_acceptance_terms"]),
            _session("tau_tool_orchestration", "failed", ["tau_agent_handoff_not_exercised"]),
            _session("skill_create_figure", "failed", ["skill_call_receipt_not_emitted", "tau_dag_receipt_not_created"]),
        ]
    )

    audit = build_audit(matrix, [runtime_block])

    assert audit["ok"] is False
    assert audit["live"] is True
    assert audit["live_unmocked_candidate_count"] == 1
    assert audit["runtime_block_candidate_count"] == 1
    assert audit["tau_dag_handoff_candidate_count"] == 0
    assert "blocked_memory_answerability_can_be_suppressed_before_chatterbox" in audit["claims"]["proves"]
    assert "memory_answerability_matrix_has_failures" in audit["failed_gates"]
    assert "tau_skill_routing_matrix_has_failures" in audit["failed_gates"]
    assert "tau_agent_handoff_missing" in audit["failed_gates"]
    assert "skill_call_receipt_missing" in audit["failed_gates"]
    assert "tau_dag_receipt_missing" in audit["failed_gates"]
    assert audit["memory_answerability_evidence"]["boundary"] == "memory_answerability_before_tau_chatterbox"
    assert audit["memory_answerability_evidence"]["ready"] is False
    assert audit["memory_answerability_evidence"]["failed_session_count"] == 1
    assert audit["memory_answerability_evidence"]["failed_receipt_paths"] == ["/tmp/sparta_qra_compliance-failed.json"]
    assert audit["tau_skill_handoff_evidence"]["boundary"] == "tau_skill_call_agent_handoff_dag_receipts"
    assert audit["tau_skill_handoff_evidence"]["ready"] is False
    assert audit["tau_skill_handoff_evidence"]["failed_session_count"] == 2
    assert audit["tau_skill_handoff_evidence"]["tau_dag_handoff_candidate_count"] == 0
    assert audit["tau_skill_handoff_evidence"]["direct_skill_call_candidate_count"] == 0


def test_audit_passes_only_when_all_relevant_rows_and_runtime_block_pass(tmp_path: Path) -> None:
    runtime_block = tmp_path / "runtime-block.json"
    runtime_block.write_text(
        """
{
  "schema": "embry.answerability_runtime_block.v1",
  "ok": true,
  "live": true,
  "mocked": false,
  "claims": {
    "proves": [
      "tau_voice_render_rejects_blocked_memory_answerability",
      "blocked_memory_answers_do_not_create_chatterbox_finished_audio"
    ]
  }
}
"""
    )

    audit = build_audit(_passing_matrix(), [runtime_block])

    assert audit["ok"] is True
    assert audit["live"] is True
    assert audit["live_unmocked_candidate_count"] == 1
    assert audit["status"] == "passed"
    assert audit["failed_gates"] == []
    assert audit["audited_status_counts"] == {"passed": 10, "failed": 0, "not_run": 0}
    assert audit["memory_answerability_evidence"]["ready"] is True
    assert audit["memory_answerability_evidence"]["failed_session_count"] == 0
    assert audit["external_research_evidence"]["ready"] is True
    assert audit["external_research_evidence"]["passed_session_count"] == 1


def test_external_research_green_does_not_mask_memory_tau_failures(tmp_path: Path) -> None:
    matrix = {
        "sessions": [
            _session("brave_research", "passed"),
            _session("sparta_qra_compliance", "failed", ["sparta_qra_answer_overfit_to_unrelated_control_exclusion"]),
            _session("skill_analytics", "failed", ["tau_agent_handoff_not_exercised"]),
        ]
    }

    audit = build_audit(matrix, [])

    assert audit["external_research"]["status_counts"] == {"passed": 1, "failed": 0, "not_run": 0}
    assert audit["external_research_evidence"]["ready"] is True
    assert audit["external_research_evidence"]["failed_session_count"] == 0
    assert audit["ok"] is False
    assert audit["live"] is False
    assert audit["live_unmocked_candidate_count"] == 0
    assert "answerability_runtime_block_receipt_missing" in audit["failed_gates"]
    assert "memory_answerability_matrix_has_failures" in audit["failed_gates"]
    assert "tau_skill_routing_matrix_has_failures" in audit["failed_gates"]
    assert "skill_tau_agent_handoff_missing" in audit["failed_gates"]


def test_live_memory_ledger_without_full_pass_is_reported_as_live_evidence(tmp_path: Path) -> None:
    ledger = tmp_path / "memory-answerability-ledger.json"
    ledger.write_text(
        """
{
  "schema": "embry.proof.receipt.v1",
  "proof_scope": "memory-answerability-ledger",
  "ok": false,
  "live": true,
  "mocked": false,
  "case_count": 12,
  "failed_gates": ["sparta_qra_answer_missing_acceptance_terms"],
  "claims": {
    "proves": [
      "memory_answerability_queries_and_failures_are_ledgered",
      "unrelated_memory_answers_are_identified_before_tau_chatterbox_speech"
    ]
  }
}
"""
    )

    matrix = _passing_matrix()
    matrix["sessions"].append(
        _session("persona_memory_recall", "failed", ["persona_memory_answer_wrong_or_unrelated"])
    )

    audit = build_audit(matrix, [ledger])

    assert audit["ok"] is False
    assert audit["live"] is True
    assert audit["live_unmocked_candidate_count"] == 1
    assert audit["runtime_block_candidate_count"] == 0
    assert "answerability_runtime_block_receipt_missing" in audit["failed_gates"]
