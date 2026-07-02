"""Tests for the conversation ladder smoke runner.

These tests exercise receipt shape and fail-closed behavior only. They do not
prove live ASR, listener, or Chatterbox synthesis behavior.
"""

from __future__ import annotations

import importlib.util
import sys
from argparse import Namespace
from pathlib import Path


def load_ladder_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "smoke_conversation_ladder.py"
    spec = importlib.util.spec_from_file_location("smoke_conversation_ladder", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_apply_path_maps_maps_container_output_path(tmp_path: Path) -> None:
    mod = load_ladder_module()
    host_out = tmp_path / "out"

    mapped = mod.apply_path_maps(Path("/out/rung1.wav"), {"/out": host_out})

    assert mapped == host_out / "rung1.wav"


def test_rung1_missing_live_dependencies_writes_fail_closed_receipt(tmp_path: Path, monkeypatch) -> None:
    mod = load_ladder_module()
    monkeypatch.delenv("WHISPER_API_KEY", raising=False)
    args = Namespace(
        rung=1,
        base_url="http://127.0.0.1:9",
        memory_url="http://127.0.0.1:8601",
        fixture=tmp_path / "missing.wav",
        fixture_provenance="unit_test_missing_fixture",
        expected_transcript="Can you say hello and tell me you are listening?",
        response_text="Hello. I am listening.",
        label=None,
        run_id="unit-rung1",
        out=tmp_path / "rung1.json",
        wait_health_s=0,
        synthesis_timeout_s=1,
        asr_openai_base_url="http://127.0.0.1:9000",
        api_key_env="WHISPER_API_KEY",
        asr_model="small.en",
        asr_device="cpu",
        asr_compute_type="int8",
        max_input_wer=0.25,
        max_output_wer=0.35,
        path_map=[],
    )

    receipt = mod.run_rung1(args)

    assert receipt["schema"] == mod.RUNG1_SCHEMA
    assert receipt["mocked"] is False
    assert receipt["live"] is False
    assert receipt["ok"] is False
    assert receipt["claims"]["proves"] == []
    assert "input_audio_exists" in receipt["failed_gates"]
    assert "asr_backend_available" in receipt["failed_gates"]
    assert "chatterbox_health_ok" in receipt["failed_gates"]
    assert receipt["services"]["asr"]["kind"] == "openai_compatible"
    assert "api_key" not in receipt["services"]["asr"]


def test_rung2_missing_live_dependencies_writes_fail_closed_receipt(tmp_path: Path, monkeypatch) -> None:
    mod = load_ladder_module()
    monkeypatch.delenv("WHISPER_API_KEY", raising=False)
    args = Namespace(
        rung=2,
        base_url="http://127.0.0.1:9",
        memory_url="http://127.0.0.1:8601",
        fixture=None,
        turn1_fixture=tmp_path / "missing-turn1.wav",
        turn2_fixture=tmp_path / "missing-turn2.wav",
        fixture_provenance="unit_test_missing_fixture",
        expected_transcript=None,
        expected_turn1_transcript="My favorite color is blue.",
        expected_turn2_transcript="What color did I say I like?",
        response_text="Hello. I am listening.",
        label=None,
        run_id="unit-rung2",
        session_id=None,
        out=tmp_path / "rung2.json",
        wait_health_s=0,
        synthesis_timeout_s=1,
        asr_openai_base_url="http://127.0.0.1:9000",
        api_key_env="WHISPER_API_KEY",
        asr_model="small.en",
        asr_device="cpu",
        asr_compute_type="int8",
        max_input_wer=0.25,
        max_output_wer=0.35,
        path_map=[],
    )

    receipt = mod.run_rung2(args)

    assert receipt["schema"] == mod.RUNG2_SCHEMA
    assert receipt["mocked"] is False
    assert receipt["live"] is False
    assert receipt["ok"] is False
    assert receipt["claims"]["proves"] == []
    assert "asr_backend_available" in receipt["failed_gates"]
    assert "chatterbox_health_ok" in receipt["failed_gates"]
    assert "turn_1_input_audio_exists" in receipt["failed_gates"]
    assert "turn_2_input_audio_exists" in receipt["failed_gates"]
    assert receipt["omitted_turn1_gate"]["proves_fail_closed_without_turn1_state"] is True


def test_rung3_missing_live_dependencies_writes_fail_closed_receipt(tmp_path: Path, monkeypatch) -> None:
    mod = load_ladder_module()
    monkeypatch.delenv("WHISPER_API_KEY", raising=False)
    args = Namespace(
        rung=3,
        base_url="http://127.0.0.1:9",
        memory_url="http://127.0.0.1:9",
        fixture=tmp_path / "missing.wav",
        turn1_fixture=None,
        turn2_fixture=None,
        fixture_provenance="unit_test_missing_fixture",
        expected_transcript="Why does Embry react to Hawaii and rain with grief?",
        expected_turn1_transcript=None,
        expected_turn2_transcript=None,
        response_text="Hello. I am listening.",
        memory_question="What memory explains why Embry Lawson reacts to Hawaii, surfing, Kai, and afternoon rain with grief?",
        memory_tag=["persona:embry"],
        memory_k=5,
        memory_timeout_s=1,
        min_memory_confidence=0.3,
        required_persona_id="embry",
        label=None,
        run_id="unit-rung3",
        session_id=None,
        out=tmp_path / "rung3.json",
        wait_health_s=0,
        synthesis_timeout_s=1,
        asr_openai_base_url="http://127.0.0.1:9000",
        api_key_env="WHISPER_API_KEY",
        asr_model="small.en",
        asr_device="cpu",
        asr_compute_type="int8",
        max_input_wer=0.25,
        max_output_wer=0.35,
        path_map=[],
    )

    receipt = mod.run_rung3(args)

    assert receipt["schema"] == mod.RUNG3_SCHEMA
    assert receipt["mocked"] is False
    assert receipt["live"] is False
    assert receipt["ok"] is False
    assert receipt["claims"]["proves"] == []
    assert "input_audio_exists" in receipt["failed_gates"]
    assert "asr_backend_available" in receipt["failed_gates"]
    assert "chatterbox_health_ok" in receipt["failed_gates"]
    assert "memory_recall_ok" in receipt["failed_gates"]


def test_rung4_missing_live_dependencies_writes_fail_closed_receipt(tmp_path: Path, monkeypatch) -> None:
    mod = load_ladder_module()
    monkeypatch.delenv("WHISPER_API_KEY", raising=False)
    args = Namespace(
        rung=4,
        base_url="http://127.0.0.1:9",
        memory_url="http://127.0.0.1:8601",
        fixture=tmp_path / "missing-interrupt.wav",
        turn1_fixture=None,
        turn2_fixture=None,
        fixture_provenance="unit_test_missing_fixture",
        expected_transcript="Wait stop.",
        expected_turn1_transcript=None,
        expected_turn2_transcript=None,
        response_text="Hello. I am listening.",
        memory_question="unused",
        memory_tag=["persona:embry"],
        memory_k=5,
        memory_timeout_s=1,
        min_memory_confidence=0.3,
        required_persona_id="embry",
        question="Embry, which control family should I use when the answer says SI?",
        first_answer=None,
        new_answer=None,
        variant_offset=4,
        label=None,
        run_id="unit-rung4",
        session_id=None,
        out=tmp_path / "rung4.json",
        wait_health_s=0,
        synthesis_timeout_s=1,
        asr_openai_base_url="http://127.0.0.1:9000",
        api_key_env="WHISPER_API_KEY",
        asr_model="small.en",
        asr_device="cpu",
        asr_compute_type="int8",
        max_input_wer=0.25,
        max_output_wer=0.35,
        path_map=[],
    )

    receipt = mod.run_rung4(args)

    assert receipt["schema"] == mod.RUNG4_SCHEMA
    assert receipt["mocked"] is False
    assert receipt["live"] is False
    assert receipt["ok"] is False
    assert receipt["claims"]["proves"] == []
    assert "interrupt_audio_exists" in receipt["failed_gates"]
    assert "asr_backend_available" in receipt["failed_gates"]
    assert "chatterbox_health_ok" in receipt["failed_gates"]
