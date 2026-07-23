"""Always-on Chatterbox Turbo HTTP server for voice-agent render plans."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import threading
import time
import urllib.request
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from chatterbox.agent.asr_acceptance import acceptance_result
from chatterbox.agent.chunking import build_render_plan
from chatterbox.agent.presets import (
    ALLOWED_TONES,
    CHATTERBOX_TAG_HANDLING,
    DELIVERY_STAGE_ALIASES,
    STAGE_PRESETS,
    TONE_TO_DELIVERY_STAGE,
    TURBO_IGNORED_PARAMS,
    TURBO_SUPPORTED_PARAMS,
    effective_delivery_stage,
    generation_params_for_stage,
    normalize_delivery_stage,
    normalize_tone,
    normalize_voice_token,
)


OUT_DIR = Path(os.getenv("CHATTERBOX_OUT_DIR", "/out"))
ACCEPTED_CACHE_DIR = OUT_DIR / "_accepted_audio_cache"
DEFAULT_REF_AUDIO = Path(os.getenv("CHATTERBOX_REF_AUDIO", "/data/embry_ref.wav"))
DEVICE = os.getenv("CHATTERBOX_DEVICE", "cuda")
DEFAULT_ASR_OPENAI_BASE_URL = os.getenv("CHATTERBOX_ASR_OPENAI_BASE_URL", "http://172.17.0.1:9000")
ASR_API_KEY_ENV = os.getenv("CHATTERBOX_ASR_API_KEY_ENV", "WHISPER_API_KEY")
CACHE_SCHEMA_VERSION = "accepted_audio_cache.v2"
BLESSED_QRA_SCHEMA_VERSION = "blessed_qra_response_cache.v1"
BLESSED_QRA_LEDGER_PATH = Path(os.getenv("CHATTERBOX_BLESSED_QRA_LEDGER", str(OUT_DIR / "_blessed_qra_ledger.json")))
ASR_ACCEPTANCE_VERSION = "asr_acceptance.v1"
TEXT_NORMALIZATION_VERSION = "asr_acceptance.normalize_text.v1"
STREAM_PROTOCOL_VERSION = "pcm_l16_chunk_stream.v1"
REFERENCE_AUDIO_ROOTS = [
    Path(item)
    for item in os.getenv(
        "CHATTERBOX_REF_AUDIO_ROOTS",
        f"{DEFAULT_REF_AUDIO.parent}:/data:/voices",
    ).split(":")
    if item
]

app = FastAPI(title="Chatterbox Turbo Agent Server")
model: Any | None = None
model_load_seconds: float | None = None
started_at_utc = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
voice_conditioning_cache: dict[str, Any] = {}
turn_controls: dict[str, dict[str, Any]] = {}
render_lock = threading.RLock()

ASR_CANDIDATE_VARIANTS: list[dict[str, Any]] = [
    {"name": "stage_default", "overrides": {}},
    {
        "name": "cooler_penalty",
        "overrides": {
            "temperature": 0.62,
            "top_p": 0.82,
            "top_k": 600,
            "repetition_penalty": 1.35,
        },
    },
    {
        "name": "baseline_penalty",
        "overrides": {
            "temperature": 0.72,
            "top_p": 0.90,
            "top_k": 900,
            "repetition_penalty": 1.28,
        },
    },
]


class RenderPlanRequest(BaseModel):
    answer_text: str = Field(min_length=1, max_length=12000)
    max_chars: int = Field(default=300, ge=80, le=1200)
    pause_after_ms: int = Field(default=250, ge=0, le=3000)
    completion_cue: str | None = Field(default=None, max_length=240)


class SynthesisRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1200)
    ref_audio: str | None = None
    label: str | None = None
    tone: str | None = Field(default=None, max_length=80)
    delivery_stage: str | None = None
    pace: str | None = Field(default=None, max_length=80)
    pause_strategy: str | None = Field(default=None, max_length=120)
    voice_delivery: dict[str, Any] = Field(default_factory=dict)
    temperature: float | None = Field(default=None, ge=0.05, le=5.0)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)
    top_k: int | None = Field(default=None, ge=1, le=5000)
    repetition_penalty: float | None = Field(default=None, ge=1.0, le=2.0)
    norm_loudness: bool | None = None


class SynthesisBatchRequest(RenderPlanRequest):
    turn_id: str | None = Field(default=None, max_length=120)
    question_text: str | None = Field(default=None, max_length=12000)
    use_blessed_qra_cache: bool = True
    blessed_qra_min_similarity: float = Field(default=0.99, ge=0.0, le=1.0)
    blessed_qra_variant: str | None = Field(default=None, max_length=120)
    blessed_qra_preserve_pauses: bool = False
    require_blessed_qra_memory_gate: bool = True
    blessed_qra_memory_key: str | None = Field(default=None, max_length=240)
    blessed_qra_memory_similarity: float | None = Field(default=None, ge=0.0)
    blessed_qra_memory_review_status: str | None = Field(default=None, max_length=80)
    ref_audio: str | None = None
    label: str | None = None
    tone: str | None = Field(default=None, max_length=80)
    delivery_stage: str | None = Field(default=None, max_length=80)
    pace: str | None = Field(default=None, max_length=80)
    pause_strategy: str | None = Field(default=None, max_length=120)
    voice_delivery: dict[str, Any] = Field(default_factory=dict)
    delivery_arc: list[dict[str, str]] | None = None
    include_completion_cue: bool = True
    stream: bool = False
    crossfade_ms: int = Field(default=20, ge=0, le=250)
    asr_verify: bool = False
    asr_max_wer: float = Field(default=0.35, ge=0.0, le=2.0)
    asr_max_duration_ratio: float = Field(default=2.5, ge=1.0, le=10.0)
    asr_max_candidates: int = Field(default=3, ge=1, le=5)
    asr_cache: bool = True


class TauVoiceChunk(BaseModel):
    chunk_id: str | None = Field(default=None, max_length=160)
    text: str = Field(min_length=1, max_length=1200)
    text_sha256: str | None = Field(default=None, max_length=128)
    tone: str | None = Field(default=None, max_length=80)
    delivery_stage: str | None = Field(default=None, max_length=80)
    pace: str | None = Field(default=None, max_length=80)
    pause_strategy: str | None = Field(default=None, max_length=120)
    pause_after_ms: int | None = Field(default=None, ge=0, le=3000)
    interruptible: bool = True
    max_chars: int | None = Field(default=None, ge=80, le=300)


class TauVoiceTurnControlPolicy(BaseModel):
    old_turn_id: str | None = Field(default=None, max_length=120)
    cancel_requested: bool = False
    stale_old_turn_chunks_should_skip: bool = False


class TauVoiceRenderRequest(BaseModel):
    schema: str = Field(default="tau.voice_render_request.v1")
    run_id: str | None = Field(default=None, max_length=160)
    conversation_id: str = Field(min_length=1, max_length=160)
    turn_id: str = Field(min_length=1, max_length=120)
    route: str = Field(default="tau_voice_render", max_length=160)
    active_domain_persona: str | None = Field(default=None, max_length=120)
    question_text: str | None = Field(default=None, max_length=12000)
    question_text_sha256: str | None = Field(default=None, max_length=128)
    memory_route_decision: dict[str, Any] = Field(default_factory=dict)
    answerability_decision: dict[str, Any] = Field(default_factory=dict)
    voice_delivery: dict[str, Any] = Field(default_factory=dict)
    speakable_chunks: list[TauVoiceChunk] = Field(min_length=1)
    tone: str | None = Field(default=None, max_length=80)
    delivery_stage: str | None = Field(default=None, max_length=80)
    pace: str | None = Field(default=None, max_length=80)
    pause_strategy: str | None = Field(default=None, max_length=120)
    interruptible: bool = True
    use_blessed_qra_cache: bool = True
    blessed_qra_min_similarity: float = Field(default=0.99, ge=0.0, le=1.0)
    blessed_qra_variant: str | None = Field(default=None, max_length=120)
    blessed_qra_preserve_pauses: bool = False
    require_blessed_qra_memory_gate: bool = True
    blessed_qra_memory_key: str | None = Field(default=None, max_length=240)
    blessed_qra_memory_similarity: float | None = Field(default=None, ge=0.0)
    blessed_qra_memory_review_status: str | None = Field(default=None, max_length=80)
    turn_control_policy: TauVoiceTurnControlPolicy = Field(default_factory=TauVoiceTurnControlPolicy)
    external_evidence: dict[str, Any] = Field(default_factory=dict)
    receipt_root: str | None = Field(default=None, max_length=2048)
    label: str | None = Field(default=None, max_length=160)
    completion_cue: str | None = Field(default=None, max_length=240)
    include_completion_cue: bool = False
    crossfade_ms: int = Field(default=20, ge=0, le=250)
    asr_verify: bool = False


class TurnControlRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=240)
    old_turn_id: str | None = Field(default=None, max_length=120)
    new_turn_id: str | None = Field(default=None, max_length=120)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def model_to_dict(model: BaseModel) -> dict[str, Any]:
    dump = getattr(model, "model_dump", None)
    if callable(dump):
        return dump()
    return model.dict()


def latency_event(events: list[dict[str, Any]], name: str, started: float, **extra: Any) -> None:
    events.append(
        {
            "name": name,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
            **extra,
        }
    )


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


def normalize_qra_text(text: str) -> str:
    return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in text).split())


def qra_similarity(left: str, right: str) -> float:
    normalized_left = normalize_qra_text(left)
    normalized_right = normalize_qra_text(right)
    if not normalized_left or not normalized_right:
        return 0.0
    if normalized_left == normalized_right:
        return 1.0
    return round(SequenceMatcher(None, normalized_left, normalized_right).ratio(), 6)


def load_blessed_qra_ledger(path: Path | None = None) -> dict[str, Any]:
    ledger_path = path or BLESSED_QRA_LEDGER_PATH
    if not ledger_path.exists():
        return {
            "ok": False,
            "enabled": True,
            "path": str(ledger_path),
            "entries": [],
            "failed_gates": ["ledger_present"],
        }
    try:
        payload = json.loads(ledger_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - exposed as receipt data
        return {
            "ok": False,
            "enabled": True,
            "path": str(ledger_path),
            "entries": [],
            "error_type": type(exc).__name__,
            "error": str(exc),
            "failed_gates": ["ledger_json_valid"],
        }
    if isinstance(payload, list):
        payload = {"schema_version": BLESSED_QRA_SCHEMA_VERSION, "entries": payload}
    entries = payload.get("entries")
    if not isinstance(entries, list):
        return {
            "ok": False,
            "enabled": True,
            "path": str(ledger_path),
            "entries": [],
            "schema_version": payload.get("schema_version"),
            "failed_gates": ["ledger_entries_list"],
        }
    return {
        "ok": True,
        "enabled": bool(payload.get("enabled", True)),
        "path": str(ledger_path),
        "schema_version": payload.get("schema_version"),
        "entries": entries,
        "failed_gates": [],
    }


def blessed_qra_candidate_questions(entry: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    for key in ["question_text", "question", "question_normalized"]:
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            candidates.append(value)
    variants = entry.get("question_variants")
    if isinstance(variants, list):
        candidates.extend(item for item in variants if isinstance(item, str) and item.strip())
    return candidates


def select_blessed_qra_variant(entry: dict[str, Any], preferred_variant: str | None) -> dict[str, Any]:
    variants = entry.get("audio_variants") or entry.get("variants")
    if isinstance(variants, list) and variants:
        valid_variants = [variant for variant in variants if isinstance(variant, dict) and variant.get("blessed", True)]
        if preferred_variant:
            for variant in valid_variants:
                if preferred_variant in {str(variant.get("id")), str(variant.get("name"))}:
                    return variant
        for variant in valid_variants:
            if variant.get("default") or variant.get("id") == "default_fast":
                return variant
        if valid_variants:
            return valid_variants[0]
    return {
        "id": "default",
        "name": "default",
        "default": True,
        "emotion_arc": entry.get("emotion_arc") or entry.get("emotion_policy"),
        "pause_profile": entry.get("pause_profile"),
        "chunks": entry.get("chunks"),
    }


def resolve_blessed_qra_audio_path(path_value: str, *, ledger_path: Path) -> Path:
    candidate = Path(path_value)
    if not candidate.is_absolute():
        candidate = ledger_path.parent / candidate
    return candidate.resolve(strict=False)


def find_blessed_qra_match(
    question_text: str | None,
    *,
    min_similarity: float,
    preferred_variant: str | None = None,
    ledger_path: Path | None = None,
) -> dict[str, Any]:
    if not question_text or not question_text.strip():
        return {
            "enabled": True,
            "hit": False,
            "reason": "question_text_missing",
            "min_similarity": min_similarity,
            "failed_gates": [],
        }
    ledger = load_blessed_qra_ledger(ledger_path)
    if not ledger.get("ok"):
        return {
            "enabled": True,
            "hit": False,
            "reason": "ledger_unavailable",
            "ledger": {key: ledger.get(key) for key in ["path", "schema_version", "failed_gates", "error_type", "error"]},
            "min_similarity": min_similarity,
            "failed_gates": [],
        }
    if not ledger.get("enabled", True):
        return {
            "enabled": False,
            "hit": False,
            "reason": "ledger_disabled",
            "ledger": {"path": ledger.get("path"), "schema_version": ledger.get("schema_version")},
            "min_similarity": min_similarity,
            "failed_gates": [],
        }

    best: dict[str, Any] | None = None
    for entry in ledger["entries"]:
        if not isinstance(entry, dict) or not entry.get("blessed", True):
            continue
        for candidate in blessed_qra_candidate_questions(entry):
            similarity = qra_similarity(question_text, candidate)
            if best is None or similarity > best["similarity"]:
                best = {
                    "entry": entry,
                    "matched_question": candidate,
                    "similarity": similarity,
                }
    if not best or best["similarity"] < min_similarity:
        return {
            "enabled": True,
            "hit": False,
            "reason": "similarity_below_threshold",
            "best_similarity": best["similarity"] if best else None,
            "min_similarity": min_similarity,
            "ledger": {"path": ledger.get("path"), "schema_version": ledger.get("schema_version")},
            "failed_gates": [],
        }

    entry = best["entry"]
    variant = select_blessed_qra_variant(entry, preferred_variant)
    chunks = variant.get("chunks")
    answer_text = entry.get("answer_text")
    if not isinstance(answer_text, str) or not answer_text.strip():
        return {
            "enabled": True,
            "hit": False,
            "reason": "entry_answer_text_missing",
            "entry_id": entry.get("id"),
            "similarity": best["similarity"],
            "failed_gates": ["entry_answer_text_present"],
        }
    if not isinstance(chunks, list) or not chunks:
        return {
            "enabled": True,
            "hit": False,
            "reason": "entry_chunks_missing",
            "entry_id": entry.get("id"),
            "variant_id": variant.get("id"),
            "similarity": best["similarity"],
            "failed_gates": ["entry_chunks_present"],
        }

    ledger_file = Path(str(ledger["path"]))
    resolved_chunks = []
    failed_gates = []
    for index, chunk in enumerate(chunks, start=1):
        if not isinstance(chunk, dict):
            failed_gates.append(f"chunk_{index}_object")
            continue
        text = chunk.get("text")
        audio = chunk.get("audio")
        if not isinstance(text, str) or not text.strip():
            failed_gates.append(f"chunk_{index}_text_present")
            continue
        if len(text) > 300:
            failed_gates.append(f"chunk_{index}_text_300_char_max")
        if not isinstance(audio, str) or not audio.strip():
            failed_gates.append(f"chunk_{index}_audio_present")
            continue
        audio_path = resolve_blessed_qra_audio_path(audio, ledger_path=ledger_file)
        if not audio_path.exists():
            failed_gates.append(f"chunk_{index}_audio_exists")
            continue
        metrics = audio_metrics(audio_path)
        if int(metrics.get("bytes") or 0) <= 44 or float(metrics.get("duration_seconds") or 0.0) <= 0:
            failed_gates.append(f"chunk_{index}_audio_non_empty")
        expected_sha256 = chunk.get("audio_sha256")
        if expected_sha256 and metrics.get("sha256") != expected_sha256:
            failed_gates.append(f"chunk_{index}_audio_sha256_match")
        resolved_chunks.append({**chunk, "index": chunk.get("index") or index, "audio": str(audio_path), "metrics": metrics})

    if failed_gates:
        return {
            "enabled": True,
            "hit": False,
            "reason": "entry_validation_failed",
            "entry_id": entry.get("id"),
            "similarity": best["similarity"],
            "failed_gates": failed_gates,
        }

    return {
        "enabled": True,
        "hit": True,
        "reason": "similarity_threshold_met",
        "schema_version": BLESSED_QRA_SCHEMA_VERSION,
        "ledger": {"path": ledger.get("path"), "schema_version": ledger.get("schema_version")},
        "entry_id": entry.get("id"),
        "variant_id": variant.get("id"),
        "variant_name": variant.get("name"),
        "variant_count": len(entry.get("audio_variants") or entry.get("variants") or [variant]),
        "memory_keys": [
            str(item)
            for item in (
                entry.get("memory_keys")
                or entry.get("qra_memory_keys")
                or ([entry.get("memory_key")] if entry.get("memory_key") else [])
            )
        ],
        "question_text": question_text,
        "matched_question": best["matched_question"],
        "similarity": best["similarity"],
        "min_similarity": min_similarity,
        "answer_text": answer_text,
        "answer_text_sha256": hashlib.sha256(answer_text.encode("utf-8")).hexdigest(),
        "evidence": entry.get("evidence"),
        "emotion_policy": variant.get("emotion_policy") or entry.get("emotion_policy"),
        "emotion_arc": variant.get("emotion_arc") or entry.get("emotion_arc"),
        "pause_profile": variant.get("pause_profile") or entry.get("pause_profile"),
        "chunks": resolved_chunks,
        "failed_gates": [],
    }


def safe_resolve_within(path_value: str | Path, roots: list[Path] | None = None) -> Path:
    """Resolve a file path under approved roots and reject traversal."""
    candidate = Path(path_value)
    if not candidate.is_absolute():
        candidate = DEFAULT_REF_AUDIO.parent / candidate
    resolved = candidate.resolve(strict=False)
    allowed_roots = [root.resolve(strict=False) for root in (roots or REFERENCE_AUDIO_ROOTS)]
    if not any(resolved == root or root in resolved.parents for root in allowed_roots):
        raise HTTPException(status_code=400, detail="reference_audio_outside_allowed_roots")
    if ".." in candidate.parts:
        raise HTTPException(status_code=400, detail="reference_audio_path_traversal")
    return resolved


def resolve_reference_audio(path_value: str | Path, roots: list[Path] | None = None) -> Path:
    resolved = safe_resolve_within(path_value, roots=roots)
    if not resolved.exists():
        raise HTTPException(status_code=404, detail="reference_audio_missing")
    if resolved.suffix.lower() not in {".wav", ".flac", ".mp3", ".ogg", ".m4a"}:
        raise HTTPException(status_code=422, detail="reference_audio_extension_not_allowed")
    max_bytes = int(os.getenv("CHATTERBOX_REF_AUDIO_MAX_BYTES", str(100 * 1024 * 1024)))
    if resolved.stat().st_size > max_bytes:
        raise HTTPException(status_code=422, detail="reference_audio_too_large")
    return resolved


def reference_audio_fingerprint(path: Path, params: dict[str, float | int | bool]) -> dict[str, Any]:
    stat = path.stat()
    material = {
        "path": str(path),
        "mtime_ns": stat.st_mtime_ns,
        "size": stat.st_size,
        "sha256": sha256_file(path),
        "exaggeration": params.get("exaggeration", 0.0),
        "norm_loudness": params.get("norm_loudness", True),
    }
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    material["cache_key"] = hashlib.sha256(encoded).hexdigest()
    return material


def prepare_voice_conditioning(ref_audio: Path | None, params: dict[str, float | int | bool]) -> dict[str, Any]:
    if model is None:
        raise HTTPException(status_code=503, detail="model_not_loaded")
    if ref_audio is None:
        return {
            "reference_audio": None,
            "conditioning_cache_hit": model.conds is not None,
            "conditioning_cache_key": "builtin",
            "conditioning_prepared": False,
        }
    fingerprint = reference_audio_fingerprint(ref_audio, params)
    cache_key = str(fingerprint["cache_key"])
    cached = voice_conditioning_cache.get(cache_key)
    if cached is not None:
        model.conds = cached
        return {
            "reference_audio": str(ref_audio),
            "conditioning_cache_hit": True,
            "conditioning_cache_key": cache_key,
            "conditioning_prepared": False,
            "fingerprint": fingerprint,
        }
    model.prepare_conditionals(
        str(ref_audio),
        exaggeration=float(params.get("exaggeration", 0.0) or 0.0),
        norm_loudness=bool(params.get("norm_loudness", True)),
    )
    voice_conditioning_cache[cache_key] = model.conds
    return {
        "reference_audio": str(ref_audio),
        "conditioning_cache_hit": False,
        "conditioning_cache_key": cache_key,
        "conditioning_prepared": True,
        "fingerprint": fingerprint,
    }


def voice_delivery_for_request(request: SynthesisRequest | SynthesisBatchRequest | TauVoiceRenderRequest) -> dict[str, Any]:
    source_delivery = getattr(request, "voice_delivery", None)
    if not isinstance(source_delivery, dict):
        source_delivery = {}
    requested_tone = getattr(request, "tone", None) or source_delivery.get("tone")
    requested_stage = getattr(request, "delivery_stage", None) or source_delivery.get("delivery_stage")
    tone = normalize_tone(requested_tone)
    requested_tone_token = normalize_voice_token(requested_tone)
    requested_tags = getattr(request, "chatterbox_tags", None) or source_delivery.get("chatterbox_tags") or []
    if isinstance(requested_tags, str):
        requested_tags = [requested_tags]
    if not isinstance(requested_tags, list):
        requested_tags = []
    tag_handling = {
        **CHATTERBOX_TAG_HANDLING,
        "requested_tags": [str(tag) for tag in requested_tags],
    }
    explicit_stage = normalize_delivery_stage(requested_stage)
    stage = effective_delivery_stage(tone=tone, delivery_stage=requested_stage)
    return {
        "schema": "chatterbox.voice_delivery.v1",
        "requested_tone": requested_tone,
        "normalized_tone": tone,
        "tone": tone,
        "tone_was_normalized": bool(requested_tone_token) and requested_tone_token != tone,
        "requested_delivery_stage": requested_stage,
        "delivery_stage": stage,
        "delivery_stage_source": "request.delivery_stage" if explicit_stage else "tone_mapping",
        "ignored_turbo_params": sorted(TURBO_IGNORED_PARAMS),
        "tag_handling": tag_handling,
        "pace": getattr(request, "pace", None) or source_delivery.get("pace"),
        "pause_strategy": getattr(request, "pause_strategy", None) or source_delivery.get("pause_strategy"),
        "wait_activity": source_delivery.get("wait_activity"),
        "source": source_delivery.get("source"),
        "confidence": source_delivery.get("confidence"),
        "evidence": source_delivery.get("evidence"),
    }


def generation_params(request: SynthesisRequest) -> dict[str, float | int | bool]:
    overrides = {
        "temperature": request.temperature,
        "top_p": request.top_p,
        "top_k": request.top_k,
        "repetition_penalty": request.repetition_penalty,
        "norm_loudness": request.norm_loudness,
    }
    return generation_params_for_stage(voice_delivery_for_request(request)["delivery_stage"], overrides=overrides)


def candidate_variants(max_candidates: int) -> list[dict[str, Any]]:
    return ASR_CANDIDATE_VARIANTS[:max_candidates]


def safe_label(value: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in value)[:80]


def synthesize_to_file(request: SynthesisRequest, out_path: Path) -> dict[str, Any]:
    import torchaudio as ta

    if model is None:
        raise HTTPException(status_code=503, detail="model_not_loaded")
    started_total = time.perf_counter()
    events: list[dict[str, Any]] = []
    latency_event(events, "request_received", started_total)
    ref_audio = resolve_reference_audio(request.ref_audio) if request.ref_audio else resolve_reference_audio(DEFAULT_REF_AUDIO)
    try:
        params = generation_params(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    voice_delivery = voice_delivery_for_request(request)
    latency_event(events, "generation_params_ready", started_total)
    started = time.perf_counter()
    try:
        with render_lock:
            conditioning = prepare_voice_conditioning(ref_audio, params)
            latency_event(
                events,
                "voice_conditioning_ready",
                started_total,
                cache_hit=conditioning.get("conditioning_cache_hit"),
                cache_key=conditioning.get("conditioning_cache_key"),
                render_lock="held",
            )
            wav = model.generate(request.text, audio_prompt_path=None, **params)
        generation_seconds = round(time.perf_counter() - started, 3)
        latency_event(events, "first_audio_ready", started_total, generation_seconds=generation_seconds)
        ta.save(str(out_path), wav, model.sr)
        latency_event(events, "audio_saved", started_total)
        os.chmod(out_path, 0o664)
        metrics = audio_metrics(out_path)
        latency_event(events, "audio_metrics_ready", started_total)
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
            "reference_audio": str(ref_audio),
            "voice_conditioning": locals().get("conditioning"),
            "audio": str(out_path),
            "tone": voice_delivery["tone"],
            "requested_tone": voice_delivery["requested_tone"],
            "normalized_tone": voice_delivery["normalized_tone"],
            "delivery_stage": voice_delivery["delivery_stage"],
            "requested_delivery_stage": voice_delivery["requested_delivery_stage"],
            "voice_delivery": voice_delivery,
            "tag_handling": voice_delivery["tag_handling"],
            "generation_params": params,
            "ignored_turbo_params": sorted(TURBO_IGNORED_PARAMS),
            "generation_seconds": generation_seconds,
            "latency_events": events,
            "total_elapsed_ms": round((time.perf_counter() - started_total) * 1000, 3),
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
        "reference_audio": conditioning.get("reference_audio"),
        "voice_conditioning": conditioning,
        "audio": str(out_path),
        "tone": voice_delivery["tone"],
        "requested_tone": voice_delivery["requested_tone"],
        "normalized_tone": voice_delivery["normalized_tone"],
        "delivery_stage": voice_delivery["delivery_stage"],
        "requested_delivery_stage": voice_delivery["requested_delivery_stage"],
        "voice_delivery": voice_delivery,
        "tag_handling": voice_delivery["tag_handling"],
        "generation_params": params,
        "ignored_turbo_params": sorted(TURBO_IGNORED_PARAMS),
        "generation_seconds": generation_seconds,
        "latency_events": events,
        "total_elapsed_ms": round((time.perf_counter() - started_total) * 1000, 3),
        "duration_seconds": duration,
        "realtime_factor": round(generation_seconds / duration, 3) if duration else None,
        "metrics": metrics,
        "failed_gates": failed_gates,
    }


def multipart_form_data(
    *,
    fields: dict[str, str],
    file_field: str,
    file_path: Path,
    content_type: str,
) -> tuple[bytes, str]:
    boundary = f"----chatterbox-{uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
                value.encode("utf-8"),
                b"\r\n",
            ]
        )
    chunks.extend(
        [
            f"--{boundary}\r\n".encode("utf-8"),
            (
                f'Content-Disposition: form-data; name="{file_field}"; '
                f'filename="{file_path.name}"\r\n'
            ).encode("utf-8"),
            f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
            file_path.read_bytes(),
            b"\r\n",
            f"--{boundary}--\r\n".encode("utf-8"),
        ]
    )
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def transcribe_openai_compatible(base_url: str, api_key: str, audio_path: Path) -> str:
    body, content_type = multipart_form_data(
        fields={"model": "whisper-1", "response_format": "json", "language": "en"},
        file_field="file",
        file_path=audio_path,
        content_type="audio/wav",
    )
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/v1/audio/transcriptions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": content_type,
            "Content-Length": str(len(body)),
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        data = json.loads(response.read().decode("utf-8"))
    return str(data.get("text") or "").strip()


def asr_acceptance_for_audio(
    *,
    text: str,
    audio_path: Path,
    duration_seconds: float | None,
    base_url: str,
    api_key: str,
    max_wer: float,
    max_duration_ratio: float,
) -> dict[str, Any]:
    try:
        transcript = transcribe_openai_compatible(base_url, api_key, audio_path)
        gate = acceptance_result(
            expected_text=text,
            transcript=transcript,
            max_wer=max_wer,
            max_duration_ratio=max_duration_ratio,
            duration_seconds=duration_seconds,
        )
        return {
            "ok": gate["ok"],
            "mocked": False,
            "live": True,
            "transcript": transcript,
            "gate": gate,
            "failed_gates": gate["failed_gates"],
        }
    except Exception as exc:  # noqa: BLE001 - receipt captures provider failures
        return {
            "ok": False,
            "mocked": False,
            "live": True,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "failed_gates": ["asr_transcription_ok"],
        }


def synthesis_request_with_overrides(
    base_request: SynthesisRequest,
    *,
    label: str,
    overrides: dict[str, Any],
) -> SynthesisRequest:
    return SynthesisRequest(
        text=base_request.text,
        ref_audio=base_request.ref_audio,
        label=label,
        tone=base_request.tone,
        delivery_stage=base_request.delivery_stage,
        pace=base_request.pace,
        pause_strategy=base_request.pause_strategy,
        temperature=overrides.get("temperature", base_request.temperature),
        top_p=overrides.get("top_p", base_request.top_p),
        top_k=overrides.get("top_k", base_request.top_k),
        repetition_penalty=overrides.get("repetition_penalty", base_request.repetition_penalty),
        norm_loudness=overrides.get("norm_loudness", base_request.norm_loudness),
    )


def accepted_audio_cache_material(
    base_request: SynthesisRequest,
    *,
    ref_audio_path: Path,
    asr_max_wer: float,
    asr_max_duration_ratio: float,
    asr_max_candidates: int,
) -> dict[str, Any]:
    params = generation_params(base_request)
    voice_delivery = voice_delivery_for_request(base_request)
    return {
        "cache_schema_version": CACHE_SCHEMA_VERSION,
        "engine": "chatterbox_turbo",
        "device": DEVICE,
        "text_normalization_version": TEXT_NORMALIZATION_VERSION,
        "asr_acceptance_version": ASR_ACCEPTANCE_VERSION,
        "output_format": {"container": "wav", "sample_rate": 24000, "channels": 1},
        "text_sha256": hashlib.sha256(base_request.text.encode("utf-8")).hexdigest(),
        "text": base_request.text,
        "tone": voice_delivery["tone"],
        "requested_tone": voice_delivery["requested_tone"],
        "normalized_tone": voice_delivery["normalized_tone"],
        "delivery_stage": voice_delivery["delivery_stage"],
        "requested_delivery_stage": voice_delivery["requested_delivery_stage"],
        "voice_delivery": voice_delivery,
        "tag_handling": voice_delivery["tag_handling"],
        "generation_params": params,
        "ignored_turbo_params": sorted(TURBO_IGNORED_PARAMS),
        "reference_audio": reference_audio_fingerprint(ref_audio_path, params),
        "candidate_variants": candidate_variants(asr_max_candidates),
        "asr_max_wer": asr_max_wer,
        "asr_max_duration_ratio": asr_max_duration_ratio,
    }


def accepted_audio_cache_key(material: dict[str, Any]) -> str:
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_accepted_audio_cache(cache_key: str, material: dict[str, Any]) -> dict[str, Any] | None:
    manifest_path = ACCEPTED_CACHE_DIR / cache_key / "manifest.json"
    if not manifest_path.exists():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if manifest.get("cache_schema_version") != CACHE_SCHEMA_VERSION:
        return None
    if manifest.get("cache_key") != cache_key or manifest.get("material") != material:
        return None
    result = manifest.get("accepted_result")
    if not isinstance(result, dict):
        return None
    audio_path = Path(str(result.get("audio")))
    if not audio_path.exists():
        return None
    metrics = audio_metrics(audio_path)
    expected_sha256 = manifest.get("accepted_audio_sha256")
    if expected_sha256 and metrics.get("sha256") != expected_sha256:
        return None
    if int(metrics.get("bytes") or 0) <= 44 or float(metrics.get("duration_seconds") or 0.0) <= 0:
        return None
    asr_gate = ((result.get("asr_verification") or {}).get("accepted_gate") or {})
    if asr_gate and not asr_gate.get("ok", True):
        return None
    cached = dict(result)
    cached["metrics"] = metrics
    cached["duration_seconds"] = float(metrics.get("duration_seconds") or 0.0)
    cached["ok"] = True
    cached["failed_gates"] = []
    asr = dict(cached.get("asr_verification") or {})
    asr.update(
        {
            "enabled": True,
            "ok": True,
            "cache_hit": True,
            "cache_key": cache_key,
            "manifest": str(manifest_path),
            "failed_gates": [],
        }
    )
    cached["asr_verification"] = asr
    cached["cache"] = {
        "hit": True,
        "cache_key": cache_key,
        "manifest": str(manifest_path),
        "audio": str(audio_path),
    }
    return cached


def save_accepted_audio_cache(
    *,
    cache_key: str,
    material: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    cache_dir = ACCEPTED_CACHE_DIR / cache_key
    cache_dir.mkdir(parents=True, exist_ok=True)
    source_audio = Path(str(result["audio"]))
    cached_audio = cache_dir / "accepted.wav"
    tmp_audio = cache_dir / f".accepted.{uuid4().hex}.tmp.wav"
    tmp_manifest = cache_dir / f".manifest.{uuid4().hex}.tmp.json"
    shutil.copy2(source_audio, tmp_audio)
    os.replace(tmp_audio, cached_audio)
    os.chmod(cached_audio, 0o664)
    cached = dict(result)
    cached["audio"] = str(cached_audio)
    cached["metrics"] = audio_metrics(cached_audio)
    cached["duration_seconds"] = float(cached["metrics"].get("duration_seconds") or 0.0)
    asr = dict(cached.get("asr_verification") or {})
    asr.update(
        {
            "cache_hit": False,
            "cache_key": cache_key,
            "manifest": str(cache_dir / "manifest.json"),
        }
    )
    cached["asr_verification"] = asr
    cached["cache"] = {
        "hit": False,
        "cache_key": cache_key,
        "manifest": str(cache_dir / "manifest.json"),
        "audio": str(cached_audio),
    }
    manifest = {
        "ok": True,
        "mocked": False,
        "live": True,
        "cache_schema_version": CACHE_SCHEMA_VERSION,
        "cache_key": cache_key,
        "material": material,
        "accepted_result": cached,
        "accepted_audio_sha256": cached["metrics"].get("sha256"),
        "accepted_audio_bytes": cached["metrics"].get("bytes"),
        "accepted_audio_duration_seconds": cached["metrics"].get("duration_seconds"),
        "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    tmp_manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp_manifest, cache_dir / "manifest.json")
    os.chmod(cache_dir / "manifest.json", 0o664)
    return cached


def synthesize_asr_accepted_to_file(
    base_request: SynthesisRequest,
    *,
    out_dir: Path,
    base_filename: str,
    asr_base_url: str,
    asr_api_key: str,
    asr_max_wer: float,
    asr_max_duration_ratio: float,
    asr_max_candidates: int,
    use_cache: bool = True,
) -> dict[str, Any]:
    ref_audio_path = resolve_reference_audio(base_request.ref_audio) if base_request.ref_audio else resolve_reference_audio(DEFAULT_REF_AUDIO)
    cache_material = accepted_audio_cache_material(
        base_request,
        ref_audio_path=ref_audio_path,
        asr_max_wer=asr_max_wer,
        asr_max_duration_ratio=asr_max_duration_ratio,
        asr_max_candidates=asr_max_candidates,
    )
    cache_key = accepted_audio_cache_key(cache_material)
    if use_cache:
        cached = load_accepted_audio_cache(cache_key, cache_material)
        if cached is not None:
            return cached

    candidates: list[dict[str, Any]] = []
    for candidate_index, variant in enumerate(candidate_variants(asr_max_candidates), start=1):
        candidate_request = synthesis_request_with_overrides(
            base_request,
            label=f"{base_request.label}_{candidate_index:02d}_{variant['name']}",
            overrides=variant["overrides"],
        )
        out_path = out_dir / f"{base_filename}_candidate_{candidate_index:02d}_{variant['name']}.wav"
        result = synthesize_to_file(candidate_request, out_path)
        audio_path = Path(str(result.get("audio")))
        candidate: dict[str, Any] = {
            "candidate_index": candidate_index,
            "variant": variant["name"],
            "overrides": variant["overrides"],
            "synthesis": result,
            "audio_exists_for_asr": audio_path.exists(),
        }
        if result.get("ok") and audio_path.exists():
            asr = asr_acceptance_for_audio(
                text=base_request.text,
                audio_path=audio_path,
                duration_seconds=result.get("duration_seconds"),
                base_url=asr_base_url,
                api_key=asr_api_key,
                max_wer=asr_max_wer,
                max_duration_ratio=asr_max_duration_ratio,
            )
            candidate["asr"] = asr
            candidate["ok"] = asr["ok"]
            candidate["failed_gates"] = asr["failed_gates"]
        else:
            candidate["ok"] = False
            candidate["failed_gates"] = ["synthesis_ok" if not result.get("ok") else "audio_exists_for_asr"]
        candidates.append(candidate)
        if candidate["ok"]:
            accepted = dict(result)
            accepted.update(
                {
                    "asr_verification": {
                        "enabled": True,
                        "ok": True,
                        "candidate_count": len(candidates),
                        "accepted_candidate_index": candidate_index,
                        "accepted_variant": variant["name"],
                        "accepted_gate": candidate.get("asr", {}).get("gate"),
                        "max_wer": asr_max_wer,
                        "max_duration_ratio": asr_max_duration_ratio,
                        "candidates": candidates,
                        "failed_gates": [],
                    }
                }
            )
            if use_cache:
                return save_accepted_audio_cache(cache_key=cache_key, material=cache_material, result=accepted)
            accepted["cache"] = {"hit": False, "disabled": True, "cache_key": cache_key}
            return accepted

    return {
        "ok": False,
        "mocked": False,
        "live": True,
        "engine": "chatterbox_turbo",
        "text": base_request.text,
        "text_sha256": hashlib.sha256(base_request.text.encode("utf-8")).hexdigest(),
        "delivery_stage": base_request.delivery_stage,
        "audio": str(out_dir / f"{base_filename}_rejected.wav"),
        "asr_verification": {
            "enabled": True,
            "ok": False,
            "candidate_count": len(candidates),
            "accepted_candidate_index": None,
            "max_wer": asr_max_wer,
            "max_duration_ratio": asr_max_duration_ratio,
            "candidates": candidates,
            "failed_gates": ["accepted_candidate_present"],
        },
        "failed_gates": ["accepted_candidate_present"],
    }


def append_with_crossfade(tensors: list[Any], next_wav: Any, *, sample_rate: int, crossfade_ms: int) -> None:
    import torch

    if not tensors or crossfade_ms <= 0:
        tensors.append(next_wav)
        return
    previous = tensors[-1]
    fade_len = min(int(sample_rate * (crossfade_ms / 1000)), previous.shape[1], next_wav.shape[1])
    if fade_len <= 0 or previous.shape[0] != next_wav.shape[0]:
        tensors.append(next_wav)
        return
    fade_out = torch.linspace(1.0, 0.0, fade_len, dtype=previous.dtype).reshape(1, -1)
    fade_in = torch.linspace(0.0, 1.0, fade_len, dtype=next_wav.dtype).reshape(1, -1)
    crossfaded = previous[:, -fade_len:] * fade_out + next_wav[:, :fade_len] * fade_in
    tensors[-1] = torch.cat([previous[:, :-fade_len], crossfaded], dim=1)
    tensors.append(next_wav[:, fade_len:])


def combine_audio_segments(
    segments: list[dict[str, Any]],
    out_path: Path,
    *,
    crossfade_ms: int = 20,
) -> dict[str, Any]:
    import torch
    import torchaudio as ta

    tensors = []
    sample_rate = None
    for segment in segments:
        audio_path = Path(segment["audio"])
        wav, sr = ta.load(str(audio_path))
        if sample_rate is None:
            sample_rate = sr
        if sr != sample_rate:
            raise HTTPException(status_code=500, detail=f"sample_rate_mismatch:{audio_path}")
        append_with_crossfade(tensors, wav, sample_rate=sr, crossfade_ms=crossfade_ms)
        pause_ms = int(segment.get("pause_after_ms") or 0)
        if pause_ms > 0:
            silence_len = int(sr * (pause_ms / 1000))
            tensors.append(torch.zeros((wav.shape[0], silence_len), dtype=wav.dtype))
    if not tensors or sample_rate is None:
        raise HTTPException(status_code=500, detail="no_audio_segments_to_combine")
    combined = torch.cat(tensors, dim=1)
    ta.save(str(out_path), combined, sample_rate)
    os.chmod(out_path, 0o664)
    return audio_metrics(out_path)


def blessed_qra_cache_disabled_receipt() -> dict[str, Any]:
    return {
        "enabled": False,
        "hit": False,
        "reason": "request_disabled",
        "schema_version": BLESSED_QRA_SCHEMA_VERSION,
        "failed_gates": [],
    }


def synthesis_batch_request_from_tau_voice_render(request: TauVoiceRenderRequest) -> tuple[SynthesisBatchRequest, dict[str, Any]]:
    failed_gates: list[str] = []
    if request.schema != "tau.voice_render_request.v1":
        failed_gates.append("tau_voice_render_schema")
    if request.question_text and request.question_text_sha256 and sha256_text(request.question_text) != request.question_text_sha256:
        failed_gates.append("question_text_sha256_matches")
    answerability_decision = request.answerability_decision or {}
    if answerability_decision.get("decision") == "block_before_speech":
        failed_gates.append("answerability_blocks_speech")
    if answerability_decision.get("failed_gates") and answerability_decision.get("decision") != "answerable":
        failed_gates.append("answerability_failed_gates_present")

    chunk_texts: list[str] = []
    delivery_stages: list[str] = []
    tones: list[str] = []
    requested_max_chars: list[int] = []
    chunk_receipts: list[dict[str, Any]] = []
    for index, chunk in enumerate(request.speakable_chunks, start=1):
        text = chunk.text.strip()
        actual_sha = sha256_text(text)
        if chunk.text_sha256 and chunk.text_sha256 != actual_sha:
            failed_gates.append(f"chunk_{index}_text_sha256_matches")
        if len(text) > 300:
            failed_gates.append(f"chunk_{index}_text_len_lte_300")
        chunk_texts.append(text)
        if chunk.delivery_stage:
            delivery_stages.append(chunk.delivery_stage)
        if chunk.tone:
            tones.append(chunk.tone)
        if chunk.max_chars:
            requested_max_chars.append(chunk.max_chars)
        chunk_receipts.append(
            {
                "chunk_id": chunk.chunk_id or f"{request.turn_id}-chunk-{index}",
                "index": index,
                "text_sha256": actual_sha,
                "declared_text_sha256": chunk.text_sha256,
                "tone": normalize_tone(chunk.tone or request.tone or request.voice_delivery.get("tone")),
                "requested_tone": chunk.tone or request.tone or request.voice_delivery.get("tone"),
                "normalized_tone": normalize_tone(chunk.tone or request.tone or request.voice_delivery.get("tone")),
                "delivery_stage": chunk.delivery_stage or request.delivery_stage or "neutral",
                "pace": chunk.pace or request.pace or request.voice_delivery.get("pace"),
                "pause_strategy": chunk.pause_strategy or request.pause_strategy or request.voice_delivery.get("pause_strategy"),
                "pause_after_ms": chunk.pause_after_ms,
                "interruptible": chunk.interruptible,
                "char_len": len(text),
            }
        )

    answer_text = " ".join(chunk_texts).strip()
    if not answer_text:
        failed_gates.append("speakable_chunks_text_present")

    max_chars = min(requested_max_chars) if requested_max_chars else 300
    max_chars = max(80, min(max_chars, 300))
    pause_values = [chunk.pause_after_ms for chunk in request.speakable_chunks if chunk.pause_after_ms is not None]
    pause_after_ms = int(pause_values[0]) if pause_values else 250
    tau_voice_delivery = voice_delivery_for_request(request)
    delivery_stage = delivery_stages[0] if delivery_stages else tau_voice_delivery["delivery_stage"]
    tone = tones[0] if tones else tau_voice_delivery["tone"]
    label = request.label or f"tau_{safe_label(request.conversation_id)}_{safe_label(request.turn_id)}"

    batch_request = SynthesisBatchRequest(
        answer_text=answer_text or " ",
        max_chars=max_chars,
        pause_after_ms=pause_after_ms,
        completion_cue=request.completion_cue,
        turn_id=request.turn_id,
        question_text=request.question_text,
        use_blessed_qra_cache=request.use_blessed_qra_cache,
        blessed_qra_min_similarity=request.blessed_qra_min_similarity,
        blessed_qra_variant=request.blessed_qra_variant,
        blessed_qra_preserve_pauses=request.blessed_qra_preserve_pauses,
        require_blessed_qra_memory_gate=request.require_blessed_qra_memory_gate,
        blessed_qra_memory_key=request.blessed_qra_memory_key,
        blessed_qra_memory_similarity=request.blessed_qra_memory_similarity,
        blessed_qra_memory_review_status=request.blessed_qra_memory_review_status,
        tone=tone,
        delivery_stage=delivery_stage,
        pace=tau_voice_delivery.get("pace"),
        pause_strategy=tau_voice_delivery.get("pause_strategy"),
        voice_delivery=tau_voice_delivery,
        delivery_arc=[
            {
                "stage": effective_delivery_stage(
                    tone=chunk.tone or request.tone or request.voice_delivery.get("tone"),
                    delivery_stage=chunk.delivery_stage,
                ),
                "tone": chunk.tone or request.tone or request.voice_delivery.get("tone") or "neutral_warm",
                "role": f"tau_chunk_{index}",
            }
            for index, chunk in enumerate(request.speakable_chunks, 1)
        ],
        label=label,
        include_completion_cue=request.include_completion_cue,
        crossfade_ms=request.crossfade_ms,
        asr_verify=request.asr_verify,
    )
    receipt = {
        "schema": request.schema,
        "ok": not failed_gates,
        "conversation_id": request.conversation_id,
        "turn_id": request.turn_id,
        "route": request.route,
        "active_domain_persona": request.active_domain_persona,
        "question_text_sha256": sha256_text(request.question_text or ""),
        "declared_question_text_sha256": request.question_text_sha256,
        "answer_text_sha256": sha256_text(answer_text),
        "source_chunk_count": len(request.speakable_chunks),
        "source_chunks": chunk_receipts,
        "memory_route_decision": request.memory_route_decision,
        "answerability_decision": answerability_decision,
        "voice_delivery": tau_voice_delivery,
        "turn_control_policy": model_to_dict(request.turn_control_policy),
        "external_evidence": request.external_evidence,
        "receipt_root": request.receipt_root,
        "mapped_batch": {
            "answer_text_sha256": sha256_text(answer_text),
            "max_chars": batch_request.max_chars,
            "pause_after_ms": batch_request.pause_after_ms,
            "tone": batch_request.tone,
            "delivery_stage": delivery_stage,
            "pace": batch_request.pace,
            "pause_strategy": batch_request.pause_strategy,
            "turn_id": batch_request.turn_id,
            "use_blessed_qra_cache": batch_request.use_blessed_qra_cache,
            "blessed_qra_variant": batch_request.blessed_qra_variant,
            "require_blessed_qra_memory_gate": batch_request.require_blessed_qra_memory_gate,
            "asr_verify": batch_request.asr_verify,
        },
        "failed_gates": failed_gates,
    }
    return batch_request, receipt


def apply_blessed_qra_memory_gate(request: SynthesisBatchRequest, match: dict[str, Any]) -> dict[str, Any]:
    if not match.get("hit"):
        return match
    if not request.require_blessed_qra_memory_gate:
        gated = dict(match)
        gated["memory_gate"] = {
            "required": False,
            "passed": True,
            "reason": "request_disabled_memory_gate",
        }
        return gated

    failed_gates = []
    review_status = (request.blessed_qra_memory_review_status or "").lower()
    memory_key = request.blessed_qra_memory_key
    memory_similarity = request.blessed_qra_memory_similarity
    allowed_keys = {str(match.get("entry_id"))}
    for key in match.get("memory_keys") or []:
        allowed_keys.add(str(key))
    if review_status not in {"approved", "blessed", "verified"}:
        failed_gates.append("memory_review_status_approved")
    if not memory_key or str(memory_key) not in allowed_keys:
        failed_gates.append("memory_key_matches_blessed_qra")
    if memory_similarity is None or float(memory_similarity) < request.blessed_qra_min_similarity:
        failed_gates.append("memory_similarity_near_exact")

    gated = dict(match)
    gated["memory_gate"] = {
        "required": True,
        "passed": not failed_gates,
        "memory_key": memory_key,
        "allowed_keys": sorted(allowed_keys),
        "memory_similarity": memory_similarity,
        "min_similarity": request.blessed_qra_min_similarity,
        "review_status": request.blessed_qra_memory_review_status,
        "failed_gates": failed_gates,
    }
    if failed_gates:
        gated.update(
            {
                "hit": False,
                "reason": "memory_gate_failed",
                "failed_gates": failed_gates,
            }
        )
    return gated


def blessed_qra_batch_response(
    request: SynthesisBatchRequest,
    *,
    match: dict[str, Any],
    batch_label: str,
    batch_dir: Path,
    started_total: float,
    batch_events: list[dict[str, Any]],
) -> dict[str, Any]:
    voice_delivery = voice_delivery_for_request(request)
    plan = build_render_plan(
        match["answer_text"],
        max_chars=request.max_chars,
        pause_after_ms=0,
        completion_cue=None,
    )
    chunk_results = []
    for index, chunk in enumerate(match["chunks"], start=1):
        metrics = dict(chunk.get("metrics") or audio_metrics(Path(str(chunk["audio"]))))
        pause_after_ms = int(chunk.get("pause_after_ms") or 0) if request.blessed_qra_preserve_pauses else 0
        chunk_results.append(
            {
                "ok": True,
                "mocked": False,
                "live": True,
                "engine": "chatterbox_turbo",
                "phase": "answer_chunk",
                "source": "blessed_qra_cache",
                "text": chunk["text"],
                "text_sha256": hashlib.sha256(str(chunk["text"]).encode("utf-8")).hexdigest(),
                "audio": chunk["audio"],
                "metrics": metrics,
                "duration_seconds": float(metrics.get("duration_seconds") or 0.0),
                "tone": voice_delivery["tone"],
                "requested_tone": voice_delivery["requested_tone"],
                "normalized_tone": voice_delivery["normalized_tone"],
                "delivery_stage": chunk.get("delivery_stage") or "neutral",
                "requested_delivery_stage": voice_delivery["requested_delivery_stage"],
                "voice_delivery": {
                    **voice_delivery,
                    "delivery_stage": chunk.get("delivery_stage") or voice_delivery["delivery_stage"],
                    "delivery_stage_source": "blessed_qra_cache.chunk",
                },
                "chunk_index": index,
                "chunk_total": len(match["chunks"]),
                "pause_after_ms": pause_after_ms,
                "can_interrupt_after": True,
                "cache": {
                    "hit": True,
                    "kind": "blessed_qra_audio",
                    "entry_id": match.get("entry_id"),
                    "variant_id": match.get("variant_id"),
                    "ledger": (match.get("ledger") or {}).get("path"),
                },
                "asr_verification": {
                    "enabled": True,
                    "ok": True,
                    "source": "blessed_qra_cache",
                    "cache_hit": True,
                    "failed_gates": [],
                },
                "failed_gates": [],
                "ignored_turbo_params": sorted(TURBO_IGNORED_PARAMS),
            }
        )
    segments = [{"audio": item["audio"], "pause_after_ms": item.get("pause_after_ms", 0)} for item in chunk_results]
    finished_audio = batch_dir / "finished_response.wav"
    finished_metrics = combine_audio_segments(segments, finished_audio, crossfade_ms=request.crossfade_ms)
    latency_event(batch_events, "blessed_qra_cache_hit", started_total, entry_id=match.get("entry_id"), similarity=match.get("similarity"))
    latency_event(batch_events, "finished_audio_ready", started_total, bytes=finished_metrics.get("bytes"))
    return {
        "ok": True,
        "mocked": False,
        "live": True,
        "engine": "chatterbox_turbo",
        "batch_label": batch_label,
        "tone": voice_delivery["tone"],
        "requested_tone": voice_delivery["requested_tone"],
        "normalized_tone": voice_delivery["normalized_tone"],
        "delivery_stage": voice_delivery["delivery_stage"],
        "requested_delivery_stage": voice_delivery["requested_delivery_stage"],
        "voice_delivery": voice_delivery,
        "tag_handling": voice_delivery["tag_handling"],
        "ignored_turbo_params": sorted(TURBO_IGNORED_PARAMS),
        "cache_key": f"blessed_qra:{match.get('entry_id')}",
        "cache_material": {
            "schema_version": BLESSED_QRA_SCHEMA_VERSION,
            "entry_id": match.get("entry_id"),
            "variant_id": match.get("variant_id"),
            "variant_name": match.get("variant_name"),
            "variant_count": match.get("variant_count"),
            "answer_text_sha256": match.get("answer_text_sha256"),
            "question_text": match.get("question_text"),
            "matched_question": match.get("matched_question"),
            "similarity": match.get("similarity"),
        },
        "answer_text_sha256": match["answer_text_sha256"],
        "render_plan": {
            **plan,
            "source": "blessed_qra_cache",
            "cached_chunk_count": len(match["chunks"]),
        },
        "chunks": chunk_results,
        "completion_cue": None,
        "finished_response_audio": str(finished_audio),
        "finished_response_metrics": finished_metrics,
        "crossfade_ms": request.crossfade_ms,
        "asr_verification": {
            "enabled": True,
            "ok": True,
            "source": "blessed_qra_cache",
            "failed_gates": [],
        },
        "blessed_qra_cache": match,
        "latency_events": batch_events,
        "total_elapsed_ms": round((time.perf_counter() - started_total) * 1000, 3),
        "failed_gates": [],
    }


def cache_key_for_batch(
    plan: dict[str, Any],
    *,
    ref_audio: str | None,
    asr_verify: bool = False,
    voice_delivery: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    material = {
        "engine": "chatterbox_turbo",
        "voice_delivery": voice_delivery,
        "answer_text_sha256": plan["answer_text_sha256"],
        "completion_cue_sha256": plan.get("completion_cue_sha256"),
        "chunk_text_sha256": [chunk["text_sha256"] for chunk in plan["chunks"]],
        "delivery_stages": [chunk["delivery_stage"] for chunk in plan["chunks"]],
        "max_chars": plan["max_chars"],
        "ref_audio": ref_audio,
        "stage_presets": {
            chunk["delivery_stage"]: generation_params_for_stage(chunk["delivery_stage"])
            for chunk in plan["chunks"]
        },
        "asr_verify": asr_verify,
    }
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest(), material


def mark_turn_control(turn_id: str, action: str, request: TurnControlRequest) -> dict[str, Any]:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    state = turn_controls.setdefault(turn_id, {"turn_id": turn_id, "events": []})
    event = {
        "action": action,
        "reason": request.reason,
        "old_turn_id": request.old_turn_id,
        "new_turn_id": request.new_turn_id,
        "timestamp": now,
    }
    state["events"].append(event)
    state["last_action"] = action
    state["updated_at"] = now
    if action == "cancel":
        state["cancelled"] = True
        state["stale_chunks_should_skip"] = True
    if action == "duck":
        state["ducked"] = True
    if action == "stop":
        state["stopped"] = True
    return {
        "ok": True,
        "mocked": False,
        "live": True,
        "turn_id": turn_id,
        "control": state,
    }


def stream_turn_should_stop(turn_id: str | None) -> bool:
    if not turn_id:
        return False
    state = turn_controls.get(turn_id)
    return bool(state and (state.get("cancelled") or state.get("stopped")))


@app.on_event("startup")
def load_model() -> None:
    global model, model_load_seconds
    from chatterbox.tts_turbo import ChatterboxTurboTTS

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    model = ChatterboxTurboTTS.from_pretrained(device=DEVICE)
    model_load_seconds = round(time.perf_counter() - started, 3)


@app.get("/health")
def health() -> dict[str, Any]:
    try:
        import torch

        torch_info = {
            "version": torch.__version__,
            "cuda_available": torch.cuda.is_available(),
            "cuda_version": torch.version.cuda,
            "device_count": torch.cuda.device_count(),
            "device_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        }
    except Exception as exc:  # noqa: BLE001 - health should report import failures as data
        torch_info = {
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
    return {
        "ok": model is not None,
        "mocked": False,
        "live": True,
        "started_at_utc": started_at_utc,
        "engine": "chatterbox_turbo",
        "device": DEVICE,
        "model_loaded": model is not None,
        "model_load_seconds": model_load_seconds,
        "voice_conditioning_cache_size": len(voice_conditioning_cache),
        "reference_audio_roots": [str(root) for root in REFERENCE_AUDIO_ROOTS],
        "supported_params": sorted(TURBO_SUPPORTED_PARAMS),
        "ignored_turbo_params": sorted(TURBO_IGNORED_PARAMS),
        "tag_handling": CHATTERBOX_TAG_HANDLING,
        "torch": torch_info,
        "nvidia_smi": run_cmd(["nvidia-smi", "--query-gpu=name,memory.total,memory.used,memory.free,driver_version", "--format=csv,noheader"]),
    }


@app.get("/presets")
def presets() -> dict[str, Any]:
    return {
        "ok": True,
        "engine": "chatterbox_turbo",
        "supported_params": sorted(TURBO_SUPPORTED_PARAMS),
        "ignored_turbo_params": sorted(TURBO_IGNORED_PARAMS),
        "tag_handling": CHATTERBOX_TAG_HANDLING,
        "allowed_tones": sorted(ALLOWED_TONES),
        "tone_to_delivery_stage": TONE_TO_DELIVERY_STAGE,
        "delivery_stage_aliases": DELIVERY_STAGE_ALIASES,
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
    label = request.label or f"sample-{uuid4().hex[:8]}"
    out_path = OUT_DIR / f"{safe_label(label)}.wav"
    return synthesize_to_file(request, out_path)


@app.post("/synthesize-batch")
def synthesize_batch(request: SynthesisBatchRequest) -> dict[str, Any]:
    started_total = time.perf_counter()
    batch_events: list[dict[str, Any]] = []
    latency_event(batch_events, "batch_received", started_total)
    batch_label = safe_label(request.label or f"batch-{uuid4().hex[:8]}")
    batch_dir = OUT_DIR / batch_label
    batch_dir.mkdir(parents=True, exist_ok=True)
    batch_voice_delivery = voice_delivery_for_request(request)
    latency_event(batch_events, "batch_dir_ready", started_total)
    blessed_qra_lookup = (
        apply_blessed_qra_memory_gate(
            request,
            find_blessed_qra_match(
                request.question_text,
                min_similarity=request.blessed_qra_min_similarity,
                preferred_variant=request.blessed_qra_variant,
            ),
        )
        if request.use_blessed_qra_cache
        else blessed_qra_cache_disabled_receipt()
    )
    latency_event(
        batch_events,
        "blessed_qra_lookup_done",
        started_total,
        enabled=blessed_qra_lookup.get("enabled"),
        hit=blessed_qra_lookup.get("hit"),
        reason=blessed_qra_lookup.get("reason"),
    )
    if blessed_qra_lookup.get("hit"):
        return blessed_qra_batch_response(
            request,
            match=blessed_qra_lookup,
            batch_label=batch_label,
            batch_dir=batch_dir,
            started_total=started_total,
            batch_events=batch_events,
        )
    plan = build_render_plan(
        request.answer_text,
        max_chars=request.max_chars,
        pause_after_ms=request.pause_after_ms,
        completion_cue=request.completion_cue,
        arc=request.delivery_arc,
    )
    latency_event(batch_events, "render_plan_ready", started_total, chunk_count=plan["chunk_count"])
    ref_audio_path = resolve_reference_audio(request.ref_audio) if request.ref_audio else resolve_reference_audio(DEFAULT_REF_AUDIO)
    ref_audio = str(ref_audio_path)
    cache_key, cache_material = cache_key_for_batch(
        plan,
        ref_audio=ref_audio,
        asr_verify=request.asr_verify,
        voice_delivery=batch_voice_delivery,
    )
    chunk_results: list[dict[str, Any]] = []
    failed_gates: list[str] = []
    asr_api_key = os.getenv(ASR_API_KEY_ENV) if request.asr_verify else None
    asr_receipt = {
        "enabled": request.asr_verify,
        "openai_base_url": DEFAULT_ASR_OPENAI_BASE_URL if request.asr_verify else None,
        "api_key_env": ASR_API_KEY_ENV if request.asr_verify else None,
        "request_overrides_allowed": False,
        "api_key_available": bool(asr_api_key) if request.asr_verify else None,
        "max_wer": request.asr_max_wer if request.asr_verify else None,
        "max_duration_ratio": request.asr_max_duration_ratio if request.asr_verify else None,
        "max_candidates": request.asr_max_candidates if request.asr_verify else None,
        "cache_enabled": request.asr_cache if request.asr_verify else None,
        "failed_gates": [],
    }
    if request.asr_verify and not asr_api_key:
        failed_gates.append("asr_api_key_available")
        asr_receipt["failed_gates"].append("asr_api_key_available")
    for chunk in plan["chunks"]:
        chunk_request = SynthesisRequest(
            text=chunk["text"],
            ref_audio=request.ref_audio,
            label=f"{batch_label}_chunk_{chunk['index']:02d}",
            tone=request.tone,
            delivery_stage=chunk["delivery_stage"],
            pace=request.pace,
            pause_strategy=request.pause_strategy,
            voice_delivery={**batch_voice_delivery, "delivery_stage": chunk["delivery_stage"]},
        )
        base_filename = f"chunk_{chunk['index']:02d}_{chunk['delivery_stage']}"
        out_path = batch_dir / f"{base_filename}.wav"
        if request.asr_verify and asr_api_key:
            result = synthesize_asr_accepted_to_file(
                chunk_request,
                out_dir=batch_dir,
                base_filename=base_filename,
                asr_base_url=DEFAULT_ASR_OPENAI_BASE_URL,
                asr_api_key=asr_api_key,
                asr_max_wer=request.asr_max_wer,
                asr_max_duration_ratio=request.asr_max_duration_ratio,
                asr_max_candidates=request.asr_max_candidates,
                use_cache=request.asr_cache,
            )
        else:
            result = synthesize_to_file(chunk_request, out_path)
        latency_event(
            batch_events,
            "chunk_done",
            started_total,
            chunk_index=chunk["index"],
            ok=result.get("ok"),
            asr_verified=bool(result.get("asr_verification", {}).get("ok")),
        )
        result.update(
            {
                "phase": "answer_chunk",
                "chunk_index": chunk["index"],
                "chunk_total": chunk["total"],
                "pause_after_ms": chunk["pause_after_ms"],
                "can_interrupt_after": chunk["can_interrupt_after"],
            }
        )
        if not result.get("ok"):
            failed_gates.append(f"chunk_{chunk['index']}_synthesis_ok")
        if request.asr_verify and result.get("asr_verification", {}).get("failed_gates"):
            failed_gates.extend(
                f"chunk_{chunk['index']}_asr_{gate}"
                for gate in result["asr_verification"]["failed_gates"]
            )
        chunk_results.append(result)

    completion_result = None
    if request.include_completion_cue and request.completion_cue:
        completion_request = SynthesisRequest(
            text=request.completion_cue,
            ref_audio=request.ref_audio,
            label=f"{batch_label}_response_complete",
            tone=request.tone,
            delivery_stage="closing",
            pace=request.pace,
            pause_strategy=request.pause_strategy,
            voice_delivery={**batch_voice_delivery, "delivery_stage": "closing"},
        )
        if request.asr_verify and asr_api_key:
            completion_result = synthesize_asr_accepted_to_file(
                completion_request,
                out_dir=batch_dir,
                base_filename="response_complete",
                asr_base_url=DEFAULT_ASR_OPENAI_BASE_URL,
                asr_api_key=asr_api_key,
                asr_max_wer=request.asr_max_wer,
                asr_max_duration_ratio=request.asr_max_duration_ratio,
                asr_max_candidates=request.asr_max_candidates,
                use_cache=request.asr_cache,
            )
        else:
            completion_result = synthesize_to_file(completion_request, batch_dir / "response_complete.wav")
        completion_result.update(
            {
                "phase": "response_complete",
                "pause_after_ms": 0,
                "separate_from_answer_text": True,
            }
        )
        if not completion_result.get("ok"):
            failed_gates.append("completion_cue_synthesis_ok")
        if request.asr_verify and completion_result.get("asr_verification", {}).get("failed_gates"):
            failed_gates.extend(
                f"completion_cue_asr_{gate}" for gate in completion_result["asr_verification"]["failed_gates"]
            )
        latency_event(batch_events, "completion_cue_done", started_total, ok=completion_result.get("ok"))

    segments = [
        {
            "audio": item["audio"],
            "pause_after_ms": item.get("pause_after_ms", 0),
        }
        for item in chunk_results
        if item.get("ok")
    ]
    if completion_result and completion_result.get("ok"):
        segments.append({"audio": completion_result["audio"], "pause_after_ms": 0})
    finished_audio = batch_dir / "finished_response.wav"
    finished_metrics = combine_audio_segments(segments, finished_audio, crossfade_ms=request.crossfade_ms) if segments else {}
    latency_event(batch_events, "finished_audio_ready", started_total, bytes=finished_metrics.get("bytes"))
    if not finished_metrics or int(finished_metrics.get("bytes") or 0) <= 44:
        failed_gates.append("finished_response_audio_non_empty")

    return {
        "ok": not failed_gates,
        "mocked": False,
        "live": True,
        "engine": "chatterbox_turbo",
        "batch_label": batch_label,
        "tone": batch_voice_delivery["tone"],
        "requested_tone": batch_voice_delivery["requested_tone"],
        "normalized_tone": batch_voice_delivery["normalized_tone"],
        "delivery_stage": batch_voice_delivery["delivery_stage"],
        "requested_delivery_stage": batch_voice_delivery["requested_delivery_stage"],
        "voice_delivery": batch_voice_delivery,
        "tag_handling": batch_voice_delivery["tag_handling"],
        "ignored_turbo_params": sorted(TURBO_IGNORED_PARAMS),
        "cache_key": cache_key,
        "cache_material": cache_material,
        "answer_text_sha256": plan["answer_text_sha256"],
        "render_plan": plan,
        "chunks": chunk_results,
        "completion_cue": completion_result,
        "finished_response_audio": str(finished_audio),
        "finished_response_metrics": finished_metrics,
        "crossfade_ms": request.crossfade_ms,
        "asr_verification": asr_receipt,
        "blessed_qra_cache": blessed_qra_lookup,
        "latency_events": batch_events,
        "total_elapsed_ms": round((time.perf_counter() - started_total) * 1000, 3),
        "failed_gates": failed_gates,
    }


@app.post("/tau/voice-render")
def tau_voice_render(request: TauVoiceRenderRequest) -> dict[str, Any]:
    batch_request, tau_receipt = synthesis_batch_request_from_tau_voice_render(request)
    if tau_receipt["failed_gates"]:
        return {
            "ok": False,
            "mocked": False,
            "live": False,
            "engine": "chatterbox_turbo",
            "source": "tau_voice_render_request",
            "tau_voice_render_request": tau_receipt,
            "failed_gates": [f"tau_voice_render:{gate}" for gate in tau_receipt["failed_gates"]],
        }

    batch = synthesize_batch(batch_request)
    failed_gates = list(batch.get("failed_gates") or [])
    return {
        **batch,
        "source": "tau_voice_render_request",
        "tau_voice_render_request": tau_receipt,
        "ok": bool(batch.get("ok")) and not failed_gates,
        "failed_gates": failed_gates,
    }


@app.post("/synthesize-batch-stream")
def synthesize_batch_stream(request: SynthesisBatchRequest) -> StreamingResponse:
    """Chunk-level PCM streaming response.

    This is chunk streaming, not token-level model streaming: each planned chunk
    is synthesized and yielded as signed 16-bit little-endian PCM. Receipts
    remain available through /synthesize-batch for deterministic verification.
    """
    request.stream = True

    def pcm_bytes(wav: Any) -> bytes:
        import torch

        clipped = torch.clamp(wav, -1.0, 1.0)
        pcm = (clipped * 32767.0).to(torch.int16).contiguous()
        return pcm.squeeze(0).cpu().numpy().tobytes()

    def stop_if_turn_controlled() -> bool:
        return stream_turn_should_stop(request.turn_id)

    def guarded_pcm_chunks(wav: Any, block_size: int = 65536):
        data = pcm_bytes(wav)
        for offset in range(0, len(data), block_size):
            if stop_if_turn_controlled():
                return
            yield data[offset : offset + block_size]

    def iter_audio():
        import torch
        import torchaudio as ta

        batch_label = safe_label(request.label or f"stream-{uuid4().hex[:8]}")
        batch_dir = OUT_DIR / batch_label
        batch_dir.mkdir(parents=True, exist_ok=True)
        blessed_qra_lookup = (
            apply_blessed_qra_memory_gate(
                request,
                find_blessed_qra_match(
                    request.question_text,
                    min_similarity=request.blessed_qra_min_similarity,
                    preferred_variant=request.blessed_qra_variant,
                ),
            )
            if request.use_blessed_qra_cache
            else blessed_qra_cache_disabled_receipt()
        )
        if blessed_qra_lookup.get("hit"):
            for chunk in blessed_qra_lookup["chunks"]:
                if stop_if_turn_controlled():
                    return
                wav, sr = ta.load(str(chunk["audio"]))
                yield from guarded_pcm_chunks(wav)
                pause_ms = int(chunk.get("pause_after_ms") or 0) if request.blessed_qra_preserve_pauses else 0
                if pause_ms > 0:
                    silence_len = int(sr * (pause_ms / 1000))
                    if silence_len > 0:
                        yield from guarded_pcm_chunks(torch.zeros((1, silence_len), dtype=torch.float32))
            return
        plan = build_render_plan(
            request.answer_text,
            max_chars=request.max_chars,
            pause_after_ms=request.pause_after_ms,
            completion_cue=request.completion_cue,
        )
        pending_tail = None
        sample_rate = None
        fade_len = 0

        stream_items = list(plan["chunks"])
        if request.include_completion_cue and request.completion_cue:
            stream_items.append(
                {
                    "index": len(stream_items) + 1,
                    "text": request.completion_cue,
                    "delivery_stage": "closing",
                    "pause_after_ms": 0,
                }
        )

        for item in stream_items:
            if stop_if_turn_controlled():
                return
            chunk_request = SynthesisRequest(
                text=item["text"],
                ref_audio=request.ref_audio,
                label=f"{batch_label}_stream_{item['index']:02d}",
                delivery_stage=item.get("delivery_stage"),
            )
            out_path = batch_dir / f"stream_{item['index']:02d}_{item.get('delivery_stage', 'neutral')}.wav"
            result = synthesize_to_file(chunk_request, out_path)
            if not result.get("ok"):
                continue
            if stop_if_turn_controlled():
                return
            wav, sr = ta.load(str(out_path))
            if sample_rate is None:
                sample_rate = sr
                fade_len = int(sr * (request.crossfade_ms / 1000))
            if pending_tail is None or fade_len <= 0 or wav.shape[1] <= fade_len:
                if pending_tail is not None:
                    if stop_if_turn_controlled():
                        return
                    yield from guarded_pcm_chunks(pending_tail)
                if fade_len > 0 and wav.shape[1] > fade_len:
                    if stop_if_turn_controlled():
                        return
                    yield from guarded_pcm_chunks(wav[:, :-fade_len])
                    pending_tail = wav[:, -fade_len:]
                else:
                    pending_tail = wav
            else:
                current_head = wav[:, :fade_len]
                if pending_tail.shape[0] == current_head.shape[0] and pending_tail.shape[1] == fade_len:
                    fade_out = torch.linspace(1.0, 0.0, fade_len, dtype=pending_tail.dtype).reshape(1, -1)
                    fade_in = torch.linspace(0.0, 1.0, fade_len, dtype=current_head.dtype).reshape(1, -1)
                    if stop_if_turn_controlled():
                        return
                    yield from guarded_pcm_chunks(pending_tail * fade_out + current_head * fade_in)
                    if stop_if_turn_controlled():
                        return
                    yield from guarded_pcm_chunks(
                        wav[:, fade_len:-fade_len] if wav.shape[1] > 2 * fade_len else wav[:, fade_len:]
                    )
                    pending_tail = wav[:, -fade_len:] if wav.shape[1] > fade_len else None
                else:
                    if stop_if_turn_controlled():
                        return
                    yield from guarded_pcm_chunks(pending_tail)
                    if stop_if_turn_controlled():
                        return
                    yield from guarded_pcm_chunks(wav[:, :-fade_len])
                    pending_tail = wav[:, -fade_len:]
            pause_ms = int(item.get("pause_after_ms") or 0)
            if pause_ms > 0 and sample_rate:
                silence_len = int(sample_rate * (pause_ms / 1000))
                if silence_len > 0:
                    if stop_if_turn_controlled():
                        return
                    yield from guarded_pcm_chunks(torch.zeros((1, silence_len), dtype=torch.float32))
        if pending_tail is not None:
            if stop_if_turn_controlled():
                return
            yield from guarded_pcm_chunks(pending_tail)

    return StreamingResponse(iter_audio(), media_type="audio/L16; rate=24000; channels=1")


@app.post("/turn/{turn_id}/cancel")
def cancel_turn(turn_id: str, request: TurnControlRequest) -> dict[str, Any]:
    return mark_turn_control(turn_id, "cancel", request)


@app.post("/playback/{turn_id}/duck")
def duck_playback(turn_id: str, request: TurnControlRequest) -> dict[str, Any]:
    return mark_turn_control(turn_id, "duck", request)


@app.post("/playback/{turn_id}/stop")
def stop_playback(turn_id: str, request: TurnControlRequest) -> dict[str, Any]:
    return mark_turn_control(turn_id, "stop", request)
