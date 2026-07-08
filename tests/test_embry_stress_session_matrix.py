from scripts.build_embry_stress_session_matrix import build_matrix


def test_matrix_contains_200_plus_labeled_sessions() -> None:
    matrix = build_matrix()

    assert matrix["session_count"] == 300
    assert matrix["folder_count"] == 15
    assert matrix["difficulty_levels"] == ["simple", "medium", "advanced", "adversarial", "soak"]
    assert len(matrix["sessions"]) == 300


def test_matrix_marks_only_receipt_backed_current_results() -> None:
    matrix = build_matrix()
    status_counts = matrix["status_counts"]

    assert status_counts == {"passed": 229, "failed": 71, "not_run": 0}
    for session in matrix["sessions"]:
        if session["status"] in {"passed", "failed"}:
            assert session["latest_receipt"]
            assert session["observed"]
        else:
            assert session["status"] == "not_run"
            assert session["latest_receipt"] is None


def test_matrix_speaker_identity_simple_cases_use_ledger_receipt() -> None:
    matrix = build_matrix()
    speaker_sessions = [
        session
        for session in matrix["sessions"]
        if session["folder_id"] == "speaker_identity" and session["difficulty"] == "simple"
    ]

    assert len(speaker_sessions) == 4
    assert all(session["status"] == "passed" for session in speaker_sessions)
    assert all(session["failed_gates"] == [] for session in speaker_sessions)
    assert all("embry-speaker-identity-ledger" in session["latest_receipt"] for session in speaker_sessions)


def test_matrix_memory_simple_cases_use_answerability_ledger_receipt() -> None:
    matrix = build_matrix()
    memory_sessions = [
        session
        for session in matrix["sessions"]
        if session["folder_id"] in {"sparta_qra_compliance", "persona_memory_recall", "persona_memory_miss"}
        and session["difficulty"] == "simple"
    ]

    assert len(memory_sessions) == 12
    assert all(session["status"] == "passed" for session in memory_sessions)
    assert all("embry-memory-answerability-ledger" in session["latest_receipt"] for session in memory_sessions)
    assert all(session["failed_gates"] == [] for session in memory_sessions)


def test_matrix_medium_memory_search_subset_has_live_receipt_results() -> None:
    matrix = build_matrix()
    sessions = [
        session
        for session in matrix["sessions"]
        if session["difficulty"] == "medium"
        and session["folder_id"]
        in {"sparta_qra_compliance", "persona_memory_recall", "persona_memory_miss", "brave_research"}
    ]

    assert len(sessions) == 16
    assert all(session["status"] == "passed" for session in sessions)
    assert all(session["failed_gates"] == [] for session in sessions)
    assert all(
        "matrix-medium-memory-search" in session["latest_receipt"]
        for session in sessions
        if session["folder_id"] == "brave_research"
    )
    assert all(
        "after-scope-fix" in session["latest_receipt"]
        for session in sessions
        if session["folder_id"] != "brave_research"
    )


def test_matrix_advanced_memory_search_subset_has_live_receipt_results() -> None:
    matrix = build_matrix()
    sessions = [
        session
        for session in matrix["sessions"]
        if session["difficulty"] == "advanced"
        and session["folder_id"]
        in {"sparta_qra_compliance", "persona_memory_recall", "persona_memory_miss", "brave_research"}
    ]

    assert len(sessions) == 16
    assert all(session["status"] == "passed" for session in sessions)
    assert all(session["failed_gates"] == [] for session in sessions)
    assert all(
        "matrix-advanced-memory-search" in session["latest_receipt"]
        for session in sessions
        if session["folder_id"] == "brave_research"
    )
    assert all(
        "after-scope-fix" in session["latest_receipt"]
        for session in sessions
        if session["folder_id"] != "brave_research"
    )


