#!/usr/bin/env python3
"""Live memory /intent voice tone sanity check for Embry voice delivery."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CASES = [
    {
        "id": "hostile_boundary",
        "q": "User is hostile; Embry should use a firm humorous boundary.",
        "listener_tone": "hostile",
        "expected_tones": ["deflect_calm", "firm_boundary", "playful_light"],
        "covers_gate": "voice_delivery_tone_expected_deflect_calm_or_firm_boundary_or_playful_light",
    },
    {
        "id": "discouraged_support",
        "q": "User is discouraged; Embry should answer gently and offer the next check.",
        "listener_tone": "discouraged",
        "expected_tones": ["calm_precise", "careful_concerned", "neutral_warm", "relieved"],
        "covers_gate": "voice_delivery_tone_expected_calm_precise_or_careful_concerned_or_neutral_warm_or_relieved",
    },
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def post_json(url: str, payload: dict[str, Any], timeout: int) -> tuple[int | None, dict[str, Any] | None, str | None]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.load(response), None
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {"body": body}
        return exc.code, parsed, f"HTTPError: {exc}"
    except Exception as exc:  # noqa: BLE001 - receipt preserves transport failure.
        return None, None, f"{type(exc).__name__}: {exc}"


def get_json(url: str, timeout: int) -> tuple[dict[str, Any] | None, str | None]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.load(response), None
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"


def run_case(base_url: str, case: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    payload = {
        "q": case["q"],
        "scope": args.scope,
        "session_id": args.session_id,
        "speaker_id": args.speaker_id,
        "speaker_resolution": {
            "status": "known",
            "speaker_id": args.speaker_id,
            "primary_speaker_match": True,
            "source": "memory_intent_voice_tone_smoke",
        },
        "listener_evidence": {
            "source": "memory_intent_voice_tone_smoke",
            "user_tone": case["listener_tone"],
        },
        "voice_delivery": {
            "source": "listener",
            "requested_tone": case["listener_tone"],
        },
    }
    status_code, response, error = post_json(f"{base_url.rstrip('/')}/intent", payload, args.timeout_s)
    voice_delivery = (response or {}).get("voice_delivery") or {}
    actual_tone = voice_delivery.get("tone")
    ok = bool(status_code == 200 and actual_tone in set(case["expected_tones"]))
    failed_gates = []
    if status_code != 200:
        failed_gates.append("memory_intent_http_200")
    if actual_tone not in set(case["expected_tones"]):
        failed_gates.append(case["covers_gate"])
    return {
        "id": case["id"],
        "ok": ok,
        "q_sha256": sha256_text(case["q"]),
        "listener_tone": case["listener_tone"],
        "expected_tones": case["expected_tones"],
        "actual_tone": actual_tone,
        "covers_gate": case["covers_gate"],
        "status_code": status_code,
        "error": error,
        "payload": payload,
        "response": response,
        "voice_delivery": voice_delivery,
        "failed_gates": failed_gates,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--memory-url", default="http://127.0.0.1:8601")
    parser.add_argument("--out-dir", default="/tmp/chatterbox-fork-agent-out/memory-intent-voice-tone/latest", type=Path)
    parser.add_argument("--timeout-s", default=30, type=int)
    parser.add_argument("--scope", default="embry_voice")
    parser.add_argument("--session-id", default="embry-memory-intent-tone-smoke")
    parser.add_argument("--speaker-id", default="horus_lupercal")
    args = parser.parse_args()

    started = time.perf_counter()
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    health, health_error = get_json(f"{args.memory_url.rstrip('/')}/health", args.timeout_s)
    failed_gates: list[str] = []
    if not health or health.get("ok") is not True:
        failed_gates.append("memory_health_ok")

    cases = [run_case(args.memory_url, case, args) for case in CASES] if not failed_gates else []
    for case in cases:
        failed_gates.extend(f"{case['id']}:{gate}" for gate in case["failed_gates"])

    receipt = {
        "schema": "chatterbox.memory_intent_voice_tone.v1",
        "ok": not failed_gates,
        "status": "passed" if not failed_gates else "failed",
        "mocked": False,
        "live": bool(health and health.get("ok") is True),
        "used_ui": False,
        "memory_url": args.memory_url,
        "started_at_utc": datetime.fromtimestamp(
            time.time() - (time.perf_counter() - started),
            timezone.utc,
        ).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "ended_at_utc": utc_now(),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "health": health,
        "health_error": health_error,
        "case_count": len(cases),
        "passing_case_count": sum(1 for case in cases if case["ok"]),
        "cases": cases,
        "failed_gates": failed_gates,
        "claims": {
            "proves": ["memory_intent_voice_tone_routes_hostile_and_discouraged_cases"] if not failed_gates else [],
            "does_not_prove": [
                "RealtimeSTT tone detection",
                "Chatterbox audio rendering",
                "Chat UX synchronization",
                "subjective voice quality",
            ],
        },
    }
    receipt_path = out_dir / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": receipt["ok"],
                "live": receipt["live"],
                "mocked": receipt["mocked"],
                "out": str(receipt_path),
                "failed_gates": failed_gates,
            },
            sort_keys=True,
        )
    )
    return 0 if receipt["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
