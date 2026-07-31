"""Bounded PCM publication tests for /synthesize-batch-stream (issue #8).

These tests run without the Chatterbox model: synthesis and torchaudio are
stubbed, and turn-control state is mutated in-process, so every assertion is
about the server publication layer rather than client transport buffering.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest
from starlette.testclient import TestClient

import chatterbox.agent.server as server


FRAME_BYTES = server.pcm_frame_bytes()
SAMPLES_PER_FRAME = FRAME_BYTES // (server.STREAM_CHANNELS * server.STREAM_BYTES_PER_SAMPLE)

THREE_SENTENCES = (
    "The first spoken sentence is deliberately long enough to stand alone. "
    "The second spoken sentence also stands alone at a similar length. "
    "The third spoken sentence closes the answer at a comparable length."
)


def frame_wav(frames: int = 1):
    import torch

    return torch.zeros((1, SAMPLES_PER_FRAME * frames), dtype=torch.float32)


def stream_payload(turn_id: str | None = None, **overrides) -> dict:
    payload = {
        "answer_text": THREE_SENTENCES,
        "max_chars": 80,
        "pause_after_ms": 0,
        "completion_cue": "",
        "include_completion_cue": False,
        "crossfade_ms": 0,
        "use_blessed_qra_cache": False,
    }
    if turn_id:
        payload["turn_id"] = turn_id
    payload.update(overrides)
    return payload


@pytest.fixture()
def client(monkeypatch, tmp_path: Path) -> TestClient:
    monkeypatch.setattr(server, "OUT_DIR", tmp_path / "out")
    monkeypatch.setattr(server, "turn_controls", {})
    monkeypatch.setitem(sys.modules, "torchaudio", types.SimpleNamespace(load=lambda path: (frame_wav(1), 24000)))
    return TestClient(server.app)


def fake_synth(monkeypatch, cancel_turn_on_call: tuple[str, int] | None = None):
    calls = {"count": 0}

    def synthesize(chunk_request, out_path):
        calls["count"] += 1
        Path(out_path).write_bytes(b"stub")
        if cancel_turn_on_call and calls["count"] == cancel_turn_on_call[1]:
            server.turn_controls[cancel_turn_on_call[0]] = {"cancelled": True}
        return {"ok": True}

    monkeypatch.setattr(server, "synthesize_to_file", synthesize)
    return calls


def test_publication_frame_policy_bounds_40ms() -> None:
    assert server.STREAM_PUBLICATION_FRAME_MS <= 40
    frame = server.pcm_frame_bytes()
    duration_ms = frame / (server.STREAM_SAMPLE_RATE * server.STREAM_CHANNELS * server.STREAM_BYTES_PER_SAMPLE) * 1000
    assert duration_ms <= 40
    assert frame == int(24000 * 0.040) * 2 == 1920
    assert server.pcm_frame_bytes(sample_rate=16000) == int(16000 * 0.040) * 2 == 1280
    assert server.pcm_frame_bytes(sample_rate=10) >= server.STREAM_CHANNELS * server.STREAM_BYTES_PER_SAMPLE


def test_bounded_pcm_frames_admits_nothing_after_stop() -> None:
    data = bytes(FRAME_BYTES * 10)
    state = {"yielded": 0, "stop_after": 3}

    def should_stop() -> bool:
        return state["yielded"] >= state["stop_after"]

    frames = []
    for frame in server.bounded_pcm_frames(data, should_stop):
        frames.append(frame)
        state["yielded"] += 1
    assert len(frames) == 3
    assert all(len(frame) == FRAME_BYTES for frame in frames)


def test_stream_emits_zero_bytes_for_precancelled_turn(client: TestClient, monkeypatch) -> None:
    fake_synth(monkeypatch)
    turn_id = "turn-precancel"
    cancel = client.post(f"/turn/{turn_id}/cancel", json={"reason": "test", "old_turn_id": turn_id})
    assert cancel.status_code == 200 and cancel.json()["control"]["cancelled"] is True
    response = client.post("/synthesize-batch-stream", json=stream_payload(turn_id))
    assert response.status_code == 200
    assert "audio/l16" in response.headers["content-type"].lower()
    assert len(response.content) == 0


def test_stream_admits_no_frame_after_mid_generation_cancel(client: TestClient, monkeypatch) -> None:
    turn_id = "turn-midcancel"
    fake_synth(monkeypatch, cancel_turn_on_call=(turn_id, 3))
    response = client.post("/synthesize-batch-stream", json=stream_payload(turn_id))
    assert response.status_code == 200
    # chunk 1 is admitted before the cancel is accepted during chunk 3's
    # synthesis; chunk 2 is still held as crossfade tail and chunk 3 onward
    # must never publish, so at most one already-admitted frame appears.
    assert len(response.content) == FRAME_BYTES


def test_stream_admits_no_frame_after_mid_generation_stop(client: TestClient, monkeypatch) -> None:
    turn_id = "turn-midstop"
    calls = {"count": 0}

    def synthesize(chunk_request, out_path):
        calls["count"] += 1
        Path(out_path).write_bytes(b"stub")
        if calls["count"] == 3:
            server.turn_controls[turn_id] = {"stopped": True}
        return {"ok": True}

    monkeypatch.setattr(server, "synthesize_to_file", synthesize)
    response = client.post("/synthesize-batch-stream", json=stream_payload(turn_id))
    assert response.status_code == 200
    assert len(response.content) == FRAME_BYTES


def blessed_hit(paths: list[Path]) -> dict:
    return {
        "hit": True,
        "answer_text": "The cached blessed answer text.",
        "chunks": [
            {"audio": str(path), "text": f"Cached chunk {index}.", "pause_after_ms": 0}
            for index, path in enumerate(paths, start=1)
        ],
    }


def test_blessed_qra_stream_zero_bytes_for_precancelled_turn(client: TestClient, monkeypatch, tmp_path: Path) -> None:
    audio = tmp_path / "blessed_1.wav"
    audio.write_bytes(b"stub")
    monkeypatch.setattr(server, "find_blessed_qra_match", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "apply_blessed_qra_memory_gate", lambda request, match: blessed_hit([audio]))
    turn_id = "turn-blessed-precancel"
    client.post(f"/turn/{turn_id}/cancel", json={"reason": "test", "old_turn_id": turn_id})
    payload = stream_payload(turn_id, use_blessed_qra_cache=True, question_text="what is the cached answer?")
    response = client.post("/synthesize-batch-stream", json=payload)
    assert response.status_code == 200
    assert len(response.content) == 0


def test_blessed_qra_stream_admits_no_frame_after_mid_cancel(client: TestClient, monkeypatch, tmp_path: Path) -> None:
    first = tmp_path / "blessed_1.wav"
    second = tmp_path / "blessed_2.wav"
    first.write_bytes(b"stub")
    second.write_bytes(b"stub")
    turn_id = "turn-blessed-midcancel"

    def load(path):
        if str(path) == str(second):
            server.turn_controls[turn_id] = {"cancelled": True}
        return frame_wav(5), 24000

    monkeypatch.setitem(sys.modules, "torchaudio", types.SimpleNamespace(load=load))
    monkeypatch.setattr(server, "find_blessed_qra_match", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "apply_blessed_qra_memory_gate", lambda request, match: blessed_hit([first, second]))
    payload = stream_payload(turn_id, use_blessed_qra_cache=True, question_text="what is the cached answer?")
    response = client.post("/synthesize-batch-stream", json=payload)
    assert response.status_code == 200
    assert len(response.content) == FRAME_BYTES * 5


def test_duplicate_cancel_is_idempotent(client: TestClient, monkeypatch) -> None:
    fake_synth(monkeypatch)
    turn_id = "turn-dup-cancel"
    first = client.post(f"/turn/{turn_id}/cancel", json={"reason": "test", "old_turn_id": turn_id})
    second = client.post(f"/turn/{turn_id}/cancel", json={"reason": "test again", "old_turn_id": turn_id})
    assert first.json()["ok"] is True and second.json()["ok"] is True
    assert second.json()["control"]["cancelled"] is True
    response = client.post("/synthesize-batch-stream", json=stream_payload(turn_id))
    assert len(response.content) == 0


def test_cancel_for_other_turn_does_not_stop_stream(client: TestClient, monkeypatch) -> None:
    fake_synth(monkeypatch)
    client.post("/turn/turn-other/cancel", json={"reason": "test", "old_turn_id": "turn-other"})
    response = client.post("/synthesize-batch-stream", json=stream_payload("turn-live"))
    assert response.status_code == 200
    # three planned chunks, one frame each, all admitted
    assert len(response.content) == FRAME_BYTES * 3


def test_non_cancelled_stream_is_valid_pcm_at_declared_format(client: TestClient, monkeypatch) -> None:
    fake_synth(monkeypatch)
    response = client.post("/synthesize-batch-stream", json=stream_payload())
    assert response.status_code == 200
    content_type = response.headers["content-type"].lower()
    assert "audio/l16" in content_type and "rate=24000" in content_type and "channels=1" in content_type
    assert len(response.content) % (server.STREAM_CHANNELS * server.STREAM_BYTES_PER_SAMPLE) == 0
    assert len(response.content) == FRAME_BYTES * 3
