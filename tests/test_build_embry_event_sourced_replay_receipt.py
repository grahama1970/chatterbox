import json
import wave
from pathlib import Path

from scripts.build_embry_event_sourced_replay_receipt import build_receipt


def _tiny_wav(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(24000)
        handle.writeframes(b"\x00\x01" * 240)


def test_build_replay_receipt_from_interruption_smoke(tmp_path: Path) -> None:
    out_root = tmp_path / "out"
    _tiny_wav(out_root / "interruption_smoke_old_answer_1.wav")
    _tiny_wav(out_root / "interruption_smoke_interrupt_ack.wav")
    _tiny_wav(out_root / "interruption_smoke_new_answer_1.wav")
    events = [
        {"sequence": 6, "type": "speech.played", "turn_id": "turn-old", "artifact_path": "/out/interruption_smoke_old_answer_1.wav"},
        {"sequence": 7, "type": "interruption.requested", "turn_id": "turn-old", "new_turn_id": "turn-new", "old_turn_id": "turn-old"},
        {"sequence": 14, "type": "speech.played", "turn_id": "turn-new", "artifact_path": "/out/interruption_smoke_interrupt_ack.wav"},
        {"sequence": 17, "type": "speech.played", "turn_id": "turn-new", "artifact_path": "/out/interruption_smoke_new_answer_1.wav"},
    ]
    source_dir = out_root / "interruption-current" / "run-1"
    source_dir.mkdir(parents=True)
    events_path = source_dir / "task-events.jsonl"
    events_path.write_text("\n".join(json.dumps(event) for event in events) + "\n")
    source = source_dir / "final-response.json"
    source.write_text(
        json.dumps(
            {
                "conversation_id": "embry-interruption-smoke",
                "events_path": str(events_path),
                "old_turn_id": "turn-old",
                "new_turn_id": "turn-new",
                "interrupt_text": "Wait, stop.",
                "stale_skipped_count": 2,
                "interruption_timeline": {"cancel_received_seq": 7},
                "new_plan": {"answer_text_sha256": "a" * 64},
            }
        )
    )

    receipt = build_receipt(source, tmp_path / "replay")

    assert receipt["ok"] is True
    assert receipt["mocked"] is False
    assert receipt["live"] is True
    assert receipt["session_id"] == "embry-interruption-smoke"
    assert receipt["event_journal"]["event_count"] >= 8
    assert receipt["event_journal"]["validation_failures"] == []
    assert receipt["replay"]["turn_ids"] == ["turn-old", "turn-new"]
    assert len(receipt["replay"]["audio_artifact_ids"]) == 3
    assert receipt["replay"]["chat_snapshots_match"] is True
