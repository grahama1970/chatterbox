"""Tests for the conversation ladder smoke runner.

These tests exercise receipt shape and fail-closed behavior only. They do not
prove live ASR, listener, or Chatterbox synthesis behavior.
"""

from __future__ import annotations

import importlib.util
import math
import sys
import wave
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


def write_silent_wav(path: Path, *, sample_rate: int = 16000, duration_ms: int = 120) -> None:
    frame_count = int(sample_rate * duration_ms / 1000)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(b"\x00\x00" * frame_count)


def write_tone_wav(path: Path, *, sample_rate: int = 16000, duration_ms: int = 400, frequency: float = 220.0) -> None:
    frame_count = int(sample_rate * duration_ms / 1000)
    frames = bytearray()
    for index in range(frame_count):
        sample = int(6000 * math.sin(2 * math.pi * frequency * index / sample_rate))
        frames.extend(sample.to_bytes(2, byteorder="little", signed=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(bytes(frames))


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


def test_rung5_missing_live_dependencies_writes_fail_closed_receipt(tmp_path: Path, monkeypatch) -> None:
    mod = load_ladder_module()
    monkeypatch.delenv("WHISPER_API_KEY", raising=False)
    monkeypatch.setattr(
        mod,
        "run_brave_search",
        lambda query, count, timeout_s: {
            "ok": False,
            "mocked": False,
            "live": False,
            "elapsed_ms": 1.0,
            "result": None,
            "failed_gates": ["unit_test_brave_unavailable"],
        },
    )
    args = Namespace(
        rung=5,
        base_url="http://127.0.0.1:9",
        memory_url="http://127.0.0.1:8601",
        fixture=tmp_path / "missing-tool.wav",
        turn1_fixture=None,
        turn2_fixture=None,
        fixture_provenance="unit_test_missing_fixture",
        expected_transcript="Search for voice agent turn detection.",
        expected_turn1_transcript=None,
        expected_turn2_transcript=None,
        response_text="Hello. I am listening.",
        memory_question="unused",
        memory_tag=["persona:embry"],
        memory_k=5,
        memory_timeout_s=1,
        min_memory_confidence=0.3,
        required_persona_id="embry",
        question="unused",
        first_answer=None,
        new_answer=None,
        variant_offset=4,
        tool_query="voice agent turn detection interruption handling",
        tool_count=3,
        tool_timeout_s=1,
        label=None,
        run_id="unit-rung5",
        session_id=None,
        out=tmp_path / "rung5.json",
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

    receipt = mod.run_rung5(args)

    assert receipt["schema"] == mod.RUNG5_SCHEMA
    assert receipt["mocked"] is False
    assert receipt["live"] is False
    assert receipt["ok"] is False
    assert receipt["claims"]["proves"] == []
    assert "input_audio_exists" in receipt["failed_gates"]
    assert "asr_backend_available" in receipt["failed_gates"]
    assert "chatterbox_health_ok" in receipt["failed_gates"]
    assert "brave_search_ok" in receipt["failed_gates"]


def test_rung6_missing_live_dependencies_writes_fail_closed_receipt(tmp_path: Path, monkeypatch) -> None:
    mod = load_ladder_module()
    monkeypatch.delenv("WHISPER_API_KEY", raising=False)
    args = Namespace(
        rung=6,
        base_url="http://127.0.0.1:9",
        memory_url="http://127.0.0.1:9",
        fixture=None,
        turn1_fixture=tmp_path / "missing-turn1.wav",
        turn2_fixture=tmp_path / "missing-turn2.wav",
        turn3_fixture=tmp_path / "missing-turn3.wav",
        fixture_provenance="unit_test_missing_fixture",
        expected_transcript=None,
        expected_turn1_transcript="Hello there.",
        expected_turn2_transcript="Rain reminds me of Kai.",
        expected_turn3_transcript="Can we keep this gentle?",
        response_text="Hello. I am listening.",
        memory_question="What memory explains why Embry Lawson reacts to Hawaii, surfing, Kai, and afternoon rain with grief?",
        memory_tag=["persona:embry"],
        memory_k=5,
        memory_timeout_s=1,
        min_memory_confidence=0.3,
        required_persona_id="embry",
        question="unused",
        first_answer=None,
        new_answer=None,
        variant_offset=4,
        tool_query="unused",
        tool_count=3,
        tool_timeout_s=1,
        label=None,
        run_id="unit-rung6",
        session_id=None,
        out=tmp_path / "rung6.json",
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

    receipt = mod.run_rung6(args)

    assert receipt["schema"] == mod.RUNG6_SCHEMA
    assert receipt["mocked"] is False
    assert receipt["live"] is False
    assert receipt["ok"] is False
    assert receipt["claims"]["proves"] == []
    assert "asr_backend_available" in receipt["failed_gates"]
    assert "chatterbox_health_ok" in receipt["failed_gates"]
    assert "turn_1_input_audio_exists" in receipt["failed_gates"]
    assert "turn_2_input_audio_exists" in receipt["failed_gates"]
    assert "turn_3_input_audio_exists" in receipt["failed_gates"]


def test_rung7_missing_live_dependencies_writes_fail_closed_receipt(tmp_path: Path, monkeypatch) -> None:
    mod = load_ladder_module()
    monkeypatch.delenv("WHISPER_API_KEY", raising=False)
    args = Namespace(
        rung=7,
        base_url="http://127.0.0.1:9",
        memory_url="http://127.0.0.1:9",
        fixture=tmp_path / "missing-listener.wav",
        turn1_fixture=None,
        turn2_fixture=None,
        turn3_fixture=None,
        fixture_provenance="unit_test_missing_fixture",
        expected_transcript="Stop that old answer.",
        expected_turn1_transcript=None,
        expected_turn2_transcript=None,
        expected_turn3_transcript=None,
        response_text="I hear you. Let me redirect.",
        memory_question="unused",
        memory_tag=["persona:embry"],
        memory_k=5,
        memory_timeout_s=1,
        min_memory_confidence=0.3,
        required_persona_id="embry",
        label=None,
        run_id="unit-rung7",
        session_id="unit-session",
        turn_id="unit-turn-7",
        old_turn_id="old-turn-6",
        listener_frame_ms=20,
        primary_speaker_enrollment=None,
        primary_speaker_threshold=0.82,
        expected_primary_speaker=True,
        question="unused",
        first_answer=None,
        new_answer=None,
        variant_offset=4,
        tool_query="unused",
        tool_count=3,
        tool_timeout_s=1,
        out=tmp_path / "rung7.json",
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

    receipt = mod.run_rung7(args)

    assert receipt["schema"] == mod.RUNG7_SCHEMA
    assert receipt["mocked"] is False
    assert receipt["live"] is False
    assert receipt["ok"] is False
    assert receipt["claims"]["proves"] == []
    assert "input_audio_exists" in receipt["failed_gates"]
    assert "asr_backend_available" in receipt["failed_gates"]
    assert "listener_audio_frame_events_present" in receipt["failed_gates"]
    assert "heard_text_ledger_present" in receipt["failed_gates"]
    assert receipt["tau_voice_render_request"]["schema"] == "tau.voice_render_request.v1"
    assert receipt["tau_voice_render_request"]["memory_route_decision"]["called"] is False


def test_rung7_primary_speaker_gate_suppresses_non_primary_before_asr(tmp_path: Path, monkeypatch) -> None:
    mod = load_ladder_module()
    monkeypatch.delenv("WHISPER_API_KEY", raising=False)
    candidate = tmp_path / "candidate.wav"
    enrollment = tmp_path / "enrollment.wav"
    write_silent_wav(candidate)
    write_silent_wav(enrollment)

    def fake_verify_primary_speaker(**_kwargs):
        return {
            "schema": "chatterbox.listener.primary_speaker_verification.v1",
            "engine": "unit.fake",
            "ok": True,
            "threshold": 0.82,
            "similarity": 0.42,
            "primary_speaker_match": False,
        }

    monkeypatch.setattr(mod, "verify_primary_speaker", fake_verify_primary_speaker)
    args = Namespace(
        rung=7,
        base_url="http://127.0.0.1:9",
        memory_url="http://127.0.0.1:9",
        fixture=candidate,
        turn1_fixture=None,
        turn2_fixture=None,
        turn3_fixture=None,
        fixture_provenance="unit_test_non_primary_fixture",
        expected_transcript=None,
        expected_turn1_transcript=None,
        expected_turn2_transcript=None,
        expected_turn3_transcript=None,
        response_text="This should not render.",
        memory_question="unused",
        memory_tag=["persona:embry"],
        memory_k=5,
        memory_timeout_s=1,
        min_memory_confidence=0.3,
        required_persona_id="embry",
        label=None,
        run_id="unit-rung7-suppress",
        session_id="unit-session",
        turn_id="unit-turn-7",
        old_turn_id=None,
        listener_frame_ms=20,
        primary_speaker_enrollment=enrollment,
        primary_speaker_threshold=0.82,
        expected_primary_speaker=False,
        question="unused",
        first_answer=None,
        new_answer=None,
        variant_offset=4,
        tool_query="unused",
        tool_count=3,
        tool_timeout_s=1,
        out=tmp_path / "rung7.json",
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

    receipt = mod.run_rung7(args)

    assert receipt["ok"] is True
    assert receipt["mocked"] is False
    assert receipt["live"] is False
    assert receipt["services"]["asr"]["kind"] == "not_called"
    assert receipt["asr_transcript"] is None
    assert receipt["heard_text_ledger"] == []
    assert receipt["tau_voice_render_request"] is None
    assert any(event["type"] == "listener.speech_suppressed" for event in receipt["listener_events"])
    assert any(event["type"] == "turn.suppressed" for event in receipt["coordinator_events"])
    assert "primary_speaker_gate_suppresses_non_primary_audio_before_asr_or_rendering" in receipt["claims"]["proves"]


def test_rung7_stress_fixture_records_mix_components_before_suppression(tmp_path: Path, monkeypatch) -> None:
    mod = load_ladder_module()
    monkeypatch.delenv("WHISPER_API_KEY", raising=False)
    primary = tmp_path / "horus-primary.wav"
    noise = tmp_path / "factory-floor-noise.wav"
    enrollment = tmp_path / "horus-enrollment.wav"
    stress_out = tmp_path / "stress" / "horus-with-factory-noise.wav"
    write_tone_wav(primary, frequency=180.0)
    write_tone_wav(noise, frequency=80.0)
    write_tone_wav(enrollment, frequency=180.0)

    def fake_verify_primary_speaker(**_kwargs):
        return {
            "schema": "chatterbox.listener.primary_speaker_verification.v1",
            "engine": "unit.fake",
            "ok": True,
            "threshold": 0.82,
            "similarity": 0.41,
            "primary_speaker_match": False,
        }

    monkeypatch.setattr(mod, "verify_primary_speaker", fake_verify_primary_speaker)
    args = Namespace(
        rung=7,
        base_url="http://127.0.0.1:9",
        memory_url="http://127.0.0.1:9",
        fixture=None,
        turn1_fixture=None,
        turn2_fixture=None,
        turn3_fixture=None,
        fixture_provenance="unit_test_stress_fixture",
        expected_transcript=None,
        expected_turn1_transcript=None,
        expected_turn2_transcript=None,
        expected_turn3_transcript=None,
        response_text="This should not render.",
        memory_question="unused",
        memory_tag=["persona:embry"],
        memory_k=5,
        memory_timeout_s=1,
        min_memory_confidence=0.3,
        required_persona_id="embry",
        label=None,
        run_id="unit-rung7-stress",
        session_id="unit-session",
        turn_id="unit-turn-7",
        old_turn_id=None,
        listener_frame_ms=20,
        primary_speaker_enrollment=enrollment,
        primary_speaker_engine="resemblyzer",
        primary_speaker_threshold=0.82,
        expected_primary_speaker=False,
        enable_speaker_identity_memory=False,
        enable_speaker_memory_recall=False,
        enable_missing_fact_writeback=False,
        speaker_memory_only=False,
        speaker_id="horus_lupercal",
        speaker_display_name="Horus Lupercal",
        active_persona_id="embry",
        speaker_tag=["persona:horus_lupercal"],
        speaker_confidence=0.0,
        speaker_evidence_source="unit",
        speaker_resolve_threshold=0.82,
        speaker_ambiguity_margin=0.05,
        speaker_prompt_variant=0,
        speaker_intent_scope="persona_memory",
        speaker_memory_collection="voice_conversation_memory",
        speaker_memory_recall_collection=None,
        speaker_memory_recall_tag=[],
        speaker_writeback_answer=None,
        stress_primary_audio=primary,
        stress_noise_audio=noise,
        stress_competing_audio=None,
        stress_output_fixture=stress_out,
        stress_kind="factory_floor_primary_speaker",
        stress_primary_gain_db=0.0,
        stress_noise_gain_db=-18.0,
        stress_competing_gain_db=-24.0,
        stress_timeout_s=10,
        question="unused",
        first_answer=None,
        new_answer=None,
        variant_offset=4,
        tool_query="unused",
        tool_count=3,
        tool_timeout_s=1,
        out=tmp_path / "rung7.json",
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

    receipt = mod.run_rung7(args)
    mod.write_rung7_sidecar_artifacts(receipt, args.out)

    assert receipt["ok"] is True
    assert receipt["mocked"] is False
    assert receipt["live"] is False
    assert receipt["stress_fixture"]["ok"] is True
    assert receipt["stress_fixture"]["components"]["primary"]["role"] == "primary_speaker"
    assert receipt["stress_fixture"]["components"]["noise"]["role"] == "factory_floor_background"
    assert Path(receipt["inputs"]["fixture"]).resolve() == stress_out.resolve()
    assert Path(receipt["artifacts"]["stress_fixture_path"]).read_text(encoding="utf-8").strip().startswith("{")
    assert "stress_fixture_mixes_primary_speaker_with_background_or_competing_audio" in receipt["claims"]["proves"]


def test_rung7_non_primary_calls_memory_identity_and_intent_clarify(tmp_path: Path, monkeypatch) -> None:
    mod = load_ladder_module()
    candidate = tmp_path / "candidate.wav"
    enrollment = tmp_path / "enrollment.wav"
    write_silent_wav(candidate)
    write_silent_wav(enrollment)
    calls = []

    def fake_verify_primary_speaker(**_kwargs):
        return {
            "schema": "chatterbox.listener.primary_speaker_verification.v1",
            "engine": "unit.fake",
            "ok": True,
            "threshold": 0.82,
            "similarity": 0.41,
            "primary_speaker_match": False,
        }

    def fake_post_memory_json(_memory_url, endpoint, payload, timeout_s):
        calls.append({"endpoint": endpoint, "payload": payload, "timeout_s": timeout_s})
        if endpoint == "/speaker/resolve":
            assert payload["candidates"][0]["speaker_id"] == "horus_lupercal"
            assert payload["candidates"][0]["display_name"] == "Horus Lupercal"
            assert payload["candidates"][0]["confidence"] == 0.41
            assert "persona:horus_lupercal" in payload["candidates"][0]["tags"]
            return {
                "schema": "memory.speaker_resolution.v1",
                "status": "unknown",
                "known": False,
                "speaker_id": None,
                "confidence": 0.41,
                "identity_prompt": {
                    "schema": "memory.speaker.identity_prompt.v1",
                    "prompt_id": "unknown_speaker_identity_01",
                    "text": "Who am I speaking with?",
                },
                "memory_tags": ["persona:embry"],
            }
        if endpoint == "/intent":
            assert payload["speaker_resolution"]["status"] == "unknown"
            return {
                "action": "CLARIFY",
                "reason": "unknown_speaker_identity",
                "clarify_kind": "speaker_identity",
                "suggestions": ["Who am I speaking with?"],
            }
        raise AssertionError(endpoint)

    monkeypatch.setattr(mod, "verify_primary_speaker", fake_verify_primary_speaker)
    monkeypatch.setattr(mod, "post_memory_json", fake_post_memory_json)
    args = Namespace(
        rung=7,
        base_url="http://127.0.0.1:9",
        memory_url="http://127.0.0.1:8601",
        fixture=candidate,
        turn1_fixture=None,
        turn2_fixture=None,
        turn3_fixture=None,
        fixture_provenance="unit_test_non_primary_fixture",
        expected_transcript=None,
        expected_turn1_transcript=None,
        expected_turn2_transcript=None,
        expected_turn3_transcript=None,
        response_text="This should not render.",
        memory_question="unused",
        memory_tag=["persona:embry"],
        memory_k=5,
        memory_timeout_s=1,
        min_memory_confidence=0.3,
        required_persona_id="embry",
        label=None,
        run_id="unit-rung7-speaker-memory",
        session_id="unit-session",
        turn_id="unit-turn-7",
        old_turn_id=None,
        listener_frame_ms=20,
        primary_speaker_enrollment=enrollment,
        primary_speaker_engine="resemblyzer",
        primary_speaker_threshold=0.82,
        expected_primary_speaker=False,
        enable_speaker_identity_memory=True,
        speaker_id="horus_lupercal",
        speaker_display_name="Horus Lupercal",
        active_persona_id="embry",
        speaker_tag=["persona:horus_lupercal"],
        speaker_confidence=0.0,
        speaker_evidence_source="unit",
        speaker_resolve_threshold=0.82,
        speaker_ambiguity_margin=0.05,
        speaker_prompt_variant=0,
        speaker_intent_scope="persona_memory",
        question="Where did I grow up?",
        first_answer=None,
        new_answer=None,
        variant_offset=4,
        tool_query="unused",
        tool_count=3,
        tool_timeout_s=1,
        out=tmp_path / "rung7.json",
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

    receipt = mod.run_rung7(args)

    assert receipt["ok"] is True
    assert receipt["services"]["asr"]["kind"] == "not_called"
    assert receipt["speaker_resolution"]["status"] == "unknown"
    assert receipt["memory_intent"]["action"] == "CLARIFY"
    assert receipt["memory_intent"]["clarify_kind"] == "speaker_identity"
    assert receipt["tau_voice_render_request"] is None
    assert [call["endpoint"] for call in calls] == ["/speaker/resolve", "/intent"]
    assert "unknown_or_non_primary_speaker_routes_to_identity_clarification_without_personal_recall" in receipt["claims"]["proves"]


def test_rung7_known_speaker_uses_speaker_scoped_memory_recall(tmp_path: Path, monkeypatch) -> None:
    mod = load_ladder_module()
    candidate = tmp_path / "candidate.wav"
    write_silent_wav(candidate)
    calls = []

    monkeypatch.setattr(mod, "build_asr_backend", lambda _args: {"kind": "unit_asr", "live": True})
    monkeypatch.setattr(mod, "transcribe_audio", lambda _backend, _audio_path: "Where did I grow up?")

    def fake_post_memory_json(_memory_url, endpoint, payload, timeout_s):
        calls.append({"endpoint": endpoint, "payload": payload, "timeout_s": timeout_s})
        if endpoint == "/speaker/resolve":
            assert payload["candidates"][0]["speaker_id"] == "horus_lupercal"
            assert payload["candidates"][0]["confidence"] == 0.93
            return {
                "schema": "memory.speaker_resolution.v1",
                "status": "known",
                "known": True,
                "speaker_id": "horus_lupercal",
                "display_name": "Horus Lupercal",
                "confidence": 0.93,
                "memory_tags": [
                    "persona:embry",
                    "persona:horus_lupercal",
                    "speaker:horus_lupercal",
                    "user:horus_lupercal",
                ],
                "recall_profile": "speaker_conversation_memory",
            }
        if endpoint == "/intent":
            assert payload["speaker_resolution"]["status"] == "known"
            return {"action": "QUERY", "reason": "known_speaker", "recall_profile": "speaker_conversation_memory"}
        if endpoint == "/recall":
            assert "speaker:horus_lupercal" in payload["tags"]
            assert "user:horus_lupercal" in payload["tags"]
            assert "persona:embry" in payload["tags"]
            assert payload["recall_profile"] == "speaker_conversation_memory"
            return {
                "found": True,
                "confidence": 0.99,
                "should_scan": False,
                "items": [{"_key": "horus-origin", "text": "Horus grew up on Cthonia."}],
            }
        raise AssertionError(endpoint)

    monkeypatch.setattr(mod, "post_memory_json", fake_post_memory_json)
    args = Namespace(
        rung=7,
        base_url="http://127.0.0.1:9",
        memory_url="http://127.0.0.1:8601",
        fixture=candidate,
        turn1_fixture=None,
        turn2_fixture=None,
        turn3_fixture=None,
        fixture_provenance="unit_test_known_horus_fixture",
        expected_transcript=None,
        expected_turn1_transcript=None,
        expected_turn2_transcript=None,
        expected_turn3_transcript=None,
        response_text="You grew up on Cthonia.",
        memory_question="unused",
        memory_tag=["persona:embry"],
        memory_k=5,
        memory_timeout_s=1,
        min_memory_confidence=0.3,
        required_persona_id="embry",
        label=None,
        run_id="unit-rung7-known-speaker-recall",
        session_id="unit-session",
        turn_id="unit-turn-7",
        old_turn_id=None,
        listener_frame_ms=20,
        primary_speaker_enrollment=None,
        primary_speaker_engine="resemblyzer",
        primary_speaker_threshold=0.82,
        expected_primary_speaker=True,
        enable_speaker_identity_memory=True,
        enable_speaker_memory_recall=True,
        enable_missing_fact_writeback=False,
        speaker_id="horus_lupercal",
        speaker_display_name="Horus Lupercal",
        active_persona_id="embry",
        speaker_tag=["persona:horus_lupercal"],
        speaker_confidence=0.93,
        speaker_evidence_source="unit",
        speaker_resolve_threshold=0.82,
        speaker_ambiguity_margin=0.05,
        speaker_prompt_variant=0,
        speaker_intent_scope="persona_memory",
        speaker_memory_collection="voice_conversation_memory",
        speaker_writeback_answer=None,
        question="Where did I grow up?",
        first_answer=None,
        new_answer=None,
        variant_offset=4,
        tool_query="unused",
        tool_count=3,
        tool_timeout_s=1,
        out=tmp_path / "rung7.json",
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

    receipt = mod.run_rung7(args)

    assert receipt["ok"] is True
    assert receipt["speaker_resolution"]["speaker_id"] == "horus_lupercal"
    assert receipt["speaker_memory_recall"]["found"] is True
    assert receipt["missing_fact_clarification"] is None
    assert receipt["memory_writeback"] is None
    assert [call["endpoint"] for call in calls] == ["/speaker/resolve", "/intent", "/recall"]
    assert "known_speaker_identity_routes_recall_through_speaker_scoped_memory_tags" in receipt["claims"]["proves"]


def test_rung7_known_speaker_recall_miss_can_write_back_missing_fact(tmp_path: Path, monkeypatch) -> None:
    mod = load_ladder_module()
    candidate = tmp_path / "candidate.wav"
    write_silent_wav(candidate)
    calls = []

    monkeypatch.setattr(mod, "build_asr_backend", lambda _args: {"kind": "unit_asr", "live": True})
    monkeypatch.setattr(mod, "transcribe_audio", lambda _backend, _audio_path: "Where did I grow up?")

    def fake_post_memory_json(_memory_url, endpoint, payload, timeout_s):
        calls.append({"endpoint": endpoint, "payload": payload, "timeout_s": timeout_s})
        if endpoint == "/speaker/resolve":
            return {
                "schema": "memory.speaker_resolution.v1",
                "status": "known",
                "known": True,
                "speaker_id": "horus_lupercal",
                "display_name": "Horus Lupercal",
                "confidence": 0.94,
                "memory_tags": [
                    "persona:embry",
                    "persona:horus_lupercal",
                    "speaker:horus_lupercal",
                    "user:horus_lupercal",
                ],
                "recall_profile": "speaker_conversation_memory",
            }
        if endpoint == "/intent":
            return {"action": "QUERY", "reason": "known_speaker", "recall_profile": "speaker_conversation_memory"}
        if endpoint == "/recall":
            return {"found": False, "confidence": 0.0, "should_scan": False, "items": []}
        if endpoint == "/upsert":
            assert payload["collection"] == "voice_conversation_memory"
            doc = payload["documents"][0]
            assert doc["speaker_id"] == "horus_lupercal"
            assert doc["persona_id"] == "embry"
            assert doc["scope"] == "persona_memory"
            assert doc["answer"] == "I grew up on Cthonia."
            assert "speaker:horus_lupercal" in doc["tags"]
            assert "speaker_memory_writeback" in doc["tags"]
            return {"ok": True, "collection": "voice_conversation_memory", "upserted": 1}
        if endpoint == "/recall/by-keys":
            assert payload["collection"] == "voice_conversation_memory"
            assert payload["key_field"] == "_key"
            return {
                "results": [
                    {
                        "_key": payload["keys"][0],
                        "speaker_id": "horus_lupercal",
                        "persona_id": "embry",
                        "answer": "I grew up on Cthonia.",
                    }
                ],
                "count": 1,
            }
        raise AssertionError(endpoint)

    monkeypatch.setattr(mod, "post_memory_json", fake_post_memory_json)
    args = Namespace(
        rung=7,
        base_url="http://127.0.0.1:9",
        memory_url="http://127.0.0.1:8601",
        fixture=candidate,
        turn1_fixture=None,
        turn2_fixture=None,
        turn3_fixture=None,
        fixture_provenance="unit_test_known_horus_fixture",
        expected_transcript=None,
        expected_turn1_transcript=None,
        expected_turn2_transcript=None,
        expected_turn3_transcript=None,
        response_text="I will remember that.",
        memory_question="unused",
        memory_tag=["persona:embry"],
        memory_k=5,
        memory_timeout_s=1,
        min_memory_confidence=0.3,
        required_persona_id="embry",
        label=None,
        run_id="unit-rung7-known-speaker-writeback",
        session_id="unit-session",
        turn_id="unit-turn-7",
        old_turn_id=None,
        listener_frame_ms=20,
        primary_speaker_enrollment=None,
        primary_speaker_engine="resemblyzer",
        primary_speaker_threshold=0.82,
        expected_primary_speaker=True,
        enable_speaker_identity_memory=True,
        enable_speaker_memory_recall=True,
        enable_missing_fact_writeback=True,
        speaker_id="horus_lupercal",
        speaker_display_name="Horus Lupercal",
        active_persona_id="embry",
        speaker_tag=["persona:horus_lupercal"],
        speaker_confidence=0.94,
        speaker_evidence_source="unit",
        speaker_resolve_threshold=0.82,
        speaker_ambiguity_margin=0.05,
        speaker_prompt_variant=0,
        speaker_intent_scope="persona_memory",
        speaker_memory_collection="voice_conversation_memory",
        speaker_writeback_answer="I grew up on Cthonia.",
        question="Where did I grow up?",
        first_answer=None,
        new_answer=None,
        variant_offset=4,
        tool_query="unused",
        tool_count=3,
        tool_timeout_s=1,
        out=tmp_path / "rung7.json",
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

    receipt = mod.run_rung7(args)

    assert receipt["ok"] is True
    assert receipt["speaker_memory_recall"]["found"] is False
    assert receipt["missing_fact_clarification"]["reason"] == "speaker_scoped_memory_recall_miss"
    assert receipt["memory_writeback"]["ok"] is True
    assert [call["endpoint"] for call in calls] == ["/speaker/resolve", "/intent", "/recall", "/upsert", "/recall/by-keys"]
    assert receipt["memory_writeback_readback"]["count"] == 1
    assert "speaker_scoped_recall_miss_creates_missing_fact_clarification" in receipt["claims"]["proves"]
    assert "missing_fact_answer_is_written_back_to_memory" in receipt["claims"]["proves"]
