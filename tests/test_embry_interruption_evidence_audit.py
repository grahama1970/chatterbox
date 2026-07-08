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
    assert audit["live"] is False
    assert audit["passing_candidate_count"] == 0
    assert "live_barge_in_receipt_present" in audit["failed_gates"]


def test_interruption_audit_normalizes_legacy_timeline_but_keeps_listener_gap(tmp_path: Path) -> None:
    events = tmp_path / "task-events.jsonl"
    events.write_text(
        "\n".join(
            [
                '{"type":"speech.played","turn_id":"turn-old","artifact_path":"/out/old.wav","timestamp":"2026-07-08T03:47:55Z"}',
                '{"type":"interruption.requested","turn_id":"turn-old","timestamp":"2026-07-08T03:47:56Z"}',
                '{"type":"playback.stopped","turn_id":"turn-old"}',
                '{"type":"speech.stale_skipped","turn_id":"turn-old"}',
            ]
        )
        + "\n"
    )
    receipt = {
        "ok": True,
        "live": True,
        "mocked": False,
        "events_path": str(events),
        "stale_skipped_count": 2,
        "interruption_timeline": {
            "old_turn_id": "turn-old",
            "new_turn_id": "turn-new",
            "post_cancel_old_turn_audio_bytes_emitted": 0,
            "new_turn_audio_started_after_cancel": True,
        },
    }

    result = audit_candidate(tmp_path / "final-response.json", receipt)

    assert result["ok"] is False
    assert result["observed"]["old_turn_id"] == "turn-old"
    assert result["observed"]["new_turn_id"] == "turn-new"
    assert result["observed"]["old_turn_bytes_after_cancel"] == 0
    assert result["observed"]["new_turn_wins"] is True
    assert result["observed"]["turn_control_stopped"] is True
    assert result["observed"]["turn_control_stale_chunks_should_skip"] is True
    assert result["observed"]["playback_offset_ms_at_interrupt"] == 1000
    assert result["chatterbox_turn_control_ok"] is True
    assert "embry_playback.audio_artifact_id" not in result["missing_fields"]
    assert "embry_playback.started_at_epoch_ms" not in result["missing_fields"]
    assert "embry_playback.offset_ms_at_interrupt" not in result["missing_fields"]
    assert "listener_interruption.detected" in result["missing_fields"]
    assert "listener_interruption.speaker_id" in result["missing_fields"]


def test_build_audit_counts_chatterbox_turn_control_without_live_listener_barge_in(tmp_path: Path) -> None:
    events = tmp_path / "task-events.jsonl"
    events.write_text(
        "\n".join(
            [
                '{"type":"speech.played","turn_id":"turn-old","artifact_path":"/out/old.wav","timestamp":"2026-07-08T03:47:55Z"}',
                '{"type":"interruption.requested","turn_id":"turn-old","timestamp":"2026-07-08T03:47:56Z"}',
                '{"type":"playback.stopped","turn_id":"turn-old"}',
                '{"type":"speech.stale_skipped","turn_id":"turn-old"}',
            ]
        )
        + "\n"
    )
    proof = tmp_path / "final-response.json"
    proof.write_text(
        f"""
{{
  "ok": true,
  "live": true,
  "mocked": false,
  "events_path": "{events}",
  "stale_skipped_count": 2,
  "interruption_timeline": {{
    "old_turn_id": "turn-old",
    "new_turn_id": "turn-new",
    "post_cancel_old_turn_audio_bytes_emitted": 0,
    "new_turn_audio_started_after_cancel": true
  }}
}}
"""
    )

    audit = build_audit([proof])

    assert audit["ok"] is False
    assert audit["live"] is True
    assert audit["chatterbox_turn_control_candidate_count"] == 1
    assert audit["best_candidate_paths"] == [str(proof)]
    assert "live_barge_in_receipt_present" in audit["failed_gates"]
    assert "chatterbox_turn_control_interruption_receipt_present" not in audit["failed_gates"]
    assert "chatterbox_turn_control_interruption_stops_old_audio_and_starts_new_turn" in audit["claims"]["proves"]


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
    assert audit["live"] is False
    assert audit["status"] == "passed"
    assert audit["failed_gates"] == []
