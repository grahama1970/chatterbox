"""Always-on Chatterbox Turbo HTTP server for voice-agent render plans."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import torch
import torchaudio as ta
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from chatterbox.agent.chunking import build_render_plan
from chatterbox.agent.presets import (
    STAGE_PRESETS,
    TURBO_IGNORED_PARAMS,
    TURBO_SUPPORTED_PARAMS,
    generation_params_for_stage,
)
from chatterbox.tts_turbo import ChatterboxTurboTTS


OUT_DIR = Path(os.getenv("CHATTERBOX_OUT_DIR", "/out"))
DEFAULT_REF_AUDIO = Path(os.getenv("CHATTERBOX_REF_AUDIO", "/data/embry_ref.wav"))
DEVICE = os.getenv("CHATTERBOX_DEVICE", "cuda")

app = FastAPI(title="Chatterbox Turbo Agent Server")
model: ChatterboxTurboTTS | None = None
model_load_seconds: float | None = None
started_at_utc = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class RenderPlanRequest(BaseModel):
    answer_text: str = Field(min_length=1, max_length=12000)
    max_chars: int = Field(default=300, ge=80, le=1200)
    pause_after_ms: int = Field(default=250, ge=0, le=3000)
    completion_cue: str | None = Field(default=None, max_length=240)


class SynthesisRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1200)
    ref_audio: str | None = None
    label: str | None = None
    delivery_stage: str | None = None
    temperature: float | None = Field(default=None, ge=0.05, le=5.0)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)
    top_k: int | None = Field(default=None, ge=1, le=5000)
    repetition_penalty: float | None = Field(default=None, ge=1.0, le=2.0)
    norm_loudness: bool | None = None


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run_cmd(cmd: list[str], timeout: int = 30) -> dict[str, Any]:
    result = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)
    return {
        "cmd": cmd,
        "returncode": result.returncode,
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
    }


def audio_metrics(path: Path) -> dict[str, Any]:
    probe = run_cmd(
        [
            "ffprobe",
            "-hide_banner",
            "-v",
            "error",
            "-show_entries",
            "format=duration,size",
            "-show_entries",
            "stream=codec_name,sample_rate,channels",
            "-of",
            "json",
            str(path),
        ]
    )
    metrics: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "bytes": path.stat().st_size if path.exists() else 0,
        "sha256": sha256_file(path) if path.exists() else None,
        "ffprobe": probe,
    }
    if probe["returncode"] == 0:
        info = json.loads(probe["stdout"])
        stream = (info.get("streams") or [{}])[0]
        fmt = info.get("format") or {}
        metrics.update(
            {
                "codec_name": stream.get("codec_name"),
                "sample_rate": int(stream.get("sample_rate") or 0),
                "channels": int(stream.get("channels") or 0),
                "duration_seconds": round(float(fmt.get("duration") or 0.0), 3),
                "ffprobe_size": int(fmt.get("size") or 0),
            }
        )
    return metrics


def generation_params(request: SynthesisRequest) -> dict[str, float | int | bool]:
    overrides = {
        "temperature": request.temperature,
        "top_p": request.top_p,
        "top_k": request.top_k,
        "repetition_penalty": request.repetition_penalty,
        "norm_loudness": request.norm_loudness,
    }
    return generation_params_for_stage(request.delivery_stage, overrides=overrides)


@app.on_event("startup")
def load_model() -> None:
    global model, model_load_seconds
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    model = ChatterboxTurboTTS.from_pretrained(device=DEVICE)
    model_load_seconds = round(time.perf_counter() - started, 3)


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": model is not None,
        "mocked": False,
        "live": True,
        "started_at_utc": started_at_utc,
        "engine": "chatterbox_turbo",
        "device": DEVICE,
        "model_loaded": model is not None,
        "model_load_seconds": model_load_seconds,
        "supported_params": sorted(TURBO_SUPPORTED_PARAMS),
        "ignored_turbo_params": sorted(TURBO_IGNORED_PARAMS),
        "torch": {
            "version": torch.__version__,
            "cuda_available": torch.cuda.is_available(),
            "cuda_version": torch.version.cuda,
            "device_count": torch.cuda.device_count(),
            "device_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        },
        "nvidia_smi": run_cmd(["nvidia-smi", "--query-gpu=name,memory.total,memory.used,memory.free,driver_version", "--format=csv,noheader"]),
    }


@app.get("/presets")
def presets() -> dict[str, Any]:
    return {
        "ok": True,
        "engine": "chatterbox_turbo",
        "supported_params": sorted(TURBO_SUPPORTED_PARAMS),
        "ignored_turbo_params": sorted(TURBO_IGNORED_PARAMS),
        "stage_presets": STAGE_PRESETS,
    }


@app.post("/render-plan")
def render_plan(request: RenderPlanRequest) -> dict[str, Any]:
    plan = build_render_plan(
        request.answer_text,
        max_chars=request.max_chars,
        pause_after_ms=request.pause_after_ms,
        completion_cue=request.completion_cue,
    )
    return {"ok": True, "mocked": False, "live": True, "plan": plan}


@app.post("/synthesize")
def synthesize(request: SynthesisRequest) -> dict[str, Any]:
    if model is None:
        raise HTTPException(status_code=503, detail="model_not_loaded")
    ref_audio = Path(request.ref_audio) if request.ref_audio else DEFAULT_REF_AUDIO
    audio_prompt_path = str(ref_audio) if ref_audio.exists() else None
    label = request.label or f"sample-{uuid4().hex[:8]}"
    safe_label = "".join(c if c.isalnum() or c in "-_" else "_" for c in label)[:80]
    out_path = OUT_DIR / f"{safe_label}.wav"
    try:
        params = generation_params(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    started = time.perf_counter()
    try:
        wav = model.generate(request.text, audio_prompt_path=audio_prompt_path, **params)
        generation_seconds = round(time.perf_counter() - started, 3)
        ta.save(str(out_path), wav, model.sr)
        os.chmod(out_path, 0o664)
        metrics = audio_metrics(out_path)
    except Exception as exc:  # noqa: BLE001 - endpoint must return a JSON receipt on model failures
        generation_seconds = round(time.perf_counter() - started, 3)
        return {
            "ok": False,
            "mocked": False,
            "live": True,
            "engine": "chatterbox_turbo",
            "requested_device": DEVICE,
            "text": request.text,
            "text_sha256": hashlib.sha256(request.text.encode("utf-8")).hexdigest(),
            "reference_audio": audio_prompt_path,
            "audio": str(out_path),
            "delivery_stage": request.delivery_stage,
            "generation_params": params,
            "generation_seconds": generation_seconds,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "failed_gates": ["generation_exception"],
        }
    duration = float(metrics.get("duration_seconds") or 0.0)
    failed_gates = []
    if duration <= 0:
        failed_gates.append("duration_present")
    if int(metrics.get("bytes") or 0) <= 44:
        failed_gates.append("audio_non_empty")
    return {
        "ok": not failed_gates,
        "mocked": False,
        "live": True,
        "engine": "chatterbox_turbo",
        "requested_device": DEVICE,
        "text": request.text,
        "text_sha256": hashlib.sha256(request.text.encode("utf-8")).hexdigest(),
        "reference_audio": audio_prompt_path,
        "audio": str(out_path),
        "delivery_stage": request.delivery_stage,
        "generation_params": params,
        "generation_seconds": generation_seconds,
        "duration_seconds": duration,
        "realtime_factor": round(generation_seconds / duration, 3) if duration else None,
        "metrics": metrics,
        "failed_gates": failed_gates,
    }
