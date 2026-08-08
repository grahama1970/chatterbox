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
import wave
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Annotated, Any, Callable, Iterator, Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)

from chatterbox.agent.asr_acceptance import acceptance_result
from chatterbox.agent.chunking import (
    compile_render_plan,
    declared_chunk_hash_failures,
)
from chatterbox.agent.backends import (
    DECLARED_SAMPLE_RATE,
    CallableVoiceBackend,
    UnknownBackendError,
    UnsupportedCapabilityError,
    VoiceBackendRegistry,
    VoiceCapabilities,
)
from chatterbox.agent.stream_manifest import (
    StreamManifest,
    validate_stream_manifest,
)
from chatterbox.agent.presets import (
    ALLOWED_TONES,
    CHATTERBOX_EVENT_TAGS,
    CHATTERBOX_TAG_HANDLING,
    DELIVERY_STAGE_ALIASES,
    TAG_CONSUMING_BACKENDS,
    detect_event_tags,
    STAGE_PRESET_AFFECT_STATUS,
    STAGE_PRESETS,
    TONE_TO_DELIVERY_STAGE,
    TONE_CALIBRATION,
    TURBO_IGNORED_PARAMS,
    TURBO_SUPPORTED_PARAMS,
    VOICE_DELIVERY_EFFECT,
    effective_delivery_stage,
    generation_params_for_stage,
    normalize_delivery_stage,
    normalize_tone,
    normalize_voice_token,
    pace_tempo_factor,
)


OUT_DIR = Path(os.getenv("CHATTERBOX_OUT_DIR", "/out"))
ACCEPTED_CACHE_DIR = OUT_DIR / "_accepted_audio_cache"
DEFAULT_REF_AUDIO = Path(os.getenv("CHATTERBOX_REF_AUDIO", "/data/embry_ref.wav"))
DEVICE = os.getenv("CHATTERBOX_DEVICE", "cuda")
DEFAULT_ASR_OPENAI_BASE_URL = os.getenv("CHATTERBOX_ASR_OPENAI_BASE_URL", "http://172.17.0.1:9000")
ASR_API_KEY_ENV = os.getenv("CHATTERBOX_ASR_API_KEY_ENV", "WHISPER_API_KEY")
EMOTION_REALIZATION_DEFAULT = os.getenv("CHATTERBOX_EMOTION_REALIZATION_DEFAULT", "fast")
CACHE_SCHEMA_VERSION = "accepted_audio_cache.v2"
BLESSED_QRA_SCHEMA_VERSION = "blessed_qra_response_cache.v1"
BLESSED_QRA_LEDGER_PATH = Path(os.getenv("CHATTERBOX_BLESSED_QRA_LEDGER", str(OUT_DIR / "_blessed_qra_ledger.json")))
ASR_ACCEPTANCE_VERSION = "asr_acceptance.v1"
TEXT_NORMALIZATION_VERSION = "asr_acceptance.normalize_text.v1"
STREAM_PROTOCOL_VERSION = "pcm_l16_chunk_stream.v1"
TAU_VOICE_RENDER_REQUEST_V1 = "tau.voice_render_request.v1"
TAU_VOICE_RENDER_REQUEST_V2 = "tau.voice_render_request.v2"
SUPPORTED_TAU_VOICE_RENDER_REQUEST_SCHEMAS = (
    TAU_VOICE_RENDER_REQUEST_V1,
    TAU_VOICE_RENDER_REQUEST_V2,
)
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
base_model: Any | None = None
base_model_load_seconds: float | None = None
started_at_utc = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
voice_conditioning_cache: dict[str, Any] = {}
turn_controls: dict[str, dict[str, Any]] = {}
tau_response_controls: dict[str, dict[str, Any]] = {}
render_lock = threading.RLock()
NonEmptyStr = Annotated[str, StringConstraints(min_length=1)]

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
    repeat_group_id: str | None = Field(default=None, max_length=160)
    tone: str | None = Field(default=None, max_length=80)
    delivery_stage: str | None = None
    pace: str | None = Field(default=None, max_length=80)
    pause_strategy: str | None = Field(default=None, max_length=120)
    voice_delivery: dict[str, Any] = Field(default_factory=dict)
    backend: str | None = Field(default=None, max_length=80)
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
    repeat_group_id: str | None = Field(default=None, max_length=160)
    tone: str | None = Field(default=None, max_length=80)
    delivery_stage: str | None = Field(default=None, max_length=80)
    pace: str | None = Field(default=None, max_length=80)
    pause_strategy: str | None = Field(default=None, max_length=120)
    voice_delivery: dict[str, Any] = Field(default_factory=dict)
    backend: str | None = Field(default=None, max_length=80)
    delivery_arc: list[dict[str, str]] | None = None
    render_chunks: list[dict[str, Any]] | None = None
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
    schema: str = Field(default=TAU_VOICE_RENDER_REQUEST_V1)
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
    repeat_group_id: str | None = Field(default=None, max_length=160)
    completion_cue: str | None = Field(default=None, max_length=240)
    include_completion_cue: bool = False
    crossfade_ms: int = Field(default=20, ge=0, le=250)
    asr_verify: bool = False


class TurnControlRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=240)
    old_turn_id: str | None = Field(default=None, max_length=120)
    new_turn_id: str | None = Field(default=None, max_length=120)
    conversation_id: str | None = Field(default=None, max_length=160)
    turn_revision: int | None = Field(default=None, ge=0)
    response_id: str | None = Field(default=None, max_length=160)
    expected_cancel_epoch: int | None = Field(default=None, ge=0)


class StrictTauVoiceModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        allow_inf_nan=False,
        validate_default=True,
        revalidate_instances="always",
    )


