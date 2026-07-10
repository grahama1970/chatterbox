#!/usr/bin/env python3
"""Build and verify a physical multi-sample Horus speaker profile."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from resemblyzer import VoiceEncoder, preprocess_wav


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact(path: Path) -> dict[str, Any]:
    return {"path": str(path.resolve()), "sha256": sha256_file(path), "bytes": path.stat().st_size}


def normalized(vector: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    if norm == 0:
        raise ValueError("zero_norm_embedding")
    return vector / norm


def embed(encoder: VoiceEncoder, path: Path) -> np.ndarray:
    return normalized(encoder.embed_utterance(preprocess_wav(path)))


def score(profile: np.ndarray, candidate: np.ndarray) -> float:
    return float(np.inner(profile, candidate))


def parse_impostor(value: str) -> tuple[str, Path]:
    role, separator, raw_path = value.partition("=")
    if not separator or not role.strip() or not raw_path.strip():
        raise argparse.ArgumentTypeError("impostor must be ROLE=/absolute/path.wav")
    return role.strip(), Path(raw_path).expanduser().resolve()


def run(args: argparse.Namespace) -> dict[str, Any]:
    enrollment = [path.resolve() for path in args.enrollment_sample]
    held_out = [path.resolve() for path in args.held_out_horus]
    impostors = [(role, path.resolve()) for role, path in args.impostor]
    required = enrollment + held_out + [path for _, path in impostors]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"missing audio artifacts: {missing}")
    if len(enrollment) < 3:
        raise ValueError("at least three physical enrollment samples are required")
    if not held_out:
        raise ValueError("at least one held-out Horus sample is required")
    if not impostors:
        raise ValueError("at least one impostor sample is required")

    encoder = VoiceEncoder(device="cpu")
    enrollment_embeddings = [embed(encoder, path) for path in enrollment]
    profile = normalized(np.mean(np.stack(enrollment_embeddings), axis=0))
    profile_hash = hashlib.sha256(profile.astype("float32").tobytes()).hexdigest()

    held_out_results = []
    for path in held_out:
        similarity = score(profile, embed(encoder, path))
        held_out_results.append({
            "audio": artifact(path),
            "similarity": round(similarity, 6),
            "accepted": similarity >= args.threshold,
        })

    impostor_results = []
    for role, path in impostors:
        similarity = score(profile, embed(encoder, path))
        impostor_results.append({
            "role": role,
            "audio": artifact(path),
            "similarity": round(similarity, 6),
            "rejected": similarity < args.threshold,
        })

    minimum_genuine = min(item["similarity"] for item in held_out_results)
    maximum_impostor = max(item["similarity"] for item in impostor_results)
    observed_margin = minimum_genuine - maximum_impostor
    failures = []
    if not all(item["accepted"] for item in held_out_results):
        failures.append("held_out_horus_rejected")
    if not all(item["rejected"] for item in impostor_results):
        failures.append("impostor_accepted")
    if observed_margin < args.min_ambiguity_margin:
        failures.append("ambiguity_margin_below_minimum")

    receipt = {
        "schema": "embry.speaker_enrollment_receipt.v2",
        "status": "pass" if not failures else "fail",
        "ok": not failures,
        "live": True,
        "mocked": False,
        "created_at": utc_now(),
        "speaker_id": "horus_lupercal",
        "engine": "resemblyzer_voice_encoder",
        "model_provenance": "resemble-ai/Resemblyzer VoiceEncoder pretrained checkpoint",
        "synthetic_enrollment": False,
        "physical_capture": True,
        "source_node": args.source_node,
        "enrollment_sample_count": len(enrollment),
        "held_out_horus_count": len(held_out),
        "impostor_sample_count": len(impostors),
        "enrollment_samples": [artifact(path) for path in enrollment],
        "held_out_horus": held_out_results,
        "impostors": impostor_results,
        "profile_sha256": profile_hash,
        "threshold": args.threshold,
        "min_ambiguity_margin": args.min_ambiguity_margin,
        "minimum_genuine_similarity": round(minimum_genuine, 6),
        "maximum_impostor_similarity": round(maximum_impostor, 6),
        "observed_ambiguity_margin": round(observed_margin, 6),
        "failed_gates": failures,
        "claims": {
            "proves": [
                "three_sample_physical_horus_profile_built",
                "held_out_physical_horus_samples_accepted",
                "listed_impostor_samples_rejected",
            ] if not failures else [],
            "does_not_prove": [
                "physical_usb_unplug_replug",
                "factory_noise_robustness",
                "overlapping_speaker_separation",
                "memory_speaker_resolution",
                "tau_or_chatterbox_routing",
            ],
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--enrollment-sample", action="append", required=True, type=Path)
    parser.add_argument("--held-out-horus", action="append", required=True, type=Path)
    parser.add_argument("--impostor", action="append", required=True, type=parse_impostor)
    parser.add_argument("--source-node", required=True)
    parser.add_argument("--threshold", type=float, default=0.75)
    parser.add_argument("--min-ambiguity-margin", type=float, default=0.08)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    receipt = run(args)
    print(json.dumps({"status": receipt["status"], "receipt": str(args.out), "failed_gates": receipt["failed_gates"]}))
    return 0 if receipt["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
