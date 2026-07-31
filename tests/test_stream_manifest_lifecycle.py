"""Fault-injection tests for stream manifests and exactly-one terminal (issue #10).

Every terminal assertion reads the persisted manifest back from disk.
"""

from __future__ import annotations

import json
import sys
import types
import wave
from pathlib import Path

import pytest
from starlette.testclient import TestClient

import chatterbox.agent.server as server
from chatterbox.agent.server import SynthesisBatchRequest
from chatterbox.agent.stream_manifest import (
    STREAM_RECEIPT_SCHEMA,
    StreamManifest,
    validate_stream_manifest,
)


ANSWER_TEXT = (
    "The first spoken sentence is deliberately long enough to stand alone. "
    "The second spoken sentence also stands alone at a similar length. "
    "The third spoken sentence closes the answer at a comparable length."
)


def write_tiny_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(24000)
        handle.writeframes(b"\x00\x00" * 2400)


@pytest.fixture()
def env(monkeypatch, tmp_path: Path):
    out_dir = tmp_path / "out"
    monkeypatch.setattr(server, "OUT_DIR", out_dir)
    monkeypatch.setattr(server, "turn_controls", {})
    monkeypatch.setattr(server, "STREAM_MANIFEST_INDEX", {})
    monkeypatch.setitem(
        sys.modules,
        "torchaudio",
        types.SimpleNamespace(load=lambda path: (__import__("torch").zeros((1, 960)), 24000)),
    )

    def fake_synthesize(chunk_request, out_path):
        write_tiny_wav(Path(out_path))
        return {"ok": True, "audio": str(out_path)}

    monkeypatch.setattr(server, "synthesize_to_file", fake_synthesize)
    return {"out_dir": out_dir, "client": TestClient(server.app), "monkeypatch": monkeypatch}


def payload(turn_id: str | None = None, **overrides) -> dict:
    body = {
        "answer_text": ANSWER_TEXT,
        "max_chars": 80,
        "pause_after_ms": 0,
        "completion_cue": "",
        "include_completion_cue": False,
        "crossfade_ms": 0,
        "use_blessed_qra_cache": False,
    }
    if turn_id:
        body["turn_id"] = turn_id
    body.update(overrides)
    return body


def read_manifest(out_dir: Path, label: str) -> dict:
    files = sorted((out_dir / label).glob("stream_manifest_*.json"))
    assert len(files) == 1
    return json.loads(files[0].read_text(encoding="utf-8"))


def test_normal_completion_terminal(env) -> None:
    response = env["client"].post("/synthesize-batch-stream", json=payload(label="mf-complete"))
    assert response.status_code == 200 and len(response.content) > 0
    manifest = read_manifest(env["out_dir"], "mf-complete")
    assert manifest["schema"] == STREAM_RECEIPT_SCHEMA
    assert manifest["status"] == "completed"
    assert manifest["terminal"]["status"] == "completed"
    assert manifest["terminal"]["published_bytes"] == len(response.content)
    assert validate_stream_manifest(manifest) == []
    assert response.headers["x-stream-id"] == manifest["stream_id"]


def test_cancel_before_first_audio(env) -> None:
    turn = "mf-precancel"
    env["client"].post(f"/turn/{turn}/cancel", json={"reason": "t", "old_turn_id": turn})
    response = env["client"].post("/synthesize-batch-stream", json=payload(turn, label="mf-precancel"))
    assert len(response.content) == 0
    manifest = read_manifest(env["out_dir"], "mf-precancel")
    assert manifest["terminal"]["status"] == "cancelled"
    assert manifest["terminal"]["reason"] == "turn_cancelled"
    assert manifest["terminal"]["published_bytes"] == 0
    assert validate_stream_manifest(manifest) == []


def test_cancel_during_audio(env) -> None:
    turn = "mf-midcancel"
    calls = {"count": 0}

    def synth(chunk_request, out_path):
        calls["count"] += 1
        write_tiny_wav(Path(out_path))
        if calls["count"] == 3:
            server.turn_controls[turn] = {"cancelled": True}
        return {"ok": True, "audio": str(out_path)}

    env["monkeypatch"].setattr(server, "synthesize_to_file", synth)
    response = env["client"].post("/synthesize-batch-stream", json=payload(turn, label="mf-midcancel"))
    assert response.status_code == 200
    manifest = read_manifest(env["out_dir"], "mf-midcancel")
    assert manifest["terminal"]["status"] == "cancelled"
    assert manifest["terminal"]["reason"] == "turn_cancelled"
    assert manifest["terminal"]["published_bytes"] == len(response.content)
    assert validate_stream_manifest(manifest) == []


def test_stop_during_audio(env) -> None:
    turn = "mf-midstop"
    calls = {"count": 0}

    def synth(chunk_request, out_path):
        calls["count"] += 1
        write_tiny_wav(Path(out_path))
        if calls["count"] == 3:
            server.turn_controls[turn] = {"stopped": True}
        return {"ok": True, "audio": str(out_path)}

    env["monkeypatch"].setattr(server, "synthesize_to_file", synth)
    env["client"].post("/synthesize-batch-stream", json=payload(turn, label="mf-midstop"))
    manifest = read_manifest(env["out_dir"], "mf-midstop")
    assert manifest["terminal"]["status"] == "cancelled"
    assert manifest["terminal"]["reason"] == "turn_stopped"


