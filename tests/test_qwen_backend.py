"""Qwen3-TTS experimental backend tests with the sidecar absent (issue #13)."""

from __future__ import annotations

import sys
import types
import wave
from pathlib import Path

import pytest
from fastapi import HTTPException
from starlette.testclient import TestClient

import chatterbox.agent.qwen_backend as qwen_backend
import chatterbox.agent.server as server
from chatterbox.agent.server import SynthesisRequest, synthesize_to_file


def write_tiny_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(24000)
        handle.writeframes(b"\x00\x00" * 2400)


class FakeTurbo:
    sr = 24000

    def __init__(self):
        self.calls = 0

    def prepare_conditionals(self, ref_audio: str, **_: object) -> None:
        pass

    def generate(self, _text: str, **_: object):
        import torch

        self.calls += 1
        return torch.zeros((1, 2400), dtype=torch.float32)


@pytest.fixture()
def env(monkeypatch, tmp_path: Path):
    root = tmp_path / "voices"
    root.mkdir()
    ref = root / "embry.wav"
    write_tiny_wav(ref)
    turbo = FakeTurbo()
    monkeypatch.setattr(server, "model", turbo)
    monkeypatch.setattr(server, "REFERENCE_AUDIO_ROOTS", [root])
    monkeypatch.setattr(server, "voice_conditioning_cache", {})
    monkeypatch.setattr(server, "OUT_DIR", tmp_path / "out")
    monkeypatch.setattr(server, "turn_controls", {})
    monkeypatch.setitem(
        sys.modules,
        "torchaudio",
        types.SimpleNamespace(
            save=lambda path, *_a, **_k: write_tiny_wav(Path(path)),
            load=lambda path: (__import__("torch").zeros((1, 960)), 24000),
        ),
    )
    return {"tmp": tmp_path, "ref": str(ref), "turbo": turbo, "monkeypatch": monkeypatch}


def test_default_install_never_imports_qwen_dependencies() -> None:
    assert "qwen_tts" not in sys.modules
    assert "qwen3_tts" in server.VOICE_BACKENDS.ids()


def test_capability_honesty_for_qwen_backend() -> None:
    caps = server.VOICE_BACKENDS.get("qwen3_tts").caps
    assert caps.voice_cloning is True
    assert caps.preset_voices is False
    assert caps.structured_affect_axes is False
    assert caps.per_segment_delivery is False
    assert caps.true_incremental_streaming is False
    assert caps.cooperative_inference_cancellation is False
    assert caps.stale_output_fencing is True
    assert caps.deterministic_seed is False
    assert caps.revision.startswith("Qwen/Qwen3-TTS-12Hz-1.7B-Base@")


def test_auto_selection_never_routes_to_qwen() -> None:
    backend, selection = server.select_voice_backend_for_request(None, None)
    assert backend.caps.backend_id == "chatterbox_turbo"
    backend, selection = server.select_voice_backend_for_request(None, {"exaggeration": 1.0})
    assert backend.caps.backend_id == "chatterbox_base_affect"
    assert selection["selection_source"] == "affect_auto"


def test_affect_request_on_qwen_fails_closed(env) -> None:
    with pytest.raises(HTTPException) as exc:
        synthesize_to_file(
            SynthesisRequest(
                text="hello",
                ref_audio=env["ref"],
                backend="qwen3_tts",
                voice_delivery={"intensity": 0.7},
            ),
            env["tmp"] / "x.wav",
        )
    assert exc.value.status_code == 422
    assert exc.value.detail["reason"] == "backend_capability_unsupported:structured_affect_axes"


def test_sidecar_down_fails_without_fallback(env) -> None:
    env["monkeypatch"].setenv("CHATTERBOX_QWEN_SIDECAR_URL", "http://127.0.0.1:1")
    result = synthesize_to_file(
        SynthesisRequest(text="hello", ref_audio=env["ref"], backend="qwen3_tts"),
        env["tmp"] / "qwen-down.wav",
    )
    assert result["ok"] is False
    assert result["engine"] == "qwen3_tts"
    assert result["backend"]["id"] == "qwen3_tts"
    assert "qwen_sidecar_unavailable" in result["error"]
    assert env["turbo"].calls == 0


def test_turbo_failure_never_switches_to_qwen(env) -> None:
    calls = {"sidecar": 0}

    def no_sidecar(*_a, **_k):
        calls["sidecar"] += 1
        raise AssertionError("sidecar must not be called")

    env["monkeypatch"].setattr(qwen_backend, "_request", no_sidecar)

    class FailingTurbo(FakeTurbo):
        def generate(self, _text: str, **_: object):
            raise RuntimeError("turbo down")

    env["monkeypatch"].setattr(server, "model", FailingTurbo())
    result = synthesize_to_file(
        SynthesisRequest(text="hello", ref_audio=env["ref"]),
        env["tmp"] / "turbo-fail.wav",
    )
    assert result["ok"] is False
    assert result["engine"] == "chatterbox_turbo"
    assert calls["sidecar"] == 0


def fake_sidecar_request(responses: dict[str, dict]):
    def _request(path: str, payload=None, timeout=0):
        return responses[path]

    return _request


def test_qwen_generate_returns_normalized_audio(env) -> None:
    import base64

    import numpy as np

    wav = np.zeros(960, dtype=np.float32)
    env["monkeypatch"].setattr(
        qwen_backend,
        "_request",
        fake_sidecar_request(
            {
                "/synthesize": {
                    "ok": True,
                    "wav_b64": base64.b64encode(wav.tobytes()).decode("ascii"),
                    "sample_rate": 24000,
                    "elapsed_s": 0.1,
                    "vram": {"resident_mb": 5000},
                }
            }
        ),
    )
    tensor, sample_rate, conditioning = qwen_backend.qwen_generate(
        text="hello", ref_audio=Path(env["ref"]), params={"temperature": 0.7}
    )
    assert sample_rate == 24000
    assert tensor.shape == (1, 960)
    assert conditioning["engine"] == "qwen3_tts"
    assert conditioning["ignored_generation_params"] == ["temperature"]


def test_stream_manifest_records_qwen_backend(env) -> None:
    import base64
    import json as jsonlib

    import numpy as np

    wav = np.zeros(960, dtype=np.float32)
    responses = {
        "/health": {"ok": True, "model_loaded": True},
        "/load": {"ok": True},
        "/synthesize": {
            "ok": True,
            "wav_b64": base64.b64encode(wav.tobytes()).decode("ascii"),
            "sample_rate": 24000,
            "elapsed_s": 0.1,
            "vram": {},
        },
    }
    env["monkeypatch"].setattr(qwen_backend, "_request", fake_sidecar_request(responses))
    client = TestClient(server.app)
    payload = {
        "answer_text": "Qwen renders this short answer through the stream.",
        "max_chars": 120,
        "pause_after_ms": 0,
        "completion_cue": "",
        "include_completion_cue": False,
        "crossfade_ms": 0,
        "use_blessed_qra_cache": False,
        "backend": "qwen3_tts",
        "label": "qwen-stream",
        "ref_audio": env["ref"],
    }
    response = client.post("/synthesize-batch-stream", json=payload)
    assert response.status_code == 200
    assert len(response.content) > 0
    manifest_files = sorted((env["tmp"] / "out" / "qwen-stream").glob("stream_manifest_*.json"))
    manifest = jsonlib.loads(manifest_files[0].read_text(encoding="utf-8"))
    assert manifest["backend"]["id"] == "qwen3_tts"
    assert manifest["terminal"]["status"] == "completed"
    assert manifest["render_plan_digest"]
