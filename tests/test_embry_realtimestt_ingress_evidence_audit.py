from pathlib import Path

from scripts.audit_embry_realtimestt_ingress_evidence import build_audit, classify_proof, extract_transcript


def _matrix_with_factory(statuses: list[str]) -> dict:
    return {
        "sessions": [
            {
                "id": f"factory-{index}",
                "difficulty": "simple",
                "folder_id": "factory_noise",
                "status": status,
                "latest_receipt": f"/tmp/factory-{index}.json",
                "failed_gates": [] if status == "passed" else ["capture_captured_audio_rms"],
                "observed": "factory row",
            }
            for index, status in enumerate(statuses)
        ]
    }


def test_classify_browser_getusermedia_success() -> None:
    receipt = {
        "ok": True,
        "live": True,
        "mocked": False,
        "proof_scope": "browser_getusermedia_to_realtimestt_to_speaker_memory_tau_chatterbox_receipt_bundle",
        "transcript": "hello from browser",
        "claims": {
            "proves": ["browser_getusermedia_audio_can_feed_realtimestt_external_audio_listener"],
        },
    }

    candidate = classify_proof(Path("/tmp/browser.json"), receipt)

    assert candidate["transport"] == "browser_getusermedia"
    assert candidate["ingress_proven"] is True
    assert candidate["transcript_present"] is True


def test_classify_loopback_wrapper_extracts_embedded_realtimestt_child_transcript() -> None:
    receipt = {
        "ok": True,
        "live": True,
        "mocked": False,
        "capture": {"captured_audio": {"exists": True, "rms": 512}},
        "children": {
            "realtimestt": {
                "receipt": {
                    "transcript": {"text": "embry ingress proof alpha seven"},
                    "asr_executor_calls": [
                        {"transcript": "embry ingress proof alpha seven"},
                    ],
                }
            }
        },
        "claims": {
            "proves": [
                "pipewire_monitor_loopback_captures_played_stress_audio",
                "captured_loopback_audio_feeds_realtimestt_automatic_vad",
            ],
        },
    }

    assert extract_transcript(receipt) == "embry ingress proof alpha seven"
    candidate = classify_proof(Path("/tmp/rung8-loopback-listener.json"), receipt)

    assert candidate["transport"] == "pipewire_monitor_loopback"
    assert candidate["ingress_proven"] is True
    assert candidate["transcript_present"] is True
    assert candidate["asr_executor_call_count"] == 1


def test_ingress_audit_fails_when_current_factory_matrix_fails() -> None:
    matrix = _matrix_with_factory(["failed", "failed"])
    proof_path = Path("/tmp/browser.json")
    audit = build_audit(
        matrix,
        proof_paths=[],
    )

    assert audit["ok"] is False
    assert "current_factory_matrix_has_failures" in audit["failed_gates"]
    assert "current_factory_matrix_has_no_passes" in audit["failed_gates"]
    assert audit["current_factory_matrix"]["status_counts"] == {
        "passed": 0,
        "failed": 2,
        "not_run": 0,
    }
    assert str(proof_path) not in {candidate["path"] for candidate in audit["historical_candidates"]}


def test_ingress_audit_counts_current_factory_loopback_candidate_even_when_matrix_rows_fail(tmp_path: Path) -> None:
    proof = tmp_path / "20260708T034407Z-factory-current" / "S06-factory-noise" / "rung8-loopback-listener.json"
    proof.parent.mkdir(parents=True)
    proof.write_text(
        """
{
  "ok": true,
  "live": true,
  "mocked": false,
  "capture": {
    "captured_audio": {
      "exists": true,
      "rms": 512
    }
  },
  "claims": {
    "proves": [
      "pipewire_monitor_loopback_captures_played_stress_audio",
      "captured_loopback_audio_feeds_realtimestt_automatic_vad"
    ]
  },
  "children": {
    "realtimestt": {
      "receipt": {
        "transcript": {"text": "current loopback transcript"}
      }
    }
  }
}
"""
    )

    audit = build_audit(_matrix_with_factory(["failed", "failed"]), [proof])

    assert audit["ok"] is False
    assert audit["live"] is True
    assert audit["current_factory_loopback_passing_candidate_count"] == 1
    assert audit["current_factory_loopback_passing_candidates"][0]["transcript_present"] is True
    assert audit["current_factory_loopback_passing_candidates"][0]["transcript"] == "current loopback transcript"
    assert "current_factory_matrix_has_failures" in audit["failed_gates"]
    assert "current_factory_matrix_has_no_passes" not in audit["failed_gates"]
    assert "current_factory_loopback_pipewire_monitor_realtimestt_slice_passes" in audit["claims"]["proves"]


def test_ingress_audit_reports_browser_device_inconsistency(tmp_path: Path) -> None:
    success = tmp_path / "success.json"
    failure = tmp_path / "failure.json"
    success.write_text(
        """
{
  "ok": true,
  "live": true,
  "mocked": false,
  "proof_scope": "browser_getusermedia_to_realtimestt_to_speaker_memory_tau_chatterbox_receipt_bundle",
  "transcript": "browser success",
  "claims": {"proves": ["browser_getusermedia_audio_can_feed_realtimestt_external_audio_listener"]}
}
"""
    )
    failure.write_text(
        """
{
  "ok": false,
  "live": false,
  "mocked": false,
  "proof_scope": "browser_getusermedia_to_realtimestt_to_speaker_memory_tau_chatterbox_receipt_bundle",
  "transcript": "",
  "failed_gates": ["listener_transcript_present"],
  "claims": {"proves": []}
}
"""
    )

    audit = build_audit(_matrix_with_factory(["passed"]), [success, failure])

    assert audit["ok"] is False
    assert audit["historical_passing_candidate_count"] == 1
    assert "browser_device_ingress_inconsistent" in audit["failed_gates"]


def test_ingress_audit_passes_when_history_and_current_matrix_pass(tmp_path: Path) -> None:
    success = tmp_path / "success.json"
    success.write_text(
        """
{
  "ok": true,
  "live": true,
  "mocked": false,
  "proof_scope": "browser_getusermedia_to_realtimestt_to_speaker_memory_tau_chatterbox_receipt_bundle",
  "transcript": "browser success",
  "claims": {"proves": ["browser_getusermedia_audio_can_feed_realtimestt_external_audio_listener"]}
}
"""
    )

    audit = build_audit(_matrix_with_factory(["passed", "passed"]), [success])

    assert audit["ok"] is True
    assert audit["status"] == "passed"
    assert audit["failed_gates"] == []
