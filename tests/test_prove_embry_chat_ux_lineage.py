from pathlib import Path

from scripts.prove_embry_chat_ux_lineage import build_receipt


def test_lineage_receipt_fails_when_audio_and_message_lack_turn_ids() -> None:
    receipt = build_receipt(
        run_id="test",
        url="http://localhost:3002/#embry-voice",
        chat_messages=[
            {
                "qid": "shared-chat:message:assistant",
                "turn_id": None,
                "entity_span_count": 0,
                "audio_artifact_count": 1,
                "text": "Embry response",
            }
        ],
        audio_artifacts=[
            {
                "qid": None,
                "turn_id": None,
                "parent_message_qid": "shared-chat:message:assistant",
                "parent_turn_id": None,
                "src": "/audio.wav",
            }
        ],
        screenshot_path=Path("/tmp/lineage.png"),
    )

    assert receipt["ok"] is False
    assert receipt["lineage_ready"] is False
    assert receipt["entity_underlines_ready"] is False
    assert "assistant_message_turn_id_missing" in receipt["failed_gates"]
    assert "audio_artifact_turn_id_missing" in receipt["failed_gates"]
    assert "chat_text_audio_same_turn_id_not_proven" in receipt["failed_gates"]
    assert "entity_underlines_not_rendered_in_assistant_message" in receipt["failed_gates"]


def test_lineage_receipt_passes_when_same_turn_and_entities_are_rendered() -> None:
    receipt = build_receipt(
        run_id="test",
        url="http://localhost:3002/#embry-voice",
        chat_messages=[
            {
                "qid": "shared-chat:message:assistant",
                "turn_id": "turn-1",
                "entity_span_count": 2,
                "audio_artifact_count": 1,
                "text": "Embry response",
            }
        ],
        audio_artifacts=[
            {
                "qid": "audio-1",
                "turn_id": "turn-1",
                "parent_message_qid": "shared-chat:message:assistant",
                "parent_turn_id": "turn-1",
                "src": "/audio.wav",
            }
        ],
        screenshot_path=Path("/tmp/lineage.png"),
    )

    assert receipt["ok"] is True
    assert receipt["lineage_ready"] is True
    assert receipt["entity_underlines_ready"] is True
    assert receipt["failed_gates"] == []
