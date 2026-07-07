from scripts.smoke_embry_intelligence_stress import classify_answer


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
