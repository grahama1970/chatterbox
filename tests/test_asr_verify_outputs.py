"""Tests for ASR receipt extraction that avoid loading Whisper."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_asr_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "asr_verify_outputs.py"
    spec = importlib.util.spec_from_file_location("asr_verify_outputs", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_iter_audio_cases_extracts_nested_batch_chunks(tmp_path: Path) -> None:
    mod = load_asr_module()
    receipt = {
        "batch_synthesis": {
            "chunks": [
                {
                    "chunk_index": 1,
                    "audio": "chunk_01.wav",
                    "text": "Hmm. I found the control family now.",
                    "text_sha256": "abc123",
                }
            ],
            "completion_cue": {
                "audio": "finished.wav",
                "text": "Anything else you need?",
                "text_sha256": "def456",
            },
        }
    }

    cases = mod.iter_audio_cases(receipt, tmp_path)

    assert [case.label for case in cases] == ["1", "finished"]
    assert [case.audio for case in cases] == [tmp_path / "chunk_01.wav", tmp_path / "finished.wav"]
    assert [case.expected_text for case in cases] == [
        "Hmm. I found the control family now.",
        "Anything else you need?",
    ]


def test_iter_audio_cases_maps_container_audio_paths(tmp_path: Path) -> None:
    mod = load_asr_module()
    host_out = tmp_path / "out"
    receipt = {
        "batch_synthesis": {
            "chunks": [
                {
                    "chunk_index": 1,
                    "audio": "/out/chunk_01.wav",
                    "text": "Mapped container path.",
                }
            ]
        }
    }

    cases = mod.iter_audio_cases(receipt, tmp_path, {"/out": host_out})

    assert len(cases) == 1
    assert cases[0].audio == host_out / "chunk_01.wav"


def test_iter_audio_cases_extracts_single_synthesis() -> None:
    mod = load_asr_module()
    receipt = {
        "synthesis": {
            "audio": "/tmp/chunk.wav",
            "text": "I can answer that.",
            "text_sha256": "abc123",
        }
    }

    cases = mod.iter_audio_cases(receipt, Path("/tmp/receipts"))

    assert len(cases) == 1
    assert cases[0].audio == Path("/tmp/chunk.wav")
    assert cases[0].expected_text == "I can answer that."


def test_iter_audio_cases_empty_receipt_returns_no_cases() -> None:
    mod = load_asr_module()

    assert mod.iter_audio_cases({"batch_synthesis": {"chunks": []}}, Path("/tmp")) == []


def test_word_error_proxy_penalizes_inserted_repeated_words() -> None:
    mod = load_asr_module()

    score = mod.word_error_proxy(
        "I found the control family now.",
        "I found the control family now. control family control family control family.",
    )

    assert score > 0.5
