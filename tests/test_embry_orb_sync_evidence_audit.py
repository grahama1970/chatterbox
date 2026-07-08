from pathlib import Path

from scripts.audit_embry_orb_sync_evidence import audit_candidate, build_audit


def test_orb_audit_rejects_screenshot_only_marker(tmp_path: Path) -> None:
    screenshot = tmp_path / "orb.png"
    screenshot.write_bytes(b"fake png")
    marker_path = tmp_path / "embry-orb.latest.json"
    marker = {
        "name": "embry-orb",
        "url": "http://localhost:3002/#embry-voice",
        "screenshot": str(screenshot),
        "verified_at": "2026-07-08T00:00:00Z",
    }

    result = audit_candidate(marker_path, marker)

    assert result["ok"] is False
    assert "turn_id" in result["missing_fields"]
    assert "audio_artifact_id" in result["missing_fields"]
    assert "orb.envelope_frame_count" in result["missing_fields"]
    assert result["observed"]["screenshot_exists"] is True


def test_orb_audit_accepts_linked_turn_audio_envelope_receipt(tmp_path: Path) -> None:
    screenshot = tmp_path / "orb.png"
    screenshot.write_bytes(b"fake png")
    marker_path = tmp_path / "embry-orb.latest.json"
    receipt_path = tmp_path / "orb-sync-receipt.json"
    receipt_path.write_text(
        """
{
  "turn_id": "turn-123",
  "audio_artifact_id": "audio-456",
  "playback": {
    "audio_artifact_id": "audio-456",
    "started_at_epoch_ms": 1783291077744
  },
  "orb": {
    "authority": "server-envelope",
    "envelope_frame_count": 363,
    "max_level": 0.615
  },
  "screenshot": {
    "path": "%s"
  }
}
"""
        % screenshot
    )
    marker = {
        "name": "embry-orb",
        "orb_sync_receipt": str(receipt_path),
        "screenshot": str(screenshot),
    }

    result = audit_candidate(marker_path, marker)

    assert result["ok"] is True
    assert result["missing_fields"] == []
    assert result["observed"]["turn_id"] == "turn-123"
    assert result["observed"]["orb_envelope_frame_count"] == 363


def test_build_audit_fails_without_any_passing_candidate(tmp_path: Path) -> None:
    marker_path = tmp_path / "missing-fields.latest.json"
    marker_path.write_text("{}")

    audit = build_audit([marker_path])

    assert audit["ok"] is False
    assert audit["status"] == "failed"
    assert audit["passing_candidate_count"] == 0
    assert "orb_sync_turn_audio_envelope_receipt_present" in audit["failed_gates"]


def test_build_audit_passes_with_one_valid_candidate(tmp_path: Path) -> None:
    screenshot = tmp_path / "orb.png"
    screenshot.write_bytes(b"fake png")
    receipt_path = tmp_path / "orb-sync-receipt.json"
    receipt_path.write_text(
        """
{
  "turn_id": "turn-123",
  "audio_artifact_id": "audio-456",
  "playback": {
    "audio_artifact_id": "audio-456",
    "started_at_epoch_ms": 1783291077744
  },
  "orb": {
    "authority": "server-envelope",
    "envelope_frame_count": 363,
    "max_level": 0.615
  },
  "screenshot": {
    "path": "%s"
  }
}
"""
        % screenshot
    )
    marker_path = tmp_path / "valid.latest.json"
    marker_path.write_text('{"orb_sync_receipt": "%s"}' % receipt_path)

    audit = build_audit([marker_path])

    assert audit["ok"] is True
    assert audit["status"] == "passed"
    assert audit["passing_candidate_count"] == 1
    assert audit["failed_gates"] == []
