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

    assert status_counts == {"passed": 4, "failed": 13, "not_run": 183}
    for session in matrix["sessions"]:
        if session["status"] in {"passed", "failed"}:
            assert session["latest_receipt"]
            assert session["observed"]
        else:
            assert session["status"] == "not_run"
            assert session["latest_receipt"] is None


def test_matrix_includes_required_route_families() -> None:
    matrix = build_matrix()
    routes = {session["route"] for session in matrix["sessions"]}

    assert "memory.sparta_qra" in routes
    assert "memory.persona_memory" in routes
    assert "brave-search.source_receipt" in routes
    assert "tau.agent_handoff" in routes
    assert "ux-lab.shared_chat" in routes
    assert "chatterbox.turn_control" in routes
