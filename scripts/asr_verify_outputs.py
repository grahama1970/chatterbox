#!/usr/bin/env python3
"""ASR verification harness for generated Chatterbox WAV artifacts.

The script reads one or more receipt JSON files, finds chunk audio records, and
transcribes them with faster-whisper when available. It writes a JSON receipt
that separates exact transport evidence from text-fidelity evidence.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chatterbox.agent.asr_acceptance import acceptance_result, word_error_rate


def word_error_proxy(expected: str, actual: str) -> float:
    return word_error_rate(expected, actual)


@dataclass
class AudioCase:
    label: str
    audio: Path
    expected_text: str
    text_sha256: str | None = None


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


def iter_audio_cases(
    receipt: dict[str, Any],
    base_path: Path,
    path_maps: dict[str, Path] | None = None,
) -> list[AudioCase]:
    cases: list[AudioCase] = []
    path_maps = path_maps or {}

    sources: list[dict[str, Any]] = [receipt]
    for key in ("batch_synthesis", "synthesis"):
        nested = receipt.get(key)
        if isinstance(nested, dict):
            sources.append(nested)

    for source in sources:
        source_items = source.get("chunks") or source.get("spoken_results") or []
        if not source_items and source.get("audio") and source.get("text"):
            source_items = [source]

        for item in source_items:
            audio = item.get("audio")
            text = item.get("text")
            if not audio or not text:
                continue
            audio_path = Path(audio)
            if not audio_path.is_absolute():
                audio_path = base_path / audio_path
            audio_path = apply_path_maps(audio_path, path_maps)
            cases.append(
                AudioCase(
                    label=str(item.get("label") or item.get("chunk_index") or audio_path.stem),
                    audio=audio_path,
                    expected_text=str(text),
                    text_sha256=item.get("text_sha256"),
                )
            )

        completion = source.get("completion_cue")
        if isinstance(completion, dict) and completion.get("audio") and completion.get("text"):
            audio_path = Path(str(completion["audio"]))
            if not audio_path.is_absolute():
                audio_path = base_path / audio_path
            audio_path = apply_path_maps(audio_path, path_maps)
            cases.append(
                AudioCase(
                    label=str(completion.get("label") or audio_path.stem),
                    audio=audio_path,
                    expected_text=str(completion["text"]),
                    text_sha256=completion.get("text_sha256"),
                )
            )

    return cases


def load_faster_whisper(model_name: str, device: str, compute_type: str):
    try:
        from faster_whisper import WhisperModel
    except Exception as exc:  # noqa: BLE001 - reported in receipt
        return None, f"{type(exc).__name__}: {exc}"
    return WhisperModel(model_name, device=device, compute_type=compute_type), None


def transcribe(model: Any, audio_path: Path) -> str:
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("receipts", nargs="+", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--model", default="small.en")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--compute-type", default="int8")
    parser.add_argument("--max-wer-proxy", type=float, default=0.08)
    parser.add_argument("--allow-missing-asr", action="store_true")
    parser.add_argument("--openai-base-url", default=None)
    parser.add_argument("--api-key-env", default="WHISPER_API_KEY")
    parser.add_argument(
        "--path-map",
        action="append",
        default=[],
        help="Map receipt audio paths from container to host paths, e.g. /out=/tmp/chatterbox-out.",
    )
    args = parser.parse_args()
    path_maps = parse_path_maps(args.path_map)

    model = None
    load_error = None
    remote_api_key = os.getenv(args.api_key_env) if args.openai_base_url else None
    if args.openai_base_url and not remote_api_key:
        load_error = f"missing_api_key_env:{args.api_key_env}"
    elif not args.openai_base_url:
        model, load_error = load_faster_whisper(args.model, args.device, args.compute_type)
    failed_gates: list[str] = []
    if model is None and not remote_api_key:
        failed_gates.append("asr_backend_available")
        if not args.allow_missing_asr:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(
                json.dumps(
                    {
                        "ok": False,
                        "mocked": False,
                        "live": False,
                        "asr_backend": "openai_compatible" if args.openai_base_url else "faster_whisper",
                        "asr_backend_error": load_error,
                        "failed_gates": failed_gates,
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            return 2

    results: list[dict[str, Any]] = []
    audio_case_count = 0
    for receipt_path in args.receipts:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        cases = iter_audio_cases(receipt, receipt_path.parent, path_maps)
        audio_case_count += len(cases)
        for case in cases:
            item: dict[str, Any] = {
                "label": case.label,
                "audio": str(case.audio),
                "audio_exists": case.audio.exists(),
                "expected_text": case.expected_text,
                "expected_text_sha256": case.text_sha256,
            }
            if not case.audio.exists():
                item["ok"] = False
                item["failed_gates"] = ["audio_exists"]
                failed_gates.append(f"{case.label}:audio_exists")
                results.append(item)
                continue
            if model is None and not remote_api_key:
                item["ok"] = False
                item["failed_gates"] = ["asr_backend_available"]
                results.append(item)
                continue
            transcript = (
                transcribe_openai_compatible(args.openai_base_url, remote_api_key, case.audio)
                if args.openai_base_url and remote_api_key
                else transcribe(model, case.audio)
            )
            gate = acceptance_result(
                expected_text=case.expected_text,
                transcript=transcript,
                max_wer=args.max_wer_proxy,
            )
            item.update(
                {
                    "transcript": transcript,
                    "wer_proxy": gate["wer"],
                    "repeated_ngram_hits": gate["repeated_ngram_hits"],
                    "ok": gate["ok"],
                    "failed_gates": gate["failed_gates"],
                }
            )
            if not item["ok"]:
                failed_gates.extend(f"{case.label}:{gate_name}" for gate_name in item["failed_gates"])
            results.append(item)

    if audio_case_count == 0:
        failed_gates.append("audio_cases_present")

    receipt_out = {
        "ok": not failed_gates,
        "mocked": False,
        "live": model is not None or remote_api_key is not None,
        "asr_backend": "openai_compatible" if args.openai_base_url else "faster_whisper",
        "openai_base_url": args.openai_base_url,
        "asr_model": args.model,
        "device": args.device,
        "compute_type": args.compute_type,
        "max_wer_proxy": args.max_wer_proxy,
        "path_maps": {source: str(target) for source, target in path_maps.items()},
        "audio_case_count": audio_case_count,
        "results": results,
        "failed_gates": failed_gates,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt_out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": receipt_out["ok"], "out": str(args.out), "failed_gates": failed_gates}))
    return 0 if receipt_out["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
