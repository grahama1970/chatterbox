#!/usr/bin/env python3
"""Live proof for bounded PCM publication after stream cancellation (issue #8).

Runs against the real Chatterbox agent server:
  1. baseline non-cancelled stream
  2. mid-stream cancel (cancel issued after first admitted audio)
  3. mid-stream stop
  4. blessed-QRA cached stream mid-cancel
  5. pre-cancelled turn stream suppression

The receipt records cancel acknowledgement time, last emitted-byte time,
post-cancel emitted bytes, and post-cancel audio duration. It proves bounded
server publication after cancellation; it does NOT prove complete
microphone-to-speaker barge-in latency or acoustic echo suppression.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
from pathlib import Path
from typing import Any
from uuid import uuid4

BYTES_PER_SECOND = 24000 * 1 * 2
READ_SIZE = 4096

ANSWER_TEXT = (
    "The first spoken sentence is deliberately long enough to stand alone as one chunk. "
    "The second spoken sentence also stands alone at a very similar length for planning. "
    "The third spoken sentence continues the answer at a comparable overall length. "
    "The fourth spoken sentence closes the cancelled answer with additional trailing words."
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


def stream_with_control(
    base_url: str,
    payload: dict[str, Any],
    *,
    control_action: str | None = None,
    control_turn_id: str | None = None,
    timeout: int = 600,
) -> dict[str, Any]:
    """Read a stream; optionally fire a turn control right after first audio."""
    request = urllib.request.Request(
        f"{base_url}/synthesize-batch-stream",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    total_bytes = 0
    pre_control_bytes = 0
    first_byte_ms = None
    last_byte_ms = None
    control_ack: dict[str, Any] | None = None
    control_sent_ms = None
    control_ack_ms = None
    with urllib.request.urlopen(request, timeout=timeout) as response:
        content_type = response.headers.get("Content-Type", "")
        while True:
            chunk = response.read(READ_SIZE)
            if not chunk:
                break
            now_ms = (time.perf_counter() - started) * 1000
            if first_byte_ms is None:
                first_byte_ms = now_ms
            last_byte_ms = now_ms
            total_bytes += len(chunk)
            if control_action and control_ack is None:
                pre_control_bytes = total_bytes
                control_sent_ms = (time.perf_counter() - started) * 1000
                control_prefix = "turn" if control_action == "cancel" else "playback"
                control_ack = post_json(
                    f"{base_url}/{control_prefix}/{control_turn_id}/{control_action}",
                    {"reason": f"bounded publication proof {control_action}", "old_turn_id": control_turn_id},
                )
                control_ack_ms = (time.perf_counter() - started) * 1000
    post_control_bytes = total_bytes - pre_control_bytes if control_ack else 0
    return {
        "content_type": content_type,
        "total_bytes": total_bytes,
        "total_audio_ms": round(total_bytes / BYTES_PER_SECOND * 1000, 3),
        "first_byte_ms": round(first_byte_ms, 3) if first_byte_ms is not None else None,
        "last_byte_ms": round(last_byte_ms, 3) if last_byte_ms is not None else None,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "control_action": control_action,
        "control_sent_ms": round(control_sent_ms, 3) if control_sent_ms is not None else None,
        "control_ack_ms": round(control_ack_ms, 3) if control_ack_ms is not None else None,
        "control_ack": control_ack,
        "bytes_before_control_ack": pre_control_bytes if control_ack else None,
        "post_control_bytes": post_control_bytes if control_ack else None,
        "post_control_audio_ms": round(post_control_bytes / BYTES_PER_SECOND * 1000, 3) if control_ack else None,
        "last_byte_after_control_ack_ms": (
            round(last_byte_ms - control_ack_ms, 3) if control_ack and last_byte_ms is not None else None
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8018")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--blessed-question", default=None)
    parser.add_argument("--blessed-variant", default=None)
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    failed_gates: list[str] = []

    with urllib.request.urlopen(f"{base_url}/health", timeout=10) as response:
        health = json.loads(response.read().decode("utf-8"))
    if not (health.get("ok") and health.get("model_loaded")):
        raise SystemExit(f"service_not_ready: {health}")

    base_payload = {
        "answer_text": ANSWER_TEXT,
        "max_chars": 90,
        "pause_after_ms": 0,
        "completion_cue": "",
        "include_completion_cue": False,
        "crossfade_ms": 0,
        "use_blessed_qra_cache": False,
    }

    baseline = stream_with_control(base_url, {**base_payload, "label": "bounded_pub_baseline"})
    if baseline["total_bytes"] <= 0:
        failed_gates.append("baseline_stream_emits_audio")

    cancel_turn = f"turn-bp-cancel-{uuid4().hex[:10]}"
    mid_cancel = stream_with_control(
        base_url,
        {**base_payload, "label": "bounded_pub_mid_cancel", "turn_id": cancel_turn},
        control_action="cancel",
        control_turn_id=cancel_turn,
    )
    if not (mid_cancel["control_ack"] or {}).get("ok"):
        failed_gates.append("mid_cancel_ack_ok")
    if mid_cancel["total_bytes"] >= baseline["total_bytes"]:
        failed_gates.append("mid_cancel_suppresses_remaining_chunks")
    if mid_cancel["last_byte_after_control_ack_ms"] is not None and mid_cancel["last_byte_after_control_ack_ms"] > 2000:
        failed_gates.append("mid_cancel_stream_ends_promptly")

    stop_turn = f"turn-bp-stop-{uuid4().hex[:10]}"
    mid_stop = stream_with_control(
        base_url,
        {**base_payload, "label": "bounded_pub_mid_stop", "turn_id": stop_turn},
        control_action="stop",
        control_turn_id=stop_turn,
    )
    if not (mid_stop["control_ack"] or {}).get("ok"):
        failed_gates.append("mid_stop_ack_ok")
    if mid_stop["total_bytes"] >= baseline["total_bytes"]:
        failed_gates.append("mid_stop_suppresses_remaining_chunks")

    pre_turn = f"turn-bp-pre-{uuid4().hex[:10]}"
    pre_ack = post_json(f"{base_url}/turn/{pre_turn}/cancel", {"reason": "pre-cancel proof", "old_turn_id": pre_turn})
    pre_cancelled = stream_with_control(
        base_url, {**base_payload, "label": "bounded_pub_pre_cancel", "turn_id": pre_turn}
    )
    if pre_cancelled["total_bytes"] != 0:
        failed_gates.append("pre_cancelled_turn_stream_emits_zero_bytes")

    blessed = None
    if args.blessed_question:
        blessed_turn = f"turn-bp-blessed-{uuid4().hex[:10]}"
        blessed = stream_with_control(
            base_url,
            {
                "answer_text": " ",
                "question_text": args.blessed_question,
                "label": "bounded_pub_blessed_cancel",
                "turn_id": blessed_turn,
                "use_blessed_qra_cache": True,
                "require_blessed_qra_memory_gate": False,
                "blessed_qra_variant": args.blessed_variant,
                "max_chars": 90,
                "pause_after_ms": 0,
                "completion_cue": "",
                "include_completion_cue": False,
                "crossfade_ms": 0,
            },
            control_action="cancel",
            control_turn_id=blessed_turn,
        )
        if blessed["total_bytes"] <= 0:
            failed_gates.append("blessed_qra_stream_emits_audio_before_cancel")
        if not (blessed["control_ack"] or {}).get("ok"):
            failed_gates.append("blessed_qra_cancel_ack_ok")
        if blessed["last_byte_after_control_ack_ms"] is not None and blessed["last_byte_after_control_ack_ms"] > 2000:
            failed_gates.append("blessed_qra_stream_ends_promptly")

    receipt = {
        "ok": not failed_gates,
        "mocked": False,
        "live": True,
        "proof_scope": "bounded_server_pcm_publication_after_stream_cancellation",
        "does_not_prove": [
            "microphone_to_speaker_barge_in_latency",
            "acoustic_echo_suppression",
            "client_playback_buffer_flush",
        ],
        "note": (
            "post_control_bytes observed at the client include pre-cancel admitted frames still "
            "in transport buffers; the <=40 ms per-frame admission bound is proven by "
            "tests/test_stream_bounded_publication.py at the publication layer."
        ),
        "base_url": base_url,
        "health": {key: health.get(key) for key in ("ok", "engine", "device", "model_loaded", "started_at_utc")},
        "publication_frame_ms": 40,
        "publication_frame_bytes": int(24000 * 0.040) * 2,
        "baseline": baseline,
        "mid_stream_cancel": mid_cancel,
        "mid_stream_stop": mid_stop,
        "pre_cancelled": {"ack": pre_ack, "stream": pre_cancelled},
        "blessed_qra_mid_cancel": blessed,
        "failed_gates": failed_gates,
    }
    args.out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": receipt["ok"],
                "out": str(args.out),
                "baseline_bytes": baseline["total_bytes"],
                "mid_cancel_post_control_bytes": mid_cancel["post_control_bytes"],
                "mid_stop_post_control_bytes": mid_stop["post_control_bytes"],
                "pre_cancelled_bytes": pre_cancelled["total_bytes"],
                "blessed_post_control_bytes": blessed["post_control_bytes"] if blessed else None,
                "failed_gates": failed_gates,
            },
            sort_keys=True,
        )
    )
    return 0 if receipt["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
