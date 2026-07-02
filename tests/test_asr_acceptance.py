"""Text-fidelity gate tests for Chatterbox candidate acceptance."""

from __future__ import annotations

from chatterbox.agent.asr_acceptance import acceptance_result, repeated_ngram_hits, word_error_rate


def test_word_error_rate_counts_insertions() -> None:
    assert word_error_rate("alpha beta", "alpha beta beta beta") == 1.0


def test_repeated_ngram_hits_detects_phrase_loops() -> None:
    hits = repeated_ngram_hits("control family and control family and control family")

    assert "control family" in hits


def test_acceptance_result_rejects_repeated_phrase_hallucination() -> None:
    result = acceptance_result(
        expected_text="I found the control family now.",
        transcript="I found the control family now. control family control family control family.",
        max_wer=0.35,
    )

    assert not result["ok"]
    assert "wer_within_limit" in result["failed_gates"]
    assert "no_repeated_ngram_hallucination" in result["failed_gates"]


def test_acceptance_result_accepts_small_punctuation_difference() -> None:
    result = acceptance_result(
        expected_text="Anything else you need?",
        transcript="Anything else you need, eh?",
        max_wer=0.35,
    )

    assert result["ok"]
    assert result["failed_gates"] == []
