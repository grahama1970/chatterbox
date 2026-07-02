#!/usr/bin/env python3
"""Render Chatterbox candidates until one passes ASR text-fidelity gates."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chatterbox.agent.asr_acceptance import acceptance_result


DEFAULT_VARIANTS: list[dict[str, Any]] = [
    {
        "name": "stage_default",
        "overrides": {},
    },
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


def apply_path_maps(path: Path, path_maps: dict[str, Path]) -> Path:
    path_text = str(path)
    for source, target in sorted(path_maps.items(), key=lambda item: len(item[0]), reverse=True):
        if path_text == source or path_text.startswith(f"{source}/"):
            return target / path_text[len(source) :].lstrip("/")
    return path


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


def transcribe_openai_compatible(base_url: str, api_key: str, audio_path: Path) -> str:
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


def post_json(url: str, payload: dict[str, Any], *, timeout: float = 180.0) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8018")
    parser.add_argument("--text", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--delivery-stage", default="neutral")
    parser.add_argument("--ref-audio", default=None)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--openai-base-url", default="http://127.0.0.1:9000")
    parser.add_argument("--api-key-env", default="WHISPER_API_KEY")
    parser.add_argument("--path-map", action="append", default=[])
    parser.add_argument("--max-wer", type=float, default=0.35)
    parser.add_argument("--max-duration-ratio", type=float, default=2.5)
    parser.add_argument("--max-candidates", type=int, default=3)
    args = parser.parse_args()

    api_key = os.getenv(args.api_key_env)
    failed_gates: list[str] = []
    if not api_key:
        failed_gates.append(f"missing_api_key_env:{args.api_key_env}")
    path_maps = parse_path_maps(args.path_map)
    candidates: list[dict[str, Any]] = []
    accepted: dict[str, Any] | None = None

    started = time.perf_counter()
    if api_key:
        for index, variant in enumerate(DEFAULT_VARIANTS[: args.max_candidates], start=1):
            candidate_label = f"{args.label}_{index:02d}_{variant['name']}"
            payload: dict[str, Any] = {
                "text": args.text,
                "label": candidate_label,
                "delivery_stage": args.delivery_stage,
                **variant["overrides"],
            }
            if args.ref_audio:
                payload["ref_audio"] = args.ref_audio

            synth = post_json(f"{args.base_url.rstrip('/')}/synthesize", payload)
            audio_path = apply_path_maps(Path(str(synth.get("audio"))), path_maps)
            candidate: dict[str, Any] = {
                "candidate_index": index,
                "variant": variant["name"],
                "payload": payload,
                "synthesis": synth,
                "audio_for_asr": str(audio_path),
                "audio_exists_for_asr": audio_path.exists(),
            }
            if not synth.get("ok"):
                candidate["ok"] = False
                candidate["failed_gates"] = ["synthesis_ok"]
                candidates.append(candidate)
                continue
            if not audio_path.exists():
                candidate["ok"] = False
                candidate["failed_gates"] = ["audio_exists_for_asr"]
                candidates.append(candidate)
                continue
            transcript = transcribe_openai_compatible(args.openai_base_url, api_key, audio_path)
            gate = acceptance_result(
                expected_text=args.text,
                transcript=transcript,
                max_wer=args.max_wer,
                max_duration_ratio=args.max_duration_ratio,
                duration_seconds=synth.get("duration_seconds"),
            )
            candidate.update(
                {
                    "transcript": transcript,
                    "asr_gate": gate,
                    "ok": gate["ok"],
                    "failed_gates": gate["failed_gates"],
                }
            )
            candidates.append(candidate)
            if gate["ok"]:
                accepted = candidate
                break

    if accepted is None:
        failed_gates.append("accepted_candidate_present")

    receipt = {
        "ok": not failed_gates,
        "mocked": False,
        "live": bool(api_key),
        "label": args.label,
        "text": args.text,
        "delivery_stage": args.delivery_stage,
        "base_url": args.base_url,
        "asr_backend": "openai_compatible",
        "openai_base_url": args.openai_base_url,
        "path_maps": {source: str(target) for source, target in path_maps.items()},
        "max_wer": args.max_wer,
        "max_duration_ratio": args.max_duration_ratio,
        "candidate_count": len(candidates),
        "accepted_candidate_index": accepted["candidate_index"] if accepted else None,
        "accepted_audio": accepted["synthesis"]["audio"] if accepted else None,
        "accepted_audio_for_asr": accepted["audio_for_asr"] if accepted else None,
        "candidates": candidates,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "failed_gates": failed_gates,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": receipt["ok"],
                "out": str(args.out),
                "candidate_count": receipt["candidate_count"],
                "accepted_candidate_index": receipt["accepted_candidate_index"],
                "failed_gates": failed_gates,
            }
        )
    )
    return 0 if receipt["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
