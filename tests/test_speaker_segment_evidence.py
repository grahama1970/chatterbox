"""Tests for fixed-window speaker segment evidence harness.

These tests cover fail-closed receipt shape only. They do not prove live
speaker segmentation or diarization.
"""

from __future__ import annotations

import importlib.util
import sys
from argparse import Namespace
from pathlib import Path


def load_segment_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "smoke_speaker_segment_evidence.py"
    spec = importlib.util.spec_from_file_location("smoke_speaker_segment_evidence", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_speaker_segment_missing_inputs_fail_closed(tmp_path: Path) -> None:
    mod = load_segment_module()
    args = Namespace(
        audio=tmp_path / "missing-audio.wav",
        horus_enrollment=tmp_path / "missing-horus.wav",
        embry_enrollment=tmp_path / "missing-embry.wav",
        window_s=2.4,
        hop_s=1.2,
        min_primary_margin=0.03,
        min_primary_ratio=0.5,
        min_window_rms=0.003,
        min_voiced_segments=4,
    )

    receipt = mod.run(args)

    assert receipt["schema"] == "chatterbox.speaker_segment_evidence.v1"
    assert receipt["ok"] is False
    assert receipt["mocked"] is False
    assert receipt["live"] is False
    assert receipt["claims"]["proves"] == []
    assert "audio_exists" in receipt["failed_gates"]
    assert "horus_enrollment_exists" in receipt["failed_gates"]
    assert "embry_enrollment_exists" in receipt["failed_gates"]