def test_matrix_adversarial_memory_search_subset_has_live_receipt_results() -> None:
    matrix = build_matrix()
    sessions = [
        session
        for session in matrix["sessions"]
        if session["difficulty"] == "adversarial"
        and session["folder_id"]
        in {"sparta_qra_compliance", "persona_memory_recall", "persona_memory_miss", "brave_research"}
    ]

    assert len(sessions) == 16
    assert all(session["status"] == "passed" for session in sessions)
    assert all(session["failed_gates"] == [] for session in sessions)
    assert all(
        "matrix-adversarial-memory-search" in session["latest_receipt"]
        for session in sessions
        if session["folder_id"] == "brave_research"
    )
    assert all(
        "after-scope-fix" in session["latest_receipt"]
        for session in sessions
        if session["folder_id"] != "brave_research"
    )


def test_matrix_soak_memory_search_subset_has_live_receipt_results() -> None:
    matrix = build_matrix()
    sessions = [
        session
        for session in matrix["sessions"]
        if session["difficulty"] == "soak"
        and session["folder_id"]
        in {"sparta_qra_compliance", "persona_memory_recall", "persona_memory_miss", "brave_research"}
    ]

    assert len(sessions) == 16
    assert all(session["status"] == "passed" for session in sessions)
    assert all(session["failed_gates"] == [] for session in sessions)
    assert all(
        "matrix-soak-memory-search" in session["latest_receipt"]
        for session in sessions
        if session["folder_id"] == "brave_research"
    )
    assert all(
        "after-scope-fix" in session["latest_receipt"]
        for session in sessions
        if session["folder_id"] != "brave_research"
    )


def test_matrix_medium_tau_and_skill_subset_records_dag_and_remaining_skill_failures() -> None:
    matrix = build_matrix()
    sessions = [
        session
        for session in matrix["sessions"]
        if session["difficulty"] == "medium"
        and session["folder_id"]
        in {"tau_tool_orchestration", "skill_create_evidence_case", "skill_create_figure", "skill_analytics"}
    ]

    assert len(sessions) == 16
    by_folder = {}
    for session in sessions:
        by_folder.setdefault(session["folder_id"], []).append(session)
    for folder in ["tau_tool_orchestration", "skill_create_evidence_case", "skill_create_figure", "skill_analytics"]:
        assert all(session["status"] == "passed" for session in by_folder[folder])
        assert all(session["failed_gates"] == [] for session in by_folder[folder])
    assert all("matrix-tau-all-dag-current" in session["latest_receipt"] for session in by_folder["tau_tool_orchestration"])
    assert all("skill-create-evidence-case-medium-live" in session["latest_receipt"] for session in by_folder["skill_create_evidence_case"])
    assert all("skill-create-figure-all-live" in session["latest_receipt"] for session in by_folder["skill_create_figure"])
    assert all("skill-analytics-all-live" in session["latest_receipt"] for session in by_folder["skill_analytics"])


def test_matrix_advanced_tau_and_skill_subset_records_dag_and_remaining_skill_failures() -> None:
    matrix = build_matrix()
    sessions = [
        session
        for session in matrix["sessions"]
        if session["difficulty"] == "advanced"
        and session["folder_id"]
        in {"tau_tool_orchestration", "skill_create_evidence_case", "skill_create_figure", "skill_analytics"}
    ]

    assert len(sessions) == 16
    by_folder = {}
    for session in sessions:
        by_folder.setdefault(session["folder_id"], []).append(session)
    for folder in ["tau_tool_orchestration", "skill_create_evidence_case", "skill_create_figure", "skill_analytics"]:
        assert all(session["status"] == "passed" for session in by_folder[folder])
        assert all(session["failed_gates"] == [] for session in by_folder[folder])
    assert all("matrix-tau-all-dag-current" in session["latest_receipt"] for session in by_folder["tau_tool_orchestration"])
    assert all("skill-create-evidence-case-advanced-live" in session["latest_receipt"] for session in by_folder["skill_create_evidence_case"])
    assert all("skill-create-figure-all-live" in session["latest_receipt"] for session in by_folder["skill_create_figure"])
    assert all("skill-analytics-all-live" in session["latest_receipt"] for session in by_folder["skill_analytics"])


