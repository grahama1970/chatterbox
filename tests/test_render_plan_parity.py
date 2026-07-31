"""Canonical render-plan parity tests for issue #9.

Every assertion about a plan reads the persisted `render_plan.json` back from
disk (the producer artifact), not just the in-memory response object.
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
from chatterbox.agent.chunking import (
    RENDER_PLAN_SCHEMA,
    compile_render_plan,
    declared_chunk_hash_failures,
    render_plan_digest,
    sha256_text,
)
from chatterbox.agent.server import SynthesisBatchRequest, TauVoiceRenderRequest


ANSWER_TEXT = (
    "The first spoken sentence is deliberately long enough to stand alone. "
    "The second spoken sentence also stands alone at a similar length. "
    "The third spoken sentence closes the answer at a comparable length."
)

RENDER_CHUNKS = [
    {
        "text": "Careful first segment with its own tone.",
        "text_sha256": sha256_text("Careful first segment with its own tone."),
        "tone": "careful_concerned",
        "delivery_stage": "slightly_concerned",
        "pace": "slow",
        "pause_strategy": "long_pauses",
        "pause_after_ms": 120,
        "interruptible": True,
    },
    {
        "text": "Firm second segment that must not be re-split.",
        "text_sha256": sha256_text("Firm second segment that must not be re-split."),
        "tone": "firm_boundary",
        "delivery_stage": "neutral",
        "pace": "normal",
        "pause_strategy": "tight",
        "pause_after_ms": 0,
        "interruptible": False,
    },
]


def write_tiny_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(24000)
        handle.writeframes(b"\x00\x00" * 2400)


def write_blessed_qra_ledger(tmp_path: Path) -> Path:
    audio = tmp_path / "blessed-variant.wav"
    write_tiny_wav(audio)
    ledger = {
        "schema_version": "blessed_qra_response_cache.v1",
        "enabled": True,
        "entries": [
            {
                "id": "qra-si-answer",
                "memory_keys": ["qra-si-answer"],
                "blessed": True,
                "question_text": "Which control family should I use when the answer says SI?",
                "question_variants": [],
                "answer_text": "Use system and communications protection.",
                "audio_variants": [
                    {
                        "id": "variant_0",
                        "name": "Variant 0",
                        "default": True,
                        "blessed": True,
                        "chunks": [
                            {
                                "index": 1,
                                "text": "Use system and communications protection.",
                                "delivery_stage": "neutral",
                                "pause_after_ms": 0,
                                "audio": str(audio),
                                "audio_sha256": server.sha256_file(audio),
                            }
                        ],
                    }
                ],
            }
        ],
    }
    path = tmp_path / "blessed-qra-ledger.json"
    path.write_text(json.dumps(ledger), encoding="utf-8")
    return path


@pytest.fixture()
def env(monkeypatch, tmp_path: Path):
    out_dir = tmp_path / "out"
    monkeypatch.setattr(server, "OUT_DIR", out_dir)
    monkeypatch.setattr(server, "turn_controls", {})
    monkeypatch.setitem(
        sys.modules,
        "torchaudio",
        types.SimpleNamespace(load=lambda path: (__import__("torch").zeros((1, 960)), 24000)),
    )

    def fake_synthesize(chunk_request, out_path):
        write_tiny_wav(Path(out_path))
        return {"ok": True, "audio": str(out_path)}

    def fake_combine(segments, out_path, *, crossfade_ms=20):
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        write_tiny_wav(Path(out_path))
        return {"path": str(out_path), "exists": True, "bytes": Path(out_path).stat().st_size, "duration_seconds": 0.1}

    ref_audio = tmp_path / "ref.wav"
    write_tiny_wav(ref_audio)
    monkeypatch.setattr(server, "resolve_reference_audio", lambda value=None: ref_audio)
    monkeypatch.setattr(server, "synthesize_to_file", fake_synthesize)
    monkeypatch.setattr(server, "combine_audio_segments", fake_combine)
    return {"out_dir": out_dir, "client": TestClient(server.app), "monkeypatch": monkeypatch}


def base_payload(**overrides) -> dict:
    payload = {
        "answer_text": ANSWER_TEXT,
        "max_chars": 80,
        "pause_after_ms": 100,
        "completion_cue": "",
        "include_completion_cue": False,
        "crossfade_ms": 0,
        "use_blessed_qra_cache": False,
    }
    payload.update(overrides)
    return payload


def read_plan_receipt(out_dir: Path, label: str) -> dict:
    return json.loads((out_dir / label / "render_plan.json").read_text(encoding="utf-8"))


def plan_chunk_identity(plan: dict) -> list[dict]:
    return [
        {
            key: chunk.get(key)
            for key in (
                "index",
                "text",
                "text_sha256",
                "delivery_stage",
                "tone",
                "pace",
                "pause_strategy",
                "pause_after_ms",
                "can_interrupt_after",
            )
        }
        for chunk in plan["chunks"]
    ]


def test_plain_answer_text_digest_parity_batch_vs_stream(env) -> None:
    batch = server.synthesize_batch(SynthesisBatchRequest(**base_payload(label="parity-batch")))
    response = env["client"].post("/synthesize-batch-stream", json=base_payload(label="parity-stream"))
    assert response.status_code == 200

    batch_receipt = read_plan_receipt(env["out_dir"], "parity-batch")
    stream_receipt = read_plan_receipt(env["out_dir"], "parity-stream")
    assert batch_receipt["plan"]["plan_schema"] == RENDER_PLAN_SCHEMA
    assert batch_receipt["render_plan_digest"] == stream_receipt["render_plan_digest"]
    assert plan_chunk_identity(batch_receipt["plan"]) == plan_chunk_identity(stream_receipt["plan"])
    assert batch_receipt["applied_controls"] == stream_receipt["applied_controls"]
    assert response.headers["x-render-plan-digest"] == stream_receipt["render_plan_digest"]
    assert batch["render_plan_digest"] == batch_receipt["render_plan_digest"]
    # digest recomputes identically from the persisted artifact
    assert render_plan_digest(stream_receipt["plan"]) == stream_receipt["render_plan_digest"]


def test_render_chunks_honored_by_stream_with_digest_parity(env) -> None:
    payload = base_payload(label="chunks-stream", render_chunks=RENDER_CHUNKS)
    response = env["client"].post("/synthesize-batch-stream", json=payload)
    assert response.status_code == 200
    server.synthesize_batch(SynthesisBatchRequest(**base_payload(label="chunks-batch", render_chunks=RENDER_CHUNKS)))

    stream_receipt = read_plan_receipt(env["out_dir"], "chunks-stream")
    batch_receipt = read_plan_receipt(env["out_dir"], "chunks-batch")
    assert stream_receipt["render_plan_digest"] == batch_receipt["render_plan_digest"]
    chunks = stream_receipt["plan"]["chunks"]
    assert [chunk["text"] for chunk in chunks] == [item["text"] for item in RENDER_CHUNKS]
    assert [chunk["tone"] for chunk in chunks] == ["careful_concerned", "firm_boundary"]
    assert [chunk["pace"] for chunk in chunks] == ["slow", "normal"]
    assert [chunk["pause_strategy"] for chunk in chunks] == ["long_pauses", "tight"]
    assert [chunk["pause_after_ms"] for chunk in chunks] == [120, 0]
    assert [chunk["can_interrupt_after"] for chunk in chunks] == [True, False]
    assert stream_receipt["plan"]["chunking_strategy"]["name"] == "caller_supplied_chunks"


def test_declared_hash_mismatch_fails_closed_same_reason_code(env) -> None:
    corrupted = [dict(RENDER_CHUNKS[0]), dict(RENDER_CHUNKS[1])]
    corrupted[1]["text_sha256"] = "0" * 64

    batch = server.synthesize_batch(SynthesisBatchRequest(**base_payload(label="hash-batch", render_chunks=corrupted)))
    assert batch["ok"] is False
    assert batch["reason"] == "render_chunk_hash_mismatch"
    assert batch["failed_gates"] == ["chunk_2_text_sha256_matches"]

    response = env["client"].post(
        "/synthesize-batch-stream", json=base_payload(label="hash-stream", render_chunks=corrupted)
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["reason"] == "render_chunk_hash_mismatch"
    assert detail["failed_gates"] == ["chunk_2_text_sha256_matches"]


def test_completion_cue_separate_from_answer_identity(env) -> None:
    with_cue = base_payload(label="cue-on", completion_cue="Answer complete.", include_completion_cue=True)
    without_cue = base_payload(label="cue-off")
    server.synthesize_batch(SynthesisBatchRequest(**with_cue))
    server.synthesize_batch(SynthesisBatchRequest(**without_cue))

    cue_plan = read_plan_receipt(env["out_dir"], "cue-on")["plan"]
    plain_plan = read_plan_receipt(env["out_dir"], "cue-off")["plan"]
    assert cue_plan["answer_text_sha256"] == plain_plan["answer_text_sha256"]
    assert cue_plan["completion_cue_sha256"] == sha256_text("Answer complete.")
    assert all("Answer complete." not in chunk["text"] for chunk in cue_plan["chunks"])
    assert cue_plan["render_plan_digest"] != plain_plan["render_plan_digest"]


def test_blessed_qra_cached_plan_digest_parity(env, tmp_path: Path) -> None:
    ledger = write_blessed_qra_ledger(tmp_path)
    env["monkeypatch"].setattr(server, "BLESSED_QRA_LEDGER_PATH", ledger)
    blessed_payload = base_payload(
        label="blessed-batch",
        answer_text=" ",
        question_text="Which control family should I use when the answer says SI?",
        use_blessed_qra_cache=True,
        require_blessed_qra_memory_gate=False,
    )
    batch = server.synthesize_batch(SynthesisBatchRequest(**blessed_payload))
    assert batch["blessed_qra_cache"]["hit"] is True

    response = env["client"].post(
        "/synthesize-batch-stream", json={**blessed_payload, "label": "blessed-stream"}
    )
    assert response.status_code == 200

    batch_receipt = read_plan_receipt(env["out_dir"], "blessed-batch")
    stream_receipt = read_plan_receipt(env["out_dir"], "blessed-stream")
    assert batch_receipt["render_plan_digest"] == stream_receipt["render_plan_digest"]
    assert batch_receipt["entry_point"] == "synthesize_batch.blessed_qra"
    assert response.headers["x-render-plan-digest"] == stream_receipt["render_plan_digest"]
    assert batch["render_plan_digest"] == batch_receipt["render_plan_digest"]


def test_tau_voice_render_v1_envelope_carries_digest(env) -> None:
    request = TauVoiceRenderRequest(
        conversation_id="conv-parity",
        turn_id="turn-parity",
        question_text="What is the plan digest?",
        question_text_sha256=sha256_text("What is the plan digest?"),
        memory_route_decision={"called": True, "source": "memory.recall"},
        use_blessed_qra_cache=False,
        speakable_chunks=[
            {
                "text": "Tau chunk one keeps its pace.",
                "text_sha256": sha256_text("Tau chunk one keeps its pace."),
                "tone": "warm",
                "pace": "slow",
                "pause_strategy": "long_pauses",
                "pause_after_ms": 80,
                "interruptible": True,
            },
            {
                "text": "Tau chunk two closes firmly.",
                "text_sha256": sha256_text("Tau chunk two closes firmly."),
                "tone": "confident",
                "pace": "normal",
                "interruptible": False,
            },
        ],
    )
    result = server.tau_voice_render(request)
    assert result["ok"] is True
    assert result["render_plan_digest"] == result["render_plan"]["render_plan_digest"]

    receipt = read_plan_receipt(env["out_dir"], result["batch_label"])
    assert receipt["render_plan_digest"] == result["render_plan_digest"]
    chunks = receipt["plan"]["chunks"]
    assert [chunk["pace"] for chunk in chunks] == ["slow", "normal"]
    assert [chunk["pause_strategy"] for chunk in chunks] == ["long_pauses", None]
    assert [chunk["can_interrupt_after"] for chunk in chunks] == [True, False]


def test_compile_render_plan_is_side_effect_free_and_stable() -> None:
    plan_a = compile_render_plan(answer_text=ANSWER_TEXT, max_chars=80, pause_after_ms=100)
    plan_b = compile_render_plan(answer_text=ANSWER_TEXT, max_chars=80, pause_after_ms=100)
    assert plan_a["render_plan_digest"] == plan_b["render_plan_digest"]
    assert declared_chunk_hash_failures(RENDER_CHUNKS) == []
