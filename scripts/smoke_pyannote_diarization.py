#!/usr/bin/env python3
"""Run a fail-closed pyannote diarization smoke over captured listener audio.

This harness is intentionally separate from the lower-latency Resemblyzer
primary-speaker gate. pyannote answers the richer diarization question:
"who spoke when?" across an audio file. It requires the pyannote package and
either a local pipeline directory or a Hugging Face token for the gated model.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_MODEL = "pyannote/speaker-diarization-community-1"
TOKEN_ENV_NAMES = ("HF_TOKEN", "HUGGINGFACE_TOKEN", "HUGGING_FACE_HUB_TOKEN")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def token_from_env() -> tuple[str | None, str | None]:
    for name in TOKEN_ENV_NAMES:
        token = os.environ.get(name)
        if token:
            return token, name
    return None, None


def segment_rows(annotation: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    iterator = annotation.itertracks(yield_label=True)
    for turn, track, speaker in iterator:
        rows.append(
            {
                "start_s": round(float(turn.start), 3),
                "end_s": round(float(turn.end), 3),
                "duration_s": round(float(turn.end - turn.start), 3),
                "track": str(track),
                "speaker": str(speaker),
            }
        )
    return rows


def overlap_seconds(segments: list[dict[str, Any]]) -> float:
    events: list[tuple[float, int]] = []
    for segment in segments:
        events.append((float(segment["start_s"]), 1))
        events.append((float(segment["end_s"]), -1))
    events.sort()
    active = 0
    previous: float | None = None
    overlap = 0.0
    for timestamp, delta in events:
        if previous is not None and active > 1:
            overlap += max(0.0, timestamp - previous)
        active += delta
        previous = timestamp
    return round(overlap, 3)


def speaker_count_gate_failures(
    *,
    speakers: list[str],
    min_speakers: int | None,
    max_speakers: int | None,
    num_speakers: int | None,
) -> list[str]:
    failures: list[str] = []
    if min_speakers is not None and len(speakers) < min_speakers:
        failures.append("min_speakers")
    if max_speakers is not None and len(speakers) > max_speakers:
        failures.append("max_speakers")
    if num_speakers is not None and len(speakers) != num_speakers:
        failures.append("num_speakers_exact_match")
    return failures


def run(args: argparse.Namespace) -> dict[str, Any]:
    started = time.perf_counter()
    audio = args.audio.resolve()
    model_path = Path(args.model).expanduser()
    local_model = model_path.exists()
    token, token_env = token_from_env()
    failed_gates: list[str] = []
    if not audio.exists():
        failed_gates.append("audio_exists")
    if not local_model and not token:
        failed_gates.append("hf_token_or_local_model_available")

    receipt: dict[str, Any] = {
        "schema": "chatterbox.pyannote_diarization_smoke.v1",
        "ok": False,
        "mocked": False,
        "live": False,
        "started_at_utc": utc_now(),
        "inputs": {
            "audio": str(audio),
            "model": str(model_path) if local_model else args.model,
            "local_model": local_model,
            "token_env": token_env,
            "device": args.device,
            "num_speakers": args.num_speakers,
        },
        "artifacts": {},
        "segments": [],
        "exclusive_segments": [],
        "summary": {},
        "failed_gates": failed_gates,
        "claims": {
            "proves": [],
            "does_not_prove": [
                "real_time_streaming_diarization",
                "perfect_overlap_separation",
                "speaker_identity_mapping_to_horus_without_enrollment_reconciliation",
                "browser_webrtc_transport",
                "generalized_factory_floor_robustness",
            ],
        },
    }
    if failed_gates:
        receipt["ended_at_utc"] = utc_now()
        receipt["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
        return receipt

    # The current Chatterbox Docker image uses Python 3.11.0rc1, which predates
    # these CPython integer-string safety helpers. Some pyannote dependencies
    # probe for them at import time.
    if not hasattr(sys, "get_int_max_str_digits"):
        def get_int_max_str_digits() -> int:
            return 0

        sys.get_int_max_str_digits = get_int_max_str_digits  # type: ignore[attr-defined]
    if not hasattr(sys, "set_int_max_str_digits"):
        def set_int_max_str_digits(maxdigits: int) -> None:
            return None

        sys.set_int_max_str_digits = set_int_max_str_digits  # type: ignore[attr-defined]

    try:
        import torch
        from pyannote.audio import Pipeline
    except Exception as exc:  # noqa: BLE001
        receipt["failed_gates"].append("pyannote_audio_installed")
        receipt["error_type"] = type(exc).__name__
        receipt["error"] = str(exc)
        receipt["ended_at_utc"] = utc_now()
        receipt["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
        return receipt

    receipt["artifacts"]["audio"] = wav_metrics(audio)
    try:
        origin = str(model_path) if local_model else args.model
        try:
            pipeline = Pipeline.from_pretrained(origin, token=token)
        except TypeError as exc:
            if "token" not in str(exc):
                raise
            pipeline = Pipeline.from_pretrained(origin, use_auth_token=token)
        if args.device == "auto":
            device_name = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            device_name = args.device
        pipeline.to(torch.device(device_name))
        kwargs: dict[str, Any] = {}
        if args.num_speakers is not None:
            kwargs["num_speakers"] = args.num_speakers
        output = pipeline(str(audio), **kwargs)
        diarization = getattr(output, "speaker_diarization", output)
        exclusive = getattr(output, "exclusive_speaker_diarization", None)
        segments = segment_rows(diarization)
        exclusive_segments = segment_rows(exclusive) if exclusive is not None else []
        speakers = sorted({segment["speaker"] for segment in segments})
        exclusive_speakers = sorted({segment["speaker"] for segment in exclusive_segments})
        summary = {
            "device": device_name,
            "segment_count": len(segments),
            "speaker_count": len(speakers),
            "speakers": speakers,
            "exclusive_segment_count": len(exclusive_segments),
            "exclusive_speaker_count": len(exclusive_speakers),
            "exclusive_speakers": exclusive_speakers,
            "overlap_seconds": overlap_seconds(segments),
        }
        receipt["segments"] = segments
        receipt["exclusive_segments"] = exclusive_segments
        receipt["summary"] = summary
        if not segments:
            receipt["failed_gates"].append("diarization_segments_present")
        receipt["failed_gates"].extend(
            speaker_count_gate_failures(
                speakers=speakers,
                min_speakers=args.min_speakers,
                max_speakers=args.max_speakers,
                num_speakers=args.num_speakers,
            )
        )
        receipt["ok"] = not receipt["failed_gates"]
        receipt["live"] = receipt["ok"]
        if receipt["ok"]:
            receipt["claims"]["proves"] = [
                "pyannote_pipeline_runs_locally_on_captured_listener_audio",
                "diarization_segments_are_auditable_in_receipt",
            ]
    except Exception as exc:  # noqa: BLE001
        receipt["failed_gates"].append("pyannote_pipeline_run")
        receipt["error_type"] = type(exc).__name__
        receipt["error"] = str(exc)

    receipt["ended_at_utc"] = utc_now()
    receipt["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    parser.add_argument("--num-speakers", type=int, default=None)
    parser.add_argument("--min-speakers", type=int, default=None)
    parser.add_argument("--max-speakers", type=int, default=None)
    args = parser.parse_args()
    receipt = run(args)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": receipt["ok"],
                "live": receipt["live"],
                "mocked": receipt["mocked"],
                "failed_gates": receipt["failed_gates"],
                "out": str(args.out),
            },
            sort_keys=True,
        )
    )
    return 0 if receipt["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