def test_matrix_adversarial_tau_and_skill_subset_records_dag_and_remaining_skill_failures() -> None:
    matrix = build_matrix()
    sessions = [
        session
        for session in matrix["sessions"]
        if session["difficulty"] == "adversarial"
        and session["folder_id"]
        in {"tau_tool_orchestration", "skill_create_evidence_case", "skill_create_figure", "skill_analytics"}
    ]

    assert len(sessions) == 16
    by_folder = {}
    for session in sessions:
        by_folder.setdefault(session["folder_id"], []).append(session)
    for folder in ["tau_tool_orchestration", "skill_create_evidence_case", "skill_create_figure", "skill_analytics"]:
        assert all(session["status"] == "passed" for session in by_folder[folder])
        assert all(session["failed_gates"] == [] for session in by_folder[folder])
    assert all("matrix-tau-all-dag-current" in session["latest_receipt"] for session in by_folder["tau_tool_orchestration"])
    assert all("skill-create-evidence-case-adversarial-live" in session["latest_receipt"] for session in by_folder["skill_create_evidence_case"])
    assert all("skill-create-figure-all-live" in session["latest_receipt"] for session in by_folder["skill_create_figure"])
    assert all("skill-analytics-all-live" in session["latest_receipt"] for session in by_folder["skill_analytics"])


def test_matrix_soak_tau_and_skill_subset_records_dag_and_remaining_skill_failures() -> None:
    matrix = build_matrix()
    sessions = [
        session
        for session in matrix["sessions"]
        if session["difficulty"] == "soak"
        and session["folder_id"]
        in {"tau_tool_orchestration", "skill_create_evidence_case", "skill_create_figure", "skill_analytics"}
    ]

    assert len(sessions) == 16
    by_folder = {}
    for session in sessions:
        by_folder.setdefault(session["folder_id"], []).append(session)
    for folder in ["tau_tool_orchestration", "skill_create_evidence_case", "skill_create_figure", "skill_analytics"]:
        assert all(session["status"] == "passed" for session in by_folder[folder])
        assert all(session["failed_gates"] == [] for session in by_folder[folder])
    assert all("matrix-tau-all-dag-current" in session["latest_receipt"] for session in by_folder["tau_tool_orchestration"])
    assert all("skill-create-evidence-case-soak-live" in session["latest_receipt"] for session in by_folder["skill_create_evidence_case"])
    assert all("skill-create-figure-all-live" in session["latest_receipt"] for session in by_folder["skill_create_figure"])
    assert all("skill-analytics-all-live" in session["latest_receipt"] for session in by_folder["skill_analytics"])


def test_matrix_medium_routes_32_47_subset_has_receipt_backed_results() -> None:
    matrix = build_matrix()
    sessions = [
        session
        for session in matrix["sessions"]
        if session["difficulty"] == "medium"
        and session["folder_id"]
        in {"skill_sparta_validator", "chat_ux_sync", "voice_control_skill", "interruption"}
    ]

    assert len(sessions) == 16
    by_folder = {}
    for session in sessions:
        by_folder.setdefault(session["folder_id"], []).append(session)

    assert all(session["status"] == "passed" for session in by_folder["skill_sparta_validator"])
    assert all("sparta-validator-all-live" in session["latest_receipt"] for session in by_folder["skill_sparta_validator"])

    assert all(session["status"] == "passed" for session in by_folder["voice_control_skill"])
    assert all("voice-control-all-matrix" in session["latest_receipt"] for session in by_folder["voice_control_skill"])

    for folder in ["interruption"]:
        assert all(session["status"] == "failed" for session in by_folder[folder])
        assert all(
            "matrix-medium-routes-32-47" in session["latest_receipt"]
            for session in by_folder[folder]
        )

    assert by_folder["chat_ux_sync"][0]["status"] == "passed"
    assert by_folder["chat_ux_sync"][1]["status"] == "passed"
    assert by_folder["chat_ux_sync"][2]["status"] == "failed"
    assert by_folder["chat_ux_sync"][3]["status"] == "failed"
    assert all("chat-ux-gate-audit" in session["latest_receipt"] for session in by_folder["chat_ux_sync"])


