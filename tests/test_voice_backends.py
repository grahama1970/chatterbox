"""Backend-neutral VoiceBackend interface tests (issue #12)."""

from __future__ import annotations

import sys
import threading
import time
import types
import wave
from pathlib import Path

import pytest
from fastapi import HTTPException
from starlette.testclient import TestClient

import chatterbox.agent.server as server
from chatterbox.agent.backends import (
    CallableVoiceBackend,
    UnknownBackendError,
    UnsupportedCapabilityError,
    VoiceCapabilities,
)
from chatterbox.agent.server import SynthesisBatchRequest, SynthesisRequest, synthesize_to_file


def write_tiny_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(24000)
        handle.writeframes(b"\x00\x00" * 2400)


class FakeModel:
    sr = 24000

    def __init__(self, sr: int = 24000, fail: bool = False):
        self.sr = sr
        self.fail = fail
        self.calls = 0

    def prepare_conditionals(self, ref_audio: str, **_: object) -> None:
        self.conds = ref_audio

    def generate(self, _text: str, **_: object):
        import torch

        self.calls += 1
        if self.fail:
            raise RuntimeError("injected engine failure")
        return torch.zeros((1, 2400), dtype=torch.float32)


@pytest.fixture()
def env(monkeypatch, tmp_path: Path):
    root = tmp_path / "voices"
    root.mkdir()
    ref = root / "embry.wav"
    ref.write_bytes(b"RIFF-ref")
    turbo = FakeModel()
    monkeypatch.setattr(server, "model", turbo)
    monkeypatch.setattr(server, "base_model", None)
    monkeypatch.setattr(server, "REFERENCE_AUDIO_ROOTS", [root])
    monkeypatch.setattr(server, "voice_conditioning_cache", {})
    monkeypatch.setattr(server, "OUT_DIR", tmp_path / "out")
    monkeypatch.setitem(
        sys.modules,
        "torchaudio",
        types.SimpleNamespace(save=lambda path, *_a, **_k: write_tiny_wav(Path(path))),
    )
    return {"tmp": tmp_path, "ref": str(ref), "turbo": turbo, "monkeypatch": monkeypatch}


AFFECT_DELIVERY = {"intensity": 0.7, "valence": -0.4}


def test_capabilities_and_digests_present() -> None:
    summary = server.VOICE_BACKENDS.summary()
    assert sorted(summary) == ["chatterbox_base_affect", "chatterbox_turbo"]
    for entry in summary.values():
        caps = entry["capabilities"]
        for field in (
            "backend_id",
            "revision",
            "voice_cloning",
            "preset_voices",
            "structured_affect_axes",
            "per_segment_delivery",
            "true_incremental_streaming",
            "cooperative_inference_cancellation",
            "deterministic_seed",
            "input_sample_formats",
            "output_sample_formats",
            "estimated_resident_vram_mb",
            "max_concurrency",
        ):
            assert field in caps
        assert len(entry["capability_digest"]) == 64
    assert summary["chatterbox_turbo"]["capabilities"]["structured_affect_axes"] is False
    assert summary["chatterbox_base_affect"]["capabilities"]["structured_affect_axes"] is True


def test_unknown_backend_fails_closed_before_render(env) -> None:
    with pytest.raises(HTTPException) as exc:
        synthesize_to_file(
            SynthesisRequest(text="hello", ref_audio=env["ref"], backend="nope"),
            env["tmp"] / "x.wav",
        )
    assert exc.value.status_code == 422
    assert exc.value.detail["reason"] == "unknown_backend"
    assert env["turbo"].calls == 0


def test_unsupported_capability_fails_closed_before_render(env) -> None:
    with pytest.raises(HTTPException) as exc:
        synthesize_to_file(
            SynthesisRequest(
                text="hello",
                ref_audio=env["ref"],
                backend="chatterbox_turbo",
                voice_delivery=AFFECT_DELIVERY,
            ),
            env["tmp"] / "x.wav",
        )
    assert exc.value.status_code == 422
    assert exc.value.detail["reason"] == "backend_capability_unsupported:structured_affect_axes"
    assert env["turbo"].calls == 0


def test_affect_auto_selection_records_backend(env) -> None:
    env["monkeypatch"].setattr(server, "base_model", FakeModel())
    result = synthesize_to_file(
        SynthesisRequest(text="hello", ref_audio=env["ref"], voice_delivery=AFFECT_DELIVERY),
        env["tmp"] / "affect.wav",
    )
    assert result["ok"] is True
    assert result["engine"] == "chatterbox_base"
    assert result["backend"]["id"] == "chatterbox_base_affect"
    assert result["backend"]["selection_source"] == "affect_auto"
    assert result["backend"]["capability_digest"]
    assert env["turbo"].calls == 0


def test_default_selection_uses_turbo(env) -> None:
    result = synthesize_to_file(
        SynthesisRequest(text="hello", ref_audio=env["ref"]),
        env["tmp"] / "turbo.wav",
    )
    assert result["ok"] is True
    assert result["engine"] == "chatterbox_turbo"
    assert result["backend"]["id"] == "chatterbox_turbo"
    assert result["backend"]["selection_source"] == "default"


def test_selected_backend_failure_never_falls_back(env) -> None:
    failing = FakeModel(fail=True)
    env["monkeypatch"].setattr(server, "base_model", failing)
    result = synthesize_to_file(
        SynthesisRequest(text="hello", ref_audio=env["ref"], voice_delivery=AFFECT_DELIVERY),
        env["tmp"] / "fail.wav",
    )
    assert result["ok"] is False
    assert result["engine"] == "chatterbox_base"
    assert result["backend"]["id"] == "chatterbox_base_affect"
    assert result["failed_gates"] == ["generation_exception"]
    assert env["turbo"].calls == 0  # no silent fallback to turbo


