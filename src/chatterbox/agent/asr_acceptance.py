"""Text fidelity gates for Chatterbox render candidates."""

from __future__ import annotations

import re
from typing import Any


def normalize_text(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def word_error_rate(expected: str, actual: str) -> float:
    """Return edit-distance word error rate, counting insertions."""
    expected_words = normalize_text(expected).split()
    actual_words = normalize_text(actual).split()
    if not expected_words:
        return 0.0 if not actual_words else 1.0
    previous = list(range(len(actual_words) + 1))
    for row_index, expected_word in enumerate(expected_words, start=1):
        current = [row_index]
        for column_index, actual_word in enumerate(actual_words, start=1):
            substitution_cost = 0 if expected_word == actual_word else 1
            current.append(
                min(
                    previous[column_index] + 1,
                    current[column_index - 1] + 1,
                    previous[column_index - 1] + substitution_cost,
                )
            )
        previous = current
    return round(previous[-1] / len(expected_words), 4)


def repeated_ngram_hits(text: str, *, ngram_size: int = 2, min_count: int = 3) -> list[str]:
    words = normalize_text(text).split()
    counts: dict[tuple[str, ...], int] = {}
    for index in range(0, max(0, len(words) - ngram_size + 1)):
        ngram = tuple(words[index : index + ngram_size])
        counts[ngram] = counts.get(ngram, 0) + 1
    return [" ".join(ngram) for ngram, count in counts.items() if count >= min_count]


def acceptance_result(
    *,
    expected_text: str,
    transcript: str,
    max_wer: float = 0.35,
    max_duration_ratio: float | None = None,
    duration_seconds: float | None = None,
) -> dict[str, Any]:
    wer = word_error_rate(expected_text, transcript)
    failed_gates: list[str] = []
    if wer > max_wer:
        failed_gates.append("wer_within_limit")
    repeated = repeated_ngram_hits(transcript)
    if repeated:
        failed_gates.append("no_repeated_ngram_hallucination")
    if max_duration_ratio is not None and duration_seconds is not None:
        expected_words = max(1, len(normalize_text(expected_text).split()))
        # 2.7 words/second is deliberately lenient for expressive speech.
        expected_max_duration = (expected_words / 2.7) * max_duration_ratio
        if duration_seconds > expected_max_duration:
            failed_gates.append("duration_within_expected_ratio")
    return {
        "ok": not failed_gates,
        "wer": wer,
        "repeated_ngram_hits": repeated,
        "failed_gates": failed_gates,
    }