def test_matrix_advanced_routes_32_47_subset_records_mixed_preflight_failures() -> None:
    matrix = build_matrix()
    sessions = [
        session
        for session in matrix["sessions"]
        if session["difficulty"] == "advanced"
        and session["folder_id"]
        in {"skill_sparta_validator", "chat_ux_sync", "voice_control_skill", "interruption"}
    ]

    assert len(sessions) == 16
    by_folder = {}
    for session in sessions:
        by_folder.setdefault(session["folder_id"], []).append(session)

    assert all(session["status"] == "passed" for session in by_folder["skill_sparta_validator"])
    assert all("sparta-validator-all-live" in session["latest_receipt"] for session in by_folder["skill_sparta_validator"])

    assert all(session["status"] == "passed" for session in by_folder["voice_control_skill"])
    assert all("voice-control-all-matrix" in session["latest_receipt"] for session in by_folder["voice_control_skill"])
    assert all(session["failed_gates"] == [] for session in by_folder["voice_control_skill"])

    assert all("matrix-advanced-routes-32-47" in session["latest_receipt"] for session in by_folder["chat_ux_sync"])
    assert all(session["failed_gates"] == ["runner_route_not_implemented"] for session in by_folder["chat_ux_sync"])
    assert all("matrix-advanced-routes-32-47" in session["latest_receipt"] for session in by_folder["interruption"])
    assert all(
        "interruption_detected_receipt_not_emitted" in session["failed_gates"]
        for session in by_folder["interruption"]
    )


def test_matrix_adversarial_routes_32_47_subset_records_mixed_preflight_failures() -> None:
    matrix = build_matrix()
    sessions = [
        session
        for session in matrix["sessions"]
        if session["difficulty"] == "adversarial"
        and session["folder_id"]
        in {"skill_sparta_validator", "chat_ux_sync", "voice_control_skill", "interruption"}
    ]

    assert len(sessions) == 16
    by_folder = {}
    for session in sessions:
        by_folder.setdefault(session["folder_id"], []).append(session)

    assert all(session["status"] == "passed" for session in by_folder["skill_sparta_validator"])
    assert all("sparta-validator-all-live" in session["latest_receipt"] for session in by_folder["skill_sparta_validator"])

    assert all(session["status"] == "passed" for session in by_folder["voice_control_skill"])
    assert all("voice-control-all-matrix" in session["latest_receipt"] for session in by_folder["voice_control_skill"])
    assert all(session["failed_gates"] == [] for session in by_folder["voice_control_skill"])

    assert all("matrix-adversarial-routes-32-47" in session["latest_receipt"] for session in by_folder["chat_ux_sync"])
    assert all(session["failed_gates"] == ["runner_route_not_implemented"] for session in by_folder["chat_ux_sync"])
    assert all("matrix-adversarial-routes-32-47" in session["latest_receipt"] for session in by_folder["interruption"])
    assert all(
        "interruption_detected_receipt_not_emitted" in session["failed_gates"]
        for session in by_folder["interruption"]
    )


def test_matrix_soak_routes_32_47_subset_records_mixed_preflight_failures() -> None:
    matrix = build_matrix()
    sessions = [
        session
        for session in matrix["sessions"]
        if session["difficulty"] == "soak"
        and session["folder_id"]
        in {"skill_sparta_validator", "chat_ux_sync", "voice_control_skill", "interruption"}
    ]

    assert len(sessions) == 16
    by_folder = {}
    for session in sessions:
        by_folder.setdefault(session["folder_id"], []).append(session)

    assert all(session["status"] == "passed" for session in by_folder["skill_sparta_validator"])
    assert all("sparta-validator-all-live" in session["latest_receipt"] for session in by_folder["skill_sparta_validator"])

    assert all(session["status"] == "passed" for session in by_folder["voice_control_skill"])
    assert all("voice-control-all-matrix" in session["latest_receipt"] for session in by_folder["voice_control_skill"])
    assert all(session["failed_gates"] == [] for session in by_folder["voice_control_skill"])

    assert all("matrix-soak-routes-32-47" in session["latest_receipt"] for session in by_folder["chat_ux_sync"])
    assert all(session["failed_gates"] == ["runner_route_not_implemented"] for session in by_folder["chat_ux_sync"])
    assert all("matrix-soak-routes-32-47" in session["latest_receipt"] for session in by_folder["interruption"])
    assert all(
        "interruption_detected_receipt_not_emitted" in session["failed_gates"]
        for session in by_folder["interruption"]
    )


