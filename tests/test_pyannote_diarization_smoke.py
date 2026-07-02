"""Tests for the pyannote diarization smoke receipt.

These tests cover fail-closed receipt shape only. They do not prove pyannote
model access, live diarization, speaker count accuracy, or overlap handling.
"""

from __future__ import annotations

import importlib.util
import sys
from argparse import Namespace
from pathlib import Path


def load_pyannote_smoke_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "smoke_pyannote_diarization.py"
    spec = importlib.util.spec_from_file_location("smoke_pyannote_diarization", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_pyannote_missing_audio_and_model_access_fail_closed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGINGFACE_TOKEN", raising=False)
    monkeypatch.delenv("HUGGING_FACE_HUB_TOKEN", raising=False)
    mod = load_pyannote_smoke_module()
    args = Namespace(
        audio=tmp_path / "missing.wav",
        model="pyannote/speaker-diarization-community-1",
        device="auto",
        num_speakers=None,
        min_speakers=None,
        max_speakers=None,
    )

    receipt = mod.run(args)

    assert receipt["schema"] == "chatterbox.pyannote_diarization_smoke.v1"
    assert receipt["ok"] is False
    assert receipt["mocked"] is False
    assert receipt["live"] is False
    assert receipt["claims"]["proves"] == []
    assert "audio_exists" in receipt["failed_gates"]
    assert "hf_token_or_local_model_available" in receipt["failed_gates"]
