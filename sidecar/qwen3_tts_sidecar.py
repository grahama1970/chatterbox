#!/usr/bin/env python3
"""Isolated Qwen3-TTS sidecar for the Chatterbox `qwen3_tts` backend (issue #13).

Runs in its OWN environment (see requirements-qwen3-tts.txt) because qwen-tts
pins transformers==4.57.3 while Chatterbox runs transformers 5.x. The Chatterbox
agent server talks to this service over the versioned contract below and never
imports Qwen dependencies.

Contract: chatterbox.qwen_sidecar.v1
  GET  /health        -> {ok, model_loaded, model_id, revision, vram, versions}
  GET  /capabilities  -> feature read-back for the exact loaded/configured model
  POST /load          -> single-flight model load; {ok, load_seconds, vram}
  POST /unload        -> free the model and CUDA cache
  POST /synthesize    -> {text, language, ref_audio_b64, ref_text?, x_vector_only}
                         -> {ok, wav_b64 (float32le mono), sample_rate, elapsed_s}
"""

from __future__ import annotations

import base64
import io
import os
import threading
import time
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

MODEL_ID = os.getenv("QWEN_TTS_MODEL", "Qwen/Qwen3-TTS-12Hz-1.7B-Base")
MODEL_REVISION = os.getenv("QWEN_TTS_REVISION") or None
DEVICE = os.getenv("QWEN_TTS_DEVICE", "cuda:0")
ATTN = os.getenv("QWEN_TTS_ATTN", "sdpa")  # flash_attention_2 needs flash-attn installed

app = FastAPI(title="qwen3-tts-sidecar")
model: Any | None = None
model_load_seconds: float | None = None
load_lock = threading.Lock()
render_lock = threading.Lock()


class SynthesizeRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    language: str = "English"
    ref_audio_b64: str | None = None
    ref_text: str | None = None
    x_vector_only: bool = True


def vram_stats() -> dict[str, Any]:
    try:
        import torch

        if not torch.cuda.is_available():
            return {"cuda": False}
        return {
            "cuda": True,
            "resident_mb": round(torch.cuda.memory_allocated() / 1024 / 1024, 1),
            "peak_mb": round(torch.cuda.max_memory_allocated() / 1024 / 1024, 1),
        }
    except Exception as exc:  # noqa: BLE001 - health must not crash
        return {"error": str(exc)}


@app.get("/health")
def health() -> dict[str, Any]:
    import qwen_tts
    import torch
    import transformers

    return {
        "ok": True,
        "mocked": False,
        "live": True,
        "schema": "chatterbox.qwen_sidecar.v1",
        "model_loaded": model is not None,
        "model_id": MODEL_ID,
        "revision": MODEL_REVISION,
        "model_load_seconds": model_load_seconds,
        "device": DEVICE,
        "vram": vram_stats(),
        "versions": {
            "qwen_tts": getattr(qwen_tts, "__version__", "unknown"),
            "transformers": transformers.__version__,
            "torch": torch.__version__,
        },
    }


@app.get("/capabilities")
def capabilities() -> dict[str, Any]:
    is_base = "Base" in MODEL_ID
    is_custom = "CustomVoice" in MODEL_ID
    is_design = "VoiceDesign" in MODEL_ID
    return {
        "schema": "chatterbox.qwen_sidecar_capabilities.v1",
        "model_id": MODEL_ID,
        "revision": MODEL_REVISION,
        "voice_clone": is_base,
        "custom_voice": is_custom,
        "voice_design": is_design,
        # Per the released-model table, only 1.7B CustomVoice/VoiceDesign have
        # instruction control; Base has none.
        "per_request_instruction": is_custom or is_design,
        "per_segment_delivery": False,
        "true_incremental_streaming": False,
        "streaming_unsupported_reason": "sidecar_contract_v1_non_streaming",
        "cooperative_model_cancellation": False,
        "cancellation_unsupported_reason": "no_mid_generation_abort_in_contract_v1",
        "deterministic_seed": False,
        "input_sample_formats": ["wav_b64_any_sr_reference"],
        "output_sample_formats": ["float32le_b64_model_sr"],
        "max_concurrency": 1,
    }


@app.post("/load")
def load() -> dict[str, Any]:
    global model, model_load_seconds
    with load_lock:
        if model is None:
            import torch
            from qwen_tts import Qwen3TTSModel

            started = time.perf_counter()
            kwargs: dict[str, Any] = {
                "device_map": DEVICE,
                "dtype": torch.bfloat16,
                "attn_implementation": ATTN,
            }
            if MODEL_REVISION:
                kwargs["revision"] = MODEL_REVISION
            model = Qwen3TTSModel.from_pretrained(MODEL_ID, **kwargs)
            model_load_seconds = round(time.perf_counter() - started, 3)
    return {"ok": True, "model_id": MODEL_ID, "load_seconds": model_load_seconds, "vram": vram_stats()}


@app.post("/unload")
def unload() -> dict[str, Any]:
    global model, model_load_seconds
    with load_lock:
        model = None
        model_load_seconds = None
        try:
            import gc

            import torch

            gc.collect()
            torch.cuda.empty_cache()
            torch.cuda.reset_peak_memory_stats()
        except Exception:  # noqa: BLE001
            pass
    return {"ok": True, "model_loaded": False, "vram": vram_stats()}


@app.post("/synthesize")
def synthesize(request: SynthesizeRequest) -> dict[str, Any]:
    import numpy as np
    import soundfile as sf

    if model is None:
        load()
    started = time.perf_counter()
    ref_audio = None
    if request.ref_audio_b64:
        data, sr = sf.read(io.BytesIO(base64.b64decode(request.ref_audio_b64)), dtype="float32")
        if data.ndim > 1:
            data = data.mean(axis=1)
        ref_audio = (data, sr)
    with render_lock:
        wavs, sample_rate = model.generate_voice_clone(
            text=request.text,
            language=request.language,
            ref_audio=ref_audio,
            ref_text=request.ref_text,
            x_vector_only_mode=request.x_vector_only and not request.ref_text,
        )
    wav = np.asarray(wavs[0], dtype=np.float32)
    return {
        "ok": True,
        "mocked": False,
        "live": True,
        "wav_b64": base64.b64encode(wav.tobytes()).decode("ascii"),
        "sample_rate": int(sample_rate),
        "samples": int(wav.shape[-1]),
        "elapsed_s": round(time.perf_counter() - started, 3),
        "vram": vram_stats(),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=os.getenv("QWEN_TTS_HOST", "127.0.0.1"), port=int(os.getenv("QWEN_TTS_PORT", "8019")))