def test_matrix_medium_routes_48_63_subset_has_receipt_backed_results() -> None:
    matrix = build_matrix()
    sessions = [
        session
        for session in matrix["sessions"]
        if session["difficulty"] == "medium"
        and session["folder_id"] in {"speaker_identity", "factory_noise", "tone_emotion"}
    ]

    assert len(sessions) == 12
    by_folder = {}
    for session in sessions:
        by_folder.setdefault(session["folder_id"], []).append(session)

    assert all(session["status"] == "passed" for session in by_folder["speaker_identity"])
    assert all("matrix-medium-routes-48-63" in session["latest_receipt"] for session in by_folder["speaker_identity"])
    assert all(session["status"] == "failed" for session in by_folder["factory_noise"])
    assert all("runner_route_not_implemented" not in session["failed_gates"] for session in by_folder["factory_noise"])
    assert by_folder["tone_emotion"][0]["status"] == "passed"
    assert all(session["status"] == "failed" for session in by_folder["tone_emotion"][1:])
    assert all("matrix-medium-routes-48-63" in session["latest_receipt"] for session in by_folder["tone_emotion"])


def test_matrix_advanced_routes_48_63_subset_has_receipt_backed_results() -> None:
    matrix = build_matrix()
    sessions = [
        session
        for session in matrix["sessions"]
        if session["difficulty"] == "advanced"
        and session["folder_id"] in {"speaker_identity", "factory_noise", "tone_emotion"}
    ]

    assert len(sessions) == 12
    assert all("matrix-advanced-routes-48-63" in session["latest_receipt"] for session in sessions)
    by_folder = {}
    for session in sessions:
        by_folder.setdefault(session["folder_id"], []).append(session)

    assert all(session["status"] == "passed" for session in by_folder["speaker_identity"])
    assert all(session["status"] == "failed" for session in by_folder["factory_noise"])
    assert all(session["failed_gates"] == ["runner_route_not_implemented"] for session in by_folder["factory_noise"])
    assert by_folder["tone_emotion"][0]["status"] == "passed"
    assert all(session["status"] == "failed" for session in by_folder["tone_emotion"][1:])
    assert all("voice_delivery_tone_expected" in session["failed_gates"][0] for session in by_folder["tone_emotion"][1:])


def test_matrix_adversarial_routes_48_63_subset_has_receipt_backed_results() -> None:
    matrix = build_matrix()
    sessions = [
        session
        for session in matrix["sessions"]
        if session["difficulty"] == "adversarial"
        and session["folder_id"] in {"speaker_identity", "factory_noise", "tone_emotion"}
    ]

    assert len(sessions) == 12
    assert all("matrix-adversarial-routes-48-63" in session["latest_receipt"] for session in sessions)
    by_folder = {}
    for session in sessions:
        by_folder.setdefault(session["folder_id"], []).append(session)

    assert all(session["status"] == "passed" for session in by_folder["speaker_identity"])
    assert all(session["status"] == "failed" for session in by_folder["factory_noise"])
    assert all(session["failed_gates"] == ["runner_route_not_implemented"] for session in by_folder["factory_noise"])
    assert by_folder["tone_emotion"][0]["status"] == "passed"
    assert all(session["status"] == "failed" for session in by_folder["tone_emotion"][1:])
    assert all("voice_delivery_tone_expected" in session["failed_gates"][0] for session in by_folder["tone_emotion"][1:])


