"""Tests for the Rung 8 PipeWire loopback smoke harness.

These tests are receipt-shape and fail-closed checks only. They do not prove
live PipeWire capture, RealtimeSTT, ASR, or speaker identity behavior.
"""

from __future__ import annotations

import importlib.util
import sys
from argparse import Namespace
from pathlib import Path


def load_rung8_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "smoke_rung8_loopback_listener.py"
    spec = importlib.util.spec_from_file_location("smoke_rung8_loopback_listener", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_parse_default_sink_id_from_wpctl_status() -> None:
    mod = load_rung8_module()
    status = """
Audio
 ├─ Sinks:
 │      61. USB Audio Front Headphones          [vol: 1.00]
 │  *   64. Jabra SPEAK 510 Analog Stereo       [vol: 0.80]
 │      66. USB Audio Speakers                  [vol: 1.00]
 ├─ Sources:
 │  *   34. HD Pro Webcam C920 Analog Stereo    [vol: 1.00]
"""

    assert mod.parse_default_sink_id(status) == "64"


def test_capture_loopback_missing_audio_fails_closed(tmp_path: Path, monkeypatch) -> None:
    mod = load_rung8_module()
    monkeypatch.setattr(mod, "pipewire_status", lambda: {"default_sink_id": "64", "wpctl_status": {"returncode": 0}})
    args = Namespace(
        play_audio=tmp_path / "missing.wav",
        sink_target=None,
        record_target=None,
        raw_capture_rate=48000,
        raw_capture_channels=2,
        capture_rate=16000,
        pre_roll_s=0.0,
        post_roll_s=0.0,
        play_timeout_s=1.0,
        min_capture_duration_s=1.0,
        min_capture_rms=50,
    )

    receipt = mod.capture_loopback(args, tmp_path)

    assert receipt["schema"] == "chatterbox.rung8.loopback_capture.v1"
    assert receipt["mocked"] is False
    assert receipt["live"] is False
    assert receipt["ok"] is False
    assert "play_audio_exists" in receipt["failed_gates"]
