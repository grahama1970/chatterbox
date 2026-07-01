#!/usr/bin/env python3
"""Pre-render reusable Embry voice cache phrases from a live Chatterbox server.

The cache covers non-factual speech only: interruption acknowledgements and
low-buffer wait responses. The manifest records exact text hashes, audio paths,
durations, and the expected-delay window used by a future voice coordinator.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from chatterbox.agent.conversation import (
    ETA_RESPONSE_RULES,
    INTERRUPTION_ACKNOWLEDGEMENTS,
    LOW_BUFFER_FILLERS,
    WAIT_RESPONSE_RULES,
    has_internal_terms,
    sha256_text,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_slug(text: str, max_len: int = 44) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", text.lower()).strip("_")
    return slug[:max_len] or "phrase"


def cache_id(material: dict[str, Any]) -> str:
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def wait_for_health(client: httpx.Client, base_url: str, timeout_s: int) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    last_error = ""
    while time.monotonic() < deadline:
        try:
            response = client.get(f"{base_url.rstrip('/')}/health", timeout=10)
            response.raise_for_status()
            health = response.json()
            if health.get("ok"):
                return health
        except (httpx.HTTPError, TimeoutError) as exc:
            last_error = str(exc)
        time.sleep(2)
    raise RuntimeError(f"server health did not become ok within {timeout_s}s: {last_error}")


def cache_usages() -> list[dict[str, Any]]:
    usages: list[dict[str, Any]] = []
    for index, text in enumerate(INTERRUPTION_ACKNOWLEDGEMENTS, start=1):
        usages.append(
            {
                "category": "interruption_acknowledgement",
                "usage_index": index,
                "text": text,
                "delivery_stage": "holding",
                "recommended_idle_action": "speak_after_barge_in",
                "min_wait_ms": None,
                "max_wait_ms": None,
            }
        )
    for index, text in enumerate(LOW_BUFFER_FILLERS, start=1):
        usages.append(
            {
                "category": "low_buffer_filler",
                "usage_index": index,
                "text": text,
                "delivery_stage": "holding",
                "recommended_idle_action": "speak_filler",
                "min_wait_ms": 700,
                "max_wait_ms": 3000,
            }
        )
    for rule_index, rule in enumerate(WAIT_RESPONSE_RULES, start=1):
        for text_index, text in enumerate(rule["texts"], start=1):
            usages.append(
                {
                    "category": "expected_wait_response",
                    "usage_index": text_index,
                    "wait_rule_index": rule_index,
                    "text": text,
                    "delivery_stage": "holding",
                    "recommended_idle_action": rule["recommended_idle_action"],
                    "min_wait_ms": rule["min_wait_ms"],
                    "max_wait_ms": rule["max_wait_ms"],
                    "hum_candidate": rule["recommended_idle_action"] == "speak_then_optional_hum",
                }
            )
    for rule_index, rule in enumerate(ETA_RESPONSE_RULES, start=1):
        for text_index, text in enumerate(rule["texts"], start=1):
            usages.append(
                {
                    "category": "eta_response",
                    "usage_index": text_index,
                    "wait_rule_index": rule_index,
                    "text": text,
                    "delivery_stage": "holding",
                    "recommended_idle_action": "speak_eta_keep_work_alive",
                    "min_wait_ms": rule["min_wait_ms"],
                    "max_wait_ms": rule["max_wait_ms"],
                    "interrupt_policy": "answer_eta_without_cancelling_work",
                }
            )
    return usages


def render_cache_entries(usages: list[dict[str, Any]], ref_audio: str | None) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for usage in usages:
        material = {
            "engine": "chatterbox_turbo",
            "text_sha256": sha256_text(usage["text"]),
            "delivery_stage": usage["delivery_stage"],
            "ref_audio": ref_audio,
        }
        render_key = cache_id(material)
        unique.setdefault(
            render_key,
            {
                "render_cache_key": render_key,
                "render_material": material,
                "text": usage["text"],
                "text_sha256": material["text_sha256"],
                "delivery_stage": usage["delivery_stage"],
                "usages": [],
            },
        )
        unique[render_key]["usages"].append(usage)
    return list(unique.values())


def synthesize_entry(
    client: httpx.Client,
    base_url: str,
    entry: dict[str, Any],
    index: int,
    ref_audio: str | None,
) -> dict[str, Any]:
    label = f"voice_cache_{index:03d}_{safe_slug(entry['text'])}"
    payload = {
        "text": entry["text"],
        "label": label,
        "delivery_stage": entry["delivery_stage"],
    }
    if ref_audio:
        payload["ref_audio"] = ref_audio
    started = time.perf_counter()
    response = client.post(f"{base_url.rstrip('/')}/synthesize", json=payload, timeout=240)
    response.raise_for_status()
    result = response.json()
    result["roundtrip_seconds"] = round(time.perf_counter() - started, 3)
    result["label"] = label
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8028")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--wait-health-s", default=300, type=int)
    parser.add_argument("--ref-audio", default=None)
    parser.add_argument("--max-items", type=int, default=None)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    failed_gates: list[str] = []
    started = time.perf_counter()
    usages = cache_usages()
    entries = render_cache_entries(usages, args.ref_audio)
    if args.max_items is not None:
        entries = entries[: args.max_items]

    with httpx.Client() as client:
        health = wait_for_health(client, args.base_url, args.wait_health_s)
        rendered = []
        for index, entry in enumerate(entries, start=1):
            if has_internal_terms(entry["text"]):
                failed_gates.append(f"no_internal_terms:{index}")
            result = synthesize_entry(client, args.base_url, entry, index, args.ref_audio)
            metrics = result.get("metrics") or {}
            if not result.get("ok"):
                failed_gates.append(f"synthesis_ok:{index}")
            if int(metrics.get("bytes") or 0) <= 44:
                failed_gates.append(f"audio_non_empty:{index}")
            if result.get("text_sha256") != entry["text_sha256"]:
                failed_gates.append(f"text_hash_roundtrip:{index}")
            rendered.append({**entry, "synthesis": result})

    usage_count_by_category: dict[str, int] = {}
    for usage in usages:
        usage_count_by_category[usage["category"]] = usage_count_by_category.get(usage["category"], 0) + 1

    manifest = {
        "ok": not failed_gates,
        "mocked": False,
        "live": True,
        "created_at_utc": utc_now(),
        "base_url": args.base_url,
        "health": health,
        "ref_audio": args.ref_audio,
        "usage_count": len(usages),
        "usage_count_by_category": usage_count_by_category,
        "rendered_unique_count": len(rendered),
        "expected_wait_rules": WAIT_RESPONSE_RULES,
        "eta_response_rules": ETA_RESPONSE_RULES,
        "entries": rendered,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "failed_gates": failed_gates,
    }
    out_path = args.out_dir / "voice-cache-manifest.json"
    out_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": manifest["ok"],
                "out": str(out_path),
                "usage_count": manifest["usage_count"],
                "rendered_unique_count": manifest["rendered_unique_count"],
                "failed_gates": failed_gates,
            },
            indent=2,
        )
    )
    if failed_gates:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