def test_matrix_soak_routes_48_63_subset_has_receipt_backed_results() -> None:
    matrix = build_matrix()
    sessions = [
        session
        for session in matrix["sessions"]
        if session["difficulty"] == "soak"
        and session["folder_id"] in {"speaker_identity", "factory_noise", "tone_emotion"}
    ]

    assert len(sessions) == 12
    assert all("matrix-soak-routes-48-63" in session["latest_receipt"] for session in sessions)
    by_folder = {}
    for session in sessions:
        by_folder.setdefault(session["folder_id"], []).append(session)

    assert all(session["status"] == "passed" for session in by_folder["speaker_identity"])
    assert all(session["status"] == "failed" for session in by_folder["factory_noise"])
    assert all(session["failed_gates"] == ["runner_route_not_implemented"] for session in by_folder["factory_noise"])
    assert by_folder["tone_emotion"][0]["status"] == "passed"
    assert all(session["status"] == "failed" for session in by_folder["tone_emotion"][1:])
    assert all("voice_delivery_tone_expected" in session["failed_gates"][0] for session in by_folder["tone_emotion"][1:])


def test_matrix_includes_required_route_families() -> None:
    matrix = build_matrix()
    routes = {session["route"] for session in matrix["sessions"]}

    assert "memory.sparta_qra" in routes
    assert "memory.persona_memory" in routes
    assert "brave-search.source_receipt" in routes
    assert "tau.agent_handoff" in routes
    assert "tau.skill.create_evidence_case" in routes
    assert "tau.skill.create_figure" in routes
    assert "tau.skill.analytics" in routes
    assert "tau.skill.sparta_validator" in routes
    assert "tau.skill.embry_voice_control" in routes
    assert "ux-lab.shared_chat" in routes
    assert "chatterbox.turn_control" in routes


def test_every_case_has_oracle_and_answerability_policy() -> None:
    matrix = build_matrix()

    for session in matrix["sessions"]:
        assert session["schema"] == "embry.stress_case.v1"
        assert session["oracle"]["type"]
        assert session["oracle"]["required_receipts"]
        assert session["oracle"]["required_gates"]
        assert session["expected_answerability"]["decision"]
        assert session["expected_answerability"]["failure_policy"]
        assert session["source_generation"]["template_family"] == session["folder_id"]


def test_direct_skill_cases_require_tau_authority() -> None:
    matrix = build_matrix()
    skill_sessions = [session for session in matrix["sessions"] if session["route"].startswith("tau.skill.")]

    assert len(skill_sessions) == 100
    assert {session["expected_route"]["required_skill"] for session in skill_sessions} == {
        "create-evidence-case",
        "create-figure",
        "analytics",
        "sparta-qra-validator-gpt",
        "embry-voice-control",
    }
    assert all(session["expected_route"]["skill_required"] is True for session in skill_sessions)
    assert all(session["expected_route"]["chatterbox_may_call_skills"] is False for session in skill_sessions)
    assert all(session["expected_route"]["ui_may_call_skills"] is False for session in skill_sessions)
    assert all("tau.agent_handoff.v1" in session["oracle"]["required_receipts"] for session in skill_sessions)
    assert all("skill.call.receipt.v1" in session["oracle"]["required_receipts"] for session in skill_sessions)


def test_matrix_direct_skill_simple_failures_use_skill_preflight_receipts() -> None:
    matrix = build_matrix()
    sessions = [
        session
        for session in matrix["sessions"]
        if session["route"].startswith("tau.skill.") and session["difficulty"] == "simple"
    ]

    assert len(sessions) == 20
    assert all(session["latest_receipt"] for session in sessions)
    assert all("embry-intelligence-stress" in session["latest_receipt"] for session in sessions)
    proven_sessions = [
        session
        for session in sessions
        if session["folder_id"]
        in {"skill_analytics", "skill_create_figure", "skill_create_evidence_case", "skill_sparta_validator"}
        or (
            session["folder_id"] == "voice_control_skill"
        )
    ]
    preflight_failures = [
        session
        for session in sessions
        if session["folder_id"]
        not in {"skill_analytics", "skill_create_figure", "skill_create_evidence_case", "skill_sparta_validator"}
        and session["folder_id"] != "voice_control_skill"
    ]
    assert len(proven_sessions) == 20
    assert len(preflight_failures) == 0
    assert all(session["status"] == "passed" for session in proven_sessions)
    assert all(session["failed_gates"] == [] for session in proven_sessions)
    assert all(
        "skill-analytics-all-live" in session["latest_receipt"]
        for session in proven_sessions
        if session["folder_id"] == "skill_analytics"
    )
    assert all(
        "skill-create-figure-all-live" in session["latest_receipt"]
        for session in proven_sessions
        if session["folder_id"] == "skill_create_figure"
    )
    assert all(
        "skill-create-evidence-case-simple-live" in session["latest_receipt"]
        for session in proven_sessions
        if session["folder_id"] == "skill_create_evidence_case"
    )
    assert all(
        "voice-control-all-matrix" in session["latest_receipt"]
        for session in proven_sessions
        if session["folder_id"] == "voice_control_skill"
    )
    assert all(
        "sparta-validator-all-live" in session["latest_receipt"]
        for session in proven_sessions
        if session["folder_id"] == "skill_sparta_validator"
    )
    assert preflight_failures == []


