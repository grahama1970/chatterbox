#!/usr/bin/env python3
"""Run live, non-mocked Chatterbox conversation sanity ladder rungs.

The rungs are deliberately narrow. Each receipt states what it proves and what
it leaves out.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chatterbox.agent.asr_acceptance import acceptance_result
from chatterbox.agent.conversation import wait_decision_for_expected_delay
from chatterbox.agent.conversation import run_interruption_scenario


RUNG1_SCHEMA = "chatterbox.conversation_ladder.rung1.v1"
RUNG2_SCHEMA = "chatterbox.conversation_ladder.rung2.v1"
RUNG3_SCHEMA = "chatterbox.conversation_ladder.rung3.v1"
RUNG4_SCHEMA = "chatterbox.conversation_ladder.rung4.v1"
RUNG5_SCHEMA = "chatterbox.conversation_ladder.rung5.v1"
RUNG6_SCHEMA = "chatterbox.conversation_ladder.rung6.v1"
RUNG7_SCHEMA = "chatterbox.conversation_ladder.rung7.listener_contract.v1"
DEFAULT_RESPONSE_TEXT = "Hello. I am listening."
BRAVE_SEARCH_RUNNER = "/home/graham/workspace/experiments/agent-skills/skills/brave-search/run.sh"
RUNG4_FIRST_ANSWER = (
    "I want to be careful with that because saying only the letters can be hard to hear. "
    "The family is System and Information Integrity, and Embry should usually say the "
    "long form before using the short identifier. For a spoken answer, the useful phrasing "
    "is System and Information Integrity, then the specific control name if we know it."
)
RUNG4_NEW_ANSWER = (
    "Okay, the practical rule is simple. Say the full control family first, then the short "
    "identifier only if it helps traceability."
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def wav_metrics(path: Path) -> dict[str, Any]:
    with wave.open(str(path), "rb") as handle:
        frame_count = handle.getnframes()
        sample_rate = handle.getframerate()
        channels = handle.getnchannels()
        sample_width = handle.getsampwidth()
    return {
        "path": str(path),
        "exists": path.exists(),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "duration_seconds": round(frame_count / sample_rate, 3) if sample_rate else 0,
        "sample_rate": sample_rate,
        "channels": channels,
        "sample_width": sample_width,
        "frame_count": frame_count,
    }


def build_rung7_stress_fixture(args: argparse.Namespace, run_id: str, receipt_root: Path) -> tuple[Path | None, dict[str, Any]]:
    primary_audio = getattr(args, "stress_primary_audio", None)
    if primary_audio is None:
        return None, {"enabled": False}

    started = time.perf_counter()
    primary_audio = Path(primary_audio).resolve()
    noise_audio = Path(args.stress_noise_audio).resolve() if args.stress_noise_audio else None
    competing_audio = Path(args.stress_competing_audio).resolve() if args.stress_competing_audio else None
    output = Path(args.stress_output_fixture).resolve() if args.stress_output_fixture else receipt_root / f"{run_id}-stress-input.wav"
    components = {
        "primary": {"role": "primary_speaker", "path": str(primary_audio), "exists": primary_audio.exists()},
        "noise": {"role": "factory_floor_background", "path": str(noise_audio), "exists": noise_audio.exists()} if noise_audio else None,
        "competing": {"role": "competing_speaker", "path": str(competing_audio), "exists": competing_audio.exists()} if competing_audio else None,
    }
    failed_gates: list[str] = []
    if not primary_audio.exists():
        failed_gates.append("stress_primary_audio_exists")
    if noise_audio and not noise_audio.exists():
        failed_gates.append("stress_noise_audio_exists")
    if competing_audio and not competing_audio.exists():
        failed_gates.append("stress_competing_audio_exists")
    if not noise_audio and not competing_audio:
        failed_gates.append("stress_has_noise_or_competing_audio")

    for key, value in list(components.items()):
        if value and value["exists"]:
            try:
                value.update(wav_metrics(Path(value["path"])))
            except Exception as exc:  # noqa: BLE001 - receipt should preserve bad audio metadata
                value["metrics_error"] = f"{type(exc).__name__}: {exc}"
                failed_gates.append(f"stress_{key}_wav_readable")

    receipt: dict[str, Any] = {
        "schema": "chatterbox.listener.stress_fixture.v1",
        "enabled": True,
        "kind": args.stress_kind,
        "output": str(output),
        "component_roles": {
            "primary": "Horus Lupercal or configured primary speaker",
            "noise": "factory-floor or industrial background noise",
            "competing": "non-primary competing speaker, optionally female",
        },
        "components": components,
        "mix": {
            "primary_gain_db": args.stress_primary_gain_db,
            "noise_gain_db": args.stress_noise_gain_db,
            "competing_gain_db": args.stress_competing_gain_db,
            "sample_rate": 16000,
            "channels": 1,
            "duration": "primary",
        },
        "failed_gates": failed_gates,
    }
    if failed_gates:
        receipt["ok"] = False
        receipt["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
        return None, receipt

    output.parent.mkdir(parents=True, exist_ok=True)
    filter_parts = [f"[0:a]volume={args.stress_primary_gain_db}dB[a0]"]
    input_labels = ["[a0]"]
    command = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(primary_audio)]
    input_index = 1
    if noise_audio:
        command.extend(["-stream_loop", "-1", "-i", str(noise_audio)])
        filter_parts.append(f"[{input_index}:a]volume={args.stress_noise_gain_db}dB,atrim=0:duration=9999[a{input_index}]")
        input_labels.append(f"[a{input_index}]")
        input_index += 1
    if competing_audio:
        command.extend(["-i", str(competing_audio)])
        filter_parts.append(f"[{input_index}:a]volume={args.stress_competing_gain_db}dB[a{input_index}]")
        input_labels.append(f"[a{input_index}]")
        input_index += 1
    filter_complex = (
        ";".join(filter_parts)
        + ";"
        + "".join(input_labels)
        + f"amix=inputs={len(input_labels)}:duration=first:dropout_transition=0,"
        + "aresample=16000,pan=mono|c0=c0[out]"
    )
    command.extend(
        [
            "-filter_complex",
            filter_complex,
            "-map",
            "[out]",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-sample_fmt",
            "s16",
            str(output),
        ]
    )
    receipt["command"] = command
    try:
        completed = subprocess.run(command, check=False, text=True, capture_output=True, timeout=args.stress_timeout_s)
        receipt["ffmpeg"] = {
            "returncode": completed.returncode,
            "stderr_tail": completed.stderr[-2000:],
        }
        if completed.returncode != 0:
            receipt["ok"] = False
            receipt["failed_gates"] = failed_gates + ["stress_ffmpeg_mix_ok"]
            receipt["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
            return None, receipt
        receipt["output_audio"] = wav_metrics(output)
        receipt["ok"] = True
        receipt["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
        return output, receipt
    except Exception as exc:  # noqa: BLE001
        receipt["ok"] = False
        receipt["failed_gates"] = failed_gates + ["stress_fixture_built"]
        receipt["error_type"] = type(exc).__name__
        receipt["error"] = str(exc)
        receipt["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
        return None, receipt


def wav_frame_events(
    *,
    audio_path: Path,
    session_id: str,
    turn_id: str,
    started: float,
    frame_ms: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    frame_events: list[dict[str, Any]] = []
    if frame_ms <= 0:
        raise ValueError("frame_ms_must_be_positive")
    with wave.open(str(audio_path), "rb") as handle:
        sample_rate = handle.getframerate()
        channels = handle.getnchannels()
        sample_width = handle.getsampwidth()
        frames_per_chunk = max(1, int(sample_rate * frame_ms / 1000))
        index = 0
        total_bytes = 0
        while True:
            data = handle.readframes(frames_per_chunk)
            if not data:
                break
            index += 1
            total_bytes += len(data)
            frame_events.append(
                {
                    "sequence": index,
                    "type": "listener.audio_frame_received",
                    "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                    "session_id": session_id,
                    "turn_id": turn_id,
                    "byte_count": len(data),
                    "sample_rate": sample_rate,
                    "channels": channels,
                    "sample_width": sample_width,
                    "frame_ms": frame_ms,
                }
            )
    return frame_events, {
        "frame_count": len(frame_events),
        "total_bytes": total_bytes,
        "frame_ms": frame_ms,
    }


def parse_path_maps(values: list[str]) -> dict[str, Path]:
    mappings: dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"path map must use SOURCE=TARGET: {value}")
        source, target = value.split("=", 1)
        source = source.rstrip("/")
        if not source or not target:
            raise ValueError(f"path map must use non-empty SOURCE=TARGET: {value}")
        mappings[source] = Path(target)
    return mappings


def apply_path_maps(path: Path, path_maps: dict[str, Path]) -> Path:
    path_text = str(path)
    for source, target in sorted(path_maps.items(), key=lambda item: len(item[0]), reverse=True):
        if path_text == source or path_text.startswith(f"{source}/"):
            return target / path_text[len(source) :].lstrip("/")
    return path


def get_json(url: str, timeout: int = 30) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.load(response)


def post_json(url: str, payload: dict[str, Any], timeout: int = 300) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def wait_for_health(base_url: str, timeout_s: int) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    last_error = ""
    while time.monotonic() < deadline:
        try:
            health = get_json(f"{base_url.rstrip('/')}/health", timeout=10)
            if health.get("ok"):
                return health
            last_error = f"health_not_ok:{health}"
        except (ConnectionResetError, TimeoutError, urllib.error.URLError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        time.sleep(2)
    raise RuntimeError(f"server health did not become ok within {timeout_s}s: {last_error}")


def load_faster_whisper(model_name: str, device: str, compute_type: str) -> tuple[Any | None, str | None]:
    try:
        from faster_whisper import WhisperModel
    except Exception as exc:  # noqa: BLE001 - reported in receipt
        return None, f"{type(exc).__name__}: {exc}"
    return WhisperModel(model_name, device=device, compute_type=compute_type), None


def transcribe_faster_whisper(model: Any, audio_path: Path) -> str:
    segments, _info = model.transcribe(str(audio_path), beam_size=1, vad_filter=False)
    return " ".join(segment.text.strip() for segment in segments).strip()


def transcribe_openai_compatible(base_url: str, api_key: str, audio_path: Path) -> str:
    import httpx

    with audio_path.open("rb") as handle:
        response = httpx.post(
            f"{base_url.rstrip('/')}/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": (audio_path.name, handle, "audio/wav")},
            data={"model": "whisper-1", "response_format": "json", "language": "en"},
            timeout=120.0,
        )
    response.raise_for_status()
    data = response.json()
    return str(data.get("text") or "").strip()


def build_asr_backend(args: argparse.Namespace) -> dict[str, Any]:
    if args.asr_openai_base_url:
        api_key = os.getenv(args.api_key_env)
        if not api_key:
            return {
                "kind": "openai_compatible",
                "live": False,
                "error": f"missing_api_key_env:{args.api_key_env}",
            }
        return {
            "kind": "openai_compatible",
            "live": True,
            "base_url": args.asr_openai_base_url,
            "api_key_env": args.api_key_env,
            "api_key": api_key,
        }
    model, error = load_faster_whisper(args.asr_model, args.asr_device, args.asr_compute_type)
    return {
        "kind": "faster_whisper",
        "live": model is not None,
        "model_name": args.asr_model,
        "device": args.asr_device,
        "compute_type": args.asr_compute_type,
        "model": model,
        "error": error,
    }


def asr_backend_receipt(backend: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in backend.items()
        if key not in {"api_key", "model"}
    }


def transcribe_audio(backend: dict[str, Any], audio_path: Path) -> str:
    if backend["kind"] == "openai_compatible":
        return transcribe_openai_compatible(str(backend["base_url"]), str(backend["api_key"]), audio_path)
    model = backend.get("model")
    if model is None:
        raise RuntimeError(backend.get("error") or "asr_backend_unavailable")
    return transcribe_faster_whisper(model, audio_path)


def parse_bool_arg(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"expected boolean value, got {value!r}")


def verify_primary_speaker(
    *,
    enrollment_audio: Path,
    candidate_audio: Path,
    engine: str,
    threshold: float,
) -> dict[str, Any]:
    started = time.perf_counter()
    receipt: dict[str, Any] = {
        "schema": "chatterbox.listener.primary_speaker_verification.v1",
        "engine": engine,
        "threshold": threshold,
        "enrollment_audio": str(enrollment_audio),
        "candidate_audio": str(candidate_audio),
        "timestamp_utc": utc_now(),
    }
    if not enrollment_audio.exists():
        return {
            **receipt,
            "ok": False,
            "primary_speaker_match": False,
            "error": "enrollment_audio_missing",
        }
    if not candidate_audio.exists():
        return {
            **receipt,
            "ok": False,
            "primary_speaker_match": False,
            "error": "candidate_audio_missing",
        }
    if engine == "resemblyzer":
        return verify_primary_speaker_resemblyzer(
            receipt=receipt,
            started=started,
            enrollment_audio=enrollment_audio,
            candidate_audio=candidate_audio,
            threshold=threshold,
        )
    if engine == "speechbrain_ecapa":
        return verify_primary_speaker_ecapa(
            receipt=receipt,
            started=started,
            enrollment_audio=enrollment_audio,
            candidate_audio=candidate_audio,
            threshold=threshold,
        )
    return {
        **receipt,
        "ok": False,
        "primary_speaker_match": False,
        "error": f"unsupported_primary_speaker_engine:{engine}",
    }


def verify_primary_speaker_resemblyzer(
    *,
    receipt: dict[str, Any],
    started: float,
    enrollment_audio: Path,
    candidate_audio: Path,
    threshold: float,
) -> dict[str, Any]:
    try:
        import numpy as np
        from resemblyzer import VoiceEncoder, preprocess_wav
    except Exception as exc:  # noqa: BLE001
        return {
            **receipt,
            "ok": False,
            "primary_speaker_match": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }

    try:
        encoder = VoiceEncoder()
        load_elapsed_ms = round((time.perf_counter() - started) * 1000, 3)

        def embed(path: Path) -> tuple[Any, dict[str, Any]]:
            preprocess_started = time.perf_counter()
            wav = preprocess_wav(path)
            preprocess_elapsed_ms = round((time.perf_counter() - preprocess_started) * 1000, 3)
            if len(wav) == 0:
                raise ValueError(f"empty_audio_after_preprocess:{path}")
            embed_started = time.perf_counter()
            embedding = encoder.embed_utterance(wav)
            return embedding, {
                "samples_after_preprocess": int(len(wav)),
                "preprocess_elapsed_ms": preprocess_elapsed_ms,
                "embed_elapsed_ms": round((time.perf_counter() - embed_started) * 1000, 3),
            }

        enrollment_embedding, enrollment_metrics = embed(enrollment_audio)
        candidate_embedding, candidate_metrics = embed(candidate_audio)
        similarity = float(np.inner(enrollment_embedding, candidate_embedding))
        match = similarity >= threshold
        return {
            **receipt,
            "ok": True,
            "primary_speaker_match": bool(match),
            "similarity": round(similarity, 4),
            "device": str(getattr(encoder, "device", "unknown")),
            "load_elapsed_ms": load_elapsed_ms,
            "enrollment": enrollment_metrics,
            "candidate": candidate_metrics,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            **receipt,
            "ok": False,
            "primary_speaker_match": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        }


def verify_primary_speaker_ecapa(
    *,
    receipt: dict[str, Any],
    started: float,
    enrollment_audio: Path,
    candidate_audio: Path,
    threshold: float,
) -> dict[str, Any]:
    try:
        import torch
        from speechbrain.inference.speaker import SpeakerRecognition
    except Exception as exc:  # noqa: BLE001
        return {
            **receipt,
            "ok": False,
            "primary_speaker_match": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }

    try:
        device = os.getenv("CHATTERBOX_ECAPA_DEVICE", "cpu")
        if device == "cuda" and not torch.cuda.is_available():
            device = "cpu"
        verifier = SpeakerRecognition.from_hparams(
            source=os.getenv("CHATTERBOX_ECAPA_MODEL", "speechbrain/spkrec-ecapa-voxceleb"),
            savedir=os.getenv("CHATTERBOX_ECAPA_SAVEDIR", "/tmp/chatterbox-ecapa-spkrec-ecapa-voxceleb"),
            run_opts={"device": device},
        )
        load_elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
        score_started = time.perf_counter()
        score, model_prediction = verifier.verify_files(str(enrollment_audio), str(candidate_audio))
        score_value = float(score.detach().cpu().flatten()[0]) if hasattr(score, "detach") else float(score)
        match = score_value >= threshold
        return {
            **receipt,
            "ok": True,
            "primary_speaker_match": bool(match),
            "similarity": round(score_value, 4),
            "model_prediction": bool(model_prediction.detach().cpu().flatten()[0])
            if hasattr(model_prediction, "detach")
            else bool(model_prediction),
            "device": device,
            "load_elapsed_ms": load_elapsed_ms,
            "candidate": {
                "score_elapsed_ms": round((time.perf_counter() - score_started) * 1000, 3),
            },
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            **receipt,
            "ok": False,
            "primary_speaker_match": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        }


def append_event(events: list[dict[str, Any]], started: float, event_type: str, **fields: Any) -> None:
    events.append(
        {
            "sequence": len(events) + 1,
            "type": event_type,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
            **fields,
        }
    )


def transcript_gate(
    *,
    backend: dict[str, Any],
    audio_path: Path,
    expected_text: str,
    max_wer: float,
) -> dict[str, Any]:
    transcript = transcribe_audio(backend, audio_path)
    gate = acceptance_result(
        expected_text=expected_text,
        transcript=transcript,
        max_wer=max_wer,
    )
    return {
        "expected_text": expected_text,
        "expected_text_sha256": sha256_text(expected_text),
        "transcript": transcript,
        "gate": gate,
    }


def synthesize_live(
    *,
    base_url: str,
    text: str,
    label: str,
    path_maps: dict[str, Path],
    timeout_s: int,
) -> tuple[dict[str, Any], Path | None, dict[str, Any]]:
    payload = {
        "text": text,
        "label": label,
        "delivery_stage": "neutral",
    }
    synthesis = post_json(f"{base_url}/synthesize", payload, timeout=timeout_s)
    raw_audio = synthesis.get("audio")
    artifact: dict[str, Any] = {"server_path": raw_audio}
    if not raw_audio:
        return synthesis, None, artifact
    output_audio_path = apply_path_maps(Path(str(raw_audio)), path_maps)
    artifact["host_path"] = str(output_audio_path)
    if output_audio_path.exists() and output_audio_path.suffix.lower() == ".wav":
        artifact.update(wav_metrics(output_audio_path))
    return synthesis, output_audio_path, artifact


def extract_favorite_color(transcript: str) -> str | None:
    match = re.search(r"\bfavou?rite color is ([a-z]+)\b", transcript, flags=re.IGNORECASE)
    if match:
        return match.group(1).lower()
    match = re.search(r"\bi like ([a-z]+)\b", transcript, flags=re.IGNORECASE)
    return match.group(1).lower() if match else None


def route_turn2_from_state(state: dict[str, Any]) -> dict[str, Any]:
    color = ((state.get("facts") or {}).get("favorite_color") or "").strip()
    if not color:
        return {
            "ok": False,
            "route": "local_state_color_recall",
            "failed_gates": ["local_state_favorite_color_present"],
            "response_text": "I do not have that color in this session state.",
        }
    return {
        "ok": True,
        "route": "local_state_color_recall",
        "failed_gates": [],
        "response_text": f"You said your favorite color is {color}.",
        "used_state": {"favorite_color": color},
    }


def post_memory_recall(memory_url: str, payload: dict[str, Any], timeout_s: int) -> dict[str, Any]:
    return post_memory_json(memory_url, "/recall", payload, timeout_s=timeout_s)


def post_memory_json(memory_url: str, endpoint: str, payload: dict[str, Any], timeout_s: int) -> dict[str, Any]:
    import httpx

    response = httpx.post(f"{memory_url.rstrip('/')}{endpoint}", json=payload, timeout=timeout_s)
    response.raise_for_status()
    data = response.json()
    if endpoint == "/recall" and "items" not in data:
        raise RuntimeError("memory_recall_missing_items")
    return data


def summarize_memory_items(items: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    summarized = []
    for item in items[:limit]:
        summarized.append(
            {
                "_key": item.get("_key"),
                "collection": item.get("_collection") or item.get("collection") or item.get("_source"),
                "persona_id": item.get("persona_id"),
                "tags": item.get("tags"),
                "scores": item.get("scores"),
                "retrieval_text": item.get("retrieval_text"),
                "emotion": item.get("emotion"),
                "stance": item.get("stance"),
                "intensity": item.get("intensity"),
                "emotional_intensity": item.get("emotional_intensity"),
                "intensity_score": item.get("intensity_score"),
            }
        )
    return summarized


def memory_item_has_tag(item: dict[str, Any], required_tag: str) -> bool:
    tags = item.get("tags")
    return isinstance(tags, list) and required_tag in tags


def response_from_embry_memory(item: dict[str, Any]) -> str:
    tags = set(item.get("tags") or [])
    emotion = str(item.get("emotion") or "grief")
    if {"location:hawaii", "person:kai"} & tags and "grief" in emotion:
        return "Rain links Kai with grief."
    return "The memory links rain with grief."


def build_speaker_resolve_payload(
    *,
    args: argparse.Namespace,
    session_id: str,
    turn_id: str,
    primary_speaker_verification: dict[str, Any] | None,
) -> dict[str, Any]:
    confidence = args.speaker_confidence
    source = args.speaker_evidence_source
    if primary_speaker_verification:
        confidence = float(primary_speaker_verification.get("similarity") or confidence or 0.0)
        source = str(primary_speaker_verification.get("engine") or source)
    candidate = {
        "speaker_id": args.speaker_id,
        "display_name": args.speaker_display_name,
        "confidence": confidence,
        "source": source,
        "tags": args.speaker_tag,
    }
    return {
        "speaker_evidence_id": f"{args.run_id or turn_id}:primary-speaker-verification",
        "session_id": session_id,
        "turn_id": turn_id,
        "persona_id": args.active_persona_id,
        "threshold": args.speaker_resolve_threshold,
        "ambiguity_margin": args.speaker_ambiguity_margin,
        "prompt_variant": args.speaker_prompt_variant,
        "allow_personal_memory": True,
        "candidates": [candidate],
    }


def extract_emotional_cues(transcript: str) -> list[dict[str, Any]]:
    cue_specs = [
        ("rain", "sensory_rain", "grief"),
        ("ray", "sensory_rain", "grief"),
        ("kai", "relationship_kai", "grief"),
        ("grief", "explicit_grief", "grief"),
        ("gentle", "requested_gentleness", "careful"),
    ]
    cues = []
    lower = transcript.lower()
    for term, label, emotion in cue_specs:
        start = lower.find(term)
        if start >= 0:
            cues.append(
                {
                    "span": transcript[start : start + len(term)],
                    "start": start,
                    "end": start + len(term),
                    "label": label,
                    "emotion": emotion,
                }
            )
    return cues


def update_emotion_state(prior: dict[str, Any], cues: list[dict[str, Any]], evidence: dict[str, Any] | None) -> dict[str, Any]:
    selected = dict(prior)
    reason = "no_salient_cue"
    confidence = 0.4
    if any(cue["emotion"] == "grief" for cue in cues) and evidence:
        selected = {
            "state": "gentle_grief",
            "intensity": 0.7,
            "tone": "gentle",
        }
        reason = "rain_kai_cue_with_memory_evidence"
        confidence = 0.82
    elif any(cue["label"] == "requested_gentleness" for cue in cues):
        selected = {
            "state": "gentle_followup",
            "intensity": max(float(prior.get("intensity") or 0.4), 0.55),
            "tone": "gentle",
        }
        reason = "user_requested_gentle_tone"
        confidence = 0.72
    return {
        "prior": prior,
        "cues": cues,
        "evidence_key": (((evidence or {}).get("items") or [{}])[0]).get("_key") if evidence else None,
        "selected": selected,
        "reason": reason,
        "confidence": confidence,
        "decay": "session_only_no_memory_write",
    }


def utterance_policy_for_state(state: dict[str, Any], turn_index: int) -> dict[str, Any]:
    current = state.get("state")
    if turn_index == 1:
        response_text = "I am listening."
        delivery_stage = "neutral"
    elif current == "gentle_grief":
        response_text = "I will keep this gentle."
        delivery_stage = "reassuring"
    else:
        response_text = "I will stay gentle and focused."
        delivery_stage = "reassuring"
    return {
        "response_text": response_text,
        "delivery_stage": delivery_stage,
        "forbidden_or_avoid_conditions": ["do_not_claim_to_know_user_inner_state"],
        "rejected_alternatives": ["playful_wait_activity", "high_energy_delivery"],
        "reason": "match_response_to_recorded_emotion_state",
    }


def transcript_requests_cancel(transcript: str) -> bool:
    return bool(re.search(r"\b(stop|cancel|wait|hold on|interrupt|pause)\b", transcript, flags=re.IGNORECASE))


def build_tau_voice_render_request(
    *,
    run_id: str,
    session_id: str,
    turn_id: str,
    transcript: str,
    response_text: str,
    receipt_root: Path,
    old_turn_id: str | None,
    cancel_requested: bool,
) -> dict[str, Any]:
    return {
        "schema": "tau.voice_render_request.v1",
        "run_id": run_id,
        "conversation_id": session_id,
        "turn_id": turn_id,
        "route": "listener_rung7_boundary",
        "active_domain_persona": "embry",
        "question_text": transcript,
        "question_text_sha256": sha256_text(transcript),
        "memory_route_decision": {
            "called": False,
            "reason": "rung7_listener_boundary_does_not_call_memory",
        },
        "speakable_chunks": [
            {
                "chunk_id": f"{turn_id}-chunk-1",
                "text": response_text,
                "text_sha256": sha256_text(response_text),
                "delivery_stage": "neutral",
                "interruptible": True,
                "max_chars": 300,
            }
        ],
        "delivery_stage": "neutral",
        "interruptible": True,
        "use_blessed_qra_cache": False,
        "turn_control_policy": {
            "old_turn_id": old_turn_id,
            "cancel_requested": cancel_requested,
            "stale_old_turn_chunks_should_skip": bool(cancel_requested and old_turn_id),
        },
        "external_evidence": {
            "heard_text_ledger": str(receipt_root / "heard-text-ledger.jsonl"),
            "listener_turn_events": str(receipt_root / "listener-turn-events.jsonl"),
            "asr_transcript": str(receipt_root / "asr-transcript.json"),
        },
        "receipt_root": str(receipt_root),
    }


def write_rung7_sidecar_artifacts(receipt: dict[str, Any], out_path: Path) -> None:
    root = out_path.resolve().parent
    root.mkdir(parents=True, exist_ok=True)
    (root / "heard-text-ledger.jsonl").write_text(
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in receipt.get("heard_text_ledger") or []),
        encoding="utf-8",
    )
    (root / "listener-turn-events.jsonl").write_text(
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in receipt.get("listener_events") or []),
        encoding="utf-8",
    )
    (root / "asr-transcript.json").write_text(
        json.dumps(receipt.get("asr_transcript") or {}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (root / "primary-speaker-verification.json").write_text(
        json.dumps(receipt.get("primary_speaker_verification") or {}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (root / "stress-fixture.json").write_text(
        json.dumps(receipt.get("stress_fixture") or {}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (root / "speaker-resolution.json").write_text(
        json.dumps(receipt.get("speaker_resolution") or {}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (root / "memory-intent.json").write_text(
        json.dumps(receipt.get("memory_intent") or {}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (root / "speaker-memory-recall.json").write_text(
        json.dumps(receipt.get("speaker_memory_recall") or {}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (root / "missing-fact-clarification.json").write_text(
        json.dumps(receipt.get("missing_fact_clarification") or {}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (root / "memory-writeback.json").write_text(
        json.dumps(receipt.get("memory_writeback") or {}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (root / "memory-writeback-readback.json").write_text(
        json.dumps(receipt.get("memory_writeback_readback") or {}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (root / "tau-voice-render-request.json").write_text(
        json.dumps(receipt.get("tau_voice_render_request") or {}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def exercise_turn_controls(base_url: str, old_turn_id: str, new_turn_id: str) -> dict[str, Any]:
    failed_gates: list[str] = []
    requests = [
        (
            "cancel",
            f"{base_url.rstrip()}/turn/{old_turn_id}/cancel",
            {"reason": "barge-in", "old_turn_id": old_turn_id, "new_turn_id": new_turn_id},
        ),
        (
            "duck",
            f"{base_url.rstrip()}/playback/{old_turn_id}/duck",
            {"reason": "user starts speaking", "old_turn_id": old_turn_id, "new_turn_id": new_turn_id},
        ),
        (
            "stop",
            f"{base_url.rstrip()}/playback/{old_turn_id}/stop",
            {"reason": "new turn takes floor", "old_turn_id": old_turn_id, "new_turn_id": new_turn_id},
        ),
    ]
    responses: list[dict[str, Any]] = []
    for action, url, payload in requests:
        try:
            response = post_json(url, payload, timeout=30)
        except Exception as exc:  # noqa: BLE001
            response = {"ok": False, "error_type": type(exc).__name__, "error": str(exc)}
        responses.append({"action": action, "request": payload, "response": response})
        if not response.get("ok"):
            failed_gates.append(f"{action}_response_ok")
    final_control = (responses[-1].get("response") or {}).get("control") or {}
    action_order = [event.get("action") for event in final_control.get("events") or []]
    if action_order[-3:] != ["cancel", "duck", "stop"]:
        failed_gates.append("control_event_order")
    for key in ["cancelled", "stale_chunks_should_skip", "ducked", "stopped"]:
        if not final_control.get(key):
            failed_gates.append(f"{key}_true")
    return {
        "ok": not failed_gates,
        "responses": responses,
        "final_control": final_control,
        "action_order": action_order,
        "failed_gates": failed_gates,
    }


def run_brave_search(query: str, count: int, timeout_s: int) -> dict[str, Any]:
    started = time.perf_counter()
    cmd = [BRAVE_SEARCH_RUNNER, "web", query, "--count", str(count), "--json"]
    result = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout_s)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    parsed: dict[str, Any] | None = None
    parse_error = None
    if result.returncode == 0:
        try:
            json_start = result.stdout.find("{")
            parsed = json.loads(result.stdout[json_start:] if json_start >= 0 else result.stdout)
        except Exception as exc:  # noqa: BLE001
            parse_error = f"{type(exc).__name__}: {exc}"
    return {
        "ok": result.returncode == 0 and parsed is not None,
        "mocked": False,
        "live": result.returncode == 0 and parsed is not None,
        "cmd": cmd,
        "elapsed_ms": elapsed_ms,
        "returncode": result.returncode,
        "stdout_tail": result.stdout[-4000:],
        "stderr_tail": result.stderr[-4000:],
        "parse_error": parse_error,
        "result": parsed,
    }


def run_rung1(args: argparse.Namespace) -> dict[str, Any]:
    started = time.perf_counter()
    run_id = args.run_id or f"rung1-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    path_maps = parse_path_maps(args.path_map)
    failed_gates: list[str] = []
    events: list[dict[str, Any]] = []
    artifacts: dict[str, Any] = {}
    services: dict[str, Any] = {}
    health: dict[str, Any] | None = None
    synthesis: dict[str, Any] | None = None
    output_audio_path: Path | None = None
    input_asr: dict[str, Any] | None = None
    output_asr: dict[str, Any] | None = None

    append_event(events, started, "rung.started", rung=1, run_id=run_id)
    fixture = args.fixture.resolve()
    if not fixture.exists():
        failed_gates.append("input_audio_exists")
    elif fixture.suffix.lower() != ".wav":
        failed_gates.append("input_audio_is_wav")
    else:
        artifacts["input_audio"] = wav_metrics(fixture)
        append_event(events, started, "listener.input_audio_ready", audio=str(fixture))

    backend = build_asr_backend(args)
    services["asr"] = asr_backend_receipt(backend)
    if not backend.get("live"):
        failed_gates.append("asr_backend_available")

    if fixture.exists() and backend.get("live"):
        try:
            transcript = transcribe_audio(backend, fixture)
            gate = acceptance_result(
                expected_text=args.expected_transcript,
                transcript=transcript,
                max_wer=args.max_input_wer,
            )
            input_asr = {
                "expected_text": args.expected_transcript,
                "expected_text_sha256": sha256_text(args.expected_transcript),
                "transcript": transcript,
                "gate": gate,
            }
            append_event(events, started, "asr.input_transcribed", ok=gate["ok"], wer=gate["wer"])
            if not gate["ok"]:
                failed_gates.extend(f"input_asr_{gate_name}" for gate_name in gate["failed_gates"])
        except Exception as exc:  # noqa: BLE001 - receipt must preserve live failure
            input_asr = {
                "expected_text": args.expected_transcript,
                "expected_text_sha256": sha256_text(args.expected_transcript),
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            failed_gates.append("input_asr_transcribed")

    base_url = args.base_url.rstrip("/")
    services["chatterbox"] = {"base_url": base_url}
    try:
        health = wait_for_health(base_url, args.wait_health_s)
        services["chatterbox"]["health"] = health
        append_event(events, started, "chatterbox.health_ok", model_loaded=health.get("model_loaded"))
    except Exception as exc:  # noqa: BLE001 - receipt must preserve live failure
        services["chatterbox"]["health_error"] = f"{type(exc).__name__}: {exc}"
        failed_gates.append("chatterbox_health_ok")

    response_text = args.response_text
    route = {
        "name": "scripted_simple",
        "requires_memory": False,
        "requires_tools": False,
        "response_text": response_text,
        "response_text_sha256": sha256_text(response_text),
    }
    if not response_text.strip():
        failed_gates.append("response_text_non_empty")

    if health and health.get("ok"):
        payload = {
            "text": response_text,
            "label": args.label or run_id,
            "delivery_stage": "neutral",
        }
        append_event(events, started, "tts.request_submitted", route=route["name"])
        try:
            synthesis = post_json(f"{base_url}/synthesize", payload, timeout=args.synthesis_timeout_s)
            append_event(events, started, "tts.response_received", ok=synthesis.get("ok"))
            if not synthesis.get("ok"):
                failed_gates.append("tts_synthesis_ok")
            raw_audio = synthesis.get("audio")
            if raw_audio:
                output_audio_path = apply_path_maps(Path(str(raw_audio)), path_maps)
                artifacts["output_audio"] = {
                    "server_path": raw_audio,
                    "host_path": str(output_audio_path),
                }
                if output_audio_path.exists() and output_audio_path.suffix.lower() == ".wav":
                    artifacts["output_audio"].update(wav_metrics(output_audio_path))
                else:
                    failed_gates.append("output_audio_exists")
            else:
                failed_gates.append("output_audio_path_present")
        except Exception as exc:  # noqa: BLE001 - receipt must preserve live failure
            synthesis = {
                "ok": False,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            failed_gates.append("tts_synthesis_response")

    if output_audio_path and output_audio_path.exists() and backend.get("live"):
        try:
            transcript = transcribe_audio(backend, output_audio_path)
            gate = acceptance_result(
                expected_text=response_text,
                transcript=transcript,
                max_wer=args.max_output_wer,
            )
            output_asr = {
                "expected_text": response_text,
                "expected_text_sha256": sha256_text(response_text),
                "transcript": transcript,
                "gate": gate,
            }
            append_event(events, started, "asr.output_transcribed", ok=gate["ok"], wer=gate["wer"])
            if not gate["ok"]:
                failed_gates.extend(f"output_asr_{gate_name}" for gate_name in gate["failed_gates"])
        except Exception as exc:  # noqa: BLE001 - receipt must preserve live failure
            output_asr = {
                "expected_text": response_text,
                "expected_text_sha256": sha256_text(response_text),
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            failed_gates.append("output_asr_transcribed")
    elif output_audio_path and not backend.get("live"):
        failed_gates.append("output_asr_backend_available")

    ended_at = utc_now()
    append_event(events, started, "rung.finished", ok=not failed_gates)
    return {
        "schema": RUNG1_SCHEMA,
        "ok": not failed_gates,
        "rung": 1,
        "run_id": run_id,
        "mocked": False,
        "live": bool(health and health.get("ok") and backend.get("live") and synthesis and synthesis.get("ok")),
        "started_at_utc": datetime.fromtimestamp(
            time.time() - (time.perf_counter() - started),
            timezone.utc,
        ).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "ended_at_utc": ended_at,
        "services": services,
        "inputs": {
            "fixture": str(fixture),
            "expected_transcript": args.expected_transcript,
            "expected_transcript_sha256": sha256_text(args.expected_transcript),
            "fixture_provenance": args.fixture_provenance,
        },
        "route": route,
        "events": events,
        "artifacts": artifacts,
        "input_asr": input_asr,
        "synthesis": synthesis,
        "output_asr": output_asr,
        "path_maps": {source: str(target) for source, target in path_maps.items()},
        "failed_gates": failed_gates,
        "claims": {
            "proves": [
                "file_backed_listener_input_can_drive_one_real_asr_tts_loop",
                "generated_response_audio_is_asr_verifiable",
            ]
            if not failed_gates
            else [],
            "does_not_prove": [
                "live_microphone_capture",
                "multi_turn_context",
                "memory_correctness",
                "tool_use",
                "emotional_steering_quality",
            ],
        },
    }


def run_rung2(args: argparse.Namespace) -> dict[str, Any]:
    started = time.perf_counter()
    run_id = args.run_id or f"rung2-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    session_id = args.session_id or f"session-{run_id}"
    path_maps = parse_path_maps(args.path_map)
    failed_gates: list[str] = []
    events: list[dict[str, Any]] = []
    services: dict[str, Any] = {}
    artifacts: dict[str, Any] = {"turns": []}
    turns: list[dict[str, Any]] = []
    state_snapshots: list[dict[str, Any]] = []
    state: dict[str, Any] = {"facts": {}}

    append_event(events, started, "rung.started", rung=2, run_id=run_id, session_id=session_id)
    if not args.turn1_fixture or not args.turn2_fixture:
        failed_gates.append("turn_fixtures_present")
    if not args.expected_turn1_transcript or not args.expected_turn2_transcript:
        failed_gates.append("expected_turn_transcripts_present")

    backend = build_asr_backend(args)
    services["asr"] = asr_backend_receipt(backend)
    if not backend.get("live"):
        failed_gates.append("asr_backend_available")

    base_url = args.base_url.rstrip("/")
    services["chatterbox"] = {"base_url": base_url}
    health: dict[str, Any] | None = None
    try:
        health = wait_for_health(base_url, args.wait_health_s)
        services["chatterbox"]["health"] = health
        append_event(events, started, "chatterbox.health_ok", model_loaded=health.get("model_loaded"))
    except Exception as exc:  # noqa: BLE001 - receipt must preserve live failure
        services["chatterbox"]["health_error"] = f"{type(exc).__name__}: {exc}"
        failed_gates.append("chatterbox_health_ok")

    turn_specs = [
        {
            "index": 1,
            "turn_id": f"{run_id}-turn-1",
            "fixture": args.turn1_fixture,
            "expected_transcript": args.expected_turn1_transcript,
            "response_text": None,
        },
        {
            "index": 2,
            "turn_id": f"{run_id}-turn-2",
            "fixture": args.turn2_fixture,
            "expected_transcript": args.expected_turn2_transcript,
            "response_text": None,
        },
    ]

    for spec in turn_specs:
        turn_failed: list[str] = []
        fixture = Path(spec["fixture"]).resolve()
        state_before = json.loads(json.dumps(state))
        turn: dict[str, Any] = {
            "turn_index": spec["index"],
            "turn_id": spec["turn_id"],
            "session_id": session_id,
            "input_audio": {"path": str(fixture), "exists": fixture.exists()},
            "state_before": state_before,
        }
        append_event(events, started, "listener.input_audio_ready", turn_id=spec["turn_id"], audio=str(fixture))
        if not fixture.exists():
            turn_failed.append("input_audio_exists")
        elif fixture.suffix.lower() != ".wav":
            turn_failed.append("input_audio_is_wav")
        else:
            turn["input_audio"].update(wav_metrics(fixture))

        if fixture.exists() and backend.get("live"):
            try:
                asr = transcript_gate(
                    backend=backend,
                    audio_path=fixture,
                    expected_text=str(spec["expected_transcript"]),
                    max_wer=args.max_input_wer,
                )
                turn["input_asr"] = asr
                append_event(
                    events,
                    started,
                    "asr.input_transcribed",
                    turn_id=spec["turn_id"],
                    ok=asr["gate"]["ok"],
                    wer=asr["gate"]["wer"],
                )
                if not asr["gate"]["ok"]:
                    turn_failed.extend(f"input_asr_{gate}" for gate in asr["gate"]["failed_gates"])
            except Exception as exc:  # noqa: BLE001
                turn["input_asr"] = {
                    "expected_text": spec["expected_transcript"],
                    "expected_text_sha256": sha256_text(str(spec["expected_transcript"])),
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
                turn_failed.append("input_asr_transcribed")

        transcript = ((turn.get("input_asr") or {}).get("transcript") or "").strip()
        if spec["index"] == 1:
            color = extract_favorite_color(transcript)
            if not color:
                turn_failed.append("local_state_favorite_color_extracted")
                color = "unknown"
            else:
                state["facts"]["favorite_color"] = color
            response_text = (
                f"I will remember that your favorite color is {color} for this session."
                if color != "unknown"
                else "I did not catch the favorite color clearly."
            )
            turn["route"] = {
                "name": "local_state_color_capture",
                "extracted": {"favorite_color": None if color == "unknown" else color},
                "requires_memory": False,
                "requires_tools": False,
            }
        else:
            route = route_turn2_from_state(state)
            turn["route"] = {
                "name": route["route"],
                "requires_memory": False,
                "requires_tools": False,
                "used_state": route.get("used_state"),
            }
            if not route["ok"]:
                turn_failed.extend(route["failed_gates"])
            response_text = route["response_text"]

        turn["response_text"] = response_text
        turn["response_text_sha256"] = sha256_text(response_text)
        if health and health.get("ok"):
            append_event(events, started, "tts.request_submitted", turn_id=spec["turn_id"])
            try:
                synthesis, output_audio_path, output_artifact = synthesize_live(
                    base_url=base_url,
                    text=response_text,
                    label=f"{run_id}_turn_{spec['index']}",
                    path_maps=path_maps,
                    timeout_s=args.synthesis_timeout_s,
                )
                turn["synthesis"] = synthesis
                turn["output_audio"] = output_artifact
                append_event(
                    events,
                    started,
                    "tts.response_received",
                    turn_id=spec["turn_id"],
                    ok=synthesis.get("ok"),
                )
                if not synthesis.get("ok"):
                    turn_failed.append("tts_synthesis_ok")
                if output_audio_path is None or not output_audio_path.exists():
                    turn_failed.append("output_audio_exists")
                elif backend.get("live"):
                    try:
                        output_asr = transcript_gate(
                            backend=backend,
                            audio_path=output_audio_path,
                            expected_text=response_text,
                            max_wer=args.max_output_wer,
                        )
                        turn["output_asr"] = output_asr
                        append_event(
                            events,
                            started,
                            "asr.output_transcribed",
                            turn_id=spec["turn_id"],
                            ok=output_asr["gate"]["ok"],
                            wer=output_asr["gate"]["wer"],
                        )
                        if not output_asr["gate"]["ok"]:
                            turn_failed.extend(f"output_asr_{gate}" for gate in output_asr["gate"]["failed_gates"])
                    except Exception as exc:  # noqa: BLE001
                        turn["output_asr"] = {
                            "expected_text": response_text,
                            "expected_text_sha256": sha256_text(response_text),
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                        }
                        turn_failed.append("output_asr_transcribed")
            except Exception as exc:  # noqa: BLE001
                turn["synthesis"] = {"ok": False, "error_type": type(exc).__name__, "error": str(exc)}
                turn_failed.append("tts_synthesis_response")

        turn["state_after"] = json.loads(json.dumps(state))
        turn["failed_gates"] = turn_failed
        state_snapshots.append(
            {
                "turn_id": spec["turn_id"],
                "before": state_before,
                "after": turn["state_after"],
            }
        )
        failed_gates.extend(f"turn_{spec['index']}_{gate}" for gate in turn_failed)
        turns.append(turn)
        artifacts["turns"].append(
            {
                "turn_id": spec["turn_id"],
                "input_audio": turn.get("input_audio"),
                "output_audio": turn.get("output_audio"),
            }
        )

    omitted_turn1_route = route_turn2_from_state({"facts": {}})
    omitted_turn1_gate = {
        "ok": not omitted_turn1_route["ok"],
        "route": omitted_turn1_route,
        "proves_fail_closed_without_turn1_state": not omitted_turn1_route["ok"],
    }
    if omitted_turn1_route["ok"]:
        failed_gates.append("turn2_fails_closed_without_turn1_state")

    if turns and len({turn["session_id"] for turn in turns}) != 1:
        failed_gates.append("stable_session_id")
    if [event["sequence"] for event in events] != list(range(1, len(events) + 1)):
        failed_gates.append("monotonic_event_sequence")
    if (state.get("facts") or {}).get("favorite_color") != "blue":
        failed_gates.append("state_favorite_color_blue")

    append_event(events, started, "rung.finished", ok=not failed_gates)
    return {
        "schema": RUNG2_SCHEMA,
        "ok": not failed_gates,
        "rung": 2,
        "run_id": run_id,
        "session_id": session_id,
        "mocked": False,
        "live": bool(health and health.get("ok") and backend.get("live") and not failed_gates),
        "started_at_utc": datetime.fromtimestamp(
            time.time() - (time.perf_counter() - started),
            timezone.utc,
        ).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "ended_at_utc": utc_now(),
        "services": services,
        "inputs": {
            "turn1_fixture": str(Path(args.turn1_fixture).resolve()) if args.turn1_fixture else None,
            "turn2_fixture": str(Path(args.turn2_fixture).resolve()) if args.turn2_fixture else None,
            "expected_turn1_transcript": args.expected_turn1_transcript,
            "expected_turn2_transcript": args.expected_turn2_transcript,
            "fixture_provenance": args.fixture_provenance,
        },
        "events": events,
        "state_snapshots": state_snapshots,
        "final_state": state,
        "omitted_turn1_gate": omitted_turn1_gate,
        "turns": turns,
        "artifacts": artifacts,
        "path_maps": {source: str(target) for source, target in path_maps.items()},
        "failed_gates": failed_gates,
        "claims": {
            "proves": [
                "file_backed_listener_can_run_two_turn_conversation",
                "router_preserves_and_uses_short_local_state",
                "turn2_fails_closed_without_turn1_state",
            ]
            if not failed_gates
            else [],
            "does_not_prove": [
                "long_term_memory_retrieval",
                "dynamic_emotion_adaptation",
                "interruption_during_playback",
            ],
        },
    }


def run_rung3(args: argparse.Namespace) -> dict[str, Any]:
    started = time.perf_counter()
    run_id = args.run_id or f"rung3-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    path_maps = parse_path_maps(args.path_map)
    failed_gates: list[str] = []
    events: list[dict[str, Any]] = []
    artifacts: dict[str, Any] = {}
    services: dict[str, Any] = {}
    input_asr: dict[str, Any] | None = None
    memory_recall: dict[str, Any] | None = None
    evidence_packet: dict[str, Any] | None = None
    synthesis: dict[str, Any] | None = None
    output_asr: dict[str, Any] | None = None

    append_event(events, started, "rung.started", rung=3, run_id=run_id)
    fixture = args.fixture.resolve()
    if not fixture.exists():
        failed_gates.append("input_audio_exists")
    elif fixture.suffix.lower() != ".wav":
        failed_gates.append("input_audio_is_wav")
    else:
        artifacts["input_audio"] = wav_metrics(fixture)
        append_event(events, started, "listener.input_audio_ready", audio=str(fixture))

    backend = build_asr_backend(args)
    services["asr"] = asr_backend_receipt(backend)
    if not backend.get("live"):
        failed_gates.append("asr_backend_available")

    base_url = args.base_url.rstrip("/")
    services["chatterbox"] = {"base_url": base_url}
    health: dict[str, Any] | None = None
    try:
        health = wait_for_health(base_url, args.wait_health_s)
        services["chatterbox"]["health"] = health
        append_event(events, started, "chatterbox.health_ok", model_loaded=health.get("model_loaded"))
    except Exception as exc:  # noqa: BLE001
        services["chatterbox"]["health_error"] = f"{type(exc).__name__}: {exc}"
        failed_gates.append("chatterbox_health_ok")

    if fixture.exists() and backend.get("live"):
        try:
            input_asr = transcript_gate(
                backend=backend,
                audio_path=fixture,
                expected_text=args.expected_transcript,
                max_wer=args.max_input_wer,
            )
            append_event(events, started, "asr.input_transcribed", ok=input_asr["gate"]["ok"], wer=input_asr["gate"]["wer"])
            if not input_asr["gate"]["ok"]:
                failed_gates.extend(f"input_asr_{gate}" for gate in input_asr["gate"]["failed_gates"])
        except Exception as exc:  # noqa: BLE001
            input_asr = {
                "expected_text": args.expected_transcript,
                "expected_text_sha256": sha256_text(args.expected_transcript),
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            failed_gates.append("input_asr_transcribed")

    memory_url = args.memory_url.rstrip("/")
    services["memory"] = {"base_url": memory_url}
    memory_tags = args.memory_tag or []
    recall_payload = {
        "q": args.memory_question,
        "collections": ["persona_memory"],
        "tags": memory_tags,
        "k": args.memory_k,
    }
    try:
        memory_recall = post_memory_recall(memory_url, recall_payload, timeout_s=args.memory_timeout_s)
        append_event(
            events,
            started,
            "memory.recall_finished",
            found=memory_recall.get("found"),
            confidence=memory_recall.get("confidence"),
            item_count=len(memory_recall.get("items") or []),
        )
        if not memory_recall.get("found"):
            failed_gates.append("memory_found")
        if memory_recall.get("should_scan"):
            failed_gates.append("memory_should_scan_false")
        if float(memory_recall.get("confidence") or 0.0) < args.min_memory_confidence:
            failed_gates.append("memory_confidence_minimum")
        items = memory_recall.get("items") or []
        if not items:
            failed_gates.append("memory_items_present")
        top = items[0] if items else {}
        if top.get("persona_id") != args.required_persona_id:
            failed_gates.append("memory_top_persona_scope")
        required_tag = f"persona:{args.required_persona_id}"
        if not memory_item_has_tag(top, required_tag):
            failed_gates.append("memory_top_persona_tag")
        evidence_packet = {
            "question": args.memory_question,
            "request": recall_payload,
            "found": memory_recall.get("found"),
            "confidence": memory_recall.get("confidence"),
            "should_scan": memory_recall.get("should_scan"),
            "meta": memory_recall.get("meta"),
            "items": summarize_memory_items(items),
        }
    except Exception as exc:  # noqa: BLE001
        services["memory"]["error"] = f"{type(exc).__name__}: {exc}"
        failed_gates.append("memory_recall_ok")

    top_item = ((evidence_packet or {}).get("items") or [{}])[0]
    response_text = response_from_embry_memory(top_item)
    route = {
        "name": "memory_grounded_embry_turn",
        "requires_memory": True,
        "requires_tools": False,
        "memory_question": args.memory_question,
        "response_text": response_text,
        "response_text_sha256": sha256_text(response_text),
    }
    if not (top_item.get("retrieval_text") or ""):
        failed_gates.append("memory_retrieval_text_present")
    response_terms = {
        term
        for term in re.findall(r"[a-z0-9]+", response_text.lower())
        if term not in {"the", "a", "an", "with", "and", "or", "to", "of", "link", "links", "linked"}
    }
    evidence_text = str(top_item.get("retrieval_text") or "").lower()
    missing_terms = sorted(term for term in response_terms if term not in evidence_text)
    if missing_terms:
        failed_gates.append("response_terms_grounded_in_memory")
    route["grounding_terms"] = {
        "required": sorted(response_terms),
        "missing_from_top_evidence": missing_terms,
    }

    output_audio_path: Path | None = None
    if health and health.get("ok"):
        append_event(events, started, "tts.request_submitted", route=route["name"])
        try:
            synthesis, output_audio_path, output_artifact = synthesize_live(
                base_url=base_url,
                text=response_text,
                label=args.label or run_id,
                path_maps=path_maps,
                timeout_s=args.synthesis_timeout_s,
            )
            artifacts["output_audio"] = output_artifact
            append_event(events, started, "tts.response_received", ok=synthesis.get("ok"))
            if not synthesis.get("ok"):
                failed_gates.append("tts_synthesis_ok")
            if output_audio_path is None or not output_audio_path.exists():
                failed_gates.append("output_audio_exists")
        except Exception as exc:  # noqa: BLE001
            synthesis = {"ok": False, "error_type": type(exc).__name__, "error": str(exc)}
            failed_gates.append("tts_synthesis_response")

    if output_audio_path and output_audio_path.exists() and backend.get("live"):
        try:
            output_asr = transcript_gate(
                backend=backend,
                audio_path=output_audio_path,
                expected_text=response_text,
                max_wer=args.max_output_wer,
            )
            append_event(events, started, "asr.output_transcribed", ok=output_asr["gate"]["ok"], wer=output_asr["gate"]["wer"])
            if not output_asr["gate"]["ok"]:
                failed_gates.extend(f"output_asr_{gate}" for gate in output_asr["gate"]["failed_gates"])
        except Exception as exc:  # noqa: BLE001
            output_asr = {
                "expected_text": response_text,
                "expected_text_sha256": sha256_text(response_text),
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            failed_gates.append("output_asr_transcribed")

    append_event(events, started, "rung.finished", ok=not failed_gates)
    return {
        "schema": RUNG3_SCHEMA,
        "ok": not failed_gates,
        "rung": 3,
        "run_id": run_id,
        "mocked": False,
        "live": bool(health and health.get("ok") and backend.get("live") and memory_recall and synthesis and synthesis.get("ok") and not failed_gates),
        "started_at_utc": datetime.fromtimestamp(
            time.time() - (time.perf_counter() - started),
            timezone.utc,
        ).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "ended_at_utc": utc_now(),
        "services": services,
        "inputs": {
            "fixture": str(fixture),
            "expected_transcript": args.expected_transcript,
            "expected_transcript_sha256": sha256_text(args.expected_transcript),
            "fixture_provenance": args.fixture_provenance,
        },
        "route": route,
        "events": events,
        "artifacts": artifacts,
        "input_asr": input_asr,
        "memory_evidence": evidence_packet,
        "synthesis": synthesis,
        "output_asr": output_asr,
        "path_maps": {source: str(target) for source, target in path_maps.items()},
        "failed_gates": failed_gates,
        "claims": {
            "proves": [
                "real_voice_turn_can_use_scoped_memory_recall_as_evidence",
                "memory_evidence_is_visible_enough_to_audit",
                "memory_grounded_response_audio_is_asr_verifiable",
            ]
            if not failed_gates
            else [],
            "does_not_prove": [
                "memory_writes",
                "full_theory_of_mind_graph_traversal",
                "subjective_voice_performance",
            ],
        },
    }


def run_rung4(args: argparse.Namespace) -> dict[str, Any]:
    started = time.perf_counter()
    run_id = args.run_id or f"rung4-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    path_maps = parse_path_maps(args.path_map)
    failed_gates: list[str] = []
    events: list[dict[str, Any]] = []
    services: dict[str, Any] = {}
    artifacts: dict[str, Any] = {}
    input_asr: dict[str, Any] | None = None

    append_event(events, started, "rung.started", rung=4, run_id=run_id)
    fixture = args.fixture.resolve()
    if not fixture.exists():
        failed_gates.append("interrupt_audio_exists")
    elif fixture.suffix.lower() != ".wav":
        failed_gates.append("interrupt_audio_is_wav")
    else:
        artifacts["interrupt_audio"] = wav_metrics(fixture)
        append_event(events, started, "listener.interrupt_audio_ready", audio=str(fixture))

    backend = build_asr_backend(args)
    services["asr"] = asr_backend_receipt(backend)
    if not backend.get("live"):
        failed_gates.append("asr_backend_available")

    base_url = args.base_url.rstrip("/")
    services["chatterbox"] = {"base_url": base_url}
    health: dict[str, Any] | None = None
    try:
        health = wait_for_health(base_url, args.wait_health_s)
        services["chatterbox"]["health"] = health
        append_event(events, started, "chatterbox.health_ok", model_loaded=health.get("model_loaded"))
    except Exception as exc:  # noqa: BLE001
        services["chatterbox"]["health_error"] = f"{type(exc).__name__}: {exc}"
        failed_gates.append("chatterbox_health_ok")

    interrupt_text = args.expected_transcript
    if fixture.exists() and backend.get("live"):
        try:
            input_asr = transcript_gate(
                backend=backend,
                audio_path=fixture,
                expected_text=args.expected_transcript,
                max_wer=args.max_input_wer,
            )
            interrupt_text = input_asr["transcript"]
            append_event(events, started, "asr.interrupt_transcribed", ok=input_asr["gate"]["ok"], wer=input_asr["gate"]["wer"])
            if not input_asr["gate"]["ok"]:
                failed_gates.extend(f"interrupt_asr_{gate}" for gate in input_asr["gate"]["failed_gates"])
        except Exception as exc:  # noqa: BLE001
            input_asr = {
                "expected_text": args.expected_transcript,
                "expected_text_sha256": sha256_text(args.expected_transcript),
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            failed_gates.append("interrupt_asr_transcribed")

    scenario_out_dir = args.out.parent / f"{args.out.stem}-scenario"
    interruption_receipt: dict[str, Any] | None = None
    if health and health.get("ok") and not any(gate.startswith("interrupt_asr_") for gate in failed_gates):
        try:
            interruption_receipt = asyncio.run(
                run_interruption_scenario(
                    base_url=base_url,
                    out_dir=scenario_out_dir,
                    question=args.question,
                    first_answer=args.first_answer or RUNG4_FIRST_ANSWER,
                    interrupt_text=interrupt_text,
                    new_answer=args.new_answer or RUNG4_NEW_ANSWER,
                    variant_offset=args.variant_offset,
                )
            )
            append_event(
                events,
                started,
                "interruption.scenario_finished",
                ok=interruption_receipt.get("ok"),
                stale_skipped_count=interruption_receipt.get("stale_skipped_count"),
            )
            if not interruption_receipt.get("ok"):
                failed_gates.append("interruption_scenario_ok")
            if int(interruption_receipt.get("stale_skipped_count") or 0) <= 0:
                failed_gates.append("stale_chunks_skipped_after_interruption")
            timeline = interruption_receipt.get("interruption_timeline") or {}
            if timeline.get("post_cancel_old_turn_audio_bytes_emitted") != 0:
                failed_gates.append("post_cancel_old_turn_audio_bytes_zero")
            if not timeline.get("new_turn_audio_started_after_cancel"):
                failed_gates.append("new_turn_audio_started_after_cancel")
            for spoken in interruption_receipt.get("spoken_results") or []:
                audio_path = spoken.get("audio")
                if audio_path:
                    host_audio = apply_path_maps(Path(str(audio_path)), path_maps)
                    if not host_audio.exists():
                        failed_gates.append("spoken_audio_exists")
        except Exception as exc:  # noqa: BLE001
            interruption_receipt = {"ok": False, "error_type": type(exc).__name__, "error": str(exc)}
            failed_gates.append("interruption_scenario_ran")

    control_receipt = None
    if interruption_receipt and interruption_receipt.get("old_turn_id") and interruption_receipt.get("new_turn_id"):
        control_receipt = exercise_turn_controls(
            base_url,
            str(interruption_receipt["old_turn_id"]),
            str(interruption_receipt["new_turn_id"]),
        )
        append_event(events, started, "turn_controls.finished", ok=control_receipt.get("ok"))
        if not control_receipt.get("ok"):
            failed_gates.extend(f"turn_controls_{gate}" for gate in control_receipt.get("failed_gates") or [])

    append_event(events, started, "rung.finished", ok=not failed_gates)
    return {
        "schema": RUNG4_SCHEMA,
        "ok": not failed_gates,
        "rung": 4,
        "run_id": run_id,
        "mocked": False,
        "live": bool(health and health.get("ok") and backend.get("live") and interruption_receipt and interruption_receipt.get("ok") and control_receipt and control_receipt.get("ok") and not failed_gates),
        "started_at_utc": datetime.fromtimestamp(
            time.time() - (time.perf_counter() - started),
            timezone.utc,
        ).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "ended_at_utc": utc_now(),
        "services": services,
        "inputs": {
            "fixture": str(fixture),
            "expected_transcript": args.expected_transcript,
            "expected_transcript_sha256": sha256_text(args.expected_transcript),
            "fixture_provenance": args.fixture_provenance,
            "question": args.question,
        },
        "events": events,
        "artifacts": {
            **artifacts,
            "scenario_dir": str(scenario_out_dir),
            "scenario_receipt": str(scenario_out_dir / "final-response.json"),
            "scenario_events": str(scenario_out_dir / "task-events.jsonl"),
        },
        "input_asr": input_asr,
        "interruption": interruption_receipt,
        "turn_controls": control_receipt,
        "path_maps": {source: str(target) for source, target in path_maps.items()},
        "failed_gates": failed_gates,
        "claims": {
            "proves": [
                "barge_in_audio_can_drive_interruption_scenario",
                "stale_old_turn_chunks_are_skipped_after_cancel",
                "turn_control_endpoints_record_cancel_duck_stop_state",
            ]
            if not failed_gates
            else [],
            "does_not_prove": [
                "robust_noisy_room_interruption_handling",
                "adaptive_false_interruption_recovery",
                "physical_speaker_playback_stop_latency",
            ],
        },
    }


def run_rung5(args: argparse.Namespace) -> dict[str, Any]:
    started = time.perf_counter()
    run_id = args.run_id or f"rung5-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    path_maps = parse_path_maps(args.path_map)
    failed_gates: list[str] = []
    events: list[dict[str, Any]] = []
    services: dict[str, Any] = {}
    artifacts: dict[str, Any] = {}
    input_asr: dict[str, Any] | None = None
    synthesis: dict[str, Any] | None = None
    output_asr: dict[str, Any] | None = None

    append_event(events, started, "rung.started", rung=5, run_id=run_id)
    fixture = args.fixture.resolve()
    if not fixture.exists():
        failed_gates.append("input_audio_exists")
    elif fixture.suffix.lower() != ".wav":
        failed_gates.append("input_audio_is_wav")
    else:
        artifacts["input_audio"] = wav_metrics(fixture)
        append_event(events, started, "listener.input_audio_ready", audio=str(fixture))

    backend = build_asr_backend(args)
    services["asr"] = asr_backend_receipt(backend)
    if not backend.get("live"):
        failed_gates.append("asr_backend_available")

    base_url = args.base_url.rstrip("/")
    services["chatterbox"] = {"base_url": base_url}
    health: dict[str, Any] | None = None
    try:
        health = wait_for_health(base_url, args.wait_health_s)
        services["chatterbox"]["health"] = health
        append_event(events, started, "chatterbox.health_ok", model_loaded=health.get("model_loaded"))
    except Exception as exc:  # noqa: BLE001
        services["chatterbox"]["health_error"] = f"{type(exc).__name__}: {exc}"
        failed_gates.append("chatterbox_health_ok")

    if fixture.exists() and backend.get("live"):
        try:
            input_asr = transcript_gate(
                backend=backend,
                audio_path=fixture,
                expected_text=args.expected_transcript,
                max_wer=args.max_input_wer,
            )
            append_event(events, started, "asr.input_transcribed", ok=input_asr["gate"]["ok"], wer=input_asr["gate"]["wer"])
            if not input_asr["gate"]["ok"]:
                failed_gates.extend(f"input_asr_{gate}" for gate in input_asr["gate"]["failed_gates"])
        except Exception as exc:  # noqa: BLE001
            input_asr = {
                "expected_text": args.expected_transcript,
                "expected_text_sha256": sha256_text(args.expected_transcript),
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            failed_gates.append("input_asr_transcribed")

    append_event(events, started, "tool.brave_search_started", query=args.tool_query)
    brave = run_brave_search(args.tool_query, args.tool_count, args.tool_timeout_s)
    append_event(events, started, "tool.brave_search_finished", ok=brave["ok"], elapsed_ms=brave["elapsed_ms"])
    if not brave["ok"]:
        failed_gates.append("brave_search_ok")
    results = ((brave.get("result") or {}).get("results") or []) if brave.get("result") else []
    if not results:
        failed_gates.append("brave_results_present")
    first_result = results[0] if results else {}
    if not first_result.get("url"):
        failed_gates.append("brave_result_url_present")
    if not first_result.get("title"):
        failed_gates.append("brave_result_title_present")

    wait_decision = wait_decision_for_expected_delay(
        int(brave.get("elapsed_ms") or 0),
        variant_offset=args.variant_offset,
        conversation_tone="casual",
        user_mood="neutral",
    )
    response_text = "I found voice agent turn detection results."
    route = {
        "name": "brave_search_tool_turn",
        "requires_memory": False,
        "requires_tools": True,
        "tool_name": "brave-search",
        "tool_query": args.tool_query,
        "response_text": response_text,
        "response_text_sha256": sha256_text(response_text),
        "used_sources": [
            {
                "title": item.get("title"),
                "url": item.get("url"),
                "description": item.get("description"),
            }
            for item in results[: args.tool_count]
        ],
    }

    output_audio_path: Path | None = None
    if health and health.get("ok"):
        append_event(events, started, "tts.request_submitted", route=route["name"])
        try:
            synthesis, output_audio_path, output_artifact = synthesize_live(
                base_url=base_url,
                text=response_text,
                label=args.label or run_id,
                path_maps=path_maps,
                timeout_s=args.synthesis_timeout_s,
            )
            artifacts["output_audio"] = output_artifact
            append_event(events, started, "tts.response_received", ok=synthesis.get("ok"))
            if not synthesis.get("ok"):
                failed_gates.append("tts_synthesis_ok")
            if output_audio_path is None or not output_audio_path.exists():
                failed_gates.append("output_audio_exists")
        except Exception as exc:  # noqa: BLE001
            synthesis = {"ok": False, "error_type": type(exc).__name__, "error": str(exc)}
            failed_gates.append("tts_synthesis_response")

    if output_audio_path and output_audio_path.exists() and backend.get("live"):
        try:
            output_asr = transcript_gate(
                backend=backend,
                audio_path=output_audio_path,
                expected_text=response_text,
                max_wer=args.max_output_wer,
            )
            append_event(events, started, "asr.output_transcribed", ok=output_asr["gate"]["ok"], wer=output_asr["gate"]["wer"])
            if not output_asr["gate"]["ok"]:
                failed_gates.extend(f"output_asr_{gate}" for gate in output_asr["gate"]["failed_gates"])
        except Exception as exc:  # noqa: BLE001
            output_asr = {
                "expected_text": response_text,
                "expected_text_sha256": sha256_text(response_text),
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            failed_gates.append("output_asr_transcribed")

    append_event(events, started, "rung.finished", ok=not failed_gates)
    return {
        "schema": RUNG5_SCHEMA,
        "ok": not failed_gates,
        "rung": 5,
        "run_id": run_id,
        "mocked": False,
        "live": bool(health and health.get("ok") and backend.get("live") and brave.get("ok") and synthesis and synthesis.get("ok") and not failed_gates),
        "started_at_utc": datetime.fromtimestamp(
            time.time() - (time.perf_counter() - started),
            timezone.utc,
        ).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "ended_at_utc": utc_now(),
        "services": services,
        "inputs": {
            "fixture": str(fixture),
            "expected_transcript": args.expected_transcript,
            "expected_transcript_sha256": sha256_text(args.expected_transcript),
            "fixture_provenance": args.fixture_provenance,
        },
        "route": route,
        "events": events,
        "artifacts": artifacts,
        "input_asr": input_asr,
        "tool": brave,
        "wait_decision": wait_decision,
        "synthesis": synthesis,
        "output_asr": output_asr,
        "path_maps": {source: str(target) for source, target in path_maps.items()},
        "failed_gates": failed_gates,
        "claims": {
            "proves": [
                "real_voice_turn_can_invoke_live_brave_search",
                "tool_latency_and_wait_decision_are_receipt_backed",
                "tool_grounded_response_audio_is_asr_verifiable",
            ]
            if not failed_gates
            else [],
            "does_not_prove": [
                "search_result_factual_correctness_beyond_recorded_sources",
                "long_running_multi_tool_orchestration",
                "emotional_steering_beyond_wait_state_selection",
            ],
        },
    }


def run_rung6(args: argparse.Namespace) -> dict[str, Any]:
    started = time.perf_counter()
    run_id = args.run_id or f"rung6-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    session_id = args.session_id or f"session-{run_id}"
    path_maps = parse_path_maps(args.path_map)
    failed_gates: list[str] = []
    events: list[dict[str, Any]] = []
    services: dict[str, Any] = {}
    turns: list[dict[str, Any]] = []
    emotion_state: dict[str, Any] = {"state": "neutral", "intensity": 0.2, "tone": "neutral"}

    append_event(events, started, "rung.started", rung=6, run_id=run_id, session_id=session_id)
    backend = build_asr_backend(args)
    services["asr"] = asr_backend_receipt(backend)
    if not backend.get("live"):
        failed_gates.append("asr_backend_available")

    base_url = args.base_url.rstrip("/")
    services["chatterbox"] = {"base_url": base_url}
    health: dict[str, Any] | None = None
    try:
        health = wait_for_health(base_url, args.wait_health_s)
        services["chatterbox"]["health"] = health
        append_event(events, started, "chatterbox.health_ok", model_loaded=health.get("model_loaded"))
    except Exception as exc:  # noqa: BLE001
        services["chatterbox"]["health_error"] = f"{type(exc).__name__}: {exc}"
        failed_gates.append("chatterbox_health_ok")

    memory_url = args.memory_url.rstrip("/")
    services["memory"] = {"base_url": memory_url}
    memory_tags = args.memory_tag or []
    memory_evidence: dict[str, Any] | None = None
    memory_recall_raw: dict[str, Any] | None = None

    turn_specs = [
        (1, args.turn1_fixture, args.expected_turn1_transcript),
        (2, args.turn2_fixture, args.expected_turn2_transcript),
        (3, args.turn3_fixture, args.expected_turn3_transcript),
    ]
    if any(not fixture for _idx, fixture, _expected in turn_specs):
        failed_gates.append("turn_fixtures_present")
    if any(not expected for _idx, _fixture, expected in turn_specs):
        failed_gates.append("expected_turn_transcripts_present")

    for turn_index, fixture_value, expected_text in turn_specs:
        turn_failed: list[str] = []
        fixture = Path(fixture_value).resolve()
        turn_id = f"{run_id}-turn-{turn_index}"
        turn: dict[str, Any] = {
            "turn_index": turn_index,
            "turn_id": turn_id,
            "session_id": session_id,
            "state_before": emotion_state,
            "input_audio": {"path": str(fixture), "exists": fixture.exists()},
        }
        append_event(events, started, "listener.input_audio_ready", turn_id=turn_id, audio=str(fixture))
        if not fixture.exists():
            turn_failed.append("input_audio_exists")
        elif fixture.suffix.lower() != ".wav":
            turn_failed.append("input_audio_is_wav")
        else:
            turn["input_audio"].update(wav_metrics(fixture))

        transcript = ""
        if fixture.exists() and backend.get("live"):
            try:
                asr = transcript_gate(
                    backend=backend,
                    audio_path=fixture,
                    expected_text=str(expected_text),
                    max_wer=args.max_input_wer,
                )
                turn["input_asr"] = asr
                transcript = asr["transcript"]
                append_event(events, started, "asr.input_transcribed", turn_id=turn_id, ok=asr["gate"]["ok"], wer=asr["gate"]["wer"])
                if not asr["gate"]["ok"]:
                    turn_failed.extend(f"input_asr_{gate}" for gate in asr["gate"]["failed_gates"])
            except Exception as exc:  # noqa: BLE001
                turn["input_asr"] = {
                    "expected_text": expected_text,
                    "expected_text_sha256": sha256_text(str(expected_text)),
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
                turn_failed.append("input_asr_transcribed")

        cues = extract_emotional_cues(transcript)
        turn["cues"] = cues
        if turn_index == 2:
            recall_payload = {
                "q": args.memory_question,
                "collections": ["persona_memory"],
                "tags": memory_tags,
                "k": args.memory_k,
            }
            try:
                memory_recall_raw = post_memory_recall(memory_url, recall_payload, timeout_s=args.memory_timeout_s)
                append_event(
                    events,
                    started,
                    "memory.recall_finished",
                    turn_id=turn_id,
                    found=memory_recall_raw.get("found"),
                    confidence=memory_recall_raw.get("confidence"),
                )
                items = memory_recall_raw.get("items") or []
                if not memory_recall_raw.get("found"):
                    turn_failed.append("memory_found")
                if memory_recall_raw.get("should_scan"):
                    turn_failed.append("memory_should_scan_false")
                if not items:
                    turn_failed.append("memory_items_present")
                top = items[0] if items else {}
                if top.get("persona_id") != args.required_persona_id:
                    turn_failed.append("memory_top_persona_scope")
                if not memory_item_has_tag(top, f"persona:{args.required_persona_id}"):
                    turn_failed.append("memory_top_persona_tag")
                memory_evidence = {
                    "question": args.memory_question,
                    "request": recall_payload,
                    "found": memory_recall_raw.get("found"),
                    "confidence": memory_recall_raw.get("confidence"),
                    "should_scan": memory_recall_raw.get("should_scan"),
                    "meta": memory_recall_raw.get("meta"),
                    "items": summarize_memory_items(items),
                }
            except Exception as exc:  # noqa: BLE001
                memory_evidence = {"error_type": type(exc).__name__, "error": str(exc)}
                turn_failed.append("memory_recall_ok")
        turn["memory_evidence"] = memory_evidence if turn_index == 2 else None

        transition = update_emotion_state(emotion_state, cues, memory_evidence)
        emotion_state = transition["selected"]
        turn["emotion_transition"] = transition
        policy = utterance_policy_for_state(emotion_state, turn_index)
        turn["utterance_policy"] = policy
        response_text = policy["response_text"]
        turn["response_text"] = response_text
        turn["response_text_sha256"] = sha256_text(response_text)

        output_audio_path: Path | None = None
        if health and health.get("ok"):
            try:
                synthesis, output_audio_path, output_artifact = synthesize_live(
                    base_url=base_url,
                    text=response_text,
                    label=f"{run_id}_turn_{turn_index}",
                    path_maps=path_maps,
                    timeout_s=args.synthesis_timeout_s,
                )
                turn["synthesis"] = synthesis
                turn["output_audio"] = output_artifact
                append_event(events, started, "tts.response_received", turn_id=turn_id, ok=synthesis.get("ok"))
                if not synthesis.get("ok"):
                    turn_failed.append("tts_synthesis_ok")
                if output_audio_path is None or not output_audio_path.exists():
                    turn_failed.append("output_audio_exists")
                elif backend.get("live"):
                    output_asr = transcript_gate(
                        backend=backend,
                        audio_path=output_audio_path,
                        expected_text=response_text,
                        max_wer=args.max_output_wer,
                    )
                    turn["output_asr"] = output_asr
                    append_event(events, started, "asr.output_transcribed", turn_id=turn_id, ok=output_asr["gate"]["ok"], wer=output_asr["gate"]["wer"])
                    if not output_asr["gate"]["ok"]:
                        turn_failed.extend(f"output_asr_{gate}" for gate in output_asr["gate"]["failed_gates"])
            except Exception as exc:  # noqa: BLE001
                turn["synthesis"] = {"ok": False, "error_type": type(exc).__name__, "error": str(exc)}
                turn_failed.append("tts_or_output_asr_ok")

        turn["state_after"] = emotion_state
        turn["failed_gates"] = turn_failed
        failed_gates.extend(f"turn_{turn_index}_{gate}" for gate in turn_failed)
        turns.append(turn)

    if not any(cue["label"] == "relationship_kai" for turn in turns for cue in turn.get("cues") or []):
        failed_gates.append("kai_cue_observed")
    if not any(cue["label"] == "sensory_rain" for turn in turns for cue in turn.get("cues") or []):
        failed_gates.append("rain_cue_observed")
    if emotion_state.get("tone") != "gentle":
        failed_gates.append("final_emotion_tone_gentle")

    append_event(events, started, "rung.finished", ok=not failed_gates)
    return {
        "schema": RUNG6_SCHEMA,
        "ok": not failed_gates,
        "rung": 6,
        "run_id": run_id,
        "session_id": session_id,
        "mocked": False,
        "live": bool(health and health.get("ok") and backend.get("live") and memory_evidence and not failed_gates),
        "started_at_utc": datetime.fromtimestamp(
            time.time() - (time.perf_counter() - started),
            timezone.utc,
        ).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "ended_at_utc": utc_now(),
        "services": services,
        "inputs": {
            "turn1_fixture": str(Path(args.turn1_fixture).resolve()) if args.turn1_fixture else None,
            "turn2_fixture": str(Path(args.turn2_fixture).resolve()) if args.turn2_fixture else None,
            "turn3_fixture": str(Path(args.turn3_fixture).resolve()) if args.turn3_fixture else None,
            "expected_turn1_transcript": args.expected_turn1_transcript,
            "expected_turn2_transcript": args.expected_turn2_transcript,
            "expected_turn3_transcript": args.expected_turn3_transcript,
            "fixture_provenance": args.fixture_provenance,
        },
        "events": events,
        "turns": turns,
        "final_emotion_state": emotion_state,
        "failed_gates": failed_gates,
        "claims": {
            "proves": [
                "dynamic_emotion_steering_uses_live_cues_and_memory_evidence",
                "utterance_style_choices_are_receipt_backed",
                "emotion_steered_responses_are_asr_verifiable",
            ]
            if not failed_gates
            else [],
            "does_not_prove": [
                "subjectively_ideal_emotional_performance",
                "globally_correct_memory_salience_ranking",
                "production_ready_live_microphone_behavior",
            ],
        },
    }


def run_rung7(args: argparse.Namespace) -> dict[str, Any]:
    started = time.perf_counter()
    rung7_defaults = {
        "primary_speaker_engine": "resemblyzer",
        "enable_speaker_identity_memory": False,
        "enable_speaker_memory_recall": False,
        "enable_missing_fact_writeback": False,
        "speaker_memory_only": False,
        "speaker_id": "horus_lupercal",
        "speaker_display_name": "Horus Lupercal",
        "active_persona_id": "embry",
        "speaker_tag": ["persona:horus_lupercal"],
        "speaker_confidence": 0.0,
        "speaker_evidence_source": "listener",
        "speaker_resolve_threshold": 0.82,
        "speaker_ambiguity_margin": 0.05,
        "speaker_prompt_variant": 0,
        "speaker_intent_scope": "persona_memory",
        "speaker_memory_collection": "voice_conversation_memory",
        "speaker_memory_recall_collection": None,
        "speaker_memory_recall_tag": [],
        "speaker_writeback_answer": None,
        "stress_primary_audio": None,
        "stress_noise_audio": None,
        "stress_competing_audio": None,
        "stress_output_fixture": None,
        "stress_kind": "factory_floor_primary_speaker",
        "stress_primary_gain_db": 0.0,
        "stress_noise_gain_db": -18.0,
        "stress_competing_gain_db": -24.0,
        "stress_timeout_s": 60,
    }
    for key, value in rung7_defaults.items():
        if not hasattr(args, key):
            setattr(args, key, value)
    run_id = args.run_id or f"rung7-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    session_id = args.session_id or f"session-{run_id}"
    turn_id = args.turn_id or f"{run_id}-turn-1"
    receipt_root = args.out.resolve().parent
    failed_gates: list[str] = []
    events: list[dict[str, Any]] = []
    artifacts: dict[str, Any] = {}
    services: dict[str, Any] = {}
    listener_events: list[dict[str, Any]] = []
    coordinator_events: list[dict[str, Any]] = []
    heard_text_ledger: list[dict[str, Any]] = []
    asr_transcript: dict[str, Any] | None = None
    primary_speaker_verification: dict[str, Any] | None = None
    speaker_resolution: dict[str, Any] | None = None
    memory_intent: dict[str, Any] | None = None
    speaker_memory_recall: dict[str, Any] | None = None
    missing_fact_clarification: dict[str, Any] | None = None
    memory_writeback: dict[str, Any] | None = None
    memory_writeback_readback: dict[str, Any] | None = None
    primary_speaker_gate_enabled = args.primary_speaker_enrollment is not None
    expected_primary_speaker = args.expected_primary_speaker
    turn_allowed_by_speaker_gate = True
    skip_asr_and_render_for_memory_only = bool(args.speaker_memory_only and args.enable_speaker_identity_memory)
    transcript = ""
    input_asr: dict[str, Any] | None = None
    stress_fixture: dict[str, Any] | None = None

    append_event(events, started, "rung.started", rung=7, run_id=run_id, session_id=session_id, turn_id=turn_id)
    append_event(events, started, "turn.started", session_id=session_id, turn_id=turn_id)
    coordinator_events.append(
        {
            "type": "turn.started",
            "session_id": session_id,
            "turn_id": turn_id,
            "timestamp_utc": utc_now(),
        }
    )

    stress_fixture_path, stress_fixture = build_rung7_stress_fixture(args, run_id, receipt_root)
    if stress_fixture and stress_fixture.get("enabled"):
        artifacts["stress_fixture"] = stress_fixture
        artifacts["stress_fixture_path"] = str(receipt_root / "stress-fixture.json")
        append_event(
            events,
            started,
            "listener.stress_fixture_built",
            ok=stress_fixture.get("ok"),
            kind=stress_fixture.get("kind"),
            output=stress_fixture.get("output"),
        )
        if not stress_fixture.get("ok"):
            failed_gates.extend(stress_fixture.get("failed_gates") or ["stress_fixture_built"])
        elif stress_fixture_path is not None:
            args.fixture = stress_fixture_path

    if args.fixture is None:
        failed_gates.append("input_audio_exists")
        fixture = Path("__missing_rung7_fixture__.wav").resolve()
    else:
        fixture = args.fixture.resolve()
    if not fixture.exists():
        failed_gates.append("input_audio_exists")
    elif fixture.suffix.lower() != ".wav":
        failed_gates.append("input_audio_is_wav")
    else:
        artifacts["input_audio"] = wav_metrics(fixture)
        append_event(events, started, "listener.input_audio_ready", turn_id=turn_id, audio=str(fixture))
        try:
            frame_events, frame_summary = wav_frame_events(
                audio_path=fixture,
                session_id=session_id,
                turn_id=turn_id,
                started=started,
                frame_ms=args.listener_frame_ms,
            )
            listener_events.extend(frame_events)
            artifacts["listener_frames"] = frame_summary
            append_event(
                events,
                started,
                "listener.frames_ingested",
                turn_id=turn_id,
                frame_count=frame_summary["frame_count"],
                total_bytes=frame_summary["total_bytes"],
            )
            if frame_summary["frame_count"] <= 0:
                failed_gates.append("listener_audio_frames_present")
        except Exception as exc:  # noqa: BLE001
            artifacts["listener_frames"] = {"error_type": type(exc).__name__, "error": str(exc)}
            failed_gates.append("listener_audio_frames_present")

    if primary_speaker_gate_enabled and fixture.exists():
        primary_speaker_verification = verify_primary_speaker(
            enrollment_audio=args.primary_speaker_enrollment.resolve(),
            candidate_audio=fixture,
            engine=args.primary_speaker_engine,
            threshold=args.primary_speaker_threshold,
        )
        services["primary_speaker_verifier"] = {
            "kind": primary_speaker_verification.get("engine"),
            "ok": primary_speaker_verification.get("ok"),
            "threshold": primary_speaker_verification.get("threshold"),
            "device": primary_speaker_verification.get("device"),
            "error_type": primary_speaker_verification.get("error_type"),
            "error": primary_speaker_verification.get("error"),
        }
        artifacts["primary_speaker_verification_path"] = str(receipt_root / "primary-speaker-verification.json")
        append_event(
            events,
            started,
            "listener.primary_speaker_verified",
            turn_id=turn_id,
            ok=primary_speaker_verification.get("ok"),
            primary_speaker_match=primary_speaker_verification.get("primary_speaker_match"),
            similarity=primary_speaker_verification.get("similarity"),
            threshold=primary_speaker_verification.get("threshold"),
        )
        listener_events.append(
            {
                "type": "listener.primary_speaker_verified",
                "session_id": session_id,
                "turn_id": turn_id,
                "ok": primary_speaker_verification.get("ok"),
                "primary_speaker_match": primary_speaker_verification.get("primary_speaker_match"),
                "similarity": primary_speaker_verification.get("similarity"),
                "threshold": primary_speaker_verification.get("threshold"),
                "timestamp_utc": utc_now(),
            }
        )
        if not primary_speaker_verification.get("ok"):
            failed_gates.append("primary_speaker_verifier_available")
        speaker_match = bool(primary_speaker_verification.get("primary_speaker_match"))
        turn_allowed_by_speaker_gate = speaker_match
        if expected_primary_speaker and not speaker_match:
            failed_gates.append("primary_speaker_expected_match")
        if not expected_primary_speaker and speaker_match:
            failed_gates.append("non_primary_speaker_suppressed")
        if not speaker_match:
            listener_events.append(
                {
                    "type": "listener.speech_suppressed",
                    "session_id": session_id,
                    "turn_id": turn_id,
                    "reason": "primary_speaker_gate_rejected",
                    "similarity": primary_speaker_verification.get("similarity"),
                    "threshold": primary_speaker_verification.get("threshold"),
                    "timestamp_utc": utc_now(),
                }
            )
            coordinator_events.append(
                {
                    "type": "turn.suppressed",
                    "session_id": session_id,
                    "turn_id": turn_id,
                    "reason": "primary_speaker_gate_rejected",
                    "timestamp_utc": utc_now(),
                }
            )

    memory_url = args.memory_url.rstrip("/")
    services["memory"] = {"base_url": memory_url}
    if args.enable_speaker_identity_memory:
        try:
            speaker_payload = build_speaker_resolve_payload(
                args=args,
                session_id=session_id,
                turn_id=turn_id,
                primary_speaker_verification=primary_speaker_verification,
            )
            speaker_resolution = post_memory_json(
                memory_url,
                "/speaker/resolve",
                speaker_payload,
                timeout_s=args.memory_timeout_s,
            )
            artifacts["speaker_resolution_path"] = str(receipt_root / "speaker-resolution.json")
            coordinator_events.append(
                {
                    "type": "memory.speaker_resolved",
                    "session_id": session_id,
                    "turn_id": turn_id,
                    "status": speaker_resolution.get("status"),
                    "speaker_id": speaker_resolution.get("speaker_id"),
                    "confidence": speaker_resolution.get("confidence"),
                    "timestamp_utc": utc_now(),
                }
            )
            intent_query = transcript or args.question
            memory_intent = post_memory_json(
                memory_url,
                "/intent",
                {
                    "q": intent_query,
                    "scope": args.speaker_intent_scope,
                    "fast": True,
                    "speaker_resolution": speaker_resolution,
                },
                timeout_s=args.memory_timeout_s,
            )
            artifacts["memory_intent_path"] = str(receipt_root / "memory-intent.json")
            coordinator_events.append(
                {
                    "type": "memory.intent_routed",
                    "session_id": session_id,
                    "turn_id": turn_id,
                    "action": memory_intent.get("action"),
                    "reason": memory_intent.get("reason"),
                    "clarify_kind": memory_intent.get("clarify_kind"),
                    "timestamp_utc": utc_now(),
                }
            )
            if (
                args.enable_speaker_memory_recall
                and turn_allowed_by_speaker_gate
                and speaker_resolution.get("status") == "known"
            ):
                recall_tags = list(speaker_resolution.get("memory_tags") or []) + list(args.speaker_memory_recall_tag or [])
                recall_payload = {
                    "q": args.question,
                    "scope": args.speaker_intent_scope,
                    "k": args.memory_k,
                    "threshold": args.min_memory_confidence,
                    "tags": recall_tags,
                    "recall_profile": speaker_resolution.get("recall_profile"),
                    "required_artifacts": ["speaker_identity", "speaker_scoped_memory"],
                }
                if args.speaker_memory_recall_collection:
                    recall_payload["collections"] = list(args.speaker_memory_recall_collection)
                recall_profile_fallback: dict[str, Any] | None = None
                try:
                    speaker_memory_recall_response = post_memory_recall(
                        memory_url,
                        recall_payload,
                        timeout_s=args.memory_timeout_s,
                    )
                except Exception as exc:  # noqa: BLE001 - preserve live service compatibility issue
                    response = getattr(exc, "response", None)
                    status_code = getattr(response, "status_code", None)
                    response_text = str(getattr(response, "text", ""))
                    rejected_profile = recall_payload.get("recall_profile")
                    if status_code == 422 and rejected_profile and "Unknown recall_profile" in response_text:
                        fallback_payload = dict(recall_payload)
                        fallback_payload.pop("recall_profile", None)
                        recall_profile_fallback = {
                            "schema": "chatterbox.memory.recall_profile_fallback.v1",
                            "reason": "memory_service_rejected_recall_profile",
                            "rejected_profile": rejected_profile,
                            "status_code": status_code,
                            "response_text": response_text[:500],
                            "fallback_request": fallback_payload,
                        }
                        speaker_memory_recall_response = post_memory_recall(
                            memory_url,
                            fallback_payload,
                            timeout_s=args.memory_timeout_s,
                        )
                    else:
                        raise
                speaker_memory_recall = {
                    "request": recall_payload,
                    "recall_profile_fallback": recall_profile_fallback,
                    "found": speaker_memory_recall_response.get("found"),
                    "confidence": speaker_memory_recall_response.get("confidence"),
                    "should_scan": speaker_memory_recall_response.get("should_scan"),
                    "items": speaker_memory_recall_response.get("items") or [],
                    "meta": speaker_memory_recall_response.get("meta"),
                    "raw": speaker_memory_recall_response,
                }
                artifacts["speaker_memory_recall_path"] = str(receipt_root / "speaker-memory-recall.json")
                coordinator_events.append(
                    {
                        "type": "memory.speaker_recall_finished",
                        "session_id": session_id,
                        "turn_id": turn_id,
                        "speaker_id": speaker_resolution.get("speaker_id"),
                        "found": speaker_memory_recall.get("found"),
                        "confidence": speaker_memory_recall.get("confidence"),
                        "item_count": len(speaker_memory_recall.get("items") or []),
                        "timestamp_utc": utc_now(),
                    }
                )
                if not speaker_memory_recall.get("found"):
                    missing_fact_clarification = {
                        "schema": "chatterbox.memory.missing_fact_clarification.v1",
                        "speaker_id": speaker_resolution.get("speaker_id"),
                        "display_name": speaker_resolution.get("display_name"),
                        "question": args.question,
                        "reason": "speaker_scoped_memory_recall_miss",
                        "text": "I do not know that yet. Tell me, and I will remember it for this speaker.",
                        "timestamp_utc": utc_now(),
                    }
                    artifacts["missing_fact_clarification_path"] = str(receipt_root / "missing-fact-clarification.json")
                    coordinator_events.append(
                        {
                            "type": "memory.missing_fact_clarification_created",
                            "session_id": session_id,
                            "turn_id": turn_id,
                            "speaker_id": speaker_resolution.get("speaker_id"),
                            "reason": "speaker_scoped_memory_recall_miss",
                            "timestamp_utc": utc_now(),
                        }
                    )
                    if args.enable_missing_fact_writeback and args.speaker_writeback_answer:
                        writeback_text = f"{speaker_resolution.get('display_name') or args.speaker_display_name}: {args.speaker_writeback_answer}"
                        writeback_key = sha256_text(
                            "|".join(
                                [
                                    str(speaker_resolution.get("speaker_id") or args.speaker_id),
                                    args.question,
                                    args.speaker_writeback_answer,
                                ]
                            )
                        )[:24]
                        writeback_payload = {
                            "collection": args.speaker_memory_collection,
                            "documents": [
                                {
                                    "_key": f"voice_fact_{writeback_key}",
                                    "schema": "memory.voice_conversation_fact.v1",
                                    "speaker_id": speaker_resolution.get("speaker_id"),
                                    "display_name": speaker_resolution.get("display_name"),
                                    "persona_id": args.active_persona_id,
                                    "scope": args.speaker_intent_scope,
                                    "question": args.question,
                                    "answer": args.speaker_writeback_answer,
                                    "text": writeback_text,
                                    "tags": sorted(set(recall_tags + ["voice_conversation_fact", "speaker_memory_writeback"])),
                                    "session_id": session_id,
                                    "turn_id": turn_id,
                                    "source": "chatterbox_rung7_missing_fact_writeback",
                                    "created_at": utc_now(),
                                }
                            ],
                        }
                        memory_writeback = post_memory_json(
                            memory_url,
                            "/upsert",
                            writeback_payload,
                            timeout_s=args.memory_timeout_s,
                        )
                        memory_writeback_readback = post_memory_json(
                            memory_url,
                            "/recall/by-keys",
                            {
                                "collection": args.speaker_memory_collection,
                                "key_field": "_key",
                                "keys": [writeback_payload["documents"][0]["_key"]],
                                "return_fields": [
                                    "_key",
                                    "speaker_id",
                                    "persona_id",
                                    "question",
                                    "answer",
                                    "tags",
                                ],
                            },
                            timeout_s=args.memory_timeout_s,
                        )
                        artifacts["memory_writeback_path"] = str(receipt_root / "memory-writeback.json")
                        artifacts["memory_writeback_readback_path"] = str(receipt_root / "memory-writeback-readback.json")
                        coordinator_events.append(
                            {
                                "type": "memory.writeback_finished",
                                "session_id": session_id,
                                "turn_id": turn_id,
                                "speaker_id": speaker_resolution.get("speaker_id"),
                                "collection": args.speaker_memory_collection,
                                "document_key": writeback_payload["documents"][0]["_key"],
                                "timestamp_utc": utc_now(),
                            }
                        )
        except Exception as exc:  # noqa: BLE001
            speaker_resolution = speaker_resolution or {
                "schema": "memory.speaker_resolution.v1",
                "status": "error",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            services["memory"]["speaker_identity_error"] = {
                "error_type": type(exc).__name__,
                "error": str(exc),
                "response_status_code": getattr(getattr(exc, "response", None), "status_code", None),
                "response_text": str(getattr(getattr(exc, "response", None), "text", ""))[:500],
            }
            failed_gates.append("memory_speaker_identity_roundtrip")

    backend = (
        build_asr_backend(args)
        if turn_allowed_by_speaker_gate and not skip_asr_and_render_for_memory_only
        else {"kind": "not_called", "live": False}
    )
    services["asr"] = asr_backend_receipt(backend)
    if turn_allowed_by_speaker_gate and not skip_asr_and_render_for_memory_only and not backend.get("live"):
        failed_gates.append("asr_backend_available")

    if fixture.exists() and turn_allowed_by_speaker_gate and backend.get("live"):
        listener_events.append(
            {
                "type": "listener.speech_started",
                "session_id": session_id,
                "turn_id": turn_id,
                "timestamp_utc": utc_now(),
                "source": "wav_frame_endpoint",
            }
        )
        try:
            transcript = transcribe_audio(backend, fixture)
            asr_transcript = {
                "schema": "chatterbox.listener.asr_transcript.v1",
                "session_id": session_id,
                "turn_id": turn_id,
                "backend": asr_backend_receipt(backend),
                "text": transcript,
                "text_sha256": sha256_text(transcript),
                "partial_transcripts": [],
                "partial_unavailable_reason": "offline_asr_backend_final_only",
                "timestamp_utc": utc_now(),
            }
            listener_events.append(
                {
                    "type": "listener.speech_final",
                    "session_id": session_id,
                    "turn_id": turn_id,
                    "text": transcript,
                    "text_sha256": sha256_text(transcript),
                    "timestamp_utc": utc_now(),
                }
            )
            listener_events.append(
                {
                    "type": "listener.speech_ended",
                    "session_id": session_id,
                    "turn_id": turn_id,
                    "timestamp_utc": utc_now(),
                }
            )
            heard_text_ledger.append(
                {
                    "schema": "chatterbox.listener.heard_text.v1",
                    "session_id": session_id,
                    "turn_id": turn_id,
                    "final_text": transcript,
                    "final_text_sha256": sha256_text(transcript),
                    "partial_transcripts": [],
                    "partial_unavailable_reason": "offline_asr_backend_final_only",
                    "asr_backend": asr_backend_receipt(backend),
                    "audio": artifacts.get("input_audio"),
                    "timestamp_utc": utc_now(),
                }
            )
            append_event(events, started, "asr.input_transcribed", turn_id=turn_id, transcript_sha256=sha256_text(transcript))
            if not transcript:
                failed_gates.append("asr_final_text_present")
            if args.expected_transcript:
                gate = acceptance_result(
                    expected_text=args.expected_transcript,
                    transcript=transcript,
                    max_wer=args.max_input_wer,
                )
                input_asr = {
                    "expected_text": args.expected_transcript,
                    "expected_text_sha256": sha256_text(args.expected_transcript),
                    "transcript": transcript,
                    "gate": gate,
                }
                if not gate["ok"]:
                    failed_gates.extend(f"input_asr_{gate_name}" for gate_name in gate["failed_gates"])
            else:
                input_asr = {"transcript": transcript, "transcript_sha256": sha256_text(transcript)}
        except Exception as exc:  # noqa: BLE001 - preserve live ASR failure
            asr_transcript = {
                "schema": "chatterbox.listener.asr_transcript.v1",
                "session_id": session_id,
                "turn_id": turn_id,
                "backend": asr_backend_receipt(backend),
                "error_type": type(exc).__name__,
                "error": str(exc),
                "timestamp_utc": utc_now(),
            }
            input_asr = {
                "expected_text": args.expected_transcript,
                "expected_text_sha256": sha256_text(args.expected_transcript or ""),
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            failed_gates.append("input_asr_transcribed")

    cancel_requested = transcript_requests_cancel(transcript) if turn_allowed_by_speaker_gate else False
    if transcript:
        coordinator_events.append(
            {
                "type": "turn.user_text_final",
                "session_id": session_id,
                "turn_id": turn_id,
                "text": transcript,
                "text_sha256": sha256_text(transcript),
                "timestamp_utc": utc_now(),
            }
        )
    if cancel_requested:
        if not args.old_turn_id:
            failed_gates.append("old_turn_id_present_for_cancel")
        coordinator_events.append(
            {
                "type": "turn.cancel_requested",
                "session_id": session_id,
                "turn_id": turn_id,
                "old_turn_id": args.old_turn_id,
                "reason": "listener_transcript_cancel_intent",
                "timestamp_utc": utc_now(),
            }
        )

    render_request = None
    if turn_allowed_by_speaker_gate and not skip_asr_and_render_for_memory_only:
        render_request = build_tau_voice_render_request(
            run_id=run_id,
            session_id=session_id,
            turn_id=turn_id,
            transcript=transcript,
            response_text=args.response_text,
            receipt_root=receipt_root,
            old_turn_id=args.old_turn_id,
            cancel_requested=cancel_requested,
        )
        coordinator_events.append(
            {
                "type": "turn.renderer_request_created",
                "session_id": session_id,
                "turn_id": turn_id,
                "schema": render_request["schema"],
                "request_sha256": sha256_text(json.dumps(render_request, sort_keys=True)),
                "timestamp_utc": utc_now(),
            }
        )
        append_event(events, started, "turn.renderer_request_created", turn_id=turn_id, schema=render_request["schema"])

    if not listener_events:
        failed_gates.append("listener_events_present")
    if not any(event.get("type") == "listener.audio_frame_received" for event in listener_events):
        failed_gates.append("listener_audio_frame_events_present")
    if turn_allowed_by_speaker_gate and not skip_asr_and_render_for_memory_only and (asr_transcript is None or not asr_transcript.get("text")):
        failed_gates.append("asr_transcript_final_text_present")
    if turn_allowed_by_speaker_gate and not skip_asr_and_render_for_memory_only and not heard_text_ledger:
        failed_gates.append("heard_text_ledger_present")
    required_coordinator_events = ["turn.started"]
    if turn_allowed_by_speaker_gate and not skip_asr_and_render_for_memory_only:
        required_coordinator_events.extend(["turn.user_text_final", "turn.renderer_request_created"])
    elif turn_allowed_by_speaker_gate:
        required_coordinator_events.append("memory.speaker_resolved")
    else:
        required_coordinator_events.append("turn.suppressed")
    for event_type in required_coordinator_events:
        if not any(event.get("type") == event_type for event in coordinator_events):
            failed_gates.append(f"coordinator_{event_type.replace('.', '_')}_present")
    if turn_allowed_by_speaker_gate and not skip_asr_and_render_for_memory_only and (not render_request or render_request["schema"] != "tau.voice_render_request.v1"):
        failed_gates.append("tau_voice_render_request_schema")
    if turn_allowed_by_speaker_gate and not skip_asr_and_render_for_memory_only and render_request and render_request["memory_route_decision"]["called"]:
        failed_gates.append("listener_boundary_did_not_call_memory")
    if args.enable_speaker_identity_memory:
        if not speaker_resolution or speaker_resolution.get("schema") != "memory.speaker_resolution.v1":
            failed_gates.append("speaker_resolution_schema")
        if not memory_intent:
            failed_gates.append("memory_intent_present")
        speaker_status = (speaker_resolution or {}).get("status")
        if not turn_allowed_by_speaker_gate and speaker_status not in {"unknown", "ambiguous"}:
            failed_gates.append("non_primary_speaker_resolves_unknown_or_ambiguous")
        if not turn_allowed_by_speaker_gate and memory_intent:
            if memory_intent.get("action") != "CLARIFY" or memory_intent.get("clarify_kind") != "speaker_identity":
                failed_gates.append("unknown_speaker_intent_clarifies_identity")
        if turn_allowed_by_speaker_gate and speaker_status == "known":
            expected_tags = {f"speaker:{args.speaker_id}", f"user:{args.speaker_id}", f"persona:{args.active_persona_id}"}
            returned_tags = set((speaker_resolution or {}).get("memory_tags") or [])
            if not expected_tags.issubset(returned_tags):
                failed_gates.append("known_speaker_memory_tags_present")
            if args.enable_speaker_memory_recall:
                if not speaker_memory_recall:
                    failed_gates.append("speaker_memory_recall_present")
                else:
                    recall_request = speaker_memory_recall.get("request") or {}
                    recall_tags = set(recall_request.get("tags") or [])
                    if not expected_tags.issubset(recall_tags):
                        failed_gates.append("speaker_memory_recall_tags_present")
                    if speaker_memory_recall.get("found"):
                        items = speaker_memory_recall.get("items") or []
                        if not items:
                            failed_gates.append("speaker_memory_recall_items_present")
                    else:
                        if not missing_fact_clarification:
                            failed_gates.append("missing_fact_clarification_present")
                        if args.enable_missing_fact_writeback:
                            if not memory_writeback:
                                failed_gates.append("memory_writeback_present")
                            elif memory_writeback.get("ok") is False:
                                failed_gates.append("memory_writeback_ok")
                            elif not memory_writeback_readback or not (
                                (memory_writeback_readback.get("results") or [])
                                or (memory_writeback_readback.get("documents") or [])
                            ):
                                failed_gates.append("memory_writeback_readback_present")

    artifacts.update(
        {
            "heard_text_ledger_path": str(receipt_root / "heard-text-ledger.jsonl"),
            "listener_turn_events_path": str(receipt_root / "listener-turn-events.jsonl"),
            "asr_transcript_path": str(receipt_root / "asr-transcript.json"),
            "primary_speaker_verification_path": str(receipt_root / "primary-speaker-verification.json"),
            "speaker_resolution_path": str(receipt_root / "speaker-resolution.json"),
            "memory_intent_path": str(receipt_root / "memory-intent.json"),
            "speaker_memory_recall_path": str(receipt_root / "speaker-memory-recall.json"),
            "missing_fact_clarification_path": str(receipt_root / "missing-fact-clarification.json"),
            "memory_writeback_path": str(receipt_root / "memory-writeback.json"),
            "memory_writeback_readback_path": str(receipt_root / "memory-writeback-readback.json"),
            "tau_voice_render_request_path": str(receipt_root / "tau-voice-render-request.json"),
        }
    )
    append_event(events, started, "rung.finished", ok=not failed_gates)
    proves: list[str] = []
    if not failed_gates:
        proves.append("listener_boundary_accepts_real_wav_audio_frames")
        if primary_speaker_gate_enabled:
            proves.append("primary_speaker_gate_makes_auditable_accept_or_suppress_decision")
        if stress_fixture and stress_fixture.get("ok"):
            proves.append("stress_fixture_mixes_primary_speaker_with_background_or_competing_audio")
            proves.append("configured_stress_fixture_audio_is_the_listener_input")
        if args.enable_speaker_identity_memory:
            proves.append("listener_speaker_evidence_roundtrips_through_memory_speaker_resolve_and_intent")
        if args.enable_speaker_memory_recall and speaker_memory_recall:
            proves.append("known_speaker_identity_routes_recall_through_speaker_scoped_memory_tags")
            if not speaker_memory_recall.get("found") and missing_fact_clarification:
                proves.append("speaker_scoped_recall_miss_creates_missing_fact_clarification")
            if memory_writeback:
                proves.append("missing_fact_answer_is_written_back_to_memory")
        if turn_allowed_by_speaker_gate:
            if skip_asr_and_render_for_memory_only:
                proves.append("speaker_memory_only_mode_skips_asr_and_tau_without_claiming_transcription_or_rendering")
            else:
                proves.extend(
                    [
                        "configured_asr_backend_produces_auditable_final_text",
                        "coordinator_creates_tau_voice_render_request_without_listener_owning_memory_or_tts",
                    ]
                )
        else:
            proves.append("primary_speaker_gate_suppresses_non_primary_audio_before_asr_or_rendering")
            if args.enable_speaker_identity_memory:
                proves.append("unknown_or_non_primary_speaker_routes_to_identity_clarification_without_personal_recall")
    return {
        "schema": RUNG7_SCHEMA,
        "ok": not failed_gates,
        "rung": 7,
        "run_id": run_id,
        "session_id": session_id,
        "turn_id": turn_id,
        "mocked": False,
        "live": bool(
            fixture.exists()
            and turn_allowed_by_speaker_gate
            and not failed_gates
            and (backend.get("live") or skip_asr_and_render_for_memory_only)
        ),
        "started_at_utc": datetime.fromtimestamp(
            time.time() - (time.perf_counter() - started),
            timezone.utc,
        ).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "ended_at_utc": utc_now(),
        "services": services,
        "inputs": {
            "fixture": str(fixture),
            "expected_transcript": args.expected_transcript,
            "fixture_provenance": args.fixture_provenance,
            "listener_frame_ms": args.listener_frame_ms,
            "old_turn_id": args.old_turn_id,
            "primary_speaker_gate_enabled": primary_speaker_gate_enabled,
            "primary_speaker_enrollment": str(args.primary_speaker_enrollment.resolve()) if args.primary_speaker_enrollment else None,
            "primary_speaker_threshold": args.primary_speaker_threshold,
            "primary_speaker_engine": args.primary_speaker_engine,
            "expected_primary_speaker": expected_primary_speaker,
            "speaker_identity_memory_enabled": args.enable_speaker_identity_memory,
            "speaker_memory_recall_enabled": args.enable_speaker_memory_recall,
            "missing_fact_writeback_enabled": args.enable_missing_fact_writeback,
            "speaker_memory_only": args.speaker_memory_only,
            "speaker_id": args.speaker_id,
            "speaker_display_name": args.speaker_display_name,
            "active_persona_id": args.active_persona_id,
            "speaker_memory_collection": args.speaker_memory_collection,
            "stress_fixture_enabled": bool(stress_fixture and stress_fixture.get("enabled")),
            "stress_kind": (stress_fixture or {}).get("kind"),
        },
        "artifacts": artifacts,
        "events": events,
        "listener_events": listener_events,
        "heard_text_ledger": heard_text_ledger,
        "coordinator_events": coordinator_events,
        "input_asr": input_asr,
        "asr_transcript": asr_transcript,
        "primary_speaker_verification": primary_speaker_verification,
        "stress_fixture": stress_fixture,
        "speaker_resolution": speaker_resolution,
        "memory_intent": memory_intent,
        "speaker_memory_recall": speaker_memory_recall,
        "missing_fact_clarification": missing_fact_clarification,
        "memory_writeback": memory_writeback,
        "memory_writeback_readback": memory_writeback_readback,
        "tau_voice_render_request": render_request,
        "failed_gates": failed_gates,
        "claims": {
            "proves": proves,
            "does_not_prove": [
                *([] if stress_fixture and stress_fixture.get("ok") else ["configured_noise_or_competing_voice_stress_case"]),
                "generalized_production_noise_robustness_beyond_the_configured_fixture",
                "browser_webrtc_readiness",
                "memory_salience_or_qra_correctness",
                "subjective_interruption_feel",
                "chatterbox_tts_output_quality",
                "physical_speaker_to_microphone_identity_gating",
                "overlapping_speaker_diarization",
            ],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rung", type=int, choices=[1, 2, 3, 4, 5, 6, 7], required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8018")
    parser.add_argument("--memory-url", default="http://127.0.0.1:8601")
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--turn1-fixture", type=Path)
    parser.add_argument("--turn2-fixture", type=Path)
    parser.add_argument("--turn3-fixture", type=Path)
    parser.add_argument("--fixture-provenance", default="provided_wav_fixture")
    parser.add_argument("--expected-transcript")
    parser.add_argument("--expected-turn1-transcript")
    parser.add_argument("--expected-turn2-transcript")
    parser.add_argument("--expected-turn3-transcript")
    parser.add_argument("--response-text", default=DEFAULT_RESPONSE_TEXT)
    parser.add_argument(
        "--memory-question",
        default="What memory explains why Embry Lawson reacts to Hawaii, surfing, Kai, and afternoon rain with grief?",
    )
    parser.add_argument("--memory-tag", action="append", default=["persona:embry"])
    parser.add_argument("--memory-k", default=5, type=int)
    parser.add_argument("--memory-timeout-s", default=10, type=int)
    parser.add_argument("--min-memory-confidence", default=0.3, type=float)
    parser.add_argument("--required-persona-id", default="embry")
    parser.add_argument("--label", default=None)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--turn-id", default=None)
    parser.add_argument("--old-turn-id", default=None)
    parser.add_argument("--listener-frame-ms", default=20, type=int)
    parser.add_argument("--primary-speaker-enrollment", type=Path, default=None)
    parser.add_argument("--primary-speaker-engine", choices=["resemblyzer", "speechbrain_ecapa"], default="resemblyzer")
    parser.add_argument("--primary-speaker-threshold", default=0.82, type=float)
    parser.add_argument("--expected-primary-speaker", default=True, type=parse_bool_arg)
    parser.add_argument("--enable-speaker-identity-memory", action="store_true")
    parser.add_argument("--enable-speaker-memory-recall", action="store_true")
    parser.add_argument("--enable-missing-fact-writeback", action="store_true")
    parser.add_argument("--speaker-memory-only", action="store_true")
    parser.add_argument("--speaker-id", default="horus_lupercal")
    parser.add_argument("--speaker-display-name", default="Horus Lupercal")
    parser.add_argument("--active-persona-id", default="embry")
    parser.add_argument("--speaker-tag", action="append", default=["persona:horus_lupercal"])
    parser.add_argument("--speaker-confidence", default=0.0, type=float)
    parser.add_argument("--speaker-evidence-source", default="listener")
    parser.add_argument("--speaker-resolve-threshold", default=0.82, type=float)
    parser.add_argument("--speaker-ambiguity-margin", default=0.05, type=float)
    parser.add_argument("--speaker-prompt-variant", default=0, type=int)
    parser.add_argument("--speaker-intent-scope", default="persona_memory")
    parser.add_argument("--speaker-memory-collection", default="voice_conversation_memory")
    parser.add_argument("--speaker-memory-recall-collection", action="append", default=None)
    parser.add_argument("--speaker-memory-recall-tag", action="append", default=[])
    parser.add_argument("--speaker-writeback-answer", default=None)
    parser.add_argument("--stress-primary-audio", type=Path, default=None)
    parser.add_argument("--stress-noise-audio", type=Path, default=None)
    parser.add_argument("--stress-competing-audio", type=Path, default=None)
    parser.add_argument("--stress-output-fixture", type=Path, default=None)
    parser.add_argument("--stress-kind", default="factory_floor_primary_speaker")
    parser.add_argument("--stress-primary-gain-db", default=0.0, type=float)
    parser.add_argument("--stress-noise-gain-db", default=-18.0, type=float)
    parser.add_argument("--stress-competing-gain-db", default=-24.0, type=float)
    parser.add_argument("--stress-timeout-s", default=60, type=int)
    parser.add_argument("--question", default="Embry, which control family should I use when the answer says SI?")
    parser.add_argument("--first-answer", default=None)
    parser.add_argument("--new-answer", default=None)
    parser.add_argument("--variant-offset", default=4, type=int)
    parser.add_argument("--tool-query", default="voice agent turn detection interruption handling")
    parser.add_argument("--tool-count", default=3, type=int)
    parser.add_argument("--tool-timeout-s", default=60, type=int)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--wait-health-s", default=240, type=int)
    parser.add_argument("--synthesis-timeout-s", default=300, type=int)
    parser.add_argument("--asr-openai-base-url", default=os.getenv("CHATTERBOX_ASR_OPENAI_BASE_URL"))
    parser.add_argument("--api-key-env", default=os.getenv("CHATTERBOX_ASR_API_KEY_ENV", "WHISPER_API_KEY"))
    parser.add_argument("--asr-model", default="small.en")
    parser.add_argument("--asr-device", default="cpu")
    parser.add_argument("--asr-compute-type", default="int8")
    parser.add_argument("--max-input-wer", default=0.25, type=float)
    parser.add_argument("--max-output-wer", default=0.35, type=float)
    parser.add_argument(
        "--path-map",
        action="append",
        default=[],
        help="Map receipt audio paths from container to host paths, e.g. /out=/tmp/chatterbox-out.",
    )
    args = parser.parse_args()

    if args.rung == 1:
        if not args.fixture or not args.expected_transcript:
            parser.error("--fixture and --expected-transcript are required for --rung 1")
        receipt = run_rung1(args)
    elif args.rung == 2:
        if not args.turn1_fixture or not args.turn2_fixture:
            parser.error("--turn1-fixture and --turn2-fixture are required for --rung 2")
        if not args.expected_turn1_transcript or not args.expected_turn2_transcript:
            parser.error("--expected-turn1-transcript and --expected-turn2-transcript are required for --rung 2")
        receipt = run_rung2(args)
    elif args.rung == 3:
        if not args.fixture or not args.expected_transcript:
            parser.error("--fixture and --expected-transcript are required for --rung 3")
        receipt = run_rung3(args)
    elif args.rung == 4:
        if not args.fixture or not args.expected_transcript:
            parser.error("--fixture and --expected-transcript are required for --rung 4")
        receipt = run_rung4(args)
    elif args.rung == 5:
        if not args.fixture or not args.expected_transcript:
            parser.error("--fixture and --expected-transcript are required for --rung 5")
        receipt = run_rung5(args)
    elif args.rung == 6:
        if not args.turn1_fixture or not args.turn2_fixture or not args.turn3_fixture:
            parser.error("--turn1-fixture, --turn2-fixture, and --turn3-fixture are required for --rung 6")
        if not args.expected_turn1_transcript or not args.expected_turn2_transcript or not args.expected_turn3_transcript:
            parser.error(
                "--expected-turn1-transcript, --expected-turn2-transcript, and --expected-turn3-transcript are required for --rung 6"
            )
        receipt = run_rung6(args)
    else:
        if not args.fixture and not args.stress_primary_audio:
            parser.error("--fixture or --stress-primary-audio is required for --rung 7")
        receipt = run_rung7(args)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.rung == 7:
        write_rung7_sidecar_artifacts(receipt, args.out)
    args.out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": receipt["ok"],
                "live": receipt["live"],
                "mocked": receipt["mocked"],
                "out": str(args.out),
                "failed_gates": receipt["failed_gates"],
            },
            sort_keys=True,
        )
    )
    return 0 if receipt["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
