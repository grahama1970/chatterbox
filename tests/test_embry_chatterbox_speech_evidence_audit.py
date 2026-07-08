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


def test_classify_blessed_qra_cached_response_candidate() -> None:
    receipt = {
        "schema": "chatterbox.tau_voice_render_smoke.v1",
        "ok": True,
        "live": True,
        "mocked": False,
        "request": {"use_blessed_qra_cache": True},
        "response": {
            "blessed_qra_cache": {
                "hit": True,
                "memory_gate": {"passed": True},
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

    candidate = classify_proof(Path("/tmp/qra-cache-hit.json"), receipt)

    assert candidate["blessed_qra_cached_response_ok"] is True


def test_classify_full_voice_delivery_envelope_is_complete() -> None:
    receipt = {
        "schema": "chatterbox.tau_voice_render_smoke.v1",
        "ok": True,
        "live": True,
        "mocked": False,
        "response": {
            "voice_delivery": {
                "tone": "memory_confident",
                "delivery_stage": "neutral",
                "pace": "measured",
                "pause_strategy": "short_answer_no_filler",
                "source": "memory.intent",
            }
        },
        "artifacts": {
            "finished_response_audio_metrics": {
                "exists": True,
                "bytes": 10,
                "duration_seconds": 1.0,
            }
        },
    }

    candidate = classify_proof(Path("/tmp/full-delivery.json"), receipt)

    assert candidate["render_audio_ok"] is True
    assert candidate["voice_delivery_missing_fields"] == []


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


def test_classify_non_primary_interruption_suppression_receipt() -> None:
    receipt = {
        "schema": "chatterbox.conversation_ladder.rung4.v1",
        "ok": True,
        "live": True,
        "mocked": False,
        "speaker_gate": {
            "enabled": True,
            "expected_primary_speaker": False,
            "suppressed": True,
            "reason": "non_primary_speaker",
        },
        "listener_interruption": {
            "speech_detected": True,
            "detected": False,
            "suppressed": True,
            "suppression_reason": "non_primary_speaker",
            "primary_speaker_match": False,
        },
        "interruption": None,
        "turn_controls": None,
    }

    candidate = classify_proof(Path("/tmp/rung4-nonprimary.json"), receipt)

    assert candidate["proof_type"] == "conversation_ladder_rung4"
    assert candidate["non_primary_interrupt_rejection_ok"] is True


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
    qra_cached = tmp_path / "qra-cached.json"
    qra_cached.write_text(
        """
{
  "schema": "chatterbox.tau_voice_render_smoke.v1",
  "ok": true,
  "live": true,
  "mocked": false,
  "request": {"use_blessed_qra_cache": true},
  "response": {"blessed_qra_cache": {"hit": true, "memory_gate": {"passed": true}}},
  "artifacts": {"finished_response_audio_metrics": {"exists": true, "bytes": 10, "duration_seconds": 1.0}}
}
"""
    )
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
    assert audit["live"] is True
    assert audit["live_render_candidate_count"] == 1
    assert audit["qra_variant_candidate_count"] == 1
    assert audit["qra_disabled_normal_render_candidate_count"] == 0
    assert audit["audible_personality_candidate_count"] == 1
    assert audit["complete_delivery_envelope_candidate_count"] == 1
    assert "live_chatterbox_can_render_audio" in audit["claims"]["proves"]
    assert "complete_voice_delivery_envelope_can_reach_chatterbox_chunks" in audit["claims"]["proves"]
    assert "tone_emotion_matrix_has_failures" in audit["failed_gates"]
    assert "interruption_matrix_has_failures" in audit["failed_gates"]


def test_audit_uses_dedicated_interruption_audit_for_covered_barge_in_gates(tmp_path: Path) -> None:
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
    qra_cached = tmp_path / "qra-cached.json"
    qra_cached.write_text(
        """
{
  "schema": "chatterbox.tau_voice_render_smoke.v1",
  "ok": true,
  "live": true,
  "mocked": false,
  "request": {"use_blessed_qra_cache": true},
  "response": {"blessed_qra_cache": {"hit": true, "memory_gate": {"passed": true}}},
  "artifacts": {"finished_response_audio_metrics": {"exists": true, "bytes": 10, "duration_seconds": 1.0}}
}
"""
    )
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
    interruption_audit = tmp_path / "interruption-audit.json"
    interruption_audit.write_text(
        """
{
  "ok": true,
  "status": "passed",
  "live": true,
  "mocked": false,
  "passing_candidate_count": 1,
  "best_candidate_paths": ["/tmp/live-horus-barge-in.json"]
}
"""
    )
    non_primary = tmp_path / "non-primary.json"
    non_primary.write_text(
        """
{
  "schema": "chatterbox.conversation_ladder.rung4.v1",
  "ok": true,
  "live": true,
  "mocked": false,
  "speaker_gate": {"enabled": true, "expected_primary_speaker": false, "suppressed": true},
  "listener_interruption": {"speech_detected": true, "detected": false, "suppressed": true},
  "interruption": null,
  "turn_controls": null
}
"""
    )
    matrix = {
        "sessions": [
            _session("tone_emotion", "passed"),
            _session(
                "interruption",
                "failed",
                [
                    "interruption_detected_receipt_not_emitted",
                    "new_horus_turn_not_exercised",
                    "new_turn_wins_receipt_not_emitted",
                    "speaker_gate_receipt_not_linked_to_turn_control",
                    "stale_audio_stream_bytes_not_measured",
                    "non_primary_interrupt_rejection_not_exercised",
                    "natural_stop_phrase_not_observed",
                ],
            ),
        ]
    }

    audit = build_audit(matrix, [render, qra, qra_cached, personality, non_primary], interruption_audit_path=interruption_audit)

    assert audit["ok"] is False
    assert audit["interruption_evidence_audit"]["ok"] is True
    assert "live_primary_speaker_interruption_barge_in_receipt_present" in audit["claims"]["proves"]
    assert "speech_matrix_gate:interruption_detected_receipt_not_emitted" not in audit["failed_gates"]
    assert "speech_matrix_gate:new_horus_turn_not_exercised" not in audit["failed_gates"]
    assert "speech_matrix_gate:new_turn_wins_receipt_not_emitted" not in audit["failed_gates"]
    assert "speech_matrix_gate:speaker_gate_receipt_not_linked_to_turn_control" not in audit["failed_gates"]
    assert "speech_matrix_gate:stale_audio_stream_bytes_not_measured" not in audit["failed_gates"]
    assert "speech_matrix_gate:non_primary_interrupt_rejection_not_exercised" not in audit["failed_gates"]
    assert "speech_matrix_gate:blessed_qra_cached_response_not_exercised" not in audit["failed_gates"]
    assert "speech_matrix_gate:natural_stop_phrase_not_observed" in audit["failed_gates"]
    assert audit["interruption_matrix_remaining_failed_gates"] == ["natural_stop_phrase_not_observed"]
    assert audit["non_primary_interrupt_rejection_candidate_count"] == 1
    assert audit["blessed_qra_cached_response_candidate_count"] == 1


def test_audit_uses_speaker_identity_audit_for_overlap_tone_gate(tmp_path: Path) -> None:
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
    speaker_identity_audit = tmp_path / "speaker-identity-audit.json"
    speaker_identity_audit.write_text(
        """
{
  "ok": false,
  "status": "failed",
  "live": true,
  "mocked": false,
  "claims": {
    "proves": ["pyannote_overlap_detection_routes_to_one_at_a_time_turn_control"]
  }
}
"""
    )
    matrix = {
        "sessions": [
            _session(
                "tone_emotion",
                "failed",
                [
                    "voice_delivery_tone_expected_firm_boundary_or_one_at_a_time_interrupt",
                    "voice_delivery_tone_expected_deflect_calm_or_firm_boundary_or_playful_light",
                ],
            ),
            _session("interruption", "passed"),
        ]
    }

    audit = build_audit(
        matrix,
        [render, qra, personality],
        speaker_identity_audit_path=speaker_identity_audit,
    )

    assert audit["ok"] is False
    assert audit["speaker_identity_evidence_audit"]["overlap_one_at_a_time_ok"] is True
    assert "pyannote_overlap_routes_to_one_at_a_time_voice_delivery" in audit["claims"]["proves"]
    assert "speech_matrix_gate:voice_delivery_tone_expected_firm_boundary_or_one_at_a_time_interrupt" not in audit["failed_gates"]
    assert "speech_matrix_gate:voice_delivery_tone_expected_deflect_calm_or_firm_boundary_or_playful_light" in audit["failed_gates"]
    assert audit["tone_emotion_matrix_remaining_failed_gates"] == [
        "voice_delivery_tone_expected_deflect_calm_or_firm_boundary_or_playful_light"
    ]


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
    assert audit["live"] is True
    assert audit["failed_gates"] == []
    assert audit["speech_matrix"]["status_counts"] == {"passed": 2, "failed": 0, "not_run": 0}
    assert audit["complete_delivery_envelope_candidate_count"] == 1
