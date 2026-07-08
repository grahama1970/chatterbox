from pathlib import Path

from scripts.audit_embry_speaker_identity_evidence import build_audit, classify_proof


def _session(status: str, observed: str = "speaker policy row") -> dict:
    return {
        "id": f"speaker-{status}",
        "folder_id": "speaker_identity",
        "difficulty": "simple",
        "status": status,
        "latest_receipt": f"/tmp/speaker-{status}.json",
        "failed_gates": [] if status == "passed" else ["speaker_gate_failed"],
        "observed": observed,
    }


def test_classify_memory_speaker_policy_ledger() -> None:
    receipt = {
        "schema": "embry.proof.receipt.v1",
        "ok": True,
        "live": True,
        "mocked": False,
        "proof_scope": "live_memory_speaker_resolution_policy_not_audio_identity",
        "source_audio_identity_proven": False,
        "cases": [
            {"id": "known_horus", "actual": {"status": "known"}},
            {"id": "unknown_speaker", "actual": {"status": "unknown"}},
            {"id": "ambiguous_low_confidence", "actual": {"status": "ambiguous"}},
            {"id": "overlap_close_scores", "actual": {"status": "ambiguous"}},
        ],
    }

    candidate = classify_proof(Path("/tmp/policy.json"), receipt)

    assert candidate["proof_type"] == "memory_speaker_policy_ledger"
    assert candidate["policy_cases_cover_known_unknown_ambiguous_overlap"] is True
    assert candidate["source_audio_identity_proven"] is False


def test_classify_known_horus_resolution_with_independent_enrollment() -> None:
    receipt = {
        "schema": "chatterbox.conversation_ladder.rung7.listener_contract.v1",
        "ok": True,
        "live": True,
        "mocked": False,
        "speaker_resolution": {
            "status": "known",
            "speaker_id": "horus_lupercal",
            "allow_personal_memory": True,
            "memory_tags": ["speaker:horus_lupercal"],
        },
        "primary_speaker_verification": {
            "enrollment_audio": "/tmp/enroll.wav",
            "candidate_audio": "/tmp/candidate.wav",
            "primary_speaker_match": True,
            "similarity": 0.9,
            "threshold": 0.8,
        },
    }

    candidate = classify_proof(Path("/tmp/known.json"), receipt)

    assert candidate["proof_type"] == "known_horus_listener_memory"
    assert candidate["known_horus_resolution_ok"] is True
    assert candidate["enrollment_independent_from_candidate"] is True


def test_classify_overlap_diarization_turn_control_receipt() -> None:
    receipt = {
        "schema": "chatterbox.overlap_turn_control.v1",
        "ok": True,
        "live": True,
        "mocked": False,
        "claims": {
            "proves": [
                "pyannote_detected_two_anonymous_overlapping_speakers",
                "memory_intent_maps_overlap_to_turn_taking_clarification",
            ]
        },
        "memory_intent": {
            "voice_delivery": {
                "tone": "one_at_a_time_interrupt",
            }
        },
        "tau_voice_render": {"ok": True},
    }

    candidate = classify_proof(Path("/tmp/overlap.json"), receipt)

    assert candidate["proof_type"] == "overlap_diarization_turn_control"
    assert candidate["overlap_diarization_turn_control_ok"] is True


def test_classify_strict_pyannote_two_speaker_receipt() -> None:
    receipt = {
        "schema": "chatterbox.pyannote_diarization_smoke.v1",
        "ok": True,
        "live": True,
        "mocked": False,
        "summary": {
            "speaker_count": 2,
            "exclusive_speaker_count": 1,
            "overlap_seconds": 4.725,
        },
    }

    candidate = classify_proof(Path("/tmp/pyannote.json"), receipt)

    assert candidate["proof_type"] == "pyannote_strict_two_speaker"
    assert candidate["pyannote_strict_two_speaker_ok"] is True
    assert candidate["pyannote_speaker_count"] == 2
    assert candidate["pyannote_exclusive_speaker_count"] == 1
    assert candidate["pyannote_overlap_seconds"] == 4.725