def tuple_from_json_array(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(value)
    return value


class TauVoiceDeliverySettingsV2(StrictTauVoiceModel):
    tone: NonEmptyStr | None = None
    intensity: float | None = None
    valence: float | None = None
    stage: NonEmptyStr | None = None


class TauVoiceDeliveryDecisionV2(StrictTauVoiceModel):
    policy_version: NonEmptyStr
    requested_delivery: TauVoiceDeliverySettingsV2
    effective_delivery: TauVoiceDeliverySettingsV2
    overridden_fields: tuple[NonEmptyStr, ...] = ()
    override_reasons: dict[NonEmptyStr, NonEmptyStr] = Field(default_factory=dict)
    evidence_references: tuple[NonEmptyStr, ...] = ()
    profile_validation_status: Literal["declared_profile", "undeclared_profile", "no_tone"]

    @field_validator("overridden_fields", "evidence_references", mode="before")
    @classmethod
    def accept_json_arrays(cls, value: Any) -> Any:
        return tuple_from_json_array(value)

    @model_validator(mode="after")
    def overrides_reconcile(self) -> "TauVoiceDeliveryDecisionV2":
        if set(self.overridden_fields) != set(self.override_reasons):
            raise ValueError("overridden_fields must exactly match override_reasons keys")
        return self


class TauVoiceSourceLineageV2(StrictTauVoiceModel):
    workflow: NonEmptyStr
    run_id: NonEmptyStr
    node_id: NonEmptyStr
    attempt_id: NonEmptyStr | None = None
    scheduler_journal_sequence: int | None = None
    state_digest: NonEmptyStr | None = None
    goal_hash: NonEmptyStr | None = None
    event_type: NonEmptyStr = "state_change"
    state_transition: NonEmptyStr | None = None


class TauVoiceResponseIdentityV2(StrictTauVoiceModel):
    request_id: NonEmptyStr
    conversation_id: NonEmptyStr
    turn_id: NonEmptyStr
    turn_revision: int = Field(ge=0)
    response_id: NonEmptyStr
    cancel_epoch: int = Field(ge=0)
    supersedes_response_id: NonEmptyStr | None = None


class TauVoiceSegmentV2(StrictTauVoiceModel):
    segment_id: NonEmptyStr
    text: NonEmptyStr
    text_sha256: NonEmptyStr
    delivery: TauVoiceDeliverySettingsV2 | None = None
    interruptible: Literal[True] = True

    @field_validator("text_sha256")
    @classmethod
    def hash_matches(cls, value: str, info: Any) -> str:
        text = info.data.get("text")
        if text is not None and sha256_text(text) != value:
            raise ValueError("text_sha256 does not match text")
        return value


class TauVoiceControlTargetV2(StrictTauVoiceModel):
    conversation_id: NonEmptyStr
    turn_id: NonEmptyStr
    turn_revision: int = Field(ge=0)
    response_id: NonEmptyStr
    expected_cancel_epoch: int = Field(ge=0)


class TauVoiceRenderBlockV2(StrictTauVoiceModel):
    identity: TauVoiceResponseIdentityV2
    lineage: TauVoiceSourceLineageV2
    delivery_decision: TauVoiceDeliveryDecisionV2
    segments: tuple[TauVoiceSegmentV2, ...] = Field(min_length=1)
    control_target: TauVoiceControlTargetV2
    extensions: dict[str, Any] = Field(default_factory=dict)

    @field_validator("segments", mode="before")
    @classmethod
    def accept_json_segment_array(cls, value: Any) -> Any:
        return tuple_from_json_array(value)

    @field_validator("control_target")
    @classmethod
    def target_matches_identity(
        cls, value: TauVoiceControlTargetV2, info: Any
    ) -> TauVoiceControlTargetV2:
        identity = info.data.get("identity")
        if identity is not None and (
            value.conversation_id != identity.conversation_id
            or value.turn_id != identity.turn_id
            or value.turn_revision != identity.turn_revision
            or value.response_id != identity.response_id
            or value.expected_cancel_epoch != identity.cancel_epoch
        ):
            raise ValueError("control_target must match the response identity")
        return value

    @model_validator(mode="after")
    def segments_match_identity(self) -> "TauVoiceRenderBlockV2":
        segment_ids = [segment.segment_id for segment in self.segments]
        if len(segment_ids) != len(set(segment_ids)):
            raise ValueError("segment_id values must be unique")
        prefix = f"{self.identity.response_id}-"
        for segment in self.segments:
            if not segment.segment_id.startswith(prefix):
                raise ValueError("segment_id must be bound to response_id")
        return self


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


def render_text_for_request(
    request: SynthesisRequest | SynthesisBatchRequest | TauVoiceRenderRequest,
) -> str:
    """All text that will actually be spoken, across the request shapes.

    Tag detection has to see the same string the model will see, so chunked
    requests are joined rather than sampled.
    """
    parts: list[str] = []
    for field in ("text", "answer_text"):
        value = getattr(request, field, None)
        if isinstance(value, str):
            parts.append(value)
    for field in ("render_chunks", "speakable_chunks"):
        for chunk in getattr(request, field, None) or []:
            chunk_text = chunk.get("text") if isinstance(chunk, dict) else getattr(chunk, "text", None)
            if isinstance(chunk_text, str):
                parts.append(chunk_text)
    return " ".join(parts)


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
    detected_tags = detect_event_tags(render_text_for_request(request))
    tag_handling = {
        **CHATTERBOX_TAG_HANDLING,
        "requested_tags": [str(tag) for tag in requested_tags],
        "detected_tags": detected_tags,
    }
    # Explicit affect is a direct instruction and keeps its base-model routing;
    # tone-derived calibration yields to tag realization, because a spoken
    # "laugh" is a defect a consumer cannot hear its way out of (chatterbox#24).
    tag_realization = normalize_voice_token(source_delivery.get("tag_realization")) or "native"
    explicit_affect = (
        source_delivery.get("intensity") is not None
        or source_delivery.get("valence") is not None
        or bool(source_delivery.get("use_base_emotion"))
    )
    inherited_preference = source_delivery.get("prefer_tag_consuming_backend")
    if isinstance(inherited_preference, bool):
        # A batch decides once over the whole answer text and propagates that
        # decision to every chunk. Re-deciding per chunk would put a tagged and
        # an untagged chunk of one utterance on different backends.
        prefer_tags = inherited_preference
    else:
        prefer_tags = bool(detected_tags) and tag_realization != "literal" and not explicit_affect
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
        "tag_realization": tag_realization,
        "detected_event_tags": detected_tags,
        "prefer_tag_consuming_backend": prefer_tags,
        "pace": getattr(request, "pace", None) or source_delivery.get("pace"),
        "pause_strategy": getattr(request, "pause_strategy", None) or source_delivery.get("pause_strategy"),
        "wait_activity": source_delivery.get("wait_activity"),
        "source": source_delivery.get("source"),
        "confidence": source_delivery.get("confidence"),
        "evidence": source_delivery.get("evidence"),
        # Weighted-emotion inputs (persona-dream arc_state). When present, the
        # renderer uses the base model that HONORS exaggeration/cfg_weight.
        "intensity": source_delivery.get("intensity"),
        "valence": source_delivery.get("valence"),
        "use_base_emotion": source_delivery.get("use_base_emotion"),
        # audible: tone alone routes through TONE_CALIBRATION -> base-affect
        # knobs + per-tone tempo. fast: turbo, tone request-only. Default is
        # fast for latency compatibility (see voice_delivery_effect).
        "emotion_realization": (
            getattr(request, "emotion_realization", None)
            or source_delivery.get("emotion_realization")
            or EMOTION_REALIZATION_DEFAULT
        ),
    }


