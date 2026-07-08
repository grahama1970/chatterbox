from pathlib import Path

from scripts.audit_embry_replay_evidence import audit_candidate, build_audit


def test_replay_audit_rejects_ui_only_dynamic_replay(tmp_path: Path) -> None:
    proof_path = tmp_path / "dynamic-replay-proof.json"
    proof = {
        "audioCount": 3,
        "screenshot": "/tmp/replay.png",
        "assertions": {
            "dynamicReplayReducedToCurrentTurn": True,
            "audioArtifactsEmbeddedInSharedChat": True,
            "liveReasoningTraceVisibleDuringReplay": True,
            "replayCompletesWithoutStaticReset": True,
        },
    }

    result = audit_candidate(proof_path, proof)

    assert result["ok"] is False
    assert "session_id" in result["missing_fields"]
    assert "event_journal.path" in result["missing_fields"]
    assert "event_journal.required_event_types" in result["missing_fields"]
    assert result["observed"]["legacy_audio_count"] == 3


def test_replay_audit_accepts_event_sourced_replay_receipt(tmp_path: Path) -> None:
    journal = tmp_path / "events.ndjson"
    event_types = [
        "listener.audio_frame_received",
        "stt.final",
        "speaker_gate.accepted",
        "memory.intent",
        "tau.voice_render_request",
        "chatterbox.audio_artifact",
        "audio.playback_started",
        "chat.turn_rendered",
    ]
    journal.write_text("\n".join(f'{{"type": "{event_type}"}}' for event_type in event_types) + "\n")
    receipt = {
        "session_id": "session-1",
        "event_journal": {
            "path": str(journal),
            "sha256": "a" * 64,
            "event_count": len(event_types),
        },
        "replay": {
            "turn_ids": ["turn-1", "turn-2"],
            "audio_artifact_ids": ["audio-1", "audio-2"],
            "original_timing_offsets_ms": [0, 1200],
            "rendered_timing_offsets_ms": [0, 1200],
            "chat_snapshots_match": True,
            "audio_offsets_match": True,
            "turn_order_matches": True,
        },
    }

    result = audit_candidate(tmp_path / "receipt.json", receipt)

    assert result["ok"] is True
    assert result["missing_fields"] == []
    assert result["observed"]["loaded_event_count"] == len(event_types)


def test_build_audit_fails_without_passing_event_sourced_candidate(tmp_path: Path) -> None:
    proof_path = tmp_path / "ui-only.json"
    proof_path.write_text('{"audioCount": 3, "assertions": {"dynamicReplayReducedToCurrentTurn": true}}')

    audit = build_audit([proof_path])

    assert audit["ok"] is False
    assert audit["status"] == "failed"
    assert audit["passing_candidate_count"] == 0
    assert "event_sourced_replay_receipt_present" in audit["failed_gates"]


def test_build_audit_passes_with_event_sourced_candidate(tmp_path: Path) -> None:
    journal = tmp_path / "events.ndjson"
    event_types = [
        "listener.audio_frame_received",
        "stt.final",
        "speaker_gate.accepted",
        "memory.intent",
        "tau.voice_render_request",
        "chatterbox.audio_artifact",
        "audio.playback_started",
        "chat.turn_rendered",
    ]
    journal.write_text("\n".join(f'{{"type": "{event_type}"}}' for event_type in event_types) + "\n")
    proof_path = tmp_path / "receipt.json"
    proof_path.write_text(
        """
{
  "session_id": "session-1",
  "event_journal": {
    "path": "%s",
    "sha256": "%s",
    "event_count": %d
  },
  "replay": {
    "turn_ids": ["turn-1"],
    "audio_artifact_ids": ["audio-1"],
    "original_timing_offsets_ms": [0],
    "rendered_timing_offsets_ms": [0],
    "chat_snapshots_match": true,
    "audio_offsets_match": true,
    "turn_order_matches": true
  }
}
"""
        % (journal, "a" * 64, len(event_types))
    )

    audit = build_audit([proof_path])

    assert audit["ok"] is True
    assert audit["status"] == "passed"
    assert audit["failed_gates"] == []


def test_build_audit_keeps_legacy_failures_visible_without_failing_current_receipt(tmp_path: Path) -> None:
    legacy_path = tmp_path / "ui-only.json"
    legacy_path.write_text('{"audioCount": 3, "assertions": {"dynamicReplayReducedToCurrentTurn": true}}')
    journal = tmp_path / "events.ndjson"
    event_types = [
        "listener.audio_frame_received",
        "stt.final",
        "speaker_gate.accepted",
        "memory.intent",
        "tau.voice_render_request",
        "chatterbox.audio_artifact",
        "audio.playback_started",
        "chat.turn_rendered",
    ]
    journal.write_text("\n".join(f'{{"type": "{event_type}"}}' for event_type in event_types) + "\n")
    proof_path = tmp_path / "receipt.json"
    proof_path.write_text(
        """
{
  "session_id": "session-1",
  "event_journal": {
    "path": "%s",
    "sha256": "%s",
    "event_count": %d
  },
  "replay": {
    "turn_ids": ["turn-1"],
    "audio_artifact_ids": ["audio-1"],
    "original_timing_offsets_ms": [0],
    "rendered_timing_offsets_ms": [0],
    "chat_snapshots_match": true,
    "audio_offsets_match": true,
    "turn_order_matches": true
  }
}
"""
        % (journal, "a" * 64, len(event_types))
    )

    audit = build_audit([legacy_path, proof_path])

    assert audit["ok"] is True
    assert audit["status"] == "passed"
    assert audit["passing_candidate_count"] == 1
    assert audit["failed_gates"] == []
    assert audit["candidates"][0]["ok"] is False
    assert audit["candidates"][1]["ok"] is True
