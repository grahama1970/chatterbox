from scripts.build_embry_stress_session_matrix import build_matrix


def test_matrix_contains_200_labeled_sessions() -> None:
    matrix = build_matrix()

    assert matrix["session_count"] == 200
    assert matrix["folder_count"] == 10
    assert matrix["difficulty_levels"] == ["simple", "medium", "advanced", "adversarial", "soak"]
    assert len(matrix["sessions"]) == 200


def test_matrix_marks_only_receipt_backed_current_results() -> None:
    matrix = build_matrix()
    status_counts = matrix["status_counts"]

    assert status_counts == {"passed": 9, "failed": 31, "not_run": 160}
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
    assert "ux-lab.shared_chat" in routes
    assert "chatterbox.turn_control" in routes
