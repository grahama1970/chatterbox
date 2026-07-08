from pathlib import Path

from scripts.audit_embry_chatterbox_speech_evidence import build_audit, classify_proof


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
            _session("tone_emotion", "passed"),
            _session("interruption", "passed"),
        ]
    }


def test_classify_tau_voice_render_audio_and_delivery_gap() -> None:
    receipt = {
        "schema": "chatterbox.tau_voice_render_smoke.v1",
        "ok": True,
        "live": True,
        "mocked": False,
        "artifacts": {
            "finished_response_audio_metrics": {
                "exists": True,
                "bytes": 10,
                "duration_seconds": 1.0,
            }
        },
        "response": {
            "voice_delivery": {
                "tone": "memory_confident",
                "delivery_stage": "satisfied",
                "pace": None,
                "pause_strategy": None,
                "source": None,
            }
        },
    }

    candidate = classify_proof(Path("/tmp/tau.json"), receipt)

    assert candidate["proof_type"] == "tau_voice_render"
    assert candidate["render_audio_ok"] is True
    assert candidate["qra_disabled_normal_render_ok"] is False
    assert candidate["voice_delivery_missing_fields"] == ["pace", "pause_strategy", "source"]


def test_classify_qra_disabled_normal_render_candidate() -> None:
    receipt = {
        "schema": "chatterbox.tau_voice_render_smoke.v1",
        "ok": True,
        "live": True,
        "mocked": False,
        "request": {"use_blessed_qra_cache": False},
        "response": {
            "blessed_qra_cache": {"enabled": False, "hit": False},
            "voice_delivery": {
                "tone": "memory_confident",
                "delivery_stage": "satisfied",
                "pace": None,
                "pause_strategy": None,
                "source": None,
            },
        },
        "artifacts": {
            "finished_response_audio_metrics": {
                "exists": True,
                "bytes": 10,
                "duration_seconds": 1.0,
            }
        },
    }

    candidate = classify_proof(Path("/tmp/qra-disabled.json"), receipt)

    assert candidate["render_audio_ok"] is True
    assert candidate["qra_disabled_normal_render_ok"] is True
    assert candidate["voice_delivery_missing_fields"] == ["pace", "pause_strategy", "source"]


def test_classify_personality_audition_played_variants() -> None:
    receipt = {
        "schema": "chatterbox.embry_personality_audition.v1",
        "ok": True,
        "live": True,
        "mocked": False,
        "variants": [
            {"render": {"returncode": 0}, "play": {"returncode": 0}},
            {"render": {"returncode": 0}, "play": {"returncode": 0}},
            {"render": {"returncode": 0}, "play": {"returncode": 0}},
            {"render": {"returncode": 0}, "play": {"returncode": 0}},
            {"render": {"returncode": 0}, "play": {"returncode": 0}},
        ],
    }

    candidate = classify_proof(Path("/tmp/personality.json"), receipt)

    assert candidate["proof_type"] == "personality_audition"
    assert candidate["played_variant_count"] == 5


def test_audit_fails_when_tone_and_interruption_matrix_fail(tmp_path: Path) -> None:
    render = tmp_path / "render.json"
    render.write_text(
        """
{
  "schema": "chatterbox.tau_voice_render_smoke.v1",
  "ok": true,
  "live": true,
  "mocked": false,
  "artifacts": {"finished_response_audio_metrics": {"exists": true, "bytes": 10, "duration_seconds": 1.0}},
  "response": {"voice_delivery": {"tone": "memory_confident", "delivery_stage": "satisfied", "pace": "brief", "pause_strategy": "short_answer_no_filler", "source": "memory.intent"}}
}
"""
    )
    qra = tmp_path / "qra.json"
    qra.write_text('{"qra_id":"qra","ok":true,"live":true,"mocked":false,"variant_count":5}')
    personality = tmp_path / "personality.json"
    personality.write_text(
        """
{
  "schema": "chatterbox.embry_personality_audition.v1",
  "ok": true,
  "live": true,
  "mocked": false,
  "variants": [
    {"render": {"returncode": 0}, "play": {"returncode": 0}},
    {"render": {"returncode": 0}, "play": {"returncode": 0}},
    {"render": {"returncode": 0}, "play": {"returncode": 0}},
    {"render": {"returncode": 0}, "play": {"returncode": 0}},
    {"render": {"returncode": 0}, "play": {"returncode": 0}}
  ]
}
"""
    )
    matrix = {
        "sessions": [
            _session("tone_emotion", "failed", ["voice_delivery_tone_expected_firm_boundary_or_one_at_a_time_interrupt"]),
            _session("interruption", "failed", ["interruption_detected_receipt_not_emitted"]),
        ]
    }

    audit = build_audit(matrix, [render, qra, personality])

    assert audit["ok"] is False
    assert audit["live_render_candidate_count"] == 1
    assert audit["qra_variant_candidate_count"] == 1
    assert audit["qra_disabled_normal_render_candidate_count"] == 0
    assert audit["audible_personality_candidate_count"] == 1
    assert "tone_emotion_matrix_has_failures" in audit["failed_gates"]
    assert "interruption_matrix_has_failures" in audit["failed_gates"]


def test_audit_passes_when_all_speech_evidence_and_matrix_rows_pass(tmp_path: Path) -> None:
    render = tmp_path / "render.json"
    render.write_text(
        """
{
  "schema": "chatterbox.tau_voice_render_smoke.v1",
  "ok": true,
  "live": true,
  "mocked": false,
  "artifacts": {"finished_response_audio_metrics": {"exists": true, "bytes": 10, "duration_seconds": 1.0}},
  "response": {"voice_delivery": {"tone": "memory_confident", "delivery_stage": "satisfied", "pace": "brief", "pause_strategy": "short_answer_no_filler", "source": "memory.intent"}}
}
"""
    )
    qra = tmp_path / "qra.json"
    qra.write_text('{"qra_id":"qra","ok":true,"live":true,"mocked":false,"variant_count":5}')
    personality = tmp_path / "personality.json"
    personality.write_text(
        """
{
  "schema": "chatterbox.embry_personality_audition.v1",
  "ok": true,
  "live": true,
  "mocked": false,
  "variants": [
    {"render": {"returncode": 0}, "play": {"returncode": 0}},
    {"render": {"returncode": 0}, "play": {"returncode": 0}},
    {"render": {"returncode": 0}, "play": {"returncode": 0}},
    {"render": {"returncode": 0}, "play": {"returncode": 0}},
    {"render": {"returncode": 0}, "play": {"returncode": 0}}
  ]
}
"""
    )

    audit = build_audit(_passing_matrix(), [render, qra, personality])

    assert audit["ok"] is True
    assert audit["failed_gates"] == []
    assert audit["speech_matrix"]["status_counts"] == {"passed": 2, "failed": 0, "not_run": 0}
