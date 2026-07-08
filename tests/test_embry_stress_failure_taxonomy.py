from scripts.build_embry_stress_failure_taxonomy import build_taxonomy
from scripts.build_embry_stress_session_matrix import build_matrix


def _taxonomy() -> dict:
    return build_taxonomy(build_matrix())


def test_taxonomy_preserves_matrix_coverage_counts() -> None:
    taxonomy = _taxonomy()

    assert taxonomy["session_count"] == 300
    assert taxonomy["matrix_status_counts"] == {"passed": 255, "failed": 45, "not_run": 0}
    assert taxonomy["receipt_backed_count"] == 300
    assert taxonomy["missing_receipt_sessions"] == []
    assert taxonomy["not_run_sessions"] == []


def test_taxonomy_groups_failures_by_subsystem() -> None:
    taxonomy = _taxonomy()
    subsystems = taxonomy["subsystems"]

    assert subsystems["memory_answerability"]["status_counts"] == {
        "passed": 60,
        "failed": 0,
        "not_run": 0,
    }
    assert subsystems["external_research"]["status_counts"] == {
        "passed": 20,
        "failed": 0,
        "not_run": 0,
    }
    assert subsystems["tau_skill_routing"]["status_counts"] == {
        "passed": 120,
        "failed": 0,
        "not_run": 0,
    }
    assert subsystems["shared_chat_ux"]["status_counts"] == {
        "passed": 20,
        "failed": 0,
        "not_run": 0,
    }
    assert subsystems["interruption_turn_control"]["status_counts"] == {
        "passed": 10,
        "failed": 10,
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

    assert gates.get("tau_agent_handoff_not_exercised", 0) == 0
    assert gates.get("skill_call_receipt_not_emitted", 0) == 0
    assert gates.get("tau_dag_receipt_not_created", 0) == 0
    assert gates.get("voice_control_controlled_live_ready", 0) == 0
    assert gates.get("voice_control_case_text-turn_pass", 0) == 0
    assert gates.get("text_turn_memory_tau_chatterbox_authority", 0) == 0
    assert gates.get("runner_route_not_implemented", 0) == 0
    assert "interruption_detected_receipt_not_emitted" not in gates
    assert gates["capture_captured_audio_rms"] == 15
    assert gates["asr_final_transcript_present"] == 5
    assert gates["asr_transcript_matches_stress_audio"] == 5
    assert gates.get("realtimestt_command_ok", 0) == 0
    assert gates.get("realtimestt_receipt_ok", 0) == 0
    assert gates["rung7_receipt_ok"] == 5
    assert gates["speaker_resolution_known_horus"] == 5
    assert gates["speaker_memory_recall_found"] == 5
    assert gates["blessed_qra_cached_response_not_exercised"] == 5
    assert gates["tau_tool_wait_not_exercised"] == 5
    assert gates["natural_stop_phrase_not_observed"] == 5
    assert top_gates[:3] == [
        {"gate": "capture_captured_audio_rms", "count": 15},
        {"gate": "blessed_qra_cached_response_not_exercised", "count": 5},
        {"gate": "natural_stop_phrase_not_observed", "count": 5},
    ]


def test_taxonomy_clears_primary_blocker_when_subsystem_has_no_failures() -> None:
    taxonomy = _taxonomy()

    assert taxonomy["subsystems"]["memory_answerability"]["primary_blocker"] == (
        "No current blocker in the matrix rows; all receipt-backed rows pass."
    )
    assert taxonomy["subsystems"]["tau_skill_routing"]["primary_blocker"] == (
        "No current blocker in the matrix rows; all receipt-backed rows pass."
    )


def test_taxonomy_keeps_live_loop_boundaries_explicit() -> None:
    taxonomy = _taxonomy()
    boundaries = "\n".join(taxonomy["does_not_prove"])

    assert "browser mic/WebRTC" in boundaries
    assert "full live RealtimeSTT -> speaker/diarization -> memory/Tau -> Chatterbox -> Chat UX loop" in boundaries
    assert "Chat UX, orb, and audible playback synchronized" in boundaries
    assert "live interruption/barge-in" in boundaries
