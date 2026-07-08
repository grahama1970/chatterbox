from scripts.rung2_source_audio_speaker_gate import case_accepts_horus


def test_case_accepts_horus_requires_ok_and_ratio_threshold() -> None:
    assert case_accepts_horus({"ok": True, "summary": {"horus_ratio": 0.75}}, 0.5)
    assert not case_accepts_horus({"ok": True, "summary": {"horus_ratio": 0.49}}, 0.5)
    assert not case_accepts_horus({"ok": False, "summary": {"horus_ratio": 1.0}}, 0.5)


def test_case_accepts_horus_handles_missing_summary_as_reject() -> None:
    assert not case_accepts_horus({"ok": True}, 0.5)
