#!/usr/bin/env python3
"""Smoke-test live turn cancel/duck/stop control endpoints."""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from uuid import uuid4


def get_json(url: str, timeout: int = 30) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.load(response)


def post_json(url: str, payload: dict[str, Any], timeout: int = 30) -> dict[str, Any]:
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
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    health = wait_for_health(base_url, args.wait_health_s)
    turn_id = f"turn-control-smoke-{uuid4().hex[:8]}"
    new_turn_id = f"turn-control-new-{uuid4().hex[:8]}"

    failed_gates: list[str] = []
    requests = [
        (
            "cancel",
            f"{base_url}/turn/{turn_id}/cancel",
            {"reason": "barge-in", "old_turn_id": turn_id, "new_turn_id": new_turn_id},
        ),
        (
            "duck",
            f"{base_url}/playback/{turn_id}/duck",
            {"reason": "user starts speaking", "old_turn_id": turn_id, "new_turn_id": new_turn_id},
        ),
        (
            "stop",
            f"{base_url}/playback/{turn_id}/stop",
            {"reason": "new turn takes floor", "old_turn_id": turn_id, "new_turn_id": new_turn_id},
        ),
    ]
    responses: list[dict[str, Any]] = []
    for action, url, payload in requests:
        response = post_json(url, payload)
        responses.append({"action": action, "request": payload, "response": response})
        if not response.get("ok"):
            failed_gates.append(f"{action}_response_ok")
        control = response.get("control") or {}
        if control.get("turn_id") != turn_id:
            failed_gates.append(f"{action}_turn_id_matches")

    final_control = (responses[-1].get("response") or {}).get("control") or {}
    action_order = [event.get("action") for event in final_control.get("events") or []]
    if action_order[-3:] != ["cancel", "duck", "stop"]:
        failed_gates.append("control_event_order")
    if not final_control.get("cancelled"):
        failed_gates.append("cancelled_state_true")
    if not final_control.get("stale_chunks_should_skip"):
        failed_gates.append("stale_chunks_should_skip_true")
    if not final_control.get("ducked"):
        failed_gates.append("ducked_state_true")
    if not final_control.get("stopped"):
        failed_gates.append("stopped_state_true")

    receipt = {
        "ok": not failed_gates,
        "mocked": False,
        "live": True,
        "proof_scope": "live_turn_control_endpoint_state_smoke",
        "does_not_prove": [
            "client_audio_player_stops_immediately",
            "networked client receives control events",
            "human-perceived interruption quality",
        ],
        "base_url": base_url,
        "health": health,
        "turn_id": turn_id,
        "new_turn_id": new_turn_id,
        "responses": responses,
        "final_control": final_control,
        "action_order": action_order,
        "failed_gates": failed_gates,
    }
    args.out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": receipt["ok"],
                "out": str(args.out),
                "action_order": action_order[-3:],
                "failed_gates": failed_gates,
            },
            sort_keys=True,
        )
    )
    return 0 if receipt["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
