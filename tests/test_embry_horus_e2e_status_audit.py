from scripts.audit_embry_horus_e2e_status import build_audit


def _goal_audit() -> dict:
    import json

    return json.load(open("docs/EMBRY_GOAL_COVERAGE_AUDIT.json"))


def test_horus_status_audit_covers_exact_requested_items() -> None:
    audit = build_audit(_goal_audit())

    assert set(audit["items"]) == {
        "real_horus_enrollment",
        "browser_mic_webrtc",
        "tau_memory_routing",
        "chatterbox_from_live_stt",
        "chat_ux_sync",
        "orb_sync",
        "replay",
        "interruption",
    }
    assert audit["status_counts"] == {"pass": 0, "fail": 8}
    assert audit["ok"] is False
    assert audit["status"] == "failed"


def test_horus_status_audit_rejects_partial_or_nonlive_receipts() -> None:
    audit = build_audit(_goal_audit())

    for item in audit["items"].values():
        assert item["status"] == "fail"
        assert item["mocked"] is False
        assert item["live_required"] is True
        assert item["failed_reasons"]
        assert item["current_failure"]

    assert "subsystem_status_not_passed" in audit["items"]["orb_sync"]["failed_reasons"][0]
    assert any(
        reason.startswith("artifact_not_clean_live_pass:docs/EMBRY_ORB_SYNC_EVIDENCE_AUDIT.json")
        for reason in audit["items"]["orb_sync"]["failed_reasons"]
    )


def test_horus_status_audit_names_concrete_next_failures() -> None:
    audit = build_audit(_goal_audit())
    failures = {item["id"]: item for item in audit["next_failed_items"]}

    assert "browser_mic_webrtc" in failures
    assert "browser" in failures["browser_mic_webrtc"]["current_failure"].lower()
    assert "RealtimeSTT" in failures["browser_mic_webrtc"]["title"]
    assert "same-turn" in audit["items"]["chatterbox_from_live_stt"]["current_failure"]
    assert "turn-id lineage" in audit["items"]["chat_ux_sync"]["current_failure"]
    assert "event-sourced replay" in audit["items"]["replay"]["current_failure"]


def test_horus_status_audit_attaches_receipt_paths_to_each_item() -> None:
    audit = build_audit(_goal_audit())

    assert audit["items"]["real_horus_enrollment"]["evidence_artifacts"][0]["path"] == (
        "docs/EMBRY_SPEAKER_IDENTITY_EVIDENCE_AUDIT.json"
    )
    assert audit["items"]["browser_mic_webrtc"]["evidence_artifacts"][0]["path"] == (
        "docs/EMBRY_REALTIMESTT_INGRESS_EVIDENCE_AUDIT.json"
    )
    assert {
        artifact["path"]
        for artifact in audit["items"]["chatterbox_from_live_stt"]["evidence_artifacts"]
    } == {
        "docs/EMBRY_REALTIMESTT_INGRESS_EVIDENCE_AUDIT.json",
        "docs/EMBRY_MEMORY_TAU_ROUTING_EVIDENCE_AUDIT.json",
        "docs/EMBRY_CHATTERBOX_SPEECH_EVIDENCE_AUDIT.json",
    }
