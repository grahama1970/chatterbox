"""Tests for browser/WebRTC transport receipt helpers.

These tests do not prove browser microphone access or WebRTC transport. They
cover deterministic helper behavior only.
"""

from __future__ import annotations

import importlib.util
import sys
import wave
from pathlib import Path


def load_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "smoke_browser_webrtc_transport.py"
    spec = importlib.util.spec_from_file_location("smoke_browser_webrtc_transport", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_write_wav_float32_shape(tmp_path: Path) -> None:
    mod = load_module()
    path = tmp_path / "audio.wav"
    mod.write_wav_float32(path, [0.0, 0.5, -0.5], 16000)

    with wave.open(str(path), "rb") as handle:
        assert handle.getnchannels() == 1
        assert handle.getframerate() == 16000
        assert handle.getsampwidth() == 2
        assert handle.getnframes() == 3
