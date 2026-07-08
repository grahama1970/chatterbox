from pathlib import Path

from scripts.audit_embry_chat_ux_sync_evidence import build_audit, classify_proof


def _session(status: str, gates: list[str] | None = None) -> dict:
    return {
        "id": f"chat-{status}",
        "folder_id": "chat_ux_sync",
        "difficulty": "simple",
        "status": status,
        "latest_receipt": f"/tmp/chat-{status}.json",
        "failed_gates": gates or [],
        "observed": "fixture row",
    }


def test_classify_gate_audit_basic_chat_and_replay_without_lineage() -> None:
    receipt = {
        "schema": "chatterbox.horus_live_loop_gate_audit.v1",
        "gates": [
            {
                "name": "Chat UX sync",
                "status": "PASS",
                "evidence": {"audio_count": 4, "audio_src_count": 4},
            },
            {
                "name": "replay",
                "status": "PASS",
                "evidence": {
                    "assertions": {
                        "dynamicReplayReducedToCurrentTurn": True,
                        "audioArtifactsEmbeddedInSharedChat": True,
                        "liveReasoningTraceVisibleDuringReplay": True,
                        "replayCompletesWithoutStaticReset": True,
                    }
                },
            },
        ],
    }

    candidate = classify_proof(Path("/tmp/audit.json"), receipt)

    assert candidate["chat_gate_pass"] is True
    assert candidate["dynamic_replay_basic"] is True
    assert candidate["inline_reasoning_trace_basic"] is True
    assert candidate["response_plan_to_chat_render_lineage"] is False
    assert candidate["extract_entities_underlines"] is False


def test_classify_lineage_and_entity_underline_receipt() -> None:
    receipt = {
        "assistant_response_plan": {"turn_id": "turn-1"},
        "chat_render_receipt": {"turn_id": "turn-1", "audio_artifact_id": "audio-1"},
        "extract_entities_receipt": {"entities": [{"id": "horus_lupercal"}]},
        "entity_underline_render_receipt": {"rendered_entity_count": 1},
    }

    candidate = classify_proof(Path("/tmp/lineage.json"), receipt)

    assert candidate["response_plan_to_chat_render_lineage"] is True
    assert candidate["extract_entities_underlines"] is True


def test_audit_fails_when_basic_ui_passes_but_lineage_and_entities_are_missing(tmp_path: Path) -> None:
    proof = tmp_path / "gate.json"
    proof.write_text(
        """
{
  "schema": "chatterbox.horus_live_loop_gate_audit.v1",
  "gates": [
    {"name": "Chat UX sync", "status": "PASS", "evidence": {"audio_count": 4, "audio_src_count": 4}},
    {"name": "replay", "status": "PASS", "evidence": {"assertions": {
      "dynamicReplayReducedToCurrentTurn": true,
      "audioArtifactsEmbeddedInSharedChat": true,
      "liveReasoningTraceVisibleDuringReplay": true,
      "replayCompletesWithoutStaticReset": true
    }}}
  ]
}
"""
    )

    audit = build_audit(
        {
            "sessions": [
                _session("passed"),
                _session("failed", ["assistant_response_plan_v1_not_linked", "entity_underline_render_receipt_not_emitted"]),
            ]
        },
        [proof],
        marker_glob=str(tmp_path / "no-markers-*.json"),
    )

    assert audit["ok"] is False
    assert audit["chat_gate_candidate_count"] == 1
    assert audit["dynamic_replay_candidate_count"] == 1
    assert "assistant_response_plan_to_chat_render_lineage_missing" in audit["failed_gates"]
    assert "extract_entities_underline_render_receipt_missing" in audit["failed_gates"]
    assert "chat_ux_matrix_has_failures" in audit["failed_gates"]


def test_audit_passes_when_matrix_and_required_receipts_pass(tmp_path: Path) -> None:
    gate = tmp_path / "gate.json"
    gate.write_text(
        """
{
  "gates": [
    {"name": "Chat UX sync", "status": "PASS", "evidence": {"audio_count": 4, "audio_src_count": 4}},
    {"name": "replay", "status": "PASS", "evidence": {"assertions": {
      "dynamicReplayReducedToCurrentTurn": true,
      "audioArtifactsEmbeddedInSharedChat": true,
      "liveReasoningTraceVisibleDuringReplay": true,
      "replayCompletesWithoutStaticReset": true
    }}}
  ]
}
"""
    )
    lineage = tmp_path / "lineage.json"
    lineage.write_text(
        """
{
  "assistant_response_plan": {"turn_id": "turn-1"},
  "chat_render_receipt": {"turn_id": "turn-1", "audio_artifact_id": "audio-1"},
  "extract_entities_receipt": {"entities": [{"id": "horus_lupercal"}]},
  "entity_underline_render_receipt": {"rendered_entity_count": 1}
}
"""
    )

    audit = build_audit(
        {"sessions": [_session("passed"), _session("passed")]},
        [gate, lineage],
        marker_glob=str(tmp_path / "no-markers-*.json"),
    )

    assert audit["ok"] is True
    assert audit["failed_gates"] == []
    assert audit["lineage_candidate_count"] == 1
    assert audit["entity_underline_candidate_count"] == 1
