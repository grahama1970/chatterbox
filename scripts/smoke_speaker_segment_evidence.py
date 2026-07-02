#!/usr/bin/env python3
"""Produce segment-level speaker evidence for Horus-vs-Embry listener audio.

This is a lightweight, local speaker-verification segmentation harness. It is
not a pyannote-style diarization pipeline and does not separate overlapping
speakers. It answers a narrower question: across fixed windows of captured
audio, does the primary Horus reference score above the competing Embry
reference by a configured margin?
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_HORUS_ENROLLMENT = (
    "/home/graham/workspace/experiments/agent-skills-loop2-shared/skills/"
    "persona-dream/voice_clone_candidates/horus_kling_clone_candidate.wav"
)
DEFAULT_EMBRY_ENROLLMENT = (
    "/home/graham/workspace/experiments/agent-skills-loop2-shared/skills/"
    "persona-dream/voice_clone_candidates/embry_kling_clone_candidate.wav"
)


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


def run(args: argparse.Namespace) -> dict[str, Any]:
    started = time.perf_counter()
    failed_gates: list[str] = []
    audio = args.audio.resolve()
    horus = args.horus_enrollment.resolve()
    embry = args.embry_enrollment.resolve()
    for name, path in {"audio": audio, "horus_enrollment": horus, "embry_enrollment": embry}.items():
        if not path.exists():
            failed_gates.append(f"{name}_exists")

    receipt: dict[str, Any] = {
        "schema": "chatterbox.speaker_segment_evidence.v1",
        "ok": False,
        "mocked": False,
        "live": False,
        "started_at_utc": utc_now(),
        "inputs": {
            "audio": str(audio),
            "horus_enrollment": str(horus),
            "embry_enrollment": str(embry),
            "window_s": args.window_s,
            "hop_s": args.hop_s,
            "min_primary_margin": args.min_primary_margin,
            "min_primary_ratio": args.min_primary_ratio,
        },
        "artifacts": {},
        "segments": [],
        "summary": {},
        "failed_gates": failed_gates,
        "claims": {
            "proves": [],
            "does_not_prove": [
                "pyannote_or_spectral_clustering_diarization",
                "overlapping_speaker_separation",
                "speaker_count_estimation",
                "word_level_speaker_attribution",
                "browser_webrtc_transport",
            ],
        },
    }
    if failed_gates:
        receipt["ended_at_utc"] = utc_now()
        receipt["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
        return receipt

    try:
        import numpy as np
        import soundfile as sf
        from resemblyzer import VoiceEncoder, preprocess_wav
    except Exception as exc:  # noqa: BLE001
        receipt["failed_gates"].append("speaker_segment_dependencies_available")
        receipt["error_type"] = type(exc).__name__
        receipt["error"] = str(exc)
        receipt["ended_at_utc"] = utc_now()
        receipt["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
        return receipt

    receipt["artifacts"] = {
        "audio": wav_metrics(audio),
        "horus_enrollment": wav_metrics(horus),
        "embry_enrollment": wav_metrics(embry),
    }
    encoder = VoiceEncoder()
    horus_embedding = encoder.embed_utterance(preprocess_wav(horus))
    embry_embedding = encoder.embed_utterance(preprocess_wav(embry))
    wav, sample_rate = sf.read(str(audio), dtype="float32", always_2d=False)
    if getattr(wav, "ndim", 1) > 1:
        wav = wav.mean(axis=1)
    if sample_rate != 16000:
        import scipy.signal

        wav = scipy.signal.resample(wav, int(len(wav) * 16000 / sample_rate))
        sample_rate = 16000
    window_samples = int(args.window_s * sample_rate)
    hop_samples = int(args.hop_s * sample_rate)
    if window_samples <= 0 or hop_samples <= 0:
        receipt["failed_gates"].append("valid_window_and_hop")
    if len(wav) < window_samples:
        receipt["failed_gates"].append("audio_long_enough_for_segments")
    if receipt["failed_gates"]:
        receipt["ended_at_utc"] = utc_now()
        receipt["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
        return receipt

    segments: list[dict[str, Any]] = []
    for start in range(0, len(wav) - window_samples + 1, hop_samples):
        end = start + window_samples
        segment_wav = wav[start:end]
        rms = float(np.sqrt(np.mean(np.square(segment_wav)))) if len(segment_wav) else 0.0
        if rms < args.min_window_rms:
            label = "silence_or_noise"
            horus_similarity = None
            embry_similarity = None
            margin = None
        else:
            embedding = encoder.embed_utterance(segment_wav)
            horus_similarity = float(np.inner(horus_embedding, embedding))
            embry_similarity = float(np.inner(embry_embedding, embedding))
            margin = horus_similarity - embry_similarity
            if margin >= args.min_primary_margin:
                label = "horus_lupercal"
            elif margin <= -args.min_primary_margin:
                label = "embry"
            else:
                label = "ambiguous"
        segments.append(
            {
                "index": len(segments),
                "start_s": round(start / sample_rate, 3),
                "end_s": round(end / sample_rate, 3),
                "rms": round(rms, 6),
                "label": label,
                "horus_similarity": round(horus_similarity, 4) if horus_similarity is not None else None,
                "embry_similarity": round(embry_similarity, 4) if embry_similarity is not None else None,
                "primary_margin": round(margin, 4) if margin is not None else None,
            }
        )

    voiced = [segment for segment in segments if segment["label"] != "silence_or_noise"]
    horus_segments = [segment for segment in voiced if segment["label"] == "horus_lupercal"]
    embry_segments = [segment for segment in voiced if segment["label"] == "embry"]
    ambiguous_segments = [segment for segment in voiced if segment["label"] == "ambiguous"]
    margins = [segment["primary_margin"] for segment in voiced if segment["primary_margin"] is not None]
    summary = {
        "segment_count": len(segments),
        "voiced_segment_count": len(voiced),
        "horus_segment_count": len(horus_segments),
        "embry_segment_count": len(embry_segments),
        "ambiguous_segment_count": len(ambiguous_segments),
        "horus_ratio": round(len(horus_segments) / len(voiced), 4) if voiced else 0.0,
        "mean_primary_margin": round(float(np.mean(margins)), 4) if margins else None,
        "min_primary_margin_observed": round(float(np.min(margins)), 4) if margins else None,
        "max_primary_margin_observed": round(float(np.max(margins)), 4) if margins else None,
    }
    receipt["segments"] = segments
    receipt["summary"] = summary
    if summary["voiced_segment_count"] < args.min_voiced_segments:
        receipt["failed_gates"].append("min_voiced_segments")
    if summary["horus_ratio"] < args.min_primary_ratio:
        receipt["failed_gates"].append("min_primary_ratio")
    if summary["mean_primary_margin"] is None or summary["mean_primary_margin"] < args.min_primary_margin:
        receipt["failed_gates"].append("mean_primary_margin")
    receipt["ok"] = not receipt["failed_gates"]
    receipt["live"] = receipt["ok"]
    if receipt["ok"]:
        receipt["claims"]["proves"] = [
            "captured_audio_segment_windows_score_closer_to_horus_than_embry_reference",
            "primary_speaker_segment_evidence_is_auditable_without_mocking",
        ]
    receipt["ended_at_utc"] = utc_now()
    receipt["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--horus-enrollment", default=DEFAULT_HORUS_ENROLLMENT, type=Path)
    parser.add_argument("--embry-enrollment", default=DEFAULT_EMBRY_ENROLLMENT, type=Path)
    parser.add_argument("--window-s", default=2.4, type=float)
    parser.add_argument("--hop-s", default=1.2, type=float)
    parser.add_argument("--min-window-rms", default=0.003, type=float)
    parser.add_argument("--min-primary-margin", default=0.03, type=float)
    parser.add_argument("--min-primary-ratio", default=0.5, type=float)
    parser.add_argument("--min-voiced-segments", default=4, type=int)
    args = parser.parse_args()
    receipt = run(args)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": receipt["ok"], "live": receipt["live"], "mocked": receipt["mocked"], "failed_gates": receipt["failed_gates"], "out": str(args.out)}, sort_keys=True))
    return 0 if receipt["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
