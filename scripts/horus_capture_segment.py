#!/usr/bin/env python3
"""Segment and verify an agent-driven Horus capture batch.

The agent starts a single continuous recording, shows the human a batch of
lines, and stops the recording when they finish reading. This script then does
everything else: split on silence, transcribe each segment, align it to the
expected line, score the level, and emit a manifest.

The human only speaks. No CLI operation is delegated to them.

    python3 scripts/horus_capture_segment.py \
        --wav /path/capture.wav --expected /path/expected.json \
        --out-dir /path/session --corpus clone
"""

from __future__ import annotations

import argparse
import audioop
import json
import re
import subprocess
import sys
import wave
from datetime import datetime, timezone
from pathlib import Path


def read_mono(path: Path) -> tuple[bytes, int]:
    with wave.open(str(path), "rb") as handle:
        rate = handle.getframerate()
        frames = handle.readframes(handle.getnframes())
        if handle.getnchannels() == 2:
            frames = audioop.tomono(frames, 2, 0.5, 0.5)
    return frames, rate


def window_rms(pcm: bytes, rate: int, window_ms: int = 50) -> list[int]:
    step = max(1, int(rate * window_ms / 1000)) * 2
    return [audioop.rms(pcm[i:i + step], 2) for i in range(0, len(pcm) - step, step)]


def noise_floor(levels: list[int]) -> int:
    """Estimate the floor from the quietest decile, so a noisy room still works."""
    if not levels:
        return 0
    ordered = sorted(levels)
    tail = ordered[: max(1, len(ordered) // 10)]
    return sum(tail) // len(tail)


def segment(pcm: bytes, rate: int, min_speech_ms: int, min_gap_ms: int) -> list[tuple[int, int]]:
    """Split into speech spans using an adaptive threshold above the noise floor."""
    window_ms = 50
    levels = window_rms(pcm, rate, window_ms)
    floor = noise_floor(levels)
    # Speech must clear the floor by a healthy margin, with an absolute minimum
    # so a dead-silent room does not make every tick look like speech.
    threshold = max(floor * 3, 400)

    gap_windows = max(1, min_gap_ms // window_ms)
    spans: list[tuple[int, int]] = []
    start = None
    quiet = 0
    for index, level in enumerate(levels):
        if level >= threshold:
            if start is None:
                start = index
            quiet = 0
        elif start is not None:
            quiet += 1
            if quiet >= gap_windows:
                spans.append((start, index - quiet))
                start = None
                quiet = 0
    if start is not None:
        spans.append((start, len(levels) - 1))

    min_windows = max(1, min_speech_ms // window_ms)
    kept = [(a, b) for a, b in spans if (b - a) >= min_windows]
    bytes_per_window = max(1, int(rate * window_ms / 1000)) * 2
    # Pad slightly so consonant onsets/offsets are not clipped off.
    pad = bytes_per_window * 4
    out = []
    for a, b in kept:
        lo = max(0, a * bytes_per_window - pad)
        hi = min(len(pcm), (b + 1) * bytes_per_window + pad)
        out.append((lo, hi))
    return out


def write_wav(path: Path, pcm: bytes, rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(pcm)


def normalize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def similarity(expected: str, actual: str) -> float:
    """Token overlap ratio - robust enough to confirm the right line was read."""
    exp, act = normalize(expected), normalize(actual)
    if not exp:
        return 0.0
    matched = 0
    remaining = list(act)
    for token in exp:
        if token in remaining:
            remaining.remove(token)
            matched += 1
    return matched / len(exp)


def transcribe(path: Path, model: str) -> str:
    result = subprocess.run(
        ["whisper", str(path), "--model", model, "--language", "en",
         "--output_format", "txt", "--output_dir", str(path.parent),
         "--fp16", "False"],
        capture_output=True, text=True, check=False,
    )
    txt = path.with_suffix(".txt")
    if txt.exists():
        return txt.read_text().strip()
    return result.stdout.strip()


def level_verdict(rms: int, peak: int) -> tuple[bool, str]:
    if peak >= 32700:
        return False, f"clipping (peak {peak})"
    if rms < 700:
        return False, f"too quiet (rms {rms})"
    if rms > 13000:
        return False, f"too hot (rms {rms})"
    return True, f"ok (rms {rms}, peak {peak})"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wav", required=True, type=Path)
    parser.add_argument("--expected", required=True, type=Path,
                        help="JSON list of {label, text}")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--speaker", default="horus")
    parser.add_argument("--model", default="base")
    parser.add_argument("--min-speech-ms", type=int, default=700)
    parser.add_argument("--min-gap-ms", type=int, default=450)
    parser.add_argument("--match-threshold", type=float, default=0.6)
    args = parser.parse_args()

    expected = json.loads(args.expected.read_text())
    pcm, rate = read_mono(args.wav)
    spans = segment(pcm, rate, args.min_speech_ms, args.min_gap_ms)

    report = {
        "schema": "embry.horus_capture_batch.v1",
        "corpus": args.corpus,
        "speaker": args.speaker,
        "synthetic": False,
        "provenance": "physical_human_recording",
        "source_wav": str(args.wav),
        "rate": rate,
        "expected_count": len(expected),
        "detected_count": len(spans),
        "segmented_at": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "takes": [],
    }

    # Report the count mismatch loudly rather than silently zipping mismatched lists.
    pairs = min(len(spans), len(expected))
    for index in range(pairs):
        lo, hi = spans[index]
        chunk = pcm[lo:hi]
        item = expected[index]
        name = f"{index + 1:03d}_{item['label']}.wav"
        dest = args.out_dir / name
        write_wav(dest, chunk, rate)

        rms = audioop.rms(chunk, 2)
        peak = audioop.max(chunk, 2)
        level_ok, level_note = level_verdict(rms, peak)
        heard = transcribe(dest, args.model)
        match = similarity(item["text"], heard)
        text_ok = match >= args.match_threshold

        report["takes"].append({
            "file": name,
            "label": item["label"],
            "expected_text": item["text"],
            "heard_text": heard,
            "match_ratio": round(match, 3),
            "seconds": round(len(chunk) / 2 / rate, 2),
            "rms": rms,
            "peak": peak,
            "level_ok": level_ok,
            "level_note": level_note,
            "text_ok": text_ok,
            "accepted": bool(level_ok and text_ok),
        })

    report["accepted_count"] = sum(1 for t in report["takes"] if t["accepted"])
    report["retake_labels"] = [t["label"] for t in report["takes"] if not t["accepted"]]
    if len(spans) != len(expected):
        report["warning"] = (
            f"detected {len(spans)} speech spans but expected {len(expected)} lines; "
            "alignment beyond the shorter list is unverified"
        )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "batch_report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != "takes"}, indent=2))
    for take in report["takes"]:
        flag = "OK " if take["accepted"] else "RETAKE"
        print(f"{flag} {take['file']:28s} match={take['match_ratio']:.2f} "
              f"{take['level_note']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
