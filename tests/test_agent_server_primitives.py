"""Server primitive tests that do not require loading the Chatterbox model."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
import time
import types
import wave

from chatterbox.agent.chunking import (
    build_render_plan,
    build_render_plan_from_chunks,
    split_spoken_chunks,
)
import chatterbox.agent.server as server
from chatterbox.agent.server import (
    ASR_API_KEY_ENV,
    CACHE_SCHEMA_VERSION,
    DEFAULT_ASR_OPENAI_BASE_URL,
    SynthesisBatchRequest,
    SynthesisRequest,
    TauVoiceRenderRequest,
    TurnControlRequest,
    accepted_audio_cache_key,
    accepted_audio_cache_material,
    apply_blessed_qra_memory_gate,
    append_with_crossfade,
    candidate_variants,
    duck_playback,
    find_blessed_qra_match,
    load_accepted_audio_cache,
    qra_similarity,
    resolve_reference_audio,
    safe_resolve_within,
    save_accepted_audio_cache,
    stop_playback,
    cancel_turn,
    stream_turn_should_stop,
    synthesis_batch_request_from_tau_voice_render,
    tau_voice_render_payload_to_batch,
    synthesis_request_with_overrides,
    synthesize_to_file,
    synthesize_batch,
    tau_voice_render,
)
from starlette.testclient import TestClient


def test_turbo_render_plan_uses_sentence_aware_300_char_safety() -> None:
    text = (
        "This is the first complete sentence for the Chatterbox Turbo safety path. "
        "This second sentence is intentionally long enough to force another chunk while preserving a natural sentence boundary. "
        "This final sentence confirms the plan records safety metadata for receipts."
    )

    plan = build_render_plan(text, max_chars=120, pause_after_ms=250)

    assert plan["chunk_count"] > 1
    assert plan["chunking_strategy"] == {
        "name": "sentence_aware_turbo_safety",
        "target_max_chars": 120,
        "requested_max_chars": 120,
        "turbo_safety_recommended_max_chars": 300,
        "safety_activated": True,
        "hard_cap_enforced": True,
        "splitter": "regex_sentence_then_clause_then_words",
        "does_not_split_inside_words": True,
    }
    assert all(chunk["char_len"] <= 120 for chunk in plan["chunks"])
    assert all(chunk["can_interrupt_after"] for chunk in plan["chunks"])


def test_turbo_render_plan_clamps_oversized_max_chars_to_300() -> None:
    text = " ".join(f"word{i}" for i in range(200))

    plan = build_render_plan(text, max_chars=900, pause_after_ms=250)

    assert plan["requested_max_chars"] == 900
    assert plan["max_chars"] == 300
    assert plan["chunking_strategy"]["target_max_chars"] == 300
    assert plan["chunking_strategy"]["hard_cap_enforced"] is True
    assert all(chunk["char_len"] <= 300 for chunk in plan["chunks"])


def test_split_spoken_chunks_does_not_split_words_for_long_sentence() -> None:
    text = " ".join(f"word{i}" for i in range(60))

    chunks = split_spoken_chunks(text, max_chars=80)

    assert len(chunks) > 1
    assert all(len(chunk) <= 80 for chunk in chunks)
    assert " " .join(chunks).replace("  ", " ") == text


def test_reference_audio_path_sandbox_allows_only_configured_roots(tmp_path: Path) -> None:
    root = tmp_path / "voices"
    root.mkdir()
    ref = root / "embry.wav"
    ref.write_bytes(b"RIFF----WAVE")

    resolved = safe_resolve_within(ref, roots=[root])

    assert resolved == ref.resolve()


def test_reference_audio_path_sandbox_rejects_traversal(tmp_path: Path) -> None:
    root = tmp_path / "voices"
    outside = tmp_path / "outside.wav"
    root.mkdir()
    outside.write_bytes(b"RIFF----WAVE")

    try:
        safe_resolve_within(root / ".." / "outside.wav", roots=[root])
    except Exception as exc:  # FastAPI HTTPException
        assert getattr(exc, "status_code", None) == 400
        assert getattr(exc, "detail", None) in {
            "reference_audio_outside_allowed_roots",
            "reference_audio_path_traversal",
        }
    else:  # pragma: no cover - explicit failure path
        raise AssertionError("path traversal should be rejected")


def test_turn_control_records_cancel_duck_and_stop() -> None:
    turn_id = "turn-test-123"

    cancel = cancel_turn(turn_id, TurnControlRequest(reason="barge-in", new_turn_id="turn-new"))
    duck = duck_playback(turn_id, TurnControlRequest(reason="embry-speaking"))
    stop = stop_playback(turn_id, TurnControlRequest(reason="final-answer-ready"))

    assert cancel["ok"]
    assert cancel["control"]["cancelled"]
    assert cancel["control"]["stale_chunks_should_skip"]
    assert duck["control"]["ducked"]
    assert stop["control"]["stopped"]
    assert [event["action"] for event in stop["control"]["events"]][-3:] == ["cancel", "duck", "stop"]


def test_batch_request_exposes_optional_asr_verification_contract() -> None:
    request = SynthesisBatchRequest(answer_text="I found the answer.")

    assert request.turn_id is None
    assert request.asr_verify is False
    assert not hasattr(request, "asr_openai_base_url")
    assert not hasattr(request, "asr_api_key_env")
    assert DEFAULT_ASR_OPENAI_BASE_URL
    assert ASR_API_KEY_ENV
    assert request.asr_max_wer == 0.35
    assert request.asr_max_duration_ratio == 2.5
    assert request.asr_max_candidates == 3


def test_batch_request_accepts_optional_turn_id_for_stream_controls() -> None:
    request = SynthesisBatchRequest(answer_text="I found the answer.", turn_id="turn-stream-123")

    assert request.turn_id == "turn-stream-123"


def test_synthesis_request_maps_tone_to_effective_delivery_stage() -> None:
    request = SynthesisRequest(text="Known answer.", tone="memory_confident")

    delivery = server.voice_delivery_for_request(request)
    params = server.generation_params(request)

    assert delivery["tone"] == "memory_confident"
    assert delivery["normalized_tone"] == "memory_confident"
    assert delivery["tone_was_normalized"] is False
    assert delivery["delivery_stage"] == "satisfied"
    assert delivery["delivery_stage_source"] == "tone_mapping"
    assert delivery["ignored_turbo_params"] == sorted(server.TURBO_IGNORED_PARAMS)
    assert params == server.generation_params_for_stage("satisfied")


def test_unknown_tone_receipt_exposes_requested_and_normalized_tone() -> None:
    request = SynthesisRequest(text="Known answer.", tone="gentle_firm")

    delivery = server.voice_delivery_for_request(request)

    assert delivery["requested_tone"] == "gentle_firm"
    assert delivery["normalized_tone"] == "neutral_warm"
    assert delivery["tone"] == "neutral_warm"
    assert delivery["tone_was_normalized"] is True
    assert delivery["ignored_turbo_params"] == ["cfg_weight", "exaggeration", "min_p"]


def test_chatterbox_tags_are_recorded_as_ignored_metadata() -> None:
    request = SynthesisRequest(
        text="Known answer.",
        voice_delivery={"chatterbox_tags": ["firm", "breath"]},
    )

    delivery = server.voice_delivery_for_request(request)

    assert delivery["tag_handling"]["requested_tags"] == ["firm", "breath"]
    assert delivery["tag_handling"]["applied_tags"] == []
    assert delivery["tag_handling"]["accepted_tags"] == []
    assert delivery["tag_handling"]["tags_interpreted"] is False
    assert delivery["tag_handling"]["inline_text_tag_behavior"] == "synthesized_as_literal_text"


def test_presets_expose_tag_handling_contract() -> None:
    response = server.presets()

    assert response["tag_handling"]["dedicated_tag_channel"] == "unsupported"
    assert response["tag_handling"]["accepted_tags"] == []
    assert response["tag_handling"]["applied_tags"] == []
    assert response["tag_handling"]["tags_interpreted"] is False


def test_presets_expose_stage_preset_affect_status() -> None:
    response = server.presets()
    status = response["stage_preset_affect_status"]

    assert status["schema"] == "chatterbox.stage_preset_affect_status.v1"
    assert status["status"] == "not_validated_as_affect_channel"
    assert status["evidence"]["duration_s_flat_spread"] == 1.36
    assert status["evidence"]["f0_sd_hz_flat_spread"] == 21.21
    assert status["evidence"]["f0_range_hz_flat_spread"] == 60.85
    assert "Do not treat STAGE_PRESETS" in status["consumer_guidance"]


def test_stochasticity_receipt_records_repeat_group_without_determinism_claim() -> None:
    request = SynthesisRequest(text="Known answer.", repeat_group_id="variance-arm-flat-r0")

    receipt = server.stochasticity_for_request(request)

    assert receipt["repeat_group_id"] == "variance-arm-flat-r0"
    assert receipt["deterministic_audio"] is False
    assert receipt["seed_supported"] is False
    assert receipt["seed"] is None
    assert "without_implying_identical_audio" in receipt["equivalence"]


def test_synthesis_request_explicit_delivery_stage_overrides_tone_mapping() -> None:
    request = SynthesisRequest(
        text="Careful answer.",
        tone="playful_light",
        delivery_stage="boundary",
        pace="firm_short",
        pause_strategy="boundary_stop_then_prompt",
        voice_delivery={"source": "memory.intent", "confidence": 0.75},
    )

    delivery = server.voice_delivery_for_request(request)

    assert delivery["tone"] == "playful_light"
    assert delivery["delivery_stage"] == "deflecting"
    assert delivery["delivery_stage_source"] == "request.delivery_stage"
    assert delivery["pace"] == "firm_short"
    assert delivery["pause_strategy"] == "boundary_stop_then_prompt"
    assert delivery["source"] == "memory.intent"
    assert delivery["confidence"] == 0.75


def test_synthesize_to_file_receipt_records_voice_delivery(tmp_path: Path, monkeypatch) -> None:
    import torch

    class FakeModel:
        sr = 24000
        conds = None

        def prepare_conditionals(self, ref_audio: str, **_: object) -> None:
            self.conds = ref_audio

        def generate(self, _text: str, **_: object):
            return torch.zeros((1, 2400), dtype=torch.float32)

    root = tmp_path / "voices"
    root.mkdir()
    ref = root / "embry.wav"
    ref.write_bytes(b"RIFF-ref")
    monkeypatch.setattr(server, "model", FakeModel())
    monkeypatch.setattr(server, "REFERENCE_AUDIO_ROOTS", [root])
    monkeypatch.setattr(server, "voice_conditioning_cache", {})
    monkeypatch.setitem(
        sys.modules,
        "torchaudio",
        types.SimpleNamespace(save=lambda path, *_args, **_kwargs: write_tiny_wav(Path(path))),
    )

    result = synthesize_to_file(
        SynthesisRequest(
            text="Known answer.",
            ref_audio=str(ref),
            tone="memory_confident",
            pace="measured",
            pause_strategy="short_answer_no_filler",
        ),
        tmp_path / "known-answer.wav",
    )

    assert result["ok"] is True
    assert result["tone"] == "memory_confident"
    assert result["normalized_tone"] == "memory_confident"
    assert result["delivery_stage"] == "satisfied"
    assert result["voice_delivery"]["pace"] == "measured"
    assert result["voice_delivery"]["pause_strategy"] == "short_answer_no_filler"
    assert result["pace_effect"]["schema"] == "chatterbox.pace_effect.v1"
    assert result["pace_effect"]["requested_pace"] == "measured"
    assert result["voice_delivery_effect"]["fields"]["pace"]["status"] == "applied"
    assert (
        result["voice_delivery_effect"]["fields"]["tone"]["status"]
        == "audible_with_emotion_realization_audible__request_only_on_default_fast_path"
    )
    assert result["voice_delivery_effect"]["fields"]["pause_strategy"]["status"] == "request_only"
    assert result["ignored_turbo_params"] == sorted(server.TURBO_IGNORED_PARAMS)
    assert result["generation_params"] == server.generation_params_for_stage("satisfied")


def test_tone_alone_routes_audibly_only_when_emotion_realization_audible() -> None:
    fast = server.emotion_knobs_from_delivery(
        {"requested_tone": "grief_safe", "tone": "grief_safe", "emotion_realization": "fast"}
    )
    assert fast is None

    audible = server.emotion_knobs_from_delivery(
        {"requested_tone": "grief_safe", "tone": "grief_safe", "emotion_realization": "audible"}
    )
    assert audible is not None
    assert audible["intensity"] == server.TONE_CALIBRATION["grief_safe"]["intensity"]
    assert audible["valence"] == server.TONE_CALIBRATION["grief_safe"]["valence"]

    no_tone = server.emotion_knobs_from_delivery({"requested_tone": None, "tone": "neutral_warm", "emotion_realization": "audible"})
    assert no_tone is None

    explicit_wins = server.emotion_knobs_from_delivery(
        {"requested_tone": "grief_safe", "tone": "grief_safe", "emotion_realization": "audible", "intensity": 0.9, "valence": -0.8}
    )
    assert explicit_wins is not None and explicit_wins["intensity"] == 0.9


def test_affect_effect_receipt_reports_applied_only_when_backend_honors_knobs() -> None:
    knobs = {"exaggeration": 1.065, "cfg_weight": 0.36, "temperature": 0.7, "intensity": 0.85, "valence": -0.7}

    applied = server.affect_effect_receipt({"intensity": 0.85, "valence": -0.7}, knobs, "chatterbox_base_affect")
    assert applied["schema"] == "chatterbox.affect_effect.v1"
    assert applied["applied"] is True
    assert applied["knob_source"] == "explicit_intensity_valence"
    assert applied["derived_knobs"] == knobs

    defaults = server.affect_effect_receipt({"use_base_emotion": True}, knobs, "chatterbox_base_affect")
    assert defaults["applied"] is True
    assert defaults["knob_source"] == "tone_affect_defaults"

    wrong_backend = server.affect_effect_receipt({"intensity": 0.85}, knobs, "chatterbox_turbo")
    assert wrong_backend["applied"] is False
    assert wrong_backend["reason"] == "backend_chatterbox_turbo_does_not_honor_affect_knobs"

    no_affect = server.affect_effect_receipt({}, None, "chatterbox_turbo")
    assert no_affect["applied"] is False
    assert no_affect["reason"] == "no_affect_requested_default_turbo_render"
    assert no_affect["knob_source"] is None


def test_apply_pace_stretch_receipt_never_claims_unproven_effect() -> None:
    import torch

    wav = torch.zeros((1, 24000), dtype=torch.float32)

    unchanged, receipt = server.apply_pace_stretch(wav, 24000, None)
    assert receipt["applied"] is False
    assert receipt["reason"] == "no_pace_requested"
    assert unchanged is wav

    unchanged, receipt = server.apply_pace_stretch(wav, 24000, "not_a_pace")
    assert receipt["applied"] is False
    assert receipt["reason"] == "unknown_pace_value_request_only"

    unchanged, receipt = server.apply_pace_stretch(wav, 24000, "neutral")
    assert receipt["applied"] is False
    assert receipt["reason"] == "identity_tempo_factor"

    stretched, receipt = server.apply_pace_stretch(wav, 24000, "fast")
    if receipt["applied"]:
        assert abs(receipt["output_duration_seconds"] - 1.0 / 1.18) < 0.05
        assert stretched.shape[-1] < wav.shape[-1]
    else:
        # Environments without a working torchaudio must degrade honestly.
        assert receipt["reason"].startswith("stretch_failed:")
        assert unchanged is wav or stretched is wav


def test_tau_voice_render_request_maps_to_batch_request() -> None:
    chunk_text = "Use system and communications protection."
    request = TauVoiceRenderRequest(
        conversation_id="conv-1",
        turn_id="turn-1",
        question_text="Which control family should I use when the answer says SI?",
        question_text_sha256=server.sha256_text("Which control family should I use when the answer says SI?"),
        memory_route_decision={"called": True, "source": "memory"},
        voice_delivery={
            "tone": "memory_confident",
            "delivery_stage": "satisfied",
            "pace": "measured",
            "pause_strategy": "short_answer_no_filler",
            "source": "memory_intent",
            "confidence": 0.86,
        },
        repeat_group_id="variance-arm-static-r0",
        speakable_chunks=[
            {
                "chunk_id": "turn-1-chunk-1",
                "text": chunk_text,
                "text_sha256": server.sha256_text(chunk_text),
                "pause_after_ms": 0,
                "max_chars": 300,
            }
        ],
        use_blessed_qra_cache=True,
        blessed_qra_memory_key="qra-si-answer",
        blessed_qra_memory_similarity=1.0,
        blessed_qra_memory_review_status="approved",
        blessed_qra_variant="variant_1",
    )

    batch, receipt = synthesis_batch_request_from_tau_voice_render(request)

    assert receipt["ok"] is True
    assert receipt["schema"] == "tau.voice_render_request.v1"
    assert receipt["failed_gates"] == []
    assert batch.answer_text == chunk_text
    assert batch.turn_id == "turn-1"
    assert batch.question_text == "Which control family should I use when the answer says SI?"
    assert batch.max_chars == 300
    assert batch.tone == "memory_confident"
    assert batch.delivery_stage == "satisfied"
    assert batch.pace == "measured"
    assert batch.pause_strategy == "short_answer_no_filler"
    assert batch.delivery_arc == [
        {"stage": "satisfied", "tone": "memory_confident", "role": "tau_chunk_1"}
    ]
    assert batch.voice_delivery["source"] == "memory_intent"
    assert batch.use_blessed_qra_cache is True
    assert batch.blessed_qra_memory_key == "qra-si-answer"
    assert receipt["voice_delivery"]["tone"] == "memory_confident"
    assert receipt["voice_delivery"]["normalized_tone"] == "memory_confident"
    assert receipt["voice_delivery"]["source"] == "memory_intent"
    assert receipt["mapped_batch"]["tone"] == "memory_confident"
    assert receipt["mapped_batch"]["delivery_stage"] == "satisfied"
    assert receipt["mapped_batch"]["repeat_group_id"] == "variance-arm-static-r0"
    assert batch.repeat_group_id == "variance-arm-static-r0"


def test_tau_voice_render_preserves_chunk_tone_arc() -> None:
    chunks = [
        ("Concerned opening.", "careful_concerned", "slightly_concerned"),
        ("Grounded explanation.", "memory_confident", "satisfied"),
        ("Happy close.", "playful_light", "positive"),
    ]
    request = TauVoiceRenderRequest(
        conversation_id="conv-tone-arc",
        turn_id="turn-tone-arc",
        speakable_chunks=[
            {"text": text, "text_sha256": server.sha256_text(text), "tone": tone}
            for text, tone, _stage in chunks
        ],
    )

    batch, receipt = synthesis_batch_request_from_tau_voice_render(request)

    assert receipt["ok"] is True
    assert [item["tone"] for item in batch.delivery_arc] == [item[1] for item in chunks]
    assert [item["stage"] for item in batch.delivery_arc] == [item[2] for item in chunks]


def test_tau_voice_render_preserves_caller_chunk_boundaries_for_render_plan() -> None:
    request = TauVoiceRenderRequest(
        conversation_id="conv-controls",
        turn_id="turn-controls",
        voice_delivery={
            "tone": "memory_confident",
            "pace": "measured",
            "pause_strategy": "long_boundary",
        },
        speakable_chunks=[
            {
                "chunk_id": "chunk-1",
                "text": "First short chunk.",
                "text_sha256": server.sha256_text("First short chunk."),
                "delivery_stage": "neutral",
                "pause_after_ms": 700,
            },
            {
                "chunk_id": "chunk-2",
                "text": "Second short chunk.",
                "text_sha256": server.sha256_text("Second short chunk."),
                "delivery_stage": "satisfied",
                "pause_after_ms": 0,
            },
        ],
        use_blessed_qra_cache=False,
    )

    batch, receipt = synthesis_batch_request_from_tau_voice_render(request)
    plan = build_render_plan_from_chunks(
        batch.render_chunks or [],
        max_chars=batch.max_chars,
        fallback_pause_after_ms=batch.pause_after_ms,
        completion_cue=batch.completion_cue,
    )
    controls = server.applied_controls_for_plan(plan, batch.voice_delivery)

    assert receipt["ok"] is True
    assert receipt["source_chunk_count"] == 2
    assert receipt["mapped_batch"]["render_chunk_count"] == 2
    assert [chunk["text"] for chunk in plan["chunks"]] == ["First short chunk.", "Second short chunk."]
    assert [chunk["pause_after_ms"] for chunk in plan["chunks"]] == [700, 0]
    assert [chunk["delivery_stage"] for chunk in plan["chunks"]] == ["neutral", "satisfied"]
    assert controls[0]["applied"]["pause_after_ms"] == 700
    assert controls[0]["applied"]["pace"] == "measured"
    assert controls[0]["applied"]["pause_strategy"] == "long_boundary"


def test_tau_voice_render_request_fails_closed_on_hash_mismatch() -> None:
    request = TauVoiceRenderRequest(
        conversation_id="conv-1",
        turn_id="turn-1",
        question_text="Original question",
        question_text_sha256="wrong",
        speakable_chunks=[
            {
                "text": "Use system and communications protection.",
                "text_sha256": "wrong",
            }
        ],
    )

    _batch, receipt = synthesis_batch_request_from_tau_voice_render(request)

    assert receipt["ok"] is False
    assert "question_text_sha256_matches" in receipt["failed_gates"]
    assert "chunk_1_text_sha256_matches" in receipt["failed_gates"]


def test_tau_voice_render_request_blocks_failed_answerability() -> None:
    request = TauVoiceRenderRequest(
        conversation_id="conv-1",
        turn_id="turn-blocked-answer",
        question_text="What private code word did I tell Embry yesterday?",
        question_text_sha256=server.sha256_text("What private code word did I tell Embry yesterday?"),
        answerability_decision={
            "decision": "block_before_speech",
            "failed_gates": ["memory_miss_should_not_answer_unrelated_record"],
        },
        speakable_chunks=[
            {
                "text": "Read and explain Embry OS configuration from embry.yaml",
                "text_sha256": server.sha256_text("Read and explain Embry OS configuration from embry.yaml"),
            }
        ],
    )

    _batch, receipt = synthesis_batch_request_from_tau_voice_render(request)

    assert receipt["ok"] is False
    assert "answerability_blocks_speech" in receipt["failed_gates"]
    assert "answerability_failed_gates_present" in receipt["failed_gates"]
    assert receipt["answerability_decision"]["decision"] == "block_before_speech"


def test_tau_voice_render_request_allows_answerable_answerability() -> None:
    chunk_text = "Horus Lupercal grew up on Cthonia."
    request = TauVoiceRenderRequest(
        conversation_id="conv-1",
        turn_id="turn-answerable",
        question_text="Where did Horus Lupercal grow up?",
        question_text_sha256=server.sha256_text("Where did Horus Lupercal grow up?"),
        answerability_decision={
            "decision": "answerable",
            "failed_gates": [],
        },
        speakable_chunks=[
            {
                "text": chunk_text,
                "text_sha256": server.sha256_text(chunk_text),
            }
        ],
    )

    batch, receipt = synthesis_batch_request_from_tau_voice_render(request)

    assert receipt["ok"] is True
    assert receipt["failed_gates"] == []
    assert batch.answer_text == chunk_text


def tau_v2_positive_payload() -> dict[str, object]:
    text = (
        "Workflow issue-288-voice-v2, run run-288-fixture, is BLOCKED, "
        "at node review, blocked by waiting on reviewer verdict."
    )
    text_sha = server.sha256_text(text)
    return {
        "schema": "tau.voice_render_request.v2",
        "conversation_id": "conv-288",
        "turn_id": "turn-288-01",
        "question_text": text,
        "question_text_sha256": text_sha,
        "use_blessed_qra_cache": False,
        "include_completion_cue": False,
        "crossfade_ms": 0,
        "v2": {
            "identity": {
                "request_id": "req-288-0001",
                "conversation_id": "conv-288",
                "turn_id": "turn-288-01",
                "turn_revision": 1,
                "response_id": "resp-288-0001",
                "cancel_epoch": 0,
                "supersedes_response_id": None,
            },
            "lineage": {
                "workflow": "issue-288-voice-v2",
                "run_id": "run-288-fixture",
                "node_id": "review",
                "attempt_id": "attempt-1",
                "scheduler_journal_sequence": 42,
                "state_digest": "d1e5f0c0a288",
                "goal_hash": "goalhash288",
                "event_type": "state_change",
                "state_transition": "RUNNING->BLOCKED",
            },
            "delivery_decision": {
                "policy_version": "tau.voice_delivery_policy.v1",
                "requested_delivery": {
                    "tone": None,
                    "intensity": None,
                    "valence": None,
                    "stage": None,
                },
                "effective_delivery": {
                    "tone": "careful_concerned",
                    "intensity": 0.45,
                    "valence": -0.25,
                    "stage": "recoverable_blocker",
                },
                "overridden_fields": [],
                "override_reasons": {},
                "evidence_references": [
                    "tau_run:run-288-fixture",
                    "state_digest:d1e5f0c0a288",
                    "authoritative_state:BLOCKED",
                ],
                "profile_validation_status": "declared_profile",
            },
            "segments": [
                {
                    "segment_id": "resp-288-0001-000",
                    "text": text,
                    "text_sha256": text_sha,
                    "delivery": {
                        "tone": "careful_concerned",
                        "intensity": 0.45,
                        "valence": -0.25,
                        "stage": "recoverable_blocker",
                    },
                    "interruptible": True,
                }
            ],
            "control_target": {
                "conversation_id": "conv-288",
                "turn_id": "turn-288-01",
                "turn_revision": 1,
                "response_id": "resp-288-0001",
                "expected_cancel_epoch": 0,
            },
            "extensions": {},
        },
    }


def test_tau_voice_render_v2_maps_canonical_payload_and_retains_digest() -> None:
    server.tau_response_controls.clear()

    batch, receipt = tau_voice_render_payload_to_batch(tau_v2_positive_payload())

    assert receipt["ok"] is True
    assert receipt["schema"] == "tau.voice_render_request.v2"
    assert receipt["response_id"] == "resp-288-0001"
    assert receipt["request_lineage_digest"] == "10242ccd97287926fbb0692163429ee95427e692dc63daf88f3a63b161b0e95b"
    assert receipt["consumer_lineage_digest"] == receipt["request_lineage_digest"]
    assert batch.turn_id == "turn-288-01"
    assert batch.voice_delivery["response_id"] == "resp-288-0001"
    assert batch.render_chunks and batch.render_chunks[0]["text_sha256"]


def test_tau_voice_render_route_accepts_v2_on_existing_endpoint(monkeypatch) -> None:
    server.tau_response_controls.clear()

    def fake_synthesize_batch(batch_request):
        return {
            "ok": True,
            "mocked": False,
            "live": True,
            "engine": "chatterbox_turbo",
            "batch_label": batch_request.label,
            "render_plan_digest": "digest-render-plan",
            "failed_gates": [],
        }

    monkeypatch.setattr(server, "synthesize_batch", fake_synthesize_batch)
    response = TestClient(server.app).post("/tau/voice-render", json=tau_v2_positive_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["consumer_digest_matches"] is True
    assert body["tau_voice_render_request"]["response_id"] == "resp-288-0001"
    assert body["request_lineage_digest"] == "10242ccd97287926fbb0692163429ee95427e692dc63daf88f3a63b161b0e95b"


def test_tau_voice_render_v2_rejects_unsupported_or_misspelled_schema_fields() -> None:
    client = TestClient(server.app)
    unsupported = tau_v2_positive_payload()
    unsupported["schema"] = "tau.voice_render_request.v3"
    response = client.post("/tau/voice-render", json=unsupported)
    assert response.status_code == 422
    assert response.json()["detail"]["reason"] == "unsupported_tau_voice_render_schema"

    misspelled = json.loads(json.dumps(tau_v2_positive_payload()))
    misspelled["v2"]["identity"]["respons_id"] = misspelled["v2"]["identity"].pop("response_id")
    response = client.post("/tau/voice-render", json=misspelled)
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["reason"] == "invalid_tau_voice_render_v2_block"
    assert "respons_id" in detail["detail"]
    assert "response_id" in detail["detail"]


def test_tau_voice_render_v2_control_target_fences_stale_responses() -> None:
    server.tau_response_controls.clear()
    _batch, receipt = tau_voice_render_payload_to_batch(tau_v2_positive_payload())
    assert receipt["response_registration"]["accepted"] is True

    wrong_conversation = server.cancel_turn(
        "turn-288-01",
        TurnControlRequest(
            reason="wrong conversation",
            conversation_id="conv-other",
            turn_revision=1,
            response_id="resp-288-0001",
            expected_cancel_epoch=0,
        ),
    )
    assert wrong_conversation["ok"] is False
    assert wrong_conversation["control"]["reason"] == "unknown_conversation"

    stale_epoch = server.cancel_turn(
        "turn-288-01",
        TurnControlRequest(
            reason="stale",
            conversation_id="conv-288",
            turn_revision=1,
            response_id="resp-288-0001",
            expected_cancel_epoch=7,
        ),
    )
    assert stale_epoch["ok"] is False
    assert stale_epoch["control"]["reason"] == "stale_cancel_epoch"

    current = server.cancel_turn(
        "turn-288-01",
        TurnControlRequest(
            reason="barge-in",
            conversation_id="conv-288",
            turn_revision=1,
            response_id="resp-288-0001",
            expected_cancel_epoch=0,
        ),
    )
    assert current["ok"] is True
    assert current["control"]["reason"] == "current_response"

    duplicate = server.cancel_turn(
        "turn-288-01",
        TurnControlRequest(
            reason="duplicate",
            conversation_id="conv-288",
            turn_revision=1,
            response_id="resp-288-0001",
            expected_cancel_epoch=1,
        ),
    )
    assert duplicate["ok"] is True
    assert duplicate["control"]["idempotent"] is True


def test_tau_voice_render_v2_new_response_blocks_late_old_control() -> None:
    server.tau_response_controls.clear()
    _batch, first = tau_voice_render_payload_to_batch(tau_v2_positive_payload())
    assert first["response_registration"]["accepted"] is True
    newer = json.loads(json.dumps(tau_v2_positive_payload()))
    newer["v2"]["identity"]["request_id"] = "req-288-0002"
    newer["v2"]["identity"]["response_id"] = "resp-288-0002"
    newer["v2"]["identity"]["supersedes_response_id"] = "resp-288-0001"
    newer["v2"]["control_target"]["response_id"] = "resp-288-0002"
    newer["v2"]["segments"][0]["segment_id"] = "resp-288-0002-000"
    _batch, second = tau_voice_render_payload_to_batch(newer)
    assert second["response_registration"]["accepted"] is True

    old_control = server.cancel_turn(
        "turn-288-01",
        TurnControlRequest(
            reason="late old response",
            conversation_id="conv-288",
            turn_revision=1,
            response_id="resp-288-0001",
            expected_cancel_epoch=0,
        ),
    )

    assert old_control["ok"] is False
    assert old_control["control"]["reason"] == "stale_response_id"


def test_stream_turn_should_stop_only_for_cancel_or_stop() -> None:
    server.turn_controls.clear()
    turn_id = "turn-stream-stop-test"

    assert stream_turn_should_stop(turn_id) is False

    duck_playback(turn_id, TurnControlRequest(reason="lower volume"))
    assert stream_turn_should_stop(turn_id) is False

    cancel_turn(turn_id, TurnControlRequest(reason="barge-in"))
    assert stream_turn_should_stop(turn_id) is True

    server.turn_controls.clear()
    stop_playback(turn_id, TurnControlRequest(reason="floor change"))
    assert stream_turn_should_stop(turn_id) is True


def test_candidate_variants_are_limited_and_start_with_stage_default() -> None:
    variants = candidate_variants(2)

    assert [variant["name"] for variant in variants] == ["stage_default", "cooler_penalty"]
    assert variants[0]["overrides"] == {}


def test_append_with_crossfade_overlaps_tail_and_head() -> None:
    import torch

    tensors = [torch.ones((1, 10), dtype=torch.float32)]
    next_wav = torch.zeros((1, 10), dtype=torch.float32)

    append_with_crossfade(tensors, next_wav, sample_rate=1000, crossfade_ms=4)

    combined = torch.cat(tensors, dim=1)
    assert combined.shape[1] == 16
    assert combined[0, :6].tolist() == [1.0] * 6
    assert combined[0, 10:].tolist() == [0.0] * 6
    overlap = combined[0, 6:10].tolist()
    assert overlap[0] > overlap[-1]
    assert all(0.0 <= value <= 1.0 for value in overlap)


def write_tiny_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(24000)
        handle.writeframes(b"\x00\x00" * 2400)


def write_blessed_qra_ledger(tmp_path: Path) -> Path:
    audio_paths = []
    for index in range(5):
        audio = tmp_path / f"variant-{index}.wav"
        write_tiny_wav(audio)
        audio_paths.append(audio)
    variants = []
    for index, audio in enumerate(audio_paths):
        variants.append(
            {
                "id": f"variant_{index}",
                "name": f"Variant {index}",
                "default": index == 0,
                "blessed": True,
                "emotion_arc": {"tone": "gentle" if index == 1 else "neutral"},
                "pause_profile": {"pause_after_ms": index * 25},
                "chunks": [
                    {
                        "index": 1,
                        "text": "Use system and communications protection.",
                        "delivery_stage": "neutral",
                        "pause_after_ms": index * 25,
                        "audio": str(audio),
                        "audio_sha256": server.sha256_file(audio),
                    }
                ],
            }
        )
    ledger = {
        "schema_version": "blessed_qra_response_cache.v1",
        "enabled": True,
        "entries": [
            {
                "id": "qra-si-answer",
                "memory_keys": ["qra-si-answer"],
                "blessed": True,
                "question_text": "Which control family should I use when the answer says SI?",
                "question_variants": ["Which control family should I use when the answer says SI"],
                "answer_text": "Use system and communications protection.",
                "audio_variants": variants,
            }
        ],
    }
    path = tmp_path / "blessed-qra-ledger.json"
    path.write_text(json.dumps(ledger), encoding="utf-8")
    return path


def test_qra_similarity_normalizes_near_exact_questions() -> None:
    assert qra_similarity(
        "Which control family should I use when the answer says SI?",
        "which control family should i use when the answer says si",
    ) == 1.0


def test_blessed_qra_lookup_selects_requested_audio_variant(tmp_path: Path) -> None:
    ledger = write_blessed_qra_ledger(tmp_path)

    match = find_blessed_qra_match(
        "Which control family should I use when the answer says SI?",
        min_similarity=0.99,
        preferred_variant="variant_3",
        ledger_path=ledger,
    )

    assert match["hit"] is True
    assert match["entry_id"] == "qra-si-answer"
    assert match["variant_id"] == "variant_3"
    assert match["variant_count"] == 5
    assert match["similarity"] == 1.0
    assert match["chunks"][0]["pause_after_ms"] == 75


def test_blessed_qra_memory_gate_is_required_by_default(tmp_path: Path) -> None:
    ledger = write_blessed_qra_ledger(tmp_path)
    match = find_blessed_qra_match(
        "Which control family should I use when the answer says SI?",
        min_similarity=0.99,
        ledger_path=ledger,
    )
    request = SynthesisBatchRequest(
        answer_text="Fallback answer.",
        question_text="Which control family should I use when the answer says SI?",
    )

    gated = apply_blessed_qra_memory_gate(request, match)

    assert gated["hit"] is False
    assert gated["reason"] == "memory_gate_failed"
    assert "memory_key_matches_blessed_qra" in gated["memory_gate"]["failed_gates"]


def test_synthesize_batch_uses_blessed_qra_cache_with_memory_gate(tmp_path: Path, monkeypatch) -> None:
    ledger = write_blessed_qra_ledger(tmp_path)
    monkeypatch.setattr(server, "BLESSED_QRA_LEDGER_PATH", ledger)
    monkeypatch.setattr(server, "OUT_DIR", tmp_path / "out")
    def fake_combine_audio_segments(segments, out_path, *, crossfade_ms=20):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        write_tiny_wav(out_path)
        return {"path": str(out_path), "exists": True, "bytes": out_path.stat().st_size, "duration_seconds": 0.1}

    monkeypatch.setattr(server, "combine_audio_segments", fake_combine_audio_segments)

    result = synthesize_batch(
        SynthesisBatchRequest(
            answer_text="Fallback answer should not render.",
            question_text="Which control family should I use when the answer says SI?",
            blessed_qra_memory_key="qra-si-answer",
            blessed_qra_memory_similarity=1.0,
            blessed_qra_memory_review_status="approved",
            blessed_qra_variant="variant_1",
            blessed_qra_preserve_pauses=True,
            crossfade_ms=0,
            label="blessed-qra-test",
        )
    )

    assert result["ok"] is True
    assert result["blessed_qra_cache"]["hit"] is True
    assert result["blessed_qra_cache"]["memory_gate"]["passed"] is True
    assert result["cache_material"]["variant_id"] == "variant_1"
    assert result["chunks"][0]["source"] == "blessed_qra_cache"
    assert result["chunks"][0]["pause_after_ms"] == 25
    assert Path(result["finished_response_audio"]).exists()


def test_tau_voice_render_endpoint_uses_blessed_qra_cache_with_memory_gate(tmp_path: Path, monkeypatch) -> None:
    ledger = write_blessed_qra_ledger(tmp_path)
    monkeypatch.setattr(server, "BLESSED_QRA_LEDGER_PATH", ledger)
    monkeypatch.setattr(server, "OUT_DIR", tmp_path / "out")

    def fake_combine_audio_segments(segments, out_path, *, crossfade_ms=20):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        write_tiny_wav(out_path)
        return {"path": str(out_path), "exists": True, "bytes": out_path.stat().st_size, "duration_seconds": 0.1}

    monkeypatch.setattr(server, "combine_audio_segments", fake_combine_audio_segments)

    result = tau_voice_render(
        TauVoiceRenderRequest(
            conversation_id="conv-qra",
            turn_id="turn-qra",
            question_text="Which control family should I use when the answer says SI?",
            question_text_sha256=server.sha256_text("Which control family should I use when the answer says SI?"),
            memory_route_decision={"called": True, "source": "memory.recall"},
            speakable_chunks=[
                {
                    "text": "Fallback answer should not render.",
                    "text_sha256": server.sha256_text("Fallback answer should not render."),
                    "delivery_stage": "neutral",
                    "max_chars": 300,
                }
            ],
            use_blessed_qra_cache=True,
            blessed_qra_memory_key="qra-si-answer",
            blessed_qra_memory_similarity=1.0,
            blessed_qra_memory_review_status="approved",
            blessed_qra_variant="variant_1",
            blessed_qra_preserve_pauses=True,
            include_completion_cue=False,
            crossfade_ms=0,
        )
    )

    assert result["ok"] is True
    assert result["source"] == "tau_voice_render_request"
    assert result["tau_voice_render_request"]["schema"] == "tau.voice_render_request.v1"
    assert result["blessed_qra_cache"]["hit"] is True
    assert result["blessed_qra_cache"]["memory_gate"]["passed"] is True
    assert result["cache_material"]["variant_id"] == "variant_1"
    assert result["chunks"][0]["source"] == "blessed_qra_cache"


def test_accepted_audio_cache_key_changes_with_text(tmp_path: Path) -> None:
    ref = tmp_path / "ref.wav"
    ref.write_bytes(b"RIFF-ref")
    first = accepted_audio_cache_material(
        SynthesisRequest(text="First answer.", delivery_stage="neutral"),
        ref_audio_path=ref,
        asr_max_wer=0.35,
        asr_max_duration_ratio=2.5,
        asr_max_candidates=3,
    )
    second = accepted_audio_cache_material(
        SynthesisRequest(text="Second answer.", delivery_stage="neutral"),
        ref_audio_path=ref,
        asr_max_wer=0.35,
        asr_max_duration_ratio=2.5,
        asr_max_candidates=3,
    )

    assert accepted_audio_cache_key(first) != accepted_audio_cache_key(second)
    assert first["cache_schema_version"] == CACHE_SCHEMA_VERSION
    assert first["asr_acceptance_version"] == "asr_acceptance.v1"
    assert first["text_normalization_version"] == "asr_acceptance.normalize_text.v1"


def test_asr_candidate_request_preserves_weighted_voice_delivery() -> None:
    base = SynthesisRequest(
        text="I will hold the boundary clearly.",
        label="base",
        tone="firm_boundary",
        delivery_stage="deflecting",
        voice_delivery={
            "tone": "firm_boundary",
            "delivery_stage": "deflecting",
            "intensity": 0.9,
            "valence": -0.7,
            "use_base_emotion": True,
            "source": "memory.intent",
        },
    )

    candidate = synthesis_request_with_overrides(
        base,
        label="candidate",
        overrides={"temperature": 0.72},
    )
    delivery = server.voice_delivery_for_request(candidate)

    assert candidate.voice_delivery["intensity"] == 0.9
    assert candidate.voice_delivery["valence"] == -0.7
    assert candidate.voice_delivery["use_base_emotion"] is True
    assert delivery["tone"] == "firm_boundary"
    assert delivery["intensity"] == 0.9
    assert server.emotion_knobs_from_delivery(delivery) == {
        "exaggeration": 1.11,
        "cfg_weight": 0.36,
        "temperature": 0.7,
        "intensity": 0.9,
        "valence": -0.7,
    }


def test_accepted_audio_cache_material_records_base_engine_for_weighted_emotion(tmp_path: Path) -> None:
    ref = tmp_path / "ref.wav"
    ref.write_bytes(b"RIFF-ref")
    material = accepted_audio_cache_material(
        SynthesisRequest(
            text="Emotion should survive ASR retries.",
            tone="firm_boundary",
            delivery_stage="deflecting",
            voice_delivery={
                "tone": "firm_boundary",
                "delivery_stage": "deflecting",
                "intensity": 0.9,
                "valence": -0.7,
                "use_base_emotion": True,
            },
        ),
        ref_audio_path=ref,
        asr_max_wer=0.35,
        asr_max_duration_ratio=2.5,
        asr_max_candidates=1,
    )

    assert material["engine"] == "chatterbox_base"
    assert material["emotion_knobs"] == {
        "exaggeration": 1.11,
        "cfg_weight": 0.36,
        "temperature": 0.7,
        "intensity": 0.9,
        "valence": -0.7,
    }
    assert material["voice_delivery"]["use_base_emotion"] is True


def test_save_and_load_accepted_audio_cache_round_trip(tmp_path: Path, monkeypatch) -> None:
    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(server, "ACCEPTED_CACHE_DIR", cache_dir)
    ref = tmp_path / "ref.wav"
    ref.write_bytes(b"RIFF-ref")
    audio = tmp_path / "accepted-source.wav"
    write_tiny_wav(audio)
    request = SynthesisRequest(text="Cached answer.", delivery_stage="neutral")
    material = accepted_audio_cache_material(
        request,
        ref_audio_path=ref,
        asr_max_wer=0.35,
        asr_max_duration_ratio=2.5,
        asr_max_candidates=3,
    )
    cache_key = accepted_audio_cache_key(material)
    result = {
        "ok": True,
        "mocked": False,
        "live": True,
        "engine": "chatterbox_turbo",
        "text": request.text,
        "text_sha256": "test",
        "audio": str(audio),
        "duration_seconds": 0.1,
        "metrics": {"bytes": audio.stat().st_size, "duration_seconds": 0.1},
        "asr_verification": {"enabled": True, "ok": True, "failed_gates": []},
        "failed_gates": [],
    }

    saved = save_accepted_audio_cache(cache_key=cache_key, material=material, result=result)
    loaded = load_accepted_audio_cache(cache_key, material)

    assert saved["cache"]["hit"] is False
    assert loaded is not None
    assert loaded["cache"]["hit"] is True
    assert loaded["asr_verification"]["cache_hit"] is True
    assert Path(loaded["audio"]).exists()


def test_accepted_audio_cache_rejects_sha_mismatch(tmp_path: Path, monkeypatch) -> None:
    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(server, "ACCEPTED_CACHE_DIR", cache_dir)
    ref = tmp_path / "ref.wav"
    ref.write_bytes(b"RIFF-ref")
    audio = tmp_path / "accepted-source.wav"
    write_tiny_wav(audio)
    request = SynthesisRequest(text="Cached answer.", delivery_stage="neutral")
    material = accepted_audio_cache_material(
        request,
        ref_audio_path=ref,
        asr_max_wer=0.35,
        asr_max_duration_ratio=2.5,
        asr_max_candidates=3,
    )
    cache_key = accepted_audio_cache_key(material)
    result = {
        "ok": True,
        "mocked": False,
        "live": True,
        "engine": "chatterbox_turbo",
        "text": request.text,
        "text_sha256": "test",
        "audio": str(audio),
        "duration_seconds": 0.1,
        "metrics": {"bytes": audio.stat().st_size, "duration_seconds": 0.1},
        "asr_verification": {
            "enabled": True,
            "ok": True,
            "accepted_gate": {"ok": True, "failed_gates": []},
            "failed_gates": [],
        },
        "failed_gates": [],
    }

    save_accepted_audio_cache(cache_key=cache_key, material=material, result=result)
    cached_audio = cache_dir / cache_key / "accepted.wav"
    cached_audio.write_bytes(cached_audio.read_bytes() + b"corrupt")

    assert load_accepted_audio_cache(cache_key, material) is None


def test_resolve_reference_audio_fails_missing_file(tmp_path: Path) -> None:
    root = tmp_path / "voices"
    root.mkdir()

    try:
        resolve_reference_audio(root / "missing.wav", roots=[root])
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 404
        assert getattr(exc, "detail", None) == "reference_audio_missing"
    else:  # pragma: no cover - explicit failure path
        raise AssertionError("missing explicit reference audio should fail closed")


def test_render_lock_prevents_voice_conditioning_bleed(tmp_path: Path, monkeypatch) -> None:
    import torch

    class FakeModel:
        sr = 24000

        def __init__(self) -> None:
            self.conds = None
            self.generated_with: list[str] = []

        def prepare_conditionals(self, ref_audio: str, **_: object) -> None:
            self.conds = ref_audio

        def generate(self, text: str, **_: object):
            time.sleep(0.05)
            self.generated_with.append(f"{text}:{self.conds}")
            return torch.zeros((1, 2400), dtype=torch.float32)

    root = tmp_path / "voices"
    root.mkdir()
    first_ref = root / "first.wav"
    second_ref = root / "second.wav"
    first_ref.write_bytes(b"RIFF-first")
    second_ref.write_bytes(b"RIFF-second")
    fake = FakeModel()
    monkeypatch.setattr(server, "model", fake)
    monkeypatch.setattr(server, "REFERENCE_AUDIO_ROOTS", [root])
    monkeypatch.setattr(server, "voice_conditioning_cache", {})
    monkeypatch.setitem(
        sys.modules,
        "torchaudio",
        types.SimpleNamespace(save=lambda path, *_args, **_kwargs: write_tiny_wav(Path(path))),
    )

    def run(label: str, ref: Path) -> dict:
        return synthesize_to_file(
            SynthesisRequest(text=label, ref_audio=str(ref), label=label),
            tmp_path / f"{label}.wav",
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        first_future = pool.submit(run, "first", first_ref)
        second_future = pool.submit(run, "second", second_ref)
        first = first_future.result()
        second = second_future.result()

    assert first["ok"]
    assert second["ok"]
    assert f"first:{first_ref.resolve()}" in fake.generated_with
    assert f"second:{second_ref.resolve()}" in fake.generated_with