def stochasticity_for_request(request: SynthesisRequest | SynthesisBatchRequest | TauVoiceRenderRequest) -> dict[str, Any]:
    source_delivery = getattr(request, "voice_delivery", None)
    if not isinstance(source_delivery, dict):
        source_delivery = {}
    repeat_group_id = getattr(request, "repeat_group_id", None) or source_delivery.get("repeat_group_id")
    return {
        "schema": "chatterbox.stochasticity.v1",
        "repeat_group_id": repeat_group_id,
        "deterministic_audio": False,
        "seed_supported": False,
        "seed": None,
        "equivalence": "same_repeat_group_id_groups_comparable_stochastic_renders_without_implying_identical_audio",
        "cache_behavior": "repeat_group_id_is_receipt_metadata_not_a_cache_buster",
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


TONE_AFFECT_DEFAULTS: dict[str, dict[str, float]] = {
    "neutral_warm": {"intensity": 0.4, "valence": 0.3},
    "calm_precise": {"intensity": 0.35, "valence": 0.1},
    "careful_concerned": {"intensity": 0.5, "valence": -0.3},
    "serious_low_energy": {"intensity": 0.4, "valence": -0.5},
    "memory_confident": {"intensity": 0.6, "valence": 0.5},
    "memory_uncertain": {"intensity": 0.45, "valence": -0.2},
    "curious_searching": {"intensity": 0.5, "valence": 0.2},
    "playful_light": {"intensity": 0.75, "valence": 0.7},
    "relieved": {"intensity": 0.7, "valence": 0.6},
    "firm_boundary": {"intensity": 0.85, "valence": -0.7},
    "identity_clarification": {"intensity": 0.5, "valence": -0.1},
    "one_at_a_time_interrupt": {"intensity": 0.8, "valence": -0.6},
    "deflect_calm": {"intensity": 0.45, "valence": -0.4},
    "grief_safe": {"intensity": 0.4, "valence": -0.6},
    "wait_presence": {"intensity": 0.25, "valence": 0.0},
}


def emotion_knobs_from_delivery(voice_delivery: dict[str, Any]) -> dict[str, float] | None:
    """Map weighted emotion (tone + intensity + valence) -> base-model controls.

    Returns None unless the delivery explicitly carries emotion (intensity,
    valence, or use_base_emotion), so default Turbo rendering is unchanged.
    intensity is the WEIGHT and scales exaggeration; negative valence lowers cfg.
    """
    vd = voice_delivery or {}
    intensity_raw = vd.get("intensity")
    valence_raw = vd.get("valence")
    audible_tone_route = (
        vd.get("emotion_realization") == "audible"
        and bool(vd.get("requested_tone"))
        # Tone-derived knobs would route to the base model, which has no tag
        # vocabulary. With native tags in the text the tag-consuming backend
        # wins and the tone is carried by the backend-independent tempo axis.
        and not vd.get("prefer_tag_consuming_backend")
    )
    if intensity_raw is None and valence_raw is None and not vd.get("use_base_emotion") and not audible_tone_route:
        return None
    if intensity_raw is None and valence_raw is None and audible_tone_route:
        calibration = TONE_CALIBRATION.get(vd.get("tone") or "neutral_warm")
        if calibration:
            intensity_raw = calibration["intensity"]
            valence_raw = calibration["valence"]

    def _num(value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    base = TONE_AFFECT_DEFAULTS.get(vd.get("tone") or "neutral_warm", {"intensity": 0.4, "valence": 0.0})
    intensity = _num(intensity_raw)
    intensity = base["intensity"] if intensity is None else intensity
    valence = _num(valence_raw)
    valence = base["valence"] if valence is None else valence
    intensity = max(0.0, min(1.0, intensity))
    valence = max(-1.0, min(1.0, valence))
    return {
        "exaggeration": round(max(0.3, min(1.4, 0.3 + 0.9 * intensity)), 3),
        "cfg_weight": round(max(0.3, min(0.5, 0.5 - 0.2 * max(0.0, -valence))), 3),
        "temperature": 0.7,
        "intensity": intensity,
        "valence": valence,
    }


def apply_pace_stretch(
    wav: Any, sr: int, pace: str | None, tone_tempo: float | None = None
) -> tuple[Any, dict[str, Any]]:
    """Apply a pitch-preserving phase-vocoder time stretch for a requested pace.

    Deterministic post-process on the rendered waveform, so its duration effect
    is exact-ratio and measurable above same-parameter stochastic spread.
    Unknown pace values are a no-op and reported as request_only in the receipt.
    """
    factor = pace_tempo_factor(pace)
    tempo_source = "requested_pace"
    if not pace and tone_tempo is not None:
        factor = float(tone_tempo)
        tempo_source = "tone_calibration"
    input_duration = round(wav.shape[-1] / sr, 3)
    receipt: dict[str, Any] = {
        "schema": "chatterbox.pace_effect.v1",
        "requested_pace": pace,
        "tempo_factor": factor,
        "tempo_source": tempo_source if factor is not None else None,
        "mechanism": "phase_vocoder_time_stretch",
        "applied": False,
        "input_duration_seconds": input_duration,
        "output_duration_seconds": input_duration,
    }
    if not pace and tone_tempo is None:
        receipt["reason"] = "no_pace_requested"
        return wav, receipt
    if factor is None:
        receipt["reason"] = "unknown_pace_value_request_only"
        return wav, receipt
    if abs(factor - 1.0) < 1e-3:
        receipt["reason"] = "identity_tempo_factor"
        return wav, receipt
    try:
        import torch
        import torchaudio

        n_fft, hop = 1024, 256
        window = torch.hann_window(n_fft, device=wav.device)
        spec = torch.stft(wav, n_fft=n_fft, hop_length=hop, window=window, return_complex=True)
        stretched = torchaudio.transforms.TimeStretch(hop_length=hop, n_freq=n_fft // 2 + 1)(spec, factor)
        out = torch.istft(stretched, n_fft=n_fft, hop_length=hop, window=window)
        if out.dim() == 1:
            out = out.unsqueeze(0)
        out = out.to(dtype=wav.dtype)
    except Exception as exc:  # noqa: BLE001 - a stretch failure must not kill the render, and must be reported honestly
        receipt["reason"] = f"stretch_failed:{type(exc).__name__}:{exc}"
        return wav, receipt
    receipt["applied"] = True
    receipt["output_duration_seconds"] = round(out.shape[-1] / sr, 3)
    return out, receipt


def tone_calibration_tempo(voice_delivery: dict[str, Any]) -> float | None:
    """Calibration tempo for a render, or None when it does not apply.

    Tempo is a post-synthesis phase-vocoder stretch, so unlike the
    intensity/valence knobs it is backend-independent: it is the part of
    TONE_CALIBRATION that survives on the tag-consuming path (chatterbox#24).
    An explicit pace always wins, since that is a direct instruction.
    """
    if voice_delivery.get("pace"):
        return None
    if voice_delivery.get("emotion_realization") != "audible":
        return None
    if not voice_delivery.get("requested_tone"):
        return None
    return TONE_CALIBRATION.get(voice_delivery.get("tone") or "neutral_warm", {}).get("tempo")


def apply_tag_handling_backend(voice_delivery: dict[str, Any], backend_id: str | None) -> dict[str, Any]:
    """Finalize tag_handling against the backend actually used, in place.

    tags_interpreted is a property of the path taken, not of the server, so it
    is only true when native tags reached a backend that consumes them.
    """
    tag_handling = voice_delivery.get("tag_handling")
    if not isinstance(tag_handling, dict):
        return {}
    detected = tag_handling.get("detected_tags") or []
    consumes = backend_id in TAG_CONSUMING_BACKENDS
    tag_handling["backend"] = backend_id
    if not detected:
        tag_handling["tags_interpreted"] = False
        tag_handling["applied_tags"] = []
        tag_handling["tags_interpreted_reason"] = (
            f"no_event_tags_in_text__backend_{backend_id}_"
            + ("would_consume_them" if consumes else "would_speak_them_literally")
        )
        return tag_handling
    tag_handling["tags_interpreted"] = consumes
    tag_handling["applied_tags"] = list(detected) if consumes else []
    if consumes:
        tag_handling["tags_interpreted_reason"] = f"backend_{backend_id}_consumes_event_tags_natively"
    elif voice_delivery.get("tag_realization") == "literal":
        tag_handling["tags_interpreted_reason"] = (
            f"tag_realization_literal_requested__backend_{backend_id}_speaks_tags_as_literal_text"
        )
    else:
        tag_handling["tags_interpreted_reason"] = (
            f"explicit_affect_knobs_route_to_backend_{backend_id}_which_speaks_tags_as_literal_text__"
            "unsatisfiable_with_tag_realization_native"
        )
    return tag_handling


def affect_effect_receipt(
    voice_delivery: dict[str, Any],
    knobs: dict[str, float] | None,
    backend_id: str | None,
) -> dict[str, Any]:
    """Per-render affect receipt in the same shape as pace_effect (#21).

    applied is true only when derived knobs actually reached a backend that
    honors them; a consumer verifies this receipt, never the echoed request.
    """
    explicit = voice_delivery.get("intensity") is not None or voice_delivery.get("valence") is not None
    receipt: dict[str, Any] = {
        "schema": "chatterbox.affect_effect.v1",
        "applied": False,
        "backend": backend_id,
        "derived_knobs": knobs,
        "knob_source": None,
        "reason": None,
    }
    if knobs is None:
        if voice_delivery.get("prefer_tag_consuming_backend"):
            # Affect WAS requested; it yielded to tag realization. Saying
            # "no affect requested" here would misdescribe the path (#24).
            receipt["knob_source"] = "tone_calibration_deferred_to_tag_realization"
            receipt["reason"] = (
                "affect_knobs_not_applied__render_kept_on_tag_consuming_backend_for_inline_event_tags; "
                "tone carried by the backend-independent tempo axis, see pace_effect.tempo_source=tone_calibration"
            )
        else:
            receipt["reason"] = "no_affect_requested_default_turbo_render"
        return receipt
    if explicit:
        receipt["knob_source"] = "explicit_intensity_valence"
    elif voice_delivery.get("emotion_realization") == "audible" and voice_delivery.get("requested_tone"):
        receipt["knob_source"] = "tone_calibration"
    else:
        receipt["knob_source"] = "tone_affect_defaults"
    if backend_id == "chatterbox_base_affect":
        receipt["applied"] = True
    else:
        receipt["reason"] = f"backend_{backend_id}_does_not_honor_affect_knobs"
    return receipt


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
    stochasticity = stochasticity_for_request(request)
    knobs = emotion_knobs_from_delivery(voice_delivery)
    try:
        backend, backend_selection = select_voice_backend_for_request(request.backend, knobs)
        apply_tag_handling_backend(voice_delivery, backend.caps.backend_id)
    except UnknownBackendError as exc:
        raise HTTPException(status_code=422, detail={"reason": "unknown_backend", "detail": str(exc)}) from exc
    except UnsupportedCapabilityError as exc:
        raise HTTPException(
            status_code=422,
            detail={"reason": str(exc), "backend": exc.backend_id, "capability": exc.capability},
        ) from exc
    engine_used = ENGINE_NAME_BY_BACKEND.get(backend.caps.backend_id, backend.caps.backend_id)
    latency_event(events, "generation_params_ready", started_total)
    started = time.perf_counter()
    try:
        with render_lock:
            if backend.caps.backend_id == "chatterbox_base_affect":
                wav, render_sr, conditioning = backend.synthesize(
                    text=request.text, ref_audio=ref_audio, knobs=knobs
                )
                latency_event(events, "voice_conditioning_ready", started_total, engine="chatterbox_base", render_lock="held")
            else:
                wav, render_sr, conditioning = backend.synthesize(
                    text=request.text, ref_audio=ref_audio, params=params
                )
                latency_event(
                    events,
                    "voice_conditioning_ready",
                    started_total,
                    cache_hit=conditioning.get("conditioning_cache_hit"),
                    cache_key=conditioning.get("conditioning_cache_key"),
                    render_lock="held",
                )
        generation_seconds = round(time.perf_counter() - started, 3)
        latency_event(events, "first_audio_ready", started_total, generation_seconds=generation_seconds)
        tone_tempo = tone_calibration_tempo(voice_delivery)
        wav, pace_effect = apply_pace_stretch(wav, int(render_sr), voice_delivery.get("pace"), tone_tempo)
        if pace_effect["applied"]:
            latency_event(
                events,
                "pace_stretch_applied",
                started_total,
                tempo_factor=pace_effect["tempo_factor"],
                output_duration_seconds=pace_effect["output_duration_seconds"],
            )
        ta.save(str(out_path), wav, render_sr)
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
            "engine": engine_used,
            "backend": backend_selection,
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
            "stochasticity": stochasticity,
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
    if int(render_sr) != DECLARED_SAMPLE_RATE:
        failed_gates.append("output_sample_rate_matches_declared")
    return {
        "ok": not failed_gates,
        "mocked": False,
        "live": True,
        "engine": engine_used,
        "backend": backend_selection,
        "output_format": {
            "declared_sample_rate": DECLARED_SAMPLE_RATE,
            "backend_sample_rate": int(render_sr),
            "channels": 1,
            "container": "wav",
        },
        "emotion_knobs": knobs,
        "affect_effect": affect_effect_receipt(voice_delivery, knobs, backend.caps.backend_id),
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
        "voice_delivery_effect": VOICE_DELIVERY_EFFECT,
        "pace_effect": pace_effect,
        "tag_handling": voice_delivery["tag_handling"],
        "stochasticity": stochasticity,
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
        repeat_group_id=base_request.repeat_group_id,
        tone=base_request.tone,
        delivery_stage=base_request.delivery_stage,
        pace=base_request.pace,
        pause_strategy=base_request.pause_strategy,
        temperature=overrides.get("temperature", base_request.temperature),
        top_p=overrides.get("top_p", base_request.top_p),
        top_k=overrides.get("top_k", base_request.top_k),
        repetition_penalty=overrides.get("repetition_penalty", base_request.repetition_penalty),
        norm_loudness=overrides.get("norm_loudness", base_request.norm_loudness),
        voice_delivery=dict(base_request.voice_delivery or {}),
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
    knobs = emotion_knobs_from_delivery(voice_delivery)
    stochasticity = stochasticity_for_request(base_request)
    return {
        "cache_schema_version": CACHE_SCHEMA_VERSION,
        "engine": "chatterbox_base" if knobs else "chatterbox_turbo",
        "emotion_knobs": knobs,
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
        "stochasticity": stochasticity,
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
    try:
        import torch
        import torchaudio as ta
    except (ModuleNotFoundError, OSError) as exc:
        if crossfade_ms == 0:
            return combine_pcm_wav_segments(segments, out_path)
        raise HTTPException(
            status_code=500,
            detail=f"torchaudio_unavailable_for_crossfade:{type(exc).__name__}",
        ) from exc

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


def combine_pcm_wav_segments(
    segments: list[dict[str, Any]],
    out_path: Path,
) -> dict[str, Any]:
    """Combine compatible PCM WAV segments without torch/torchaudio."""
    params: wave._wave_params | None = None
    frames: list[bytes] = []
    for segment in segments:
        audio_path = Path(segment["audio"])
        with wave.open(str(audio_path), "rb") as handle:
            current_params = handle.getparams()
            if current_params.comptype != "NONE":
                raise HTTPException(status_code=500, detail=f"compressed_wav_not_supported:{audio_path}")
            compare_params = wave._wave_params(
                current_params.nchannels,
                current_params.sampwidth,
                current_params.framerate,
                0,
                current_params.comptype,
                current_params.compname,
            )
            if params is None:
                params = compare_params
            if compare_params != params:
                raise HTTPException(status_code=500, detail=f"wav_params_mismatch:{audio_path}")
            frames.append(handle.readframes(current_params.nframes))
        pause_ms = int(segment.get("pause_after_ms") or 0)
        if pause_ms > 0 and params is not None:
            silence_frames = int(params.framerate * (pause_ms / 1000))
            frames.append(b"\x00" * silence_frames * params.nchannels * params.sampwidth)
    if not frames or params is None:
        raise HTTPException(status_code=500, detail="no_audio_segments_to_combine")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), "wb") as handle:
        handle.setnchannels(params.nchannels)
        handle.setsampwidth(params.sampwidth)
        handle.setframerate(params.framerate)
        handle.writeframes(b"".join(frames))
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
    if request.schema != TAU_VOICE_RENDER_REQUEST_V1:
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
    render_chunks: list[dict[str, Any]] = []
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
        render_chunks.append(
            {
                "text": text,
                "tone": normalize_tone(chunk.tone or request.tone or request.voice_delivery.get("tone")),
                "requested_tone": chunk.tone or request.tone or request.voice_delivery.get("tone"),
                "delivery_stage": effective_delivery_stage(
                    tone=chunk.tone or request.tone or request.voice_delivery.get("tone"),
                    delivery_stage=chunk.delivery_stage,
                ),
                "requested_delivery_stage": chunk.delivery_stage or request.delivery_stage,
                "pace": chunk.pace or request.pace or request.voice_delivery.get("pace"),
                "pause_strategy": chunk.pause_strategy or request.pause_strategy or request.voice_delivery.get("pause_strategy"),
                "pause_after_ms": chunk.pause_after_ms,
                "interruptible": chunk.interruptible,
                "role": f"tau_chunk_{index}",
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
        repeat_group_id=request.repeat_group_id or request.voice_delivery.get("repeat_group_id"),
        tone=tone,
        delivery_stage=delivery_stage,
        pace=tau_voice_delivery.get("pace"),
        pause_strategy=tau_voice_delivery.get("pause_strategy"),
        voice_delivery=tau_voice_delivery,
        render_chunks=render_chunks,
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
            "repeat_group_id": batch_request.repeat_group_id,
            "turn_id": batch_request.turn_id,
            "use_blessed_qra_cache": batch_request.use_blessed_qra_cache,
            "blessed_qra_variant": batch_request.blessed_qra_variant,
            "require_blessed_qra_memory_gate": batch_request.require_blessed_qra_memory_gate,
            "asr_verify": batch_request.asr_verify,
            "render_chunk_count": len(batch_request.render_chunks or []),
        },
        "failed_gates": failed_gates,
    }
    return batch_request, receipt


def summarize_validation_error(exc: ValidationError) -> str:
    parts = []
    for error in exc.errors():
        location = ".".join(str(item) for item in error["loc"]) or "<root>"
        parts.append(f"{location}: {error['msg']}")
    return "; ".join(sorted(parts))


def tau_voice_render_request_lineage_digest(
    envelope: dict[str, Any],
    block: TauVoiceRenderBlockV2,
) -> str:
    material = {
        "schema": envelope.get("schema"),
        "identity": block.identity.model_dump(mode="json"),
        "lineage": block.lineage.model_dump(mode="json"),
        "segment_text_sha256": [segment.text_sha256 for segment in block.segments],
    }
    return sha256_text(json.dumps(material, sort_keys=True, separators=(",", ":")))


def parse_tau_voice_render_v2(payload: dict[str, Any]) -> TauVoiceRenderBlockV2:
    schema = payload.get("schema")
    if schema != TAU_VOICE_RENDER_REQUEST_V2:
        raise HTTPException(
            status_code=422,
            detail={
                "reason": "unsupported_tau_voice_render_schema",
                "schema": schema,
                "supported_schemas": list(SUPPORTED_TAU_VOICE_RENDER_REQUEST_SCHEMAS),
            },
        )
    block = payload.get("v2")
    if not isinstance(block, dict):
        raise HTTPException(
            status_code=422,
            detail={"reason": "missing_tau_voice_render_v2_block"},
        )
    try:
        return TauVoiceRenderBlockV2.model_validate(block)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "reason": "invalid_tau_voice_render_v2_block",
                "detail": summarize_validation_error(exc),
            },
        ) from exc


def register_tau_response_identity(identity: TauVoiceResponseIdentityV2) -> dict[str, Any]:
    key = identity.conversation_id
    previous = tau_response_controls.get(key)
    if previous and identity.supersedes_response_id not in (
        None,
        previous.get("response_id"),
    ):
        return {
            "accepted": False,
            "reason": "supersedes_mismatch",
            "current_response_id": previous.get("response_id"),
        }
    record = {
        **identity.model_dump(mode="json"),
        "events": [],
        "cancelled": False,
        "stopped": False,
        "ducked": False,
    }
    tau_response_controls[key] = record
    return {"accepted": True, "response_id": identity.response_id}


def tau_response_control_target_from_request(
    turn_id: str,
    request: TurnControlRequest,
) -> TauVoiceControlTargetV2 | None:
    supplied_identity_fields = [
        request.conversation_id,
        request.turn_revision,
        request.response_id,
        request.expected_cancel_epoch,
    ]
    if all(value is None for value in supplied_identity_fields):
        return None
    values = {
        "conversation_id": request.conversation_id,
        "turn_id": turn_id,
        "turn_revision": request.turn_revision,
        "response_id": request.response_id,
        "expected_cancel_epoch": request.expected_cancel_epoch,
    }
    if any(value is None for value in values.values()):
        raise HTTPException(
            status_code=422,
            detail={
                "reason": "incomplete_tau_voice_control_target",
                "required": [
                    "conversation_id",
                    "turn_id",
                    "turn_revision",
                    "response_id",
                    "expected_cancel_epoch",
                ],
            },
        )
    try:
        return TauVoiceControlTargetV2.model_validate(values)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "reason": "invalid_tau_voice_control_target",
                "detail": summarize_validation_error(exc),
            },
        ) from exc


