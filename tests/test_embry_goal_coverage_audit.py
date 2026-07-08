from scripts.build_embry_goal_coverage_audit import build_audit


def _audit() -> dict:
    import json

    requirements = json.load(open("docs/voice_chat_e2e_requirements.json"))
    taxonomy = json.load(open("docs/EMBRY_STRESS_FAILURE_TAXONOMY.json"))
    return build_audit(requirements, taxonomy)


def test_goal_audit_covers_all_named_objective_subsystems() -> None:
    audit = _audit()

    assert set(audit["subsystems"]) == {
        "realtimestt_ingress",
        "speaker_identity",
        "memory_tau_routing",
        "chatterbox_speech",
        "chat_ux_sync",
        "orb_sync",
        "replay",
        "interruption",
    }
    assert audit["overall"] == {
        "ready": False,
        "reason": "Goal subsystems still include failing, partial, and insufficient-evidence rows.",
        "status": "not_ready",
    }


def test_goal_audit_keeps_pass_fail_counts_attached_to_subsystems() -> None:
    audit = _audit()
    subsystems = audit["subsystems"]

    assert subsystems["memory_tau_routing"]["taxonomy"]["status_counts"] == {
        "passed": 20,
        "failed": 180,
        "not_run": 0,
    }
    assert subsystems["chat_ux_sync"]["taxonomy"]["status_counts"] == {
        "passed": 4,
        "failed": 16,
        "not_run": 0,
    }
    assert subsystems["interruption"]["taxonomy"]["status_counts"] == {
        "passed": 0,
        "failed": 20,
        "not_run": 0,
    }
    assert subsystems["orb_sync"]["taxonomy"]["status_counts"] == {
        "passed": 0,
        "failed": 0,
        "not_run": 0,
    }


def test_goal_audit_names_current_hard_failures() -> None:
    audit = _audit()

    assert audit["subsystems"]["memory_tau_routing"]["status"] == "failing"
    assert audit["subsystems"]["memory_tau_routing"]["evidence_artifacts"] == [
        "docs/EMBRY_MEMORY_TAU_ROUTING_EVIDENCE_AUDIT.json"
    ]
    assert audit["subsystems"]["speaker_identity"]["evidence_artifacts"] == [
        "docs/EMBRY_SPEAKER_IDENTITY_EVIDENCE_AUDIT.json"
    ]
    assert audit["subsystems"]["chat_ux_sync"]["status"] == "failing"
    assert audit["subsystems"]["chat_ux_sync"]["evidence_artifacts"] == [
        "docs/EMBRY_CHAT_UX_SYNC_EVIDENCE_AUDIT.json"
    ]
    assert audit["subsystems"]["interruption"]["status"] == "failing"
    assert audit["subsystems"]["realtimestt_ingress"]["evidence_artifacts"] == [
        "docs/EMBRY_REALTIMESTT_INGRESS_EVIDENCE_AUDIT.json"
    ]
    assert audit["subsystems"]["interruption"]["evidence_artifacts"] == [
        "docs/EMBRY_INTERRUPTION_EVIDENCE_AUDIT.json"
    ]
    assert audit["subsystems"]["chatterbox_speech"]["evidence_artifacts"] == [
        "docs/EMBRY_CHATTERBOX_SPEECH_EVIDENCE_AUDIT.json"
    ]
    assert audit["subsystems"]["orb_sync"]["status"] == "insufficient_evidence"
    assert audit["goal_subsystem_status_counts"] == {
        "failing": 4,
        "partial": 3,
        "insufficient_evidence": 1,
    }


def test_goal_audit_points_to_next_receipt_needed_for_orb_and_replay() -> None:
    audit = _audit()

    orb = audit["subsystems"]["orb_sync"]
    replay = audit["subsystems"]["replay"]

    assert "turn_id" in orb["next_proof"]
    assert "orb authority" in orb["next_proof"]
    assert orb["evidence_artifacts"] == ["docs/EMBRY_ORB_SYNC_EVIDENCE_AUDIT.json"]
    assert "event journal" in replay["next_proof"]
    assert "original timing" in replay["summary"]
    assert replay["evidence_artifacts"] == ["docs/EMBRY_REPLAY_EVIDENCE_AUDIT.json"]
