from scripts.smoke_embry_memory_answerability_ledger import (
    answerability_decision,
    scope_for_route,
    selected_answerability_sessions,
)


def test_selected_answerability_sessions_are_the_12_simple_memory_cases() -> None:
    sessions = selected_answerability_sessions()

    assert len(sessions) == 12
    assert {session["folder_id"] for session in sessions} == {
        "sparta_qra_compliance",
        "persona_memory_recall",
        "persona_memory_miss",
    }
    assert {session["difficulty"] for session in sessions} == {"simple"}


def test_scope_for_route_uses_sparta_scope_only_for_sparta_qra() -> None:
    assert scope_for_route("memory.sparta_qra") == "sparta_qra"
    assert scope_for_route("memory.persona_memory") == "persona_memory"
    assert scope_for_route("memory.persona_memory.fail_closed") == "persona_memory"


def test_answerability_decision_blocks_failed_answer_before_speech() -> None:
    decision = answerability_decision(
        {"route": "memory.persona_memory"},
        {"ok_http": True, "json": {"can_answer": True, "final_response": "Unrelated skill text", "sources": [{"source": "skill_descriptions"}]}},
        ["persona_memory_answer_uses_unrelated_source_collection"],
    )

    assert decision["decision"] == "block_before_speech"
    assert decision["final_response_present"] is True
    assert decision["records_used_count"] == 1


def test_answerability_decision_allows_clean_answer() -> None:
    decision = answerability_decision(
        {"route": "memory.persona_memory"},
        {"ok_http": True, "json": {"can_answer": True, "final_response": "Horus grew up on Cthonia.", "sources": [{"source": "persona_memory"}]}},
        [],
    )

    assert decision["decision"] == "answerable"