def mark_tau_response_control(
    target: TauVoiceControlTargetV2,
    action: str,
    request: TurnControlRequest,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    state = tau_response_controls.get(target.conversation_id)
    receipt = {
        "action": action,
        "target": target.model_dump(mode="json"),
        "idempotent": False,
    }
    if state is None:
        return {**receipt, "accepted": False, "reason": "unknown_conversation"}
    if target.turn_id != state.get("turn_id"):
        return {**receipt, "accepted": False, "reason": "stale_turn"}
    if target.turn_revision != state.get("turn_revision"):
        return {**receipt, "accepted": False, "reason": "stale_turn_revision"}
    if target.response_id != state.get("response_id"):
        return {**receipt, "accepted": False, "reason": "stale_response_id"}
    if target.expected_cancel_epoch != state.get("cancel_epoch"):
        return {**receipt, "accepted": False, "reason": "stale_cancel_epoch"}
    if action == "cancel" and state.get("cancelled"):
        return {**receipt, "accepted": True, "idempotent": True, "reason": "already_cancelled"}
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
        state["cancel_epoch"] = int(state["cancel_epoch"]) + 1
    if action == "duck":
        state["ducked"] = True
    if action == "stop":
        state["stopped"] = True
    return {**receipt, "accepted": True, "reason": "current_response", "state": state}


def synthesis_batch_request_from_tau_voice_render_v2(
    payload: dict[str, Any],
    block: TauVoiceRenderBlockV2,
) -> tuple[SynthesisBatchRequest, dict[str, Any]]:
    failed_gates: list[str] = []
    registration = register_tau_response_identity(block.identity)
    if not registration.get("accepted"):
        failed_gates.append("response_identity_registered")
    digest = tau_voice_render_request_lineage_digest(payload, block)
    requested = block.delivery_decision.effective_delivery
    voice_delivery = {
        "schema": "chatterbox.tau_voice_delivery.v2",
        "source": "tau.voice_render_request.v2.delivery_decision",
        "tone": requested.tone,
        "delivery_stage": requested.stage,
        "stage": requested.stage,
        "intensity": requested.intensity,
        "valence": requested.valence,
        "requested_delivery": block.delivery_decision.requested_delivery.model_dump(mode="json"),
        "effective_delivery": block.delivery_decision.effective_delivery.model_dump(mode="json"),
        "overridden_fields": list(block.delivery_decision.overridden_fields),
        "override_reasons": dict(block.delivery_decision.override_reasons),
        "policy_version": block.delivery_decision.policy_version,
        "profile_validation_status": block.delivery_decision.profile_validation_status,
        "evidence_references": list(block.delivery_decision.evidence_references),
        "request_lineage_digest": digest,
        "response_id": block.identity.response_id,
        "turn_revision": block.identity.turn_revision,
        "cancel_epoch": block.identity.cancel_epoch,
    }
    render_chunks = []
    chunk_receipts = []
    for index, segment in enumerate(block.segments, start=1):
        delivery = segment.delivery or block.delivery_decision.effective_delivery
        stage = delivery.stage or requested.stage or "neutral"
        tone = delivery.tone or requested.tone
        render_chunks.append(
            {
                "text": segment.text,
                "text_sha256": segment.text_sha256,
                "tone": tone,
                "requested_tone": tone,
                "delivery_stage": effective_delivery_stage(tone=tone, delivery_stage=stage),
                "requested_delivery_stage": stage,
                "interruptible": segment.interruptible,
                "role": f"tau_v2_segment_{index}",
            }
        )
        chunk_receipts.append(
            {
                "segment_id": segment.segment_id,
                "index": index,
                "text_sha256": segment.text_sha256,
                "tone": tone,
                "delivery_stage": stage,
                "interruptible": segment.interruptible,
            }
        )
    answer_text = " ".join(segment.text.strip() for segment in block.segments).strip()
    batch_request = SynthesisBatchRequest(
        answer_text=answer_text or " ",
        max_chars=300,
        pause_after_ms=250,
        completion_cue=payload.get("completion_cue"),
        turn_id=block.identity.turn_id,
        question_text=payload.get("question_text"),
        use_blessed_qra_cache=bool(payload.get("use_blessed_qra_cache", False)),
        blessed_qra_min_similarity=float(payload.get("blessed_qra_min_similarity", 0.99)),
        blessed_qra_variant=payload.get("blessed_qra_variant"),
        blessed_qra_preserve_pauses=bool(payload.get("blessed_qra_preserve_pauses", False)),
        require_blessed_qra_memory_gate=bool(
            payload.get("require_blessed_qra_memory_gate", True)
        ),
        blessed_qra_memory_key=payload.get("blessed_qra_memory_key"),
        blessed_qra_memory_similarity=payload.get("blessed_qra_memory_similarity"),
        blessed_qra_memory_review_status=payload.get("blessed_qra_memory_review_status"),
        repeat_group_id=(
            payload.get("repeat_group_id")
            or (payload.get("voice_delivery") or {}).get("repeat_group_id")
        ),
        tone=requested.tone,
        delivery_stage=requested.stage,
        voice_delivery=voice_delivery,
        render_chunks=render_chunks,
        delivery_arc=[
            {
                "stage": chunk["delivery_stage"],
                "tone": chunk["tone"] or "neutral_warm",
                "role": chunk["role"],
            }
            for chunk in render_chunks
        ],
        label=payload.get("label")
        or f"tau_{safe_label(block.identity.conversation_id)}_{safe_label(block.identity.response_id)}",
        include_completion_cue=bool(payload.get("include_completion_cue", False)),
        crossfade_ms=int(payload.get("crossfade_ms", 20)),
        asr_verify=bool(payload.get("asr_verify", False)),
    )
    receipt = {
        "schema": TAU_VOICE_RENDER_REQUEST_V2,
        "ok": not failed_gates,
        "conversation_id": block.identity.conversation_id,
        "turn_id": block.identity.turn_id,
        "turn_revision": block.identity.turn_revision,
        "response_id": block.identity.response_id,
        "cancel_epoch": block.identity.cancel_epoch,
        "request_id": block.identity.request_id,
        "lineage": block.lineage.model_dump(mode="json"),
        "delivery_decision": block.delivery_decision.model_dump(mode="json"),
        "control_target": block.control_target.model_dump(mode="json"),
        "request_lineage_digest": digest,
        "consumer_lineage_digest": digest,
        "source_segment_count": len(block.segments),
        "source_segments": chunk_receipts,
        "response_registration": registration,
        "mapped_batch": {
            "answer_text_sha256": sha256_text(answer_text),
            "turn_id": batch_request.turn_id,
            "response_id": block.identity.response_id,
            "render_chunk_count": len(batch_request.render_chunks or []),
            "tone": batch_request.tone,
            "delivery_stage": batch_request.delivery_stage,
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
    stochasticity = stochasticity_for_request(request)
    plan = compile_render_plan(
        answer_text=match["answer_text"],
        render_chunks=blessed_render_chunks(match),
        max_chars=request.max_chars,
        pause_after_ms=0,
        completion_cue=None,
    )
    persist_render_plan_receipt(
        batch_dir,
        plan=plan,
        entry_point="synthesize_batch.blessed_qra",
        batch_label=batch_label,
        voice_delivery=voice_delivery,
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
        "stochasticity": stochasticity,
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
        "render_plan_digest": plan["render_plan_digest"],
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
    knobs = emotion_knobs_from_delivery(voice_delivery or {})
    material = {
        "engine": "chatterbox_base" if knobs else "chatterbox_turbo",
        "emotion_knobs": knobs,
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


def applied_controls_for_plan(plan: dict[str, Any], voice_delivery: dict[str, Any]) -> list[dict[str, Any]]:
    controls = []
    for chunk in plan.get("chunks") or []:
        pause_after_ms = int(chunk.get("pause_after_ms") or 0)
        controls.append(
            {
                "chunk_index": chunk["index"],
                "requested": {
                    "tone": voice_delivery.get("requested_tone"),
                    "delivery_stage": voice_delivery.get("requested_delivery_stage"),
                    "pace": voice_delivery.get("pace"),
                    "pause_strategy": voice_delivery.get("pause_strategy"),
                    "pause_after_ms": chunk.get("pause_after_ms"),
                },
                "normalized": {
                    "tone": voice_delivery.get("normalized_tone") or voice_delivery.get("tone"),
                    "delivery_stage": chunk.get("delivery_stage"),
                    "pace": voice_delivery.get("pace"),
                    "pause_strategy": voice_delivery.get("pause_strategy"),
                    "pause_after_ms": pause_after_ms,
                },
                "applied": {
                    "tone": voice_delivery.get("tone"),
                    "delivery_stage": chunk.get("delivery_stage"),
                    "pace": voice_delivery.get("pace"),
                    "pause_strategy": voice_delivery.get("pause_strategy"),
                    "pause_after_ms": pause_after_ms,
                    "can_interrupt_after": bool(chunk.get("can_interrupt_after", True)),
                },
            }
        )
    return controls


def blessed_render_chunks(match: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "text": chunk.get("text"),
            "delivery_stage": chunk.get("delivery_stage"),
            "pause_after_ms": chunk.get("pause_after_ms"),
            "role": f"blessed_chunk_{index}",
        }
        for index, chunk in enumerate(match.get("chunks") or [], start=1)
    ]


def persist_render_plan_receipt(
    batch_dir: Path,
    *,
    plan: dict[str, Any],
    entry_point: str,
    batch_label: str,
    voice_delivery: dict[str, Any],
) -> Path:
    receipt = {
        "schema": "chatterbox.render_plan_receipt.v1",
        "entry_point": entry_point,
        "batch_label": batch_label,
        "render_plan_digest": plan["render_plan_digest"],
        "plan": plan,
        "applied_controls": applied_controls_for_plan(plan, voice_delivery),
    }
    path = batch_dir / "render_plan.json"
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def mark_turn_control(turn_id: str, action: str, request: TurnControlRequest) -> dict[str, Any]:
    target = tau_response_control_target_from_request(turn_id, request)
    if target is not None:
        control = mark_tau_response_control(target, action, request)
        return {
            "ok": bool(control.get("accepted")),
            "mocked": False,
            "live": True,
            "turn_id": turn_id,
            "control": control,
        }
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


STREAM_SAMPLE_RATE = 24000
STREAM_CHANNELS = 1
STREAM_BYTES_PER_SAMPLE = 2
# Publication frame policy: at most this much already-encoded PCM may be
# admitted between turn-control checks, bounding stale audio after a cancel.
STREAM_PUBLICATION_FRAME_MS = 40


def pcm_frame_bytes(
    *,
    sample_rate: int = STREAM_SAMPLE_RATE,
    channels: int = STREAM_CHANNELS,
    bytes_per_sample: int = STREAM_BYTES_PER_SAMPLE,
    frame_ms: int = STREAM_PUBLICATION_FRAME_MS,
) -> int:
    sample_bytes = channels * bytes_per_sample
    return max(sample_bytes, int(sample_rate * frame_ms / 1000) * sample_bytes)


def bounded_pcm_frames(
    data: bytes,
    should_stop: Callable[[], bool],
    *,
    sample_rate: int = STREAM_SAMPLE_RATE,
) -> Iterator[bytes]:
    block_size = pcm_frame_bytes(sample_rate=sample_rate)
    for offset in range(0, len(data), block_size):
        if should_stop():
            return
        yield data[offset : offset + block_size]


class StreamSegmentSynthesisError(RuntimeError):
    """A planned segment failed to synthesize; the stream must terminate failed."""


STREAM_MANIFEST_INDEX: dict[str, str] = {}
STREAM_MANIFEST_INDEX_MAX = 256


def register_stream_manifest(stream_id: str, path: Path) -> None:
    STREAM_MANIFEST_INDEX[stream_id] = str(path)
    while len(STREAM_MANIFEST_INDEX) > STREAM_MANIFEST_INDEX_MAX:
        STREAM_MANIFEST_INDEX.pop(next(iter(STREAM_MANIFEST_INDEX)))


@app.get("/stream-manifest/{stream_id}")
def get_stream_manifest(stream_id: str) -> dict[str, Any]:
    path = STREAM_MANIFEST_INDEX.get(stream_id)
    if not path or not Path(path).exists():
        raise HTTPException(status_code=404, detail="stream_manifest_not_found")
    manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    return {
        "ok": True,
        "mocked": False,
        "live": True,
        "manifest": manifest,
        "validation_failures": validate_stream_manifest(manifest),
    }


@app.on_event("startup")
def load_model() -> None:
    global model, model_load_seconds
    from chatterbox.tts_turbo import ChatterboxTurboTTS

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    model = ChatterboxTurboTTS.from_pretrained(device=DEVICE)
    model_load_seconds = round(time.perf_counter() - started, 3)


TONE_CALIBRATION_MATRIX_PATH = Path(__file__).resolve().parents[3] / "docs" / "proofs" / "tone_calibration_matrix.json"


def tone_calibration_matrix_receipt() -> dict[str, Any]:
    """Published result of the tone_matrix eval: which tones are measurably distinct."""
    try:
        matrix = json.loads(TONE_CALIBRATION_MATRIX_PATH.read_text())
        return {
            "status": "calibrated",
            "receipt_path": str(TONE_CALIBRATION_MATRIX_PATH),
            "classification": matrix.get("classification"),
            "noise_floor": matrix.get("noise_floor", {}).get("spread"),
            "generated": matrix.get("generated"),
        }
    except FileNotFoundError:
        return {"status": "not_yet_calibrated", "receipt_path": str(TONE_CALIBRATION_MATRIX_PATH)}
    except Exception as exc:  # noqa: BLE001 - health must report a bad matrix file as data
        return {"status": "matrix_unreadable", "error": f"{type(exc).__name__}: {exc}"}


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
        "supported_tau_voice_render_request_schemas": list(
            SUPPORTED_TAU_VOICE_RENDER_REQUEST_SCHEMAS
        ),
        "supported_params": sorted(TURBO_SUPPORTED_PARAMS),
        "ignored_turbo_params": sorted(TURBO_IGNORED_PARAMS),
        "tag_handling": CHATTERBOX_TAG_HANDLING,
        "stage_preset_affect_status": STAGE_PRESET_AFFECT_STATUS,
        "voice_delivery_effect": VOICE_DELIVERY_EFFECT,
        "tone_calibration": TONE_CALIBRATION,
        "tone_calibration_matrix": tone_calibration_matrix_receipt(),
        "voice_backends": VOICE_BACKENDS.summary(),
        "supported_backends": VOICE_BACKENDS.ids(),
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
        "stage_preset_affect_status": STAGE_PRESET_AFFECT_STATUS,
        "voice_delivery_effect": VOICE_DELIVERY_EFFECT,
        "tone_calibration": TONE_CALIBRATION,
        "tone_calibration_matrix": tone_calibration_matrix_receipt(),
        "allowed_tones": sorted(ALLOWED_TONES),
        "tone_to_delivery_stage": TONE_TO_DELIVERY_STAGE,
        "delivery_stage_aliases": DELIVERY_STAGE_ALIASES,
        "stage_presets": STAGE_PRESETS,
    }


@app.post("/render-plan")
def render_plan(request: RenderPlanRequest) -> dict[str, Any]:
    plan = compile_render_plan(
        answer_text=request.answer_text,
        max_chars=request.max_chars,
        pause_after_ms=request.pause_after_ms,
        completion_cue=request.completion_cue,
    )
    return {"ok": True, "mocked": False, "live": True, "plan": plan, "render_plan_digest": plan["render_plan_digest"]}


@app.post("/synthesize")
def synthesize(request: SynthesisRequest) -> dict[str, Any]:
    label = request.label or f"sample-{uuid4().hex[:8]}"
    out_path = OUT_DIR / f"{safe_label(label)}.wav"
    return synthesize_to_file(request, out_path)


class EmotionRenderRequest(BaseModel):
    """Base-model render that HONORS exaggeration/cfg_weight (Turbo ignores them).

    Emotion-weighting bridge: persona-dream maps verdict -> emotion -> intensity
    weight -> (exaggeration, cfg_weight); this endpoint applies them acoustically.
    """

    text: str
    ref_audio: str | None = None
    exaggeration: float = Field(default=0.5, ge=0.0, le=2.0)
    cfg_weight: float = Field(default=0.5, ge=0.0, le=1.0)
    temperature: float = Field(default=0.7, gt=0.0, le=2.0)
    seed: int | None = None
    label: str | None = None


def get_base_model() -> Any:
    """Lazily load the base ChatterboxTTS (separate from the Turbo model)."""
    global base_model, base_model_load_seconds
    if base_model is None:
        from chatterbox.tts import ChatterboxTTS

        started = time.perf_counter()
        base_model = ChatterboxTTS.from_pretrained(device=DEVICE)
        base_model_load_seconds = round(time.perf_counter() - started, 3)
    return base_model


def build_voice_backend_registry() -> VoiceBackendRegistry:
    registry = VoiceBackendRegistry()

    def turbo_generate(*, text: str, ref_audio: Path, params: dict[str, Any]):
        conditioning = prepare_voice_conditioning(ref_audio, params)
        wav = model.generate(text, audio_prompt_path=None, **params)
        return wav, model.sr, conditioning

    def affect_generate(*, text: str, ref_audio: Path, knobs: dict[str, Any]):
        base = get_base_model()
        wav = base.generate(
            text,
            audio_prompt_path=str(ref_audio),
            exaggeration=float(knobs["exaggeration"]),
            cfg_weight=float(knobs["cfg_weight"]),
            temperature=float(knobs["temperature"]),
        )
        conditioning = {
            "reference_audio": str(ref_audio),
            "engine": "chatterbox_base",
            "emotion_knobs": knobs,
        }
        return wav, base.sr, conditioning

    def unload_base_model() -> None:
        global base_model, base_model_load_seconds
        base_model = None
        base_model_load_seconds = None

    registry.register(
        CallableVoiceBackend(
            caps=VoiceCapabilities(
                backend_id="chatterbox_turbo",
                revision="ResembleAI/chatterbox-turbo",
                voice_cloning=True,
                preset_voices=False,
                structured_affect_axes=False,
                per_segment_delivery=True,
                true_incremental_streaming=False,
                cooperative_inference_cancellation=False,
                stale_output_fencing=True,
                deterministic_seed=False,
                input_sample_formats=("wav_any_sr_reference",),
                output_sample_formats=("wav_float32_24000", "pcm_s16le_24000"),
                estimated_resident_vram_mb=3500,
                max_concurrency=1,
            ),
            loader=lambda: load_model() if model is None else None,
            generator=turbo_generate,
            is_loaded=lambda: model is not None,
        )
    )
    registry.register(
        CallableVoiceBackend(
            caps=VoiceCapabilities(
                backend_id="chatterbox_base_affect",
                revision="ResembleAI/chatterbox",
                voice_cloning=True,
                preset_voices=False,
                structured_affect_axes=True,
                per_segment_delivery=True,
                true_incremental_streaming=False,
                cooperative_inference_cancellation=False,
                stale_output_fencing=True,
                deterministic_seed=False,
                input_sample_formats=("wav_any_sr_reference",),
                output_sample_formats=("wav_float32_24000", "pcm_s16le_24000"),
                estimated_resident_vram_mb=3000,
                max_concurrency=1,
            ),
            loader=lambda: get_base_model() and None,
            generator=affect_generate,
            is_loaded=lambda: base_model is not None,
            unloader=unload_base_model,
        )
    )
    return registry


VOICE_BACKENDS = build_voice_backend_registry()
# Experimental, explicit-only sidecar backend; registration imports no Qwen deps.
from chatterbox.agent.qwen_backend import register_qwen_backend  # noqa: E402

register_qwen_backend(VOICE_BACKENDS)

ENGINE_NAME_BY_BACKEND = {
    "chatterbox_turbo": "chatterbox_turbo",
    "chatterbox_base_affect": "chatterbox_base",
    "qwen3_tts": "qwen3_tts",
}


def select_voice_backend_for_request(
    requested: str | None,
    knobs: dict[str, Any] | None,
) -> tuple[CallableVoiceBackend, dict[str, Any]]:
    """Explicit selection wins and is capability-checked; otherwise weighted
    affect routes to the base model exactly as before."""
    if requested:
        backend = VOICE_BACKENDS.get(requested)
        if knobs and not backend.caps.structured_affect_axes:
            raise UnsupportedCapabilityError(backend.caps.backend_id, "structured_affect_axes")
        selection_source = "request.backend"
    else:
        backend = VOICE_BACKENDS.get("chatterbox_base_affect" if knobs else "chatterbox_turbo")
        selection_source = "affect_auto" if knobs else "default"
    return backend, {
        "id": backend.caps.backend_id,
        "selection_source": selection_source,
        "capability_digest": backend.caps.digest(),
    }


@app.post("/synthesize-emotion")
def synthesize_emotion(request: EmotionRenderRequest) -> dict[str, Any]:
    import torchaudio as ta

    ref = resolve_reference_audio(request.ref_audio) if request.ref_audio else resolve_reference_audio(DEFAULT_REF_AUDIO)
    label = safe_label(request.label or f"emotion-{uuid4().hex[:8]}")
    out_path = OUT_DIR / f"{label}.wav"
    started = time.perf_counter()
    try:
        m = get_base_model()
        with render_lock:
            if request.seed is not None:
                import torch
                torch.manual_seed(int(request.seed))
            wav = m.generate(
                request.text,
                audio_prompt_path=str(ref),
                exaggeration=float(request.exaggeration),
                cfg_weight=float(request.cfg_weight),
                temperature=float(request.temperature),
            )
        ta.save(str(out_path), wav, m.sr)
        os.chmod(out_path, 0o664)
    except Exception as exc:  # noqa: BLE001 - endpoint returns a JSON receipt on failure
        return {
            "ok": False,
            "mocked": False,
            "live": True,
            "engine": "chatterbox_base",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "generation_seconds": round(time.perf_counter() - started, 3),
        }
    generation_seconds = round(time.perf_counter() - started, 3)
    return {
        "ok": True,
        "mocked": False,
        "live": True,
        "engine": "chatterbox_base",
        "honors_exaggeration_cfg_weight": True,
        "requested_device": DEVICE,
        "base_model_load_seconds": base_model_load_seconds,
        "text": request.text,
        "reference_audio": str(ref),
        "params": {
            "exaggeration": request.exaggeration,
            "cfg_weight": request.cfg_weight,
            "temperature": request.temperature,
        },
        "generation_seconds": generation_seconds,
        "audio": str(out_path),
        "audio_metrics": audio_metrics(out_path),
    }


@app.post("/synthesize-batch")
def synthesize_batch(request: SynthesisBatchRequest) -> dict[str, Any]:
    started_total = time.perf_counter()
    batch_events: list[dict[str, Any]] = []
    latency_event(batch_events, "batch_received", started_total)
    batch_label = safe_label(request.label or f"batch-{uuid4().hex[:8]}")
    batch_dir = OUT_DIR / batch_label
    batch_dir.mkdir(parents=True, exist_ok=True)
    batch_voice_delivery = voice_delivery_for_request(request)
    batch_stochasticity = stochasticity_for_request(request)
    hash_failures = declared_chunk_hash_failures(request.render_chunks)
    if hash_failures:
        return {
            "ok": False,
            "mocked": False,
            "live": True,
            "engine": "chatterbox_turbo",
            "batch_label": batch_label,
            "reason": "render_chunk_hash_mismatch",
            "failed_gates": hash_failures,
        }
    batch_knobs = emotion_knobs_from_delivery(batch_voice_delivery)
    try:
        batch_backend, batch_backend_selection = select_voice_backend_for_request(request.backend, batch_knobs)
        apply_tag_handling_backend(batch_voice_delivery, batch_backend.caps.backend_id)
    except UnknownBackendError as exc:
        raise HTTPException(status_code=422, detail={"reason": "unknown_backend", "detail": str(exc)}) from exc
    except UnsupportedCapabilityError as exc:
        raise HTTPException(
            status_code=422,
            detail={"reason": str(exc), "backend": exc.backend_id, "capability": exc.capability},
        ) from exc
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
    plan = compile_render_plan(
        answer_text=request.answer_text,
        render_chunks=request.render_chunks,
        max_chars=request.max_chars,
        pause_after_ms=request.pause_after_ms,
        completion_cue=request.completion_cue,
        arc=request.delivery_arc,
    )
    persist_render_plan_receipt(
        batch_dir,
        plan=plan,
        entry_point="synthesize_batch",
        batch_label=batch_label,
        voice_delivery=batch_voice_delivery,
    )
    applied_controls = applied_controls_for_plan(plan, batch_voice_delivery)
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
            repeat_group_id=request.repeat_group_id,
            tone=request.tone,
            delivery_stage=chunk["delivery_stage"],
            pace=request.pace,
            pause_strategy=request.pause_strategy,
            voice_delivery={**batch_voice_delivery, "delivery_stage": chunk["delivery_stage"]},
            backend=request.backend,
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
                "applied_control": applied_controls[chunk["index"] - 1],
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
            repeat_group_id=request.repeat_group_id,
            tone=request.tone,
            delivery_stage="closing",
            pace=request.pace,
            pause_strategy=request.pause_strategy,
            voice_delivery={**batch_voice_delivery, "delivery_stage": "closing"},
            backend=request.backend,
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
        "engine": cache_material["engine"],
        "batch_label": batch_label,
        "tone": batch_voice_delivery["tone"],
        "requested_tone": batch_voice_delivery["requested_tone"],
        "normalized_tone": batch_voice_delivery["normalized_tone"],
        "delivery_stage": batch_voice_delivery["delivery_stage"],
        "requested_delivery_stage": batch_voice_delivery["requested_delivery_stage"],
        "voice_delivery": batch_voice_delivery,
        "voice_delivery_effect": VOICE_DELIVERY_EFFECT,
        "emotion_knobs": batch_knobs,
        "affect_effect": affect_effect_receipt(batch_voice_delivery, batch_knobs, batch_backend_selection["id"]),
        "tag_handling": batch_voice_delivery["tag_handling"],
        "stochasticity": batch_stochasticity,
        "applied_controls": applied_controls,
        "ignored_turbo_params": sorted(TURBO_IGNORED_PARAMS),
        "cache_key": cache_key,
        "cache_material": cache_material,
        "answer_text_sha256": plan["answer_text_sha256"],
        "render_plan": plan,
        "render_plan_digest": plan["render_plan_digest"],
        "backend": batch_backend_selection,
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


def tau_voice_render_payload_to_batch(
    request: TauVoiceRenderRequest | dict[str, Any],
) -> tuple[SynthesisBatchRequest, dict[str, Any]]:
    if isinstance(request, TauVoiceRenderRequest):
        return synthesis_batch_request_from_tau_voice_render(request)
    if not isinstance(request, dict):
        raise HTTPException(
            status_code=422,
            detail={"reason": "tau_voice_render_request_must_be_json_object"},
        )
    schema = request.get("schema", TAU_VOICE_RENDER_REQUEST_V1)
    if schema == TAU_VOICE_RENDER_REQUEST_V1:
        try:
            parsed = TauVoiceRenderRequest.model_validate(request)
        except ValidationError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "reason": "invalid_tau_voice_render_v1_block",
                    "detail": summarize_validation_error(exc),
                },
            ) from exc
        return synthesis_batch_request_from_tau_voice_render(parsed)
    if schema == TAU_VOICE_RENDER_REQUEST_V2:
        block = parse_tau_voice_render_v2(request)
        return synthesis_batch_request_from_tau_voice_render_v2(request, block)
    raise HTTPException(
        status_code=422,
        detail={
            "reason": "unsupported_tau_voice_render_schema",
            "schema": schema,
            "supported_schemas": list(SUPPORTED_TAU_VOICE_RENDER_REQUEST_SCHEMAS),
        },
    )


@app.post("/tau/voice-render")
def tau_voice_render(request: dict[str, Any] | TauVoiceRenderRequest) -> dict[str, Any]:
    batch_request, tau_receipt = tau_voice_render_payload_to_batch(request)
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
        "request_lineage_digest": tau_receipt.get("request_lineage_digest"),
        "consumer_lineage_digest": tau_receipt.get("consumer_lineage_digest"),
        "consumer_digest_matches": (
            tau_receipt.get("request_lineage_digest")
            == tau_receipt.get("consumer_lineage_digest")
            if tau_receipt.get("request_lineage_digest")
            else None
        ),
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
    hash_failures = declared_chunk_hash_failures(request.render_chunks)
    if hash_failures:
        raise HTTPException(
            status_code=422,
            detail={"reason": "render_chunk_hash_mismatch", "failed_gates": hash_failures},
        )
    batch_label = safe_label(request.label or f"stream-{uuid4().hex[:8]}")
    batch_dir = OUT_DIR / batch_label
    batch_dir.mkdir(parents=True, exist_ok=True)
    stream_voice_delivery = voice_delivery_for_request(request)
    try:
        stream_backend, stream_backend_selection = select_voice_backend_for_request(
            request.backend, emotion_knobs_from_delivery(stream_voice_delivery)
        )
        apply_tag_handling_backend(stream_voice_delivery, stream_backend.caps.backend_id)
    except UnknownBackendError as exc:
        raise HTTPException(status_code=422, detail={"reason": "unknown_backend", "detail": str(exc)}) from exc
    except UnsupportedCapabilityError as exc:
        raise HTTPException(
            status_code=422,
            detail={"reason": str(exc), "backend": exc.backend_id, "capability": exc.capability},
        ) from exc
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
        plan = compile_render_plan(
            answer_text=blessed_qra_lookup["answer_text"],
            render_chunks=blessed_render_chunks(blessed_qra_lookup),
            max_chars=request.max_chars,
            pause_after_ms=0,
            completion_cue=None,
        )
    else:
        plan = compile_render_plan(
            answer_text=request.answer_text,
            render_chunks=request.render_chunks,
            max_chars=request.max_chars,
            pause_after_ms=request.pause_after_ms,
            completion_cue=request.completion_cue,
            arc=request.delivery_arc,
        )
    persist_render_plan_receipt(
        batch_dir,
        plan=plan,
        entry_point="synthesize_batch_stream",
        batch_label=batch_label,
        voice_delivery=stream_voice_delivery,
    )
    stream_id = f"stream-{uuid4().hex[:16]}"
    manifest = StreamManifest(
        batch_dir / f"stream_manifest_{stream_id}.json",
        stream_id=stream_id,
        header={
            "batch_label": batch_label,
            "entry_point": "synthesize_batch_stream",
            "request_digest": sha256_text(
                json.dumps(request.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
            ),
            "render_plan_digest": plan["render_plan_digest"],
            "lineage": {
                "turn_id": request.turn_id,
                "repeat_group_id": request.repeat_group_id,
            },
            "backend": {
                **stream_backend_selection,
                "engine": "chatterbox_turbo",
                "device": DEVICE,
                "server_started_at_utc": started_at_utc,
            },
            "output_format": {
                "encoding": "pcm_s16le",
                "sample_rate": STREAM_SAMPLE_RATE,
                "channels": STREAM_CHANNELS,
                "publication_frame_ms": STREAM_PUBLICATION_FRAME_MS,
            },
            "blessed_qra_hit": bool(blessed_qra_lookup.get("hit")),
            "planned_segment_count": plan["chunk_count"],
        },
    )
    register_stream_manifest(stream_id, manifest.path)
    totals = {"published_bytes": 0, "published_frames": 0}

    def pcm_bytes(wav: Any) -> bytes:
        import torch

        clipped = torch.clamp(wav, -1.0, 1.0)
        pcm = (clipped * 32767.0).to(torch.int16).contiguous()
        return pcm.squeeze(0).cpu().numpy().tobytes()

    def stop_if_turn_controlled() -> bool:
        return stream_turn_should_stop(request.turn_id)

    def guarded_pcm_chunks(wav: Any, sample_rate: int = STREAM_SAMPLE_RATE):
        for frame in bounded_pcm_frames(
            pcm_bytes(wav),
            stop_if_turn_controlled,
            sample_rate=sample_rate,
        ):
            totals["published_bytes"] += len(frame)
            totals["published_frames"] += 1
            yield frame

    def produce():
        import torch
        import torchaudio as ta

        if blessed_qra_lookup.get("hit"):
            for index, chunk in enumerate(blessed_qra_lookup["chunks"], start=1):
                if stop_if_turn_controlled():
                    return
                wav, sr = ta.load(str(chunk["audio"]))
                yield from guarded_pcm_chunks(wav, sr)
                manifest.record("cached_segment_published", segment_index=index)
                pause_ms = int(chunk.get("pause_after_ms") or 0) if request.blessed_qra_preserve_pauses else 0
                if pause_ms > 0:
                    silence_len = int(sr * (pause_ms / 1000))
                    if silence_len > 0:
                        yield from guarded_pcm_chunks(torch.zeros((1, silence_len), dtype=torch.float32), sr)
            return
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
                    "is_completion_cue": True,
                }
        )

        for item in stream_items:
            if stop_if_turn_controlled():
                return
            chunk_request = SynthesisRequest(
                text=item["text"],
                ref_audio=request.ref_audio,
                label=f"{batch_label}_stream_{item['index']:02d}",
                repeat_group_id=request.repeat_group_id,
                tone=request.tone,
                delivery_stage=item.get("delivery_stage"),
                pace=request.pace,
                pause_strategy=request.pause_strategy,
                voice_delivery={**stream_voice_delivery, "delivery_stage": item.get("delivery_stage")},
                backend=request.backend,
            )
            out_path = batch_dir / f"stream_{item['index']:02d}_{item.get('delivery_stage', 'neutral')}.wav"
            result = synthesize_to_file(chunk_request, out_path)
            if not result.get("ok"):
                manifest.record(
                    "segment_synthesis_failed",
                    segment_index=item["index"],
                    is_completion_cue=bool(item.get("is_completion_cue")),
                )
                raise StreamSegmentSynthesisError(f"chunk_{item['index']}_synthesis_ok")
            manifest.record(
                "segment_synthesized",
                segment_index=item["index"],
                is_completion_cue=bool(item.get("is_completion_cue")),
            )
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
                    yield from guarded_pcm_chunks(pending_tail, sample_rate or STREAM_SAMPLE_RATE)
                if fade_len > 0 and wav.shape[1] > fade_len:
                    if stop_if_turn_controlled():
                        return
                    yield from guarded_pcm_chunks(wav[:, :-fade_len], sample_rate or STREAM_SAMPLE_RATE)
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
                    yield from guarded_pcm_chunks(
                        pending_tail * fade_out + current_head * fade_in,
                        sample_rate or STREAM_SAMPLE_RATE,
                    )
                    if stop_if_turn_controlled():
                        return
                    yield from guarded_pcm_chunks(
                        wav[:, fade_len:-fade_len] if wav.shape[1] > 2 * fade_len else wav[:, fade_len:],
                        sample_rate or STREAM_SAMPLE_RATE,
                    )
                    pending_tail = wav[:, -fade_len:] if wav.shape[1] > fade_len else None
                else:
                    if stop_if_turn_controlled():
                        return
                    yield from guarded_pcm_chunks(pending_tail, sample_rate or STREAM_SAMPLE_RATE)
                    if stop_if_turn_controlled():
                        return
                    yield from guarded_pcm_chunks(wav[:, :-fade_len], sample_rate or STREAM_SAMPLE_RATE)
                    pending_tail = wav[:, -fade_len:]
            pause_ms = int(item.get("pause_after_ms") or 0)
            if pause_ms > 0 and sample_rate:
                silence_len = int(sample_rate * (pause_ms / 1000))
                if silence_len > 0:
                    if stop_if_turn_controlled():
                        return
                    yield from guarded_pcm_chunks(
                        torch.zeros((1, silence_len), dtype=torch.float32),
                        sample_rate or STREAM_SAMPLE_RATE,
                    )
        if pending_tail is not None:
            if stop_if_turn_controlled():
                return
            yield from guarded_pcm_chunks(pending_tail, sample_rate or STREAM_SAMPLE_RATE)

    def iter_audio():
        try:
            yield from produce()
        except GeneratorExit:
            manifest.finalize("cancelled", reason="client_disconnected", **totals)
            raise
        except StreamSegmentSynthesisError as exc:
            manifest.finalize(
                "failed",
                reason="segment_synthesis_failed",
                failed_gates=[str(exc)],
                **totals,
            )
            return
        except Exception as exc:
            manifest.finalize(
                "failed",
                reason=f"producer_exception:{type(exc).__name__}",
                **totals,
            )
            raise
        state = turn_controls.get(request.turn_id) if request.turn_id else None
        if state and (state.get("cancelled") or state.get("stopped")):
            manifest.finalize(
                "cancelled",
                reason="turn_cancelled" if state.get("cancelled") else "turn_stopped",
                control_state={key: value for key, value in state.items() if key != "events"},
                **totals,
            )
        else:
            manifest.finalize("completed", **totals)

    return StreamingResponse(
        iter_audio(),
        media_type="audio/L16; rate=24000; channels=1",
        headers={
            "X-Render-Plan-Digest": plan["render_plan_digest"],
            "X-Batch-Label": batch_label,
            "X-Stream-Id": stream_id,
        },
    )


@app.post("/turn/{turn_id}/cancel")
def cancel_turn(turn_id: str, request: TurnControlRequest) -> dict[str, Any]:
    return mark_turn_control(turn_id, "cancel", request)


@app.post("/playback/{turn_id}/duck")
def duck_playback(turn_id: str, request: TurnControlRequest) -> dict[str, Any]:
    return mark_turn_control(turn_id, "duck", request)


@app.post("/playback/{turn_id}/stop")
def stop_playback(turn_id: str, request: TurnControlRequest) -> dict[str, Any]:
    return mark_turn_control(turn_id, "stop", request)
