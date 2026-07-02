#!/usr/bin/env python3
"""Smoke-test the Chatterbox chunk-streaming endpoint.

This proves stream transport, PCM format, byte count, and playable WAV
conversion. It does not prove ASR text fidelity; use smoke_asr_gated_batch.py
for semantic text/audio checks.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path
from typing import Any


DEFAULT_TEXT = (
    "Okay. I can stream this in short chunks while the rest of the answer is still being prepared. "
    "The important part is that the human hears speech quickly, and the system can still stop between chunks."
)


def get_json(url: str, timeout: int = 30) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.load(response)


def wait_for_health(base_url: str, timeout_s: int) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    last_error = ""
    while time.monotonic() < deadline:
        try:
            health = get_json(f"{base_url.rstrip('/')}/health", timeout=10)
            if health.get("ok"):
                return health
        except (ConnectionResetError, urllib.error.URLError, TimeoutError) as exc:
            last_error = str(exc)
        time.sleep(2)
    raise RuntimeError(f"server health did not become ok within {timeout_s}s: {last_error}")


def run_cmd(cmd: list[str], timeout: int = 30) -> dict[str, Any]:
    result = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)
    return {
        "cmd": cmd,
        "returncode": result.returncode,
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
    }


def ffprobe(path: Path) -> dict[str, Any]:
    probe = run_cmd(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=codec_name,sample_rate,channels",
            "-show_entries",
            "format=duration,size",
            "-of",
            "json",
            str(path),
        ]
    )
    parsed: dict[str, Any] = {"probe": probe}
    if probe["returncode"] == 0:
        data = json.loads(probe["stdout"])
        stream = (data.get("streams") or [{}])[0]
        fmt = data.get("format") or {}
        parsed.update(
            {
                "codec_name": stream.get("codec_name"),
                "sample_rate": int(stream.get("sample_rate") or 0),
                "channels": int(stream.get("channels") or 0),
                "duration_seconds": round(float(fmt.get("duration") or 0.0), 3),
                "bytes": int(fmt.get("size") or 0),
            }
        )
    return parsed


def wav_signal_stats(path: Path) -> dict[str, Any]:
    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        sample_width = handle.getsampwidth()
        frame_count = handle.getnframes()
        frames = handle.readframes(frame_count)
    if sample_width != 2 or not frames:
        return {
            "ok": False,
            "channels": channels,
            "sample_width": sample_width,
            "frame_count": frame_count,
            "error": "unsupported_or_empty_pcm",
        }
    samples = [
        int.from_bytes(frames[index : index + 2], byteorder="little", signed=True)
        for index in range(0, len(frames), 2)
    ]
    if not samples:
        return {"ok": False, "channels": channels, "sample_width": sample_width, "frame_count": frame_count}
    peak = max(abs(sample) for sample in samples)
    rms = math.sqrt(sum(float(sample) * float(sample) for sample in samples) / len(samples))
    clipped_samples = sum(1 for sample in samples if abs(sample) >= 32760)
    return {
        "ok": True,
        "channels": channels,
        "sample_width": sample_width,
        "frame_count": frame_count,
        "sample_count": len(samples),
        "peak": peak,
        "rms": round(rms, 3),
        "clipped_samples": clipped_samples,
        "clipped_ratio": round(clipped_samples / len(samples), 6),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8018")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--wait-health-s", default=240, type=int)
    parser.add_argument("--label", default="stream_endpoint_smoke_script")
    parser.add_argument("--answer-text", default=DEFAULT_TEXT)
    parser.add_argument("--max-chars", default=120, type=int)
    parser.add_argument("--pause-after-ms", default=160, type=int)
    parser.add_argument("--completion-cue", default="Anything else you need?")
    parser.add_argument("--crossfade-ms", default=20, type=int)
    args = parser.parse_args()

    failed_gates: list[str] = []
    base_url = args.base_url.rstrip("/")
    out_dir = args.out.parent / args.out.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    pcm_path = out_dir / "stream.pcm"
    wav_path = out_dir / "stream.wav"
    args.out.parent.mkdir(parents=True, exist_ok=True)

    health = wait_for_health(base_url, args.wait_health_s)
    payload = {
        "label": args.label,
        "answer_text": args.answer_text,
        "max_chars": args.max_chars,
        "pause_after_ms": args.pause_after_ms,
        "completion_cue": args.completion_cue,
        "include_completion_cue": True,
        "crossfade_ms": args.crossfade_ms,
    }
    request = urllib.request.Request(
        f"{base_url}/synthesize-batch-stream",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    first_byte_ms = None
    total_bytes = 0
    chunk_count = 0
    chunk_read_events: list[dict[str, Any]] = []
    headers: dict[str, str] = {}
    with urllib.request.urlopen(request, timeout=300) as response, pcm_path.open("wb") as handle:
        headers = {key.lower(): value for key, value in response.headers.items()}
        while True:
            chunk = response.read(65536)
            if not chunk:
                break
            if first_byte_ms is None:
                first_byte_ms = round((time.perf_counter() - started) * 1000, 3)
            chunk_count += 1
            total_bytes += len(chunk)
            chunk_read_events.append(
                {
                    "index": chunk_count,
                    "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                    "bytes": len(chunk),
                    "total_bytes": total_bytes,
                }
            )
            handle.write(chunk)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)

    convert = run_cmd(
        [
            "ffmpeg",
            "-y",
            "-f",
            "s16le",
            "-ar",
            "24000",
            "-ac",
            "1",
            "-i",
            str(pcm_path),
            str(wav_path),
        ],
        timeout=60,
    )
    metrics = ffprobe(wav_path)
    signal_stats = wav_signal_stats(wav_path) if wav_path.exists() else {"ok": False, "error": "wav_missing"}

    if "audio/l16" not in headers.get("content-type", "").lower():
        failed_gates.append("content_type_audio_l16")
    if headers.get("transfer-encoding", "").lower() != "chunked":
        failed_gates.append("transfer_encoding_chunked")
    if total_bytes <= 44:
        failed_gates.append("stream_bytes_non_empty")
    if chunk_count <= 0:
        failed_gates.append("stream_chunks_present")
    if first_byte_ms is None:
        failed_gates.append("first_byte_observed")
    if convert["returncode"] != 0:
        failed_gates.append("pcm_to_wav_conversion_ok")
    if metrics.get("codec_name") != "pcm_s16le":
        failed_gates.append("wav_codec_pcm_s16le")
    if metrics.get("sample_rate") != 24000:
        failed_gates.append("wav_sample_rate_24000")
    if metrics.get("channels") != 1:
        failed_gates.append("wav_mono")
    if float(metrics.get("duration_seconds") or 0.0) <= 0:
        failed_gates.append("wav_duration_present")
    if not signal_stats.get("ok"):
        failed_gates.append("wav_signal_stats_ok")
    if float(signal_stats.get("rms") or 0.0) <= 1.0:
        failed_gates.append("wav_non_silent")
    if float(signal_stats.get("clipped_ratio") or 0.0) > 0.01:
        failed_gates.append("wav_not_clipped")
    if chunk_read_events and chunk_read_events != sorted(chunk_read_events, key=lambda item: item["elapsed_ms"]):
        failed_gates.append("stream_chunk_events_ordered")
    if first_byte_ms is not None and elapsed_ms <= first_byte_ms:
        failed_gates.append("stream_progress_after_first_byte")

    receipt = {
        "ok": not failed_gates,
        "mocked": False,
        "live": True,
        "proof_scope": "stream_transport_pcm_audio_only",
        "does_not_prove": ["asr_text_fidelity", "semantic_answer_quality"],
        "base_url": base_url,
        "health": health,
        "request": payload,
        "headers": headers,
        "pcm_path": str(pcm_path),
        "wav_path": str(wav_path),
        "first_byte_ms": first_byte_ms,
        "elapsed_ms": elapsed_ms,
        "stream_chunk_reads": chunk_count,
        "stream_chunk_read_events": chunk_read_events,
        "stream_bytes": total_bytes,
        "conversion": convert,
        "wav_metrics": metrics,
        "wav_signal_stats": signal_stats,
        "failed_gates": failed_gates,
    }
    args.out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": receipt["ok"],
                "out": str(args.out),
                "wav": str(wav_path),
                "first_byte_ms": first_byte_ms,
                "elapsed_ms": elapsed_ms,
                "stream_bytes": total_bytes,
                "failed_gates": failed_gates,
            },
            sort_keys=True,
        )
    )
    return 0 if receipt["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