def test_strict_pyannote_one_speaker_receipt_does_not_pass_two_speaker_gate() -> None:
    receipt = {
        "schema": "chatterbox.pyannote_diarization_smoke.v1",
        "ok": True,
        "live": True,
        "mocked": False,
        "summary": {
            "speaker_count": 1,
            "exclusive_speaker_count": 1,
            "overlap_seconds": 0,
        },
    }

    candidate = classify_proof(Path("/tmp/pyannote.json"), receipt)

    assert candidate["proof_type"] == "pyannote_strict_two_speaker"
    assert candidate["pyannote_strict_two_speaker_ok"] is False


def test_audit_fails_when_matrix_passes_but_physical_identity_is_unproven(tmp_path: Path) -> None:
    policy = tmp_path / "policy.json"
    policy.write_text(
        """
{
  "schema": "embry.proof.receipt.v1",
  "ok": true,
  "live": true,
  "mocked": false,
  "proof_scope": "live_memory_speaker_resolution_policy_not_audio_identity",
  "source_audio_identity_proven": false,
  "cases": [
    {"id": "known_horus", "actual": {"status": "known"}},
    {"id": "unknown_speaker", "actual": {"status": "unknown"}},
    {"id": "ambiguous_low_confidence", "actual": {"status": "ambiguous"}},
    {"id": "overlap_close_scores", "actual": {"status": "ambiguous"}}
  ]
}
"""
    )
    fixture = tmp_path / "fixture.json"
    fixture.write_text(
        """
{
  "schema": "chatterbox.primary_speaker_gate_suite.v1",
  "mocked": false,
  "live": false,
  "cases": {
    "primary": {"primary_speaker_match": true},
    "female_alt": {"primary_speaker_match": false},
    "other_male": {"primary_speaker_match": false},
    "background_noise": {"primary_speaker_match": false}
  }
}
"""
    )
    known = tmp_path / "known.json"
    known.write_text(
        """
{
  "schema": "chatterbox.conversation_ladder.rung7.listener_contract.v1",
  "ok": true,
  "live": true,
  "mocked": false,
  "claims": {"does_not_prove": ["physical_speaker_to_microphone_identity_gating"]},
  "speaker_resolution": {
    "status": "known",
    "speaker_id": "horus_lupercal",
    "allow_personal_memory": true,
    "memory_tags": ["speaker:horus_lupercal"]
  },
  "primary_speaker_verification": {
    "enrollment_audio": "/tmp/same.wav",
    "candidate_audio": "/tmp/same.wav",
    "primary_speaker_match": true
  }
}
"""
    )
    unknown = tmp_path / "unknown.json"
    unknown.write_text(
        """
{
  "schema": "chatterbox.conversation_ladder.rung7.listener_contract.v1",
  "ok": true,
  "live": false,
  "mocked": false,
  "speaker_resolution": {
    "status": "unknown",
    "allow_personal_memory": false,
    "identity_prompt": {"text": "Who is this?"}
  }
}
"""
    )

    audit = build_audit(
        {"sessions": [_session("passed", "source_audio_identity_proven=false")]},
        [policy, fixture, known, unknown],
    )

    assert audit["ok"] is False
    assert audit["policy_ledger_candidate_count"] == 1
    assert audit["live"] is True
    assert audit["fixture_gate_candidate_count"] == 1
    assert audit["known_horus_candidate_count"] == 1
    assert audit["unknown_fail_closed_candidate_count"] == 1
    assert "independent_horus_enrollment_receipt_missing" in audit["failed_gates"]
    assert "physical_speaker_to_microphone_identity_gating_not_proven" in audit["failed_gates"]
    assert "matrix_contains_source_audio_identity_unproven_rows" in audit["failed_gates"]
    assert "overlap_diarization_not_proven" in audit["failed_gates"]