def test_segment_synthesis_failure_terminates_failed(env) -> None:
    calls = {"count": 0}

    def synth(chunk_request, out_path):
        calls["count"] += 1
        if calls["count"] == 2:
            return {"ok": False, "error": "injected"}
        write_tiny_wav(Path(out_path))
        return {"ok": True, "audio": str(out_path)}

    env["monkeypatch"].setattr(server, "synthesize_to_file", synth)
    response = env["client"].post("/synthesize-batch-stream", json=payload(label="mf-segfail"))
    assert response.status_code == 200  # raw EOF stays raw; the manifest carries the truth
    manifest = read_manifest(env["out_dir"], "mf-segfail")
    assert manifest["terminal"]["status"] == "failed"
    assert manifest["terminal"]["reason"] == "segment_synthesis_failed"
    assert manifest["terminal"]["failed_gates"] == ["chunk_2_synthesis_ok"]
    events = [event["event"] for event in manifest["events"]]
    assert "segment_synthesis_failed" in events
    assert validate_stream_manifest(manifest) == []


def test_client_disconnect_records_explicit_terminal(env) -> None:
    import asyncio

    response = server.synthesize_batch_stream(SynthesisBatchRequest(**payload(label="mf-disconnect")))

    async def read_one_then_disconnect():
        iterator = response.body_iterator
        first = await iterator.__anext__()
        assert len(first) > 0
        await iterator.aclose()

    asyncio.run(read_one_then_disconnect())
    manifest = read_manifest(env["out_dir"], "mf-disconnect")
    assert manifest["terminal"]["status"] == "cancelled"
    assert manifest["terminal"]["reason"] == "client_disconnected"
    assert validate_stream_manifest(manifest) == []


def test_producer_exception_terminates_failed(env) -> None:
    def synth(chunk_request, out_path):
        raise RuntimeError("gpu fell over")

    env["monkeypatch"].setattr(server, "synthesize_to_file", synth)
    response = server.synthesize_batch_stream(SynthesisBatchRequest(**payload(label="mf-exc")))

    import asyncio

    async def drain():
        async for _ in response.body_iterator:
            pass

    with pytest.raises(RuntimeError):
        asyncio.run(drain())
    manifest = read_manifest(env["out_dir"], "mf-exc")
    assert manifest["terminal"]["status"] == "failed"
    assert manifest["terminal"]["reason"] == "producer_exception:RuntimeError"
    assert validate_stream_manifest(manifest) == []


def test_late_duplicate_terminal_is_fenced(tmp_path: Path) -> None:
    manifest = StreamManifest(tmp_path / "m.json", stream_id="s-1", header={"render_plan_digest": "d"})
    assert manifest.finalize("completed", published_bytes=1920) is True
    assert manifest.finalize("cancelled", reason="late") is False
    data = json.loads((tmp_path / "m.json").read_text(encoding="utf-8"))
    assert data["terminal"]["status"] == "completed"
    assert [e["event"] for e in data["events"]].count("terminal") == 1
    assert any(e["event"] == "late_terminal_candidate_ignored" for e in data["events"])
    assert validate_stream_manifest(data) == []


def test_restart_read_back_and_validator_rejections(tmp_path: Path) -> None:
    manifest = StreamManifest(tmp_path / "m.json", stream_id="s-2", header={"render_plan_digest": "digest-a"})
    manifest.finalize("cancelled", reason="turn_cancelled", published_bytes=3840)
    # simulate restart: a fresh process reads only the disk artifact
    data = json.loads((tmp_path / "m.json").read_text(encoding="utf-8"))
    assert validate_stream_manifest(data, expected_render_plan_digest="digest-a") == []
    assert validate_stream_manifest(data, expected_render_plan_digest="digest-b") == ["render_plan_digest_matches"]

    unterminated = StreamManifest(tmp_path / "open.json", stream_id="s-3", header={})
    open_data = json.loads((tmp_path / "open.json").read_text(encoding="utf-8"))
    assert "terminal_state_present" in validate_stream_manifest(open_data)

    corrupt = dict(data)
    corrupt["events"] = data["events"] + [{"event": "terminal", "status": "completed"}]
    assert "exactly_one_terminal_event" in validate_stream_manifest(corrupt)
    corrupt_bytes = json.loads(json.dumps(data))
    corrupt_bytes["terminal"]["published_bytes"] = -3
    assert "published_bytes_possible" in validate_stream_manifest(corrupt_bytes)


def test_manifest_endpoint_correlates_stream_id(env) -> None:
    response = env["client"].post("/synthesize-batch-stream", json=payload(label="mf-endpoint"))
    stream_id = response.headers["x-stream-id"]
    lookup = env["client"].get(f"/stream-manifest/{stream_id}")
    assert lookup.status_code == 200
    body = lookup.json()
    assert body["manifest"]["stream_id"] == stream_id
    assert body["validation_failures"] == []
    assert env["client"].get("/stream-manifest/unknown-id").status_code == 404


def test_manifest_index_is_bounded(env) -> None:
    env["monkeypatch"].setattr(server, "STREAM_MANIFEST_INDEX_MAX", 3)
    for index in range(5):
        server.register_stream_manifest(f"s-{index}", Path(f"/tmp/x-{index}.json"))
    assert len(server.STREAM_MANIFEST_INDEX) == 3
    assert "s-0" not in server.STREAM_MANIFEST_INDEX
