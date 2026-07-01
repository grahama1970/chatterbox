#!/usr/bin/env python3
"""Run a live interruption smoke against the Chatterbox agent server.

The smoke asks an Embry-style question, lets the old answer begin, simulates a
barge-in correction, verifies old queued chunks are skipped, and synthesizes a
short recovery utterance so interruption does not feel like a cold stop.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from chatterbox.agent.conversation import run_interruption_scenario


DEFAULT_QUESTION = "Embry, which control family should I use when the answer says SI?"
DEFAULT_FIRST_ANSWER = (
    "I want to be careful with that because saying only the letters can be hard to hear. "
    "The family is System and Information Integrity, and Embry should usually say the "
    "long form before using the short identifier. For a spoken answer, the useful phrasing "
    "is System and Information Integrity, then the specific control name if we know it."
)
DEFAULT_INTERRUPT = "Wait, stop. I need the practical speech rule, not the whole control explanation."
DEFAULT_NEW_ANSWER = (
    "Okay, the practical rule is simple. Say the full control family first, then the short "
    "identifier only if it helps traceability. If the acronym sounds unclear, keep the long "
    "form in the spoken answer and put the raw identifier in the receipt."
)


def get_json(url: str, timeout: int = 30) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.load(response)


async def wait_for_health(base_url: str, timeout_s: int) -> dict:
    deadline = time.monotonic() + timeout_s
    last_error = ""
    while time.monotonic() < deadline:
        try:
            health = await asyncio.to_thread(get_json, f"{base_url.rstrip('/')}/health", 10)
            if health.get("ok"):
                return health
        except (ConnectionResetError, urllib.error.URLError, TimeoutError) as exc:
            last_error = str(exc)
        await asyncio.sleep(2)
    raise RuntimeError(f"server health did not become ok within {timeout_s}s: {last_error}")


async def async_main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8028")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--wait-health-s", default=300, type=int)
    parser.add_argument("--question", default=DEFAULT_QUESTION)
    parser.add_argument("--first-answer", default=DEFAULT_FIRST_ANSWER)
    parser.add_argument("--interrupt-text", default=DEFAULT_INTERRUPT)
    parser.add_argument("--new-answer", default=DEFAULT_NEW_ANSWER)
    parser.add_argument("--variant-offset", type=int, default=4)
    args = parser.parse_args()

    await wait_for_health(args.base_url, args.wait_health_s)
    receipt = await run_interruption_scenario(
        base_url=args.base_url,
        out_dir=args.out_dir,
        question=args.question,
        first_answer=args.first_answer,
        interrupt_text=args.interrupt_text,
        new_answer=args.new_answer,
        variant_offset=args.variant_offset,
    )
    print(
        json.dumps(
            {
                "ok": receipt["ok"],
                "out": str(args.out_dir / "final-response.json"),
                "events": receipt["events_path"],
                "acknowledgement": receipt["acknowledgement"],
                "stale_skipped_count": receipt["stale_skipped_count"],
                "failed_gates": receipt["failed_gates"],
            },
            indent=2,
        )
    )
    return 0 if receipt["ok"] else 1


def main() -> None:
    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