def test_audit_passes_only_with_physical_identity_and_overlap_evidence_removed_from_failures(tmp_path: Path) -> None:
    policy = tmp_path / "policy.json"
    policy.write_text(
        """
{
  "schema": "embry.proof.receipt.v1",
  "ok": true,
  "live": true,
  "mocked": false,
  "proof_scope": "live_memory_speaker_resolution_policy_not_audio_identity",
  "cases": [
    {"id": "known_horus", "actual": {"status": "known"}},
    {"id": "unknown_speaker", "actual": {"status": "unknown"}},
    {"id": "ambiguous_low_confidence", "actual": {"status": "ambiguous"}},
    {"id": "overlap_close_scores", "actual": {"status": "ambiguous"}}
  ]
}
"""
    )
    fixture = tmp_path / "fixture.json"
    fixture.write_text(
        """
{
  "schema": "chatterbox.primary_speaker_gate_suite.v1",
  "cases": {
    "primary": {"primary_speaker_match": true},
    "female_alt": {"primary_speaker_match": false},
    "other_male": {"primary_speaker_match": false},
    "background_noise": {"primary_speaker_match": false}
  }
}
"""
    )
    known = tmp_path / "known.json"
    known.write_text(
        """
{
  "schema": "chatterbox.conversation_ladder.rung7.listener_contract.v1",
  "ok": true,
  "live": true,
  "mocked": false,
  "source_audio_identity_proven": true,
  "claims": {"does_not_prove": []},
  "speaker_resolution": {
    "status": "known",
    "speaker_id": "horus_lupercal",
    "allow_personal_memory": true,
    "memory_tags": ["speaker:horus_lupercal"]
  },
  "primary_speaker_verification": {
    "enrollment_audio": "/tmp/enroll.wav",
    "candidate_audio": "/tmp/candidate.wav",
    "primary_speaker_match": true
  }
}
"""
    )
    unknown = tmp_path / "unknown.json"
    unknown.write_text(
        """
{
  "schema": "chatterbox.conversation_ladder.rung7.listener_contract.v1",
  "speaker_resolution": {
    "status": "unknown",
    "allow_personal_memory": false,
    "identity_prompt": {"text": "Who is this?"}
  }
}
"""
    )
    overlap = tmp_path / "overlap.json"
    overlap.write_text(
        """
{
  "schema": "chatterbox.overlap_turn_control.v1",
  "ok": true,
  "live": true,
  "mocked": false,
  "claims": {
    "proves": [
      "pyannote_detected_two_anonymous_overlapping_speakers",
      "memory_intent_maps_overlap_to_turn_taking_clarification"
    ]
  },
  "memory_intent": {"voice_delivery": {"tone": "one_at_a_time_interrupt"}},
  "tau_voice_render": {"ok": true}
}
"""
    )

    pyannote = tmp_path / "pyannote.json"
    pyannote.write_text(
        """
{
  "schema": "chatterbox.pyannote_diarization_smoke.v1",
  "ok": true,
  "live": true,
  "mocked": false,
  "summary": {
    "speaker_count": 2,
    "exclusive_speaker_count": 1,
    "overlap_seconds": 4.725
  }
}
"""
    )

    audit = build_audit({"sessions": [_session("passed")]}, [policy, fixture, known, unknown, overlap, pyannote])

    assert audit["ok"] is True
    assert audit["pyannote_strict_two_speaker_candidate_count"] == 1
    assert "pyannote_strict_smoke_detects_two_speakers_in_overlap_audio" in audit["claims"]["proves"]
    assert audit["live"] is True
    assert audit["policy_ledger_candidate_count"] == 1
    assert audit["fixture_gate_candidate_count"] == 1
    assert audit["known_horus_candidate_count"] == 1
    assert audit["unknown_fail_closed_candidate_count"] == 1
    assert audit["overlap_diarization_candidate_count"] == 1
    assert audit["independent_enrollment_candidate_count"] == 1
    assert audit["physical_identity_candidate_count"] == 1
    assert audit["failed_gates"] == []
