#!/usr/bin/env python3
"""Smoke-test stream suppression for a cancelled turn."""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from uuid import uuid4


DEFAULT_TEXT = (
    "This old turn should not keep speaking after the listener cancels it. "
    "The stream must observe the cancelled turn id before emitting audio."
)


def post_json(url: str, payload: dict[str, Any], timeout: int = 30) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def wait_for_health(base_url: str, timeout_s: int) -> dict[str, Any]:
    deadline = time.time() + timeout_s
    last_error = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/health", timeout=5) as response:
                data = json.loads(response.read().decode("utf-8"))
            if data.get("ok") and data.get("model_loaded"):
                return data
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = str(exc)
        time.sleep(2)
    raise SystemExit(f"health_not_ready: {last_error}")


def read_stream(base_url: str, payload: dict[str, Any], timeout: int, max_bytes: int | None = None) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{base_url}/synthesize-batch-stream",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    total_bytes = 0
    read_count = 0
    first_byte_ms = None
    headers: dict[str, str] = {}
    with urllib.request.urlopen(request, timeout=timeout) as response:
        headers = {key.lower(): value for key, value in response.headers.items()}
        while True:
            chunk = response.read(65536)
            if not chunk:
                break
            if first_byte_ms is None:
                first_byte_ms = round((time.perf_counter() - started) * 1000, 3)
            read_count += 1
            total_bytes += len(chunk)
            if max_bytes is not None and total_bytes >= max_bytes:
                break
    return {
        "headers": headers,
        "bytes": total_bytes,
        "read_count": read_count,
        "first_byte_ms": first_byte_ms,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8018")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--wait-health-s", default=240, type=int)
    parser.add_argument("--label", default="stream_turn_cancel_smoke")
    parser.add_argument("--answer-text", default=DEFAULT_TEXT)
    parser.add_argument("--max-chars", default=80, type=int)
    parser.add_argument("--pause-after-ms", default=0, type=int)
    parser.add_argument("--crossfade-ms", default=0, type=int)
    parser.add_argument("--stream-timeout-s", default=300, type=int)
    args = parser.parse_args()

    failed_gates: list[str] = []
    base_url = args.base_url.rstrip("/")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    health = wait_for_health(base_url, args.wait_health_s)

    baseline_payload = {
        "label": f"{args.label}_baseline",
        "answer_text": args.answer_text,
        "max_chars": args.max_chars,
        "pause_after_ms": args.pause_after_ms,
        "completion_cue": "",
        "include_completion_cue": False,
        "crossfade_ms": args.crossfade_ms,
    }
    baseline_stream = read_stream(base_url, baseline_payload, args.stream_timeout_s, max_bytes=65536)

    turn_id = f"turn-cancel-{uuid4().hex[:12]}"
    cancel = post_json(
        f"{base_url}/turn/{turn_id}/cancel",
        {"reason": "stream cancellation smoke", "old_turn_id": turn_id},
    )
    cancelled_payload = {
        **baseline_payload,
        "label": f"{args.label}_cancelled",
        "turn_id": turn_id,
    }
    cancelled_stream = read_stream(base_url, cancelled_payload, args.stream_timeout_s)

    if baseline_stream["bytes"] <= 0:
        failed_gates.append("baseline_stream_emits_audio")
    if not cancel.get("ok"):
        failed_gates.append("cancel_endpoint_ok")
    if not cancel.get("control", {}).get("cancelled"):
        failed_gates.append("cancelled_state_true")
    if cancelled_stream["bytes"] != 0:
        failed_gates.append("cancelled_turn_stream_emits_zero_bytes")
    if "audio/l16" not in cancelled_stream["headers"].get("content-type", "").lower():
        failed_gates.append("cancelled_stream_content_type_audio_l16")

    receipt = {
        "ok": not failed_gates,
        "mocked": False,
        "live": True,
        "proof_scope": "pre_cancelled_turn_stream_suppression",
        "does_not_prove": [
            "live_microphone_listener",
            "mid_buffer_audio_device_flush",
            "semantic_answer_quality",
        ],
        "base_url": base_url,
        "health": health,
        "turn_id": turn_id,
        "baseline_request": baseline_payload,
        "baseline_stream": baseline_stream,
        "cancel": cancel,
        "cancelled_request": cancelled_payload,
        "cancelled_stream": cancelled_stream,
        "old_turn_bytes_after_cancel": cancelled_stream["bytes"],
        "failed_gates": failed_gates,
    }
    args.out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": receipt["ok"],
                "out": str(args.out),
                "baseline_bytes": baseline_stream["bytes"],
                "old_turn_bytes_after_cancel": cancelled_stream["bytes"],
                "failed_gates": failed_gates,
            },
            sort_keys=True,
        )
    )
    return 0 if receipt["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
