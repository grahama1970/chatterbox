"""Chatterbox-side adapter for the isolated Qwen3-TTS sidecar (issue #13).

This module never imports Qwen dependencies: it is a thin HTTP client for the
`chatterbox.qwen_sidecar.v1` contract, registered as the explicit-only
`qwen3_tts` backend. Auto-selection rules never route here; a sidecar or load
failure raises instead of falling back to another engine.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from chatterbox.agent.backends import (
    DECLARED_SAMPLE_RATE,
    CallableVoiceBackend,
    VoiceBackendRegistry,
    VoiceCapabilities,
)

QWEN_BACKEND_ID = "qwen3_tts"
DEFAULT_SIDECAR_URL = "http://127.0.0.1:8019"
DEFAULT_MODEL_ID = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
PINNED_REVISION = "fd4b254389122332181a7c3db7f27e918eec64e3"


def sidecar_url() -> str:
    return os.getenv("CHATTERBOX_QWEN_SIDECAR_URL", DEFAULT_SIDECAR_URL).rstrip("/")


class QwenSidecarUnavailable(RuntimeError):
    pass


def _request(path: str, payload: dict[str, Any] | None = None, timeout: int = 1800) -> dict[str, Any]:
    url = f"{sidecar_url()}{path}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST" if payload is not None else "GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError) as exc:
        raise QwenSidecarUnavailable(f"qwen_sidecar_unavailable: {url}: {exc}") from exc


def sidecar_is_loaded() -> bool:
    try:
        return bool(_request("/health", timeout=5).get("model_loaded"))
    except QwenSidecarUnavailable:
        return False


def sidecar_load() -> None:
    _request("/load", payload={})


def sidecar_unload() -> None:
    _request("/unload", payload={}, timeout=60)


def sidecar_capabilities() -> dict[str, Any]:
    return _request("/capabilities", timeout=10)


def qwen_generate(*, text: str, ref_audio: Path, params: dict[str, Any] | None = None):
    """Voice-clone render via the sidecar; ignores Turbo-only generation params."""
    import torch

    ref_b64 = base64.b64encode(Path(ref_audio).read_bytes()).decode("ascii")
    result = _request(
        "/synthesize",
        payload={
            "text": text,
            "language": os.getenv("CHATTERBOX_QWEN_LANGUAGE", "English"),
            "ref_audio_b64": ref_b64,
            "ref_text": os.getenv("CHATTERBOX_QWEN_REF_TEXT") or None,
            "x_vector_only": True,
        },
    )
    if not result.get("ok"):
        raise RuntimeError(f"qwen_sidecar_synthesis_failed: {result}")
    import numpy as np

    wav = np.frombuffer(base64.b64decode(result["wav_b64"]), dtype=np.float32).copy()
    tensor = torch.from_numpy(wav).reshape(1, -1)
    sample_rate = int(result["sample_rate"])
    if sample_rate != DECLARED_SAMPLE_RATE:
        import torchaudio

        tensor = torchaudio.functional.resample(tensor, sample_rate, DECLARED_SAMPLE_RATE)
        sample_rate = DECLARED_SAMPLE_RATE
    conditioning = {
        "reference_audio": str(ref_audio),
        "engine": QWEN_BACKEND_ID,
        "sidecar_url": sidecar_url(),
        "sidecar_elapsed_s": result.get("elapsed_s"),
        "sidecar_vram": result.get("vram"),
        "x_vector_only_mode": True,
        "ignored_generation_params": sorted(params) if params else [],
    }
    return tensor, sample_rate, conditioning


QWEN_CAPABILITIES = VoiceCapabilities(
    backend_id=QWEN_BACKEND_ID,
    revision=f"{DEFAULT_MODEL_ID}@{PINNED_REVISION[:12]}",
    voice_cloning=True,
    preset_voices=False,
    structured_affect_axes=False,
    per_segment_delivery=False,
    true_incremental_streaming=False,
    cooperative_inference_cancellation=False,
    stale_output_fencing=True,
    deterministic_seed=False,
    input_sample_formats=("wav_any_sr_reference",),
    output_sample_formats=("wav_float32_24000_resampled", "pcm_s16le_24000"),
    estimated_resident_vram_mb=6000,
    max_concurrency=1,
)


def register_qwen_backend(registry: VoiceBackendRegistry) -> None:
    registry.register(
        CallableVoiceBackend(
            caps=QWEN_CAPABILITIES,
            loader=sidecar_load,
            generator=qwen_generate,
            is_loaded=sidecar_is_loaded,
            unloader=sidecar_unload,
        )
    )
