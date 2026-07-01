#!/usr/bin/env python3
"""Smoke-test a running Chatterbox Turbo agent server."""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def post_json(url: str, payload: dict[str, Any], timeout: int = 120) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def get_json(url: str, timeout: int = 30) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.load(response)


def wait_for_health(base_url: str, timeout_s: int) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    last_error = ""
    while time.monotonic() < deadline:
        try:
            health = get_json(f"{base_url}/health", timeout=10)
            if health.get("ok"):
                return health
        except (ConnectionResetError, urllib.error.URLError, TimeoutError) as exc:
            last_error = str(exc)
        time.sleep(2)
    raise RuntimeError(f"server health did not become ok within {timeout_s}s: {last_error}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8017")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--wait-health-s", default=180, type=int)
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    failed_gates: list[str] = []

    health = wait_for_health(args.base_url.rstrip("/"), args.wait_health_s)
    presets = get_json(f"{args.base_url.rstrip('/')}/presets")
    plan = post_json(
        f"{args.base_url.rstrip('/')}/render-plan",
        {
            "answer_text": (
                "Hmm. I want to be careful here. The integrity answer starts with system and "
                "information integrity, then narrows to memory protection, malicious code "
                "protection, and software, firmware, and information integrity."
            ),
            "max_chars": 140,
            "completion_cue": "Anything else you need?",
        },
    )
    chunks = (plan.get("plan") or {}).get("chunks") or []
    if not chunks:
        failed_gates.append("render_plan_chunks_present")
    synth = post_json(
        f"{args.base_url.rstrip('/')}/synthesize",
        {
            "text": chunks[0]["text"] if chunks else "Agent server smoke.",
            "label": "agent_server_smoke_chunk_01",
            "delivery_stage": chunks[0].get("delivery_stage", "neutral") if chunks else "neutral",
        },
    )
    if not synth.get("ok"):
        failed_gates.append("synthesis_ok")
    if not synth.get("generation_params"):
        failed_gates.append("generation_params_present")
    if synth.get("delivery_stage") != (chunks[0].get("delivery_stage") if chunks else "neutral"):
        failed_gates.append("delivery_stage_roundtrip")
    if "temperature" not in (synth.get("generation_params") or {}):
        failed_gates.append("temperature_param_present")

    batch = post_json(
        f"{args.base_url.rstrip('/')}/synthesize-batch",
        {
            "answer_text": (
                "Hmm. I found the control family now. It expands to system and information "
                "integrity. The important part is that Embry should say the long form, not "
                "just the acronym, because acronyms are hard to understand in speech."
            ),
            "max_chars": 115,
            "pause_after_ms": 300,
            "completion_cue": "Anything else you need?",
            "label": "agent_server_smoke_finished_response",
            "include_completion_cue": True,
        },
        timeout=240,
    )
    if not batch.get("ok"):
        failed_gates.append("batch_synthesis_ok")
    if not batch.get("chunks"):
        failed_gates.append("batch_chunks_present")
    if not batch.get("completion_cue"):
        failed_gates.append("batch_completion_cue_present")
    finished_metrics = batch.get("finished_response_metrics") or {}
    if int(finished_metrics.get("bytes") or 0) <= 44:
        failed_gates.append("batch_finished_response_audio_non_empty")
    if float(finished_metrics.get("duration_seconds") or 0.0) <= 0:
        failed_gates.append("batch_finished_response_duration_present")
    chunk_audios = [chunk.get("audio") for chunk in batch.get("chunks") or [] if chunk.get("audio")]
    if not chunk_audios:
        failed_gates.append("batch_chunk_audio_paths_present")

    receipt = {
        "ok": not failed_gates,
        "mocked": False,
        "live": True,
        "base_url": args.base_url,
        "health": health,
        "presets": presets,
        "render_plan": plan,
        "synthesis": synth,
        "batch_synthesis": batch,
        "failed_gates": failed_gates,
    }
    args.out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": receipt["ok"], "out": str(args.out), "failed_gates": failed_gates}, indent=2))
    if failed_gates:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
