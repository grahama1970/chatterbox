from scripts.rung1_audio_graph_realtimestt import compact_alnum, normalize_text


def test_nonce_normalization_matches_digit_words_and_digit_punctuation() -> None:
    assert normalize_text("Alpha 7-7-8-1") == "alpha 7 7 8 1"
    assert normalize_text("alpha seven seven eight one") == "alpha 7 7 8 1"
    assert compact_alnum("Alpha 7, 7, 8, 1.") == compact_alnum("alpha seven seven eight one")

