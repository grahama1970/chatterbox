"""Server primitive tests that do not require loading the Chatterbox model."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
import time
import types
import wave

from chatterbox.agent.chunking import build_render_plan, split_spoken_chunks
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
    synthesize_to_file,
    synthesize_batch,
    tau_voice_render,
)


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
    assert delivery["delivery_stage"] == "satisfied"
    assert delivery["delivery_stage_source"] == "tone_mapping"
    assert params == server.generation_params_for_stage("satisfied")


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
    assert result["delivery_stage"] == "satisfied"
    assert result["voice_delivery"]["pace"] == "measured"
    assert result["voice_delivery"]["pause_strategy"] == "short_answer_no_filler"
    assert result["generation_params"] == server.generation_params_for_stage("satisfied")


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
    assert receipt["voice_delivery"]["source"] == "memory_intent"
    assert receipt["mapped_batch"]["tone"] == "memory_confident"
    assert receipt["mapped_batch"]["delivery_stage"] == "satisfied"


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
