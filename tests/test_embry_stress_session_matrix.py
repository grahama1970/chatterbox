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

    assert status_counts == {"passed": 9, "failed": 31, "not_run": 260}
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


def test_matrix_memory_simple_failures_use_answerability_ledger_receipt() -> None:
    matrix = build_matrix()
    memory_sessions = [
        session
        for session in matrix["sessions"]
        if session["folder_id"] in {"sparta_qra_compliance", "persona_memory_recall", "persona_memory_miss"}
        and session["difficulty"] == "simple"
    ]

    assert len(memory_sessions) == 12
    assert all(session["status"] == "failed" for session in memory_sessions)
    assert all("embry-memory-answerability-ledger" in session["latest_receipt"] for session in memory_sessions)
    assert all(session["failed_gates"] for session in memory_sessions)


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
