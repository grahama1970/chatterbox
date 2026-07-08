from pathlib import Path

from scripts.audit_embry_interruption_evidence import audit_candidate, build_audit


def test_interruption_audit_rejects_stream_cancel_only_receipt(tmp_path: Path) -> None:
    receipt = {
        "ok": True,
        "live": True,
        "mocked": False,
        "proof_scope": "pre_cancelled_turn_stream_suppression",
        "turn_id": "turn-old",
        "old_turn_bytes_after_cancel": 0,
        "cancel": {"control": {"cancelled": True, "stale_chunks_should_skip": True}},
    }

    result = audit_candidate(tmp_path / "stream-cancel.json", receipt)

    assert result["ok"] is False
    assert "listener_interruption.detected" in result["missing_fields"]
    assert "embry_playback.offset_ms_at_interrupt" in result["missing_fields"]
    assert "new_turn.wins" in result["missing_fields"]
    assert result["observed"]["old_turn_bytes_after_cancel"] == 0


def test_interruption_audit_accepts_live_barge_in_receipt(tmp_path: Path) -> None:
    receipt = {
        "turn_id": "turn-old",
        "old_turn_id": "turn-old",
        "new_turn_id": "turn-new",
        "embry_playback": {
            "audio_artifact_id": "audio-old",
            "started_at_epoch_ms": 1783291077744,
            "offset_ms_at_interrupt": 2410,
        },
        "listener_interruption": {
            "detected": True,
            "speaker_id": "horus_lupercal",
            "primary_speaker_match": True,
        },
        "turn_control": {
            "cancelled": True,
            "stopped": True,
            "stale_chunks_should_skip": True,
        },
        "stale_audio": {"old_turn_bytes_after_cancel": 0},
        "new_turn": {"wins": True, "response_started": True},
    }

    result = audit_candidate(tmp_path / "barge-in.json", receipt)

    assert result["ok"] is True
    assert result["missing_fields"] == []
    assert result["observed"]["listener_speaker_id"] == "horus_lupercal"
    assert result["observed"]["new_turn_wins"] is True


def test_build_audit_fails_without_live_barge_in_candidate(tmp_path: Path) -> None:
    proof = tmp_path / "stream-cancel.json"
    proof.write_text(
        '{"turn_id":"turn-old","old_turn_bytes_after_cancel":0,'
        '"cancel":{"control":{"cancelled":true,"stale_chunks_should_skip":true}}}'
    )

    audit = build_audit([proof])

    assert audit["ok"] is False
    assert audit["status"] == "failed"
    assert audit["passing_candidate_count"] == 0
    assert "live_barge_in_receipt_present" in audit["failed_gates"]


def test_build_audit_passes_with_live_barge_in_candidate(tmp_path: Path) -> None:
    proof = tmp_path / "barge-in.json"
    proof.write_text(
        """
{
  "turn_id": "turn-old",
  "old_turn_id": "turn-old",
  "new_turn_id": "turn-new",
  "embry_playback": {
    "audio_artifact_id": "audio-old",
    "started_at_epoch_ms": 1783291077744,
    "offset_ms_at_interrupt": 2410
  },
  "listener_interruption": {
    "detected": true,
    "speaker_id": "horus_lupercal",
    "primary_speaker_match": true
  },
  "turn_control": {
    "cancelled": true,
    "stopped": true,
    "stale_chunks_should_skip": true
  },
  "stale_audio": {"old_turn_bytes_after_cancel": 0},
  "new_turn": {"wins": true, "response_started": true}
}
"""
    )

    audit = build_audit([proof])

    assert audit["ok"] is True
    assert audit["status"] == "passed"
    assert audit["failed_gates"] == []
