#!/usr/bin/env python3
"""Mock memory wait-control packets and verify Chatterbox decisions.

This is wiring-only: it fakes the memory/graph-memory-operator wait prediction
that issue #48 is meant to implement for real. The receipt is intentionally
marked mocked=true/live=false so it cannot be confused with a memory-backed
latency prediction.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from chatterbox.agent.conversation import wait_decision_for_expected_delay


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def fake_memory_wait_packets() -> list[dict[str, Any]]:
    return [
        {
            "turn_id": "mock-turn-long-research",
            "phase": "research_pending",
            "expected_wait_ms": 9000,
            "remaining_wait_ms": 9000,
            "eta_requested": False,
            "allow_hum": True,
            "source": {
                "route": "memory.intent -> brave-search -> answer",
                "prediction_source": "mock_memory_latency_stats",
                "confidence": 0.72,
                "ticket": "https://github.com/grahama1970/graph-memory-operator/issues/48",
            },
        },
        {
            "turn_id": "mock-turn-eta-interrupt",
            "phase": "eta_interruption",
            "expected_wait_ms": 9000,
            "remaining_wait_ms": 9000,
            "eta_requested": True,
            "allow_hum": True,
            "source": {
                "route": "existing_work_continues",
                "prediction_source": "mock_memory_latency_stats",
                "confidence": 0.72,
                "ticket": "https://github.com/grahama1970/graph-memory-operator/issues/48",
            },
        },
    ]


def decision_for_packet(packet: dict[str, Any], *, variant_offset: int) -> dict[str, Any]:
    return wait_decision_for_expected_delay(
        int(packet["remaining_wait_ms"]),
        eta_requested=bool(packet["eta_requested"]),
        allow_hum=bool(packet["allow_hum"]),
        variant_offset=variant_offset,
    )


def build_receipt() -> dict[str, Any]:
    failed_gates: list[str] = []
    packets = fake_memory_wait_packets()
    cases = []
    for packet in packets:
        variant_offset = 4 if not packet["eta_requested"] else 0
        decision = decision_for_packet(packet, variant_offset=variant_offset)
        cases.append({"packet": packet, "chatterbox_wait_decision": decision})

    long_wait = cases[0]["chatterbox_wait_decision"]
    eta = cases[1]["chatterbox_wait_decision"]
    if long_wait["text"] != "This will take a little while. You can grab coffee if you want.":
        failed_gates.append("long_wait_text_expected")
    if not long_wait["should_start_hum"]:
        failed_gates.append("long_wait_starts_hum")
    if not long_wait["hum"]["enabled"]:
        failed_gates.append("long_wait_hum_enabled")
    if eta["text"] != "Probably under ten seconds.":
        failed_gates.append("eta_text_expected")
    if not eta["keeps_existing_work_alive"]:
        failed_gates.append("eta_keeps_existing_work_alive")
    if eta["should_start_hum"]:
        failed_gates.append("eta_does_not_start_hum")

    return {
        "ok": not failed_gates,
        "mocked": True,
        "live": False,
        "created_at_utc": utc_now(),
        "mock_scope": "memory_wait_prediction_only",
        "does_not_prove": [
            "memory.intent latency prediction exists",
            "graph-memory-operator emits wait packets",
            "real hum playback starts",
            "real task telemetry is preserved",
        ],
        "cases": cases,
        "failed_gates": failed_gates,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    receipt = build_receipt()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": receipt["ok"], "out": str(args.out), "failed_gates": receipt["failed_gates"]}, indent=2))
    if receipt["failed_gates"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