def test_output_sample_rate_mismatch_gates(env) -> None:
    env["monkeypatch"].setattr(server, "base_model", FakeModel(sr=16000))
    result = synthesize_to_file(
        SynthesisRequest(text="hello", ref_audio=env["ref"], voice_delivery=AFFECT_DELIVERY),
        env["tmp"] / "sr.wav",
    )
    assert "output_sample_rate_matches_declared" in result["failed_gates"]
    assert result["output_format"] == {
        "declared_sample_rate": 24000,
        "backend_sample_rate": 16000,
        "channels": 1,
        "container": "wav",
    }


def test_single_flight_concurrent_load() -> None:
    loads = {"count": 0}
    loaded = {"value": False}

    def slow_loader():
        loads["count"] += 1
        time.sleep(0.05)
        loaded["value"] = True

    backend = CallableVoiceBackend(
        caps=server.VOICE_BACKENDS.get("chatterbox_base_affect").caps,
        loader=slow_loader,
        generator=lambda **_: (None, 24000, {}),
        is_loaded=lambda: loaded["value"],
    )
    threads = [threading.Thread(target=backend.load) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert loads["count"] == 1
    assert backend.health().state == "loaded"


def test_health_transitions_and_unload() -> None:
    state = {"loaded": False}

    def unload():
        state["loaded"] = False

    backend = CallableVoiceBackend(
        caps=server.VOICE_BACKENDS.get("chatterbox_base_affect").caps,
        loader=lambda: state.__setitem__("loaded", True),
        generator=lambda **_: (None, 24000, {}),
        is_loaded=lambda: state["loaded"],
        unloader=unload,
    )
    assert backend.health().state == "unloaded"
    backend.load()
    assert backend.health().state == "loaded"
    assert backend.health().load_seconds is not None
    backend.unload()
    assert backend.health().state == "unloaded"

    def broken_loader():
        raise RuntimeError("no weights")

    failing = CallableVoiceBackend(
        caps=backend.caps,
        loader=broken_loader,
        generator=lambda **_: (None, 24000, {}),
        is_loaded=lambda: False,
    )
    with pytest.raises(RuntimeError):
        failing.load()
    assert failing._health.state == "failed"


def test_registry_typed_errors() -> None:
    with pytest.raises(UnknownBackendError):
        server.VOICE_BACKENDS.get("qwen3")
    with pytest.raises(UnsupportedCapabilityError):
        server.select_voice_backend_for_request("chatterbox_turbo", {"exaggeration": 1.0})


def test_batch_and_stream_receipts_carry_backend_identity(env) -> None:
    env["monkeypatch"].setattr(
        server,
        "synthesize_to_file",
        lambda chunk_request, out_path: (write_tiny_wav(Path(out_path)) or {"ok": True, "audio": str(out_path)}),
    )
    env["monkeypatch"].setattr(server, "resolve_reference_audio", lambda value=None: Path(env["ref"]))
    env["monkeypatch"].setattr(
        server,
        "combine_audio_segments",
        lambda segments, out_path, crossfade_ms=20: (write_tiny_wav(Path(out_path)) or {"bytes": 5000}),
    )
    env["monkeypatch"].setitem(
        sys.modules,
        "torchaudio",
        types.SimpleNamespace(
            save=lambda path, *_a, **_k: write_tiny_wav(Path(path)),
            load=lambda path: (__import__("torch").zeros((1, 960)), 24000),
        ),
    )
    payload = {
        "answer_text": "Backend identity must appear in receipts for this answer.",
        "max_chars": 120,
        "pause_after_ms": 0,
        "completion_cue": "",
        "include_completion_cue": False,
        "crossfade_ms": 0,
        "use_blessed_qra_cache": False,
    }
    batch = server.synthesize_batch(SynthesisBatchRequest(**payload, label="be-batch"))
    assert batch["backend"]["id"] == "chatterbox_turbo"
    assert batch["backend"]["capability_digest"]

    client = TestClient(server.app)
    response = client.post("/synthesize-batch-stream", json={**payload, "label": "be-stream"})
    assert response.status_code == 200
    import json as jsonlib

    manifest_files = sorted((env["tmp"] / "out" / "be-stream").glob("stream_manifest_*.json"))
    manifest = jsonlib.loads(manifest_files[0].read_text(encoding="utf-8"))
    assert manifest["backend"]["id"] == "chatterbox_turbo"
    assert manifest["backend"]["capability_digest"]

    assert client.post("/synthesize-batch-stream", json={**payload, "backend": "nope"}).status_code == 422


def test_same_plan_renders_through_either_backend(env) -> None:
    env["monkeypatch"].setattr(server, "base_model", FakeModel())
    chunks = [{"text": "Same canonical plan for both backends."}]
    turbo_result = synthesize_to_file(
        SynthesisRequest(text=chunks[0]["text"], ref_audio=env["ref"], backend="chatterbox_turbo"),
        env["tmp"] / "plan-turbo.wav",
    )
    affect_result = synthesize_to_file(
        SynthesisRequest(
            text=chunks[0]["text"],
            ref_audio=env["ref"],
            backend="chatterbox_base_affect",
            voice_delivery=AFFECT_DELIVERY,
        ),
        env["tmp"] / "plan-affect.wav",
    )
    assert turbo_result["ok"] is True and affect_result["ok"] is True
    assert turbo_result["text_sha256"] == affect_result["text_sha256"]
    assert {turbo_result["backend"]["id"], affect_result["backend"]["id"]} == {
        "chatterbox_turbo",
        "chatterbox_base_affect",
    }