def test_matrix_interruption_simple_failures_use_turn_control_receipt() -> None:
    matrix = build_matrix()
    sessions = [
        session
        for session in matrix["sessions"]
        if session["folder_id"] == "interruption" and session["difficulty"] == "simple"
    ]

    assert len(sessions) == 4
    assert all(session["status"] == "failed" for session in sessions)
    assert all("matrix-interruption-simple" in session["latest_receipt"] for session in sessions)
    assert all("runner_route_not_implemented" not in session["failed_gates"] for session in sessions)
    assert all("interruption_detected_receipt_not_emitted" in session["failed_gates"] for session in sessions)


def test_matrix_factory_noise_simple_failures_use_audio_capture_receipts() -> None:
    matrix = build_matrix()
    sessions = [
        session
        for session in matrix["sessions"]
        if session["folder_id"] == "factory_noise" and session["difficulty"] == "simple"
    ]

    assert len(sessions) == 4
    assert all(session["status"] == "failed" for session in sessions)
    assert all(session["latest_receipt"] for session in sessions)
    assert all("runner_route_not_implemented" not in session["failed_gates"] for session in sessions)
    assert any("capture_captured_audio_rms" in session["failed_gates"] for session in sessions)
    assert any("speaker_resolution_known_horus" in session["failed_gates"] for session in sessions)


def test_matrix_chat_ux_simple_cases_split_replay_passes_from_lineage_failures() -> None:
    matrix = build_matrix()
    sessions = [
        session
        for session in matrix["sessions"]
        if session["folder_id"] == "chat_ux_sync" and session["difficulty"] == "simple"
    ]

    assert len(sessions) == 4
    by_id = {session["id"]: session for session in sessions}
    assert by_id["chat_ux_sync-simple-01"]["status"] == "passed"
    assert by_id["chat_ux_sync-simple-02"]["status"] == "passed"
    assert by_id["chat_ux_sync-simple-03"]["status"] == "failed"
    assert by_id["chat_ux_sync-simple-04"]["status"] == "failed"
    assert all("chat-ux-gate-audit" in session["latest_receipt"] for session in sessions)
    assert "chat_turn_id_matches_response_plan_not_proven" in by_id["chat_ux_sync-simple-03"]["failed_gates"]
    assert "spoken_transcript_entity_underlines_not_proven" in by_id["chat_ux_sync-simple-04"]["failed_gates"]


def test_every_case_requires_humanized_conversation_delivery() -> None:
    matrix = build_matrix()

    for session in matrix["sessions"]:
        delivery = session["conversation_requirements"]
        assert delivery["schema"] == "embry.conversation_delivery_requirements.v1"
        assert delivery["flat_neutral_allowed"] is False
        assert delivery["memory_intent_required"] is True
        assert delivery["conversation_arc"]
        assert delivery["steering_strategy"]
        assert delivery["required_tone_family"]
        assert delivery["inline_emotion_tags_required"] is True
        assert delivery["minimum_inline_emotion_tag_count"] >= 1
        assert delivery["suggested_inline_emotion_tags"]
        assert delivery["pause_strategy_required"] is True
        assert delivery["interruption_strategy"]["required"] is True
        assert delivery["interruption_strategy"]["natural_stop_required"] is True
        assert delivery["spoken_text_schema_required"] is True
        assert "spoken_text_with_inline_emotion_tags" in session["expected_evidence"]
        assert "pause_and_interruption_policy" in session["expected_evidence"]
