from scripts.build_embry_stress_session_matrix import build_matrix
from scripts.smoke_embry_intelligence_stress import (
    classify_answer,
    classify_matrix_answer,
    classify_voice_delivery_intent,
    select_matrix_sessions,
)


def answer_payload(text: str, *, can_answer: bool = True) -> dict:
    return {
        "ok_http": True,
        "json": {
            "can_answer": can_answer,
            "final_response": text,
        },
    }


def test_sparta_qra_acceptance_rejects_unrelated_control_exclusion() -> None:
    failed = classify_answer(
        {"kind": "sparta_qra_acceptance"},
        answer_payload("S0609 is a terminal NON_GENERATION QRA coverage outcome."),
    )

    assert "sparta_qra_answer_overfit_to_unrelated_control_exclusion" in failed
    assert "sparta_qra_answer_missing_acceptance_terms" in failed


def test_persona_memory_requires_expected_terms() -> None:
    failed = classify_answer(
        {"kind": "expected_terms", "expected_terms": ["cthonia"]},
        answer_payload("Build and operate the Horus TTS pipeline."),
    )

    assert failed == ["persona_memory_answer_wrong_or_unrelated"]


def test_memory_miss_must_not_return_unrelated_answer() -> None:
    failed = classify_answer(
        {"kind": "memory_miss"},
        answer_payload("Read and explain Embry OS configuration from embry.yaml."),
    )

    assert failed == ["memory_miss_should_not_answer_unrelated_record"]


def test_memory_miss_allows_no_answer() -> None:
    failed = classify_answer(
        {"kind": "memory_miss"},
        answer_payload("", can_answer=False),
    )

    assert failed == []


def test_matrix_answer_rejects_persona_memory_from_skill_collection() -> None:
    failed = classify_matrix_answer(
        {"route": "memory.persona_memory", "question": "What did Horus last ask Embry about voice testing?"},
        {
            "ok_http": True,
            "json": {
                "can_answer": True,
                "final_response": "Build and operate the Horus TTS pipeline.",
                "sources": [{"source": "skill_descriptions", "key": "skill_tts-horus"}],
            },
        },
    )

    assert "persona_memory_answer_uses_unrelated_source_collection" in failed


def test_matrix_sparta_rejects_control_exclusion_for_any_qra_question() -> None:
    failed = classify_matrix_answer(
        {"route": "memory.sparta_qra", "question": "What should Embry do when a SPARTA QRA has weak evidence?"},
        answer_payload("S0609 is recorded as a terminal NON_GENERATION QRA coverage outcome."),
    )

    assert "sparta_qra_answer_overfit_to_unrelated_control_exclusion" in failed


def test_matrix_answer_marks_unsupported_route_unimplemented() -> None:
    failed = classify_matrix_answer(
        {"route": "tau.agent_handoff", "question": "Ask Tau to create an evidence-case."},
        answer_payload(""),
    )

    assert failed == ["runner_route_not_implemented"]


def intent_payload(tone: str, *, source: str = "memory_intent", delivery_stage: str = "satisfied") -> dict:
    return {
        "ok_http": True,
        "json": {
            "voice_delivery": {
                "source": source,
                "tone": tone,
                "delivery_stage": delivery_stage,
            },
        },
    }


def test_voice_delivery_intent_rejects_generic_memory_confident_for_overlap() -> None:
    failed = classify_voice_delivery_intent(
        {
            "route": "memory.intent.voice_delivery",
            "question": "Two speakers overlap; Embry should say a human one-at-a-time boundary.",
        },
        intent_payload("memory_confident"),
    )

    assert "voice_delivery_tone_expected_firm_boundary_or_one_at_a_time_interrupt" in failed


def test_voice_delivery_intent_accepts_one_at_a_time_overlap_tone() -> None:
    failed = classify_voice_delivery_intent(
        {
            "route": "memory.intent.voice_delivery",
            "question": "Two speakers overlap; Embry should say a human one-at-a-time boundary.",
        },
        intent_payload("one_at_a_time_interrupt", delivery_stage="boundary"),
    )

    assert failed == []


def test_select_matrix_sessions_filters_folder_difficulty_and_limit() -> None:
    selected = select_matrix_sessions(
        build_matrix(),
        folder="sparta_qra_compliance",
        difficulty="simple",
        offset=0,
        limit=2,
    )

    assert [session["id"] for session in selected] == [
        "sparta_qra_compliance-simple-01",
        "sparta_qra_compliance-simple-02",
    ]


def test_select_matrix_sessions_applies_offset_after_filters() -> None:
    selected = select_matrix_sessions(
        build_matrix(),
        folder=None,
        difficulty="simple",
        offset=16,
        limit=2,
    )

    assert [session["id"] for session in selected] == [
        "tau_tool_orchestration-simple-01",
        "tau_tool_orchestration-simple-02",
    ]
