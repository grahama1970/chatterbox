#!/usr/bin/env python3
"""Smoke-test ASR-gated batch synthesis through the Chatterbox agent server."""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_TEXT = (
    "Hmm. I found the control family now. It expands to system and information "
    "integrity. The important part is that Embry should say the long form, not "
    "just the acronym, because acronyms are hard to understand in speech."
)


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
        except (ConnectionResetError, urllib.error.URLError, TimeoutError) as exc:
            last_error = str(exc)
        time.sleep(2)
    raise RuntimeError(f"server health did not become ok within {timeout_s}s: {last_error}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8018")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--wait-health-s", default=240, type=int)
    parser.add_argument("--label", default="asr_gated_batch_smoke_script")
    parser.add_argument("--answer-text", default=DEFAULT_TEXT)
    parser.add_argument("--max-chars", default=120, type=int)
    parser.add_argument("--pause-after-ms", default=180, type=int)
    parser.add_argument("--completion-cue", default="Anything else you need?")
    parser.add_argument("--asr-max-wer", default=0.35, type=float)
    parser.add_argument("--asr-max-duration-ratio", default=2.5, type=float)
    parser.add_argument("--asr-max-candidates", default=3, type=int)
    parser.add_argument("--expect-cache-hit", action="store_true")
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    failed_gates: list[str] = []
    base_url = args.base_url.rstrip("/")
    health = wait_for_health(base_url, args.wait_health_s)

    payload: dict[str, Any] = {
        "label": args.label,
        "answer_text": args.answer_text,
        "max_chars": args.max_chars,
        "pause_after_ms": args.pause_after_ms,
        "completion_cue": args.completion_cue,
        "include_completion_cue": True,
        "crossfade_ms": 20,
        "asr_verify": True,
        "asr_max_wer": args.asr_max_wer,
        "asr_max_duration_ratio": args.asr_max_duration_ratio,
        "asr_max_candidates": args.asr_max_candidates,
        "asr_cache": True,
    }

    started = time.perf_counter()
    batch = post_json(f"{base_url}/synthesize-batch", payload, timeout=300)
    client_elapsed_ms = round((time.perf_counter() - started) * 1000, 3)

    if not batch.get("ok"):
        failed_gates.append("batch_ok")
    if not batch.get("asr_verification", {}).get("enabled"):
        failed_gates.append("asr_enabled")
    if batch.get("failed_gates"):
        failed_gates.append("batch_failed_gates_empty")
    chunks = batch.get("chunks") or []
    if not chunks:
        failed_gates.append("chunks_present")
    for chunk in chunks:
        asr = chunk.get("asr_verification") or {}
        if not asr.get("ok"):
            failed_gates.append(f"chunk_{chunk.get('chunk_index')}_asr_ok")
        if asr.get("accepted_candidate_index") is None:
            failed_gates.append(f"chunk_{chunk.get('chunk_index')}_accepted_candidate")
        if args.expect_cache_hit and not (chunk.get("cache") or {}).get("hit"):
            failed_gates.append(f"chunk_{chunk.get('chunk_index')}_cache_hit")
        for candidate in asr.get("candidates") or []:
            gate = (candidate.get("asr") or {}).get("gate") or {}
            if gate.get("repeated_ngram_hits"):
                failed_gates.append(f"chunk_{chunk.get('chunk_index')}_no_repeated_ngram_hits")
    completion = batch.get("completion_cue") or {}
    if args.completion_cue and not completion.get("asr_verification", {}).get("ok"):
        failed_gates.append("completion_cue_asr_ok")
    if args.expect_cache_hit and args.completion_cue and not (completion.get("cache") or {}).get("hit"):
        failed_gates.append("completion_cue_cache_hit")
    finished_metrics = batch.get("finished_response_metrics") or {}
    if int(finished_metrics.get("bytes") or 0) <= 44:
        failed_gates.append("finished_audio_non_empty")
    if float(finished_metrics.get("duration_seconds") or 0.0) <= 0:
        failed_gates.append("finished_audio_duration_present")

    receipt = {
        "ok": not failed_gates,
        "mocked": False,
        "live": True,
        "base_url": base_url,
        "health": health,
        "request": payload,
        "batch": batch,
        "client_elapsed_ms": client_elapsed_ms,
        "failed_gates": failed_gates,
    }
    args.out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": receipt["ok"],
                "out": str(args.out),
                "failed_gates": failed_gates,
                "batch_failed_gates": batch.get("failed_gates"),
                "finished_audio": batch.get("finished_response_audio"),
                "client_elapsed_ms": client_elapsed_ms,
            },
            sort_keys=True,
        )
    )
    return 0 if receipt["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
