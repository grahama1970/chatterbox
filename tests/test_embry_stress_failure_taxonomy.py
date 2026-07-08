from scripts.build_embry_stress_failure_taxonomy import build_taxonomy
from scripts.build_embry_stress_session_matrix import build_matrix


def _taxonomy() -> dict:
    return build_taxonomy(build_matrix())


def test_taxonomy_preserves_matrix_coverage_counts() -> None:
    taxonomy = _taxonomy()

    assert taxonomy["session_count"] == 300
    assert taxonomy["matrix_status_counts"] == {"passed": 109, "failed": 191, "not_run": 0}
    assert taxonomy["receipt_backed_count"] == 300
    assert taxonomy["missing_receipt_sessions"] == []
    assert taxonomy["not_run_sessions"] == []


def test_taxonomy_groups_failures_by_subsystem() -> None:
    taxonomy = _taxonomy()
    subsystems = taxonomy["subsystems"]

    assert subsystems["memory_answerability"]["status_counts"] == {
        "passed": 0,
        "failed": 60,
        "not_run": 0,
    }
    assert subsystems["external_research"]["status_counts"] == {
        "passed": 20,
        "failed": 0,
        "not_run": 0,
    }
    assert subsystems["tau_skill_routing"]["status_counts"] == {
        "passed": 60,
        "failed": 60,
        "not_run": 0,
    }
    assert subsystems["shared_chat_ux"]["status_counts"] == {
        "passed": 4,
        "failed": 16,
        "not_run": 0,
    }
    assert subsystems["interruption_turn_control"]["status_counts"] == {
        "passed": 0,
        "failed": 20,
        "not_run": 0,
    }
    assert subsystems["speaker_identity"]["status_counts"] == {
        "passed": 20,
        "failed": 0,
        "not_run": 0,
    }
    assert subsystems["realtimestt_audio_ingress"]["status_counts"] == {
        "passed": 0,
        "failed": 20,
        "not_run": 0,
    }
    assert subsystems["tone_emotion_intent"]["status_counts"] == {
        "passed": 5,
        "failed": 15,
        "not_run": 0,
    }


def test_taxonomy_exposes_top_repair_blockers() -> None:
    taxonomy = _taxonomy()
    gates = taxonomy["failed_gate_counts"]
    top_gates = taxonomy["top_failed_gates"]

    assert gates["tau_agent_handoff_not_exercised"] == 60
    assert gates["skill_call_receipt_not_emitted"] == 60
    assert gates["tau_dag_receipt_not_created"] == 60
    assert gates["runner_route_not_implemented"] == 24
    assert gates["interruption_detected_receipt_not_emitted"] == 20
    assert top_gates[:3] == [
        {"gate": "tau_agent_handoff_not_exercised", "count": 60},
        {"gate": "skill_call_receipt_not_emitted", "count": 60},
        {"gate": "tau_dag_receipt_not_created", "count": 60},
    ]


def test_taxonomy_keeps_live_loop_boundaries_explicit() -> None:
    taxonomy = _taxonomy()
    boundaries = "\n".join(taxonomy["does_not_prove"])

    assert "browser mic/WebRTC" in boundaries
    assert "full live RealtimeSTT -> speaker/diarization -> memory/Tau -> Chatterbox -> Chat UX loop" in boundaries
    assert "Chat UX, orb, and audible playback synchronized" in boundaries
    assert "live interruption/barge-in" in boundaries
