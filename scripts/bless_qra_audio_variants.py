#!/usr/bin/env python3
"""Create blessed QRA audio variants for instant Chatterbox playback."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_VARIANTS = [
    {"id": "default_fast", "name": "Default fast", "delivery_stage": "neutral", "pause_after_ms": 0, "default": True},
    {"id": "gentle", "name": "Gentle", "delivery_stage": "slightly_concerned", "pause_after_ms": 180},
    {"id": "warm", "name": "Warm", "delivery_stage": "positive", "pause_after_ms": 120},
    {"id": "confident", "name": "Confident", "delivery_stage": "satisfied", "pause_after_ms": 60},
    {"id": "urgent_clear", "name": "Urgent clear", "delivery_stage": "neutral", "pause_after_ms": 0},
]


def post_json(url: str, payload: dict[str, Any], timeout: int = 300) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def wait_for_health(base_url: str, timeout_s: int) -> dict[str, Any]:
    deadline = time.time() + timeout_s
    last_error = ""
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url.rstrip('/')}/health", timeout=5) as response:
                health = json.loads(response.read().decode("utf-8"))
            if health.get("ok"):
                return health
        except Exception as exc:  # noqa: BLE001 - receipt captures last error
            last_error = f"{type(exc).__name__}: {exc}"
        time.sleep(2)
    raise RuntimeError(f"server health not ready: {last_error}")


def load_ledger(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "schema_version": "blessed_qra_response_cache.v1",
            "enabled": True,
            "entries": [],
        }
    return json.loads(path.read_text(encoding="utf-8"))


def host_path_for_audio(audio: str, *, container_out_prefix: str, host_out_dir: Path | None) -> Path:
    path = Path(audio)
    if host_out_dir and audio.startswith(container_out_prefix.rstrip("/") + "/"):
        relative = audio[len(container_out_prefix.rstrip("/") + "/") :]
        return host_out_dir / relative
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8018")
    parser.add_argument("--wait-health-s", default=240, type=int)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--qra-id", required=True)
    parser.add_argument("--memory-key", default=None)
    parser.add_argument("--question", required=True)
    parser.add_argument("--answer", required=True)
    parser.add_argument("--ref-audio", default=None)
    parser.add_argument("--max-chars", default=300, type=int)
    parser.add_argument("--label-prefix", default="blessed_qra")
    parser.add_argument("--container-out-prefix", default="/out")
    parser.add_argument("--host-out-dir", default=None, type=Path)
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    args.ledger.parent.mkdir(parents=True, exist_ok=True)
    health = wait_for_health(base_url, args.wait_health_s)
    plan_response = post_json(
        f"{base_url}/render-plan",
        {"answer_text": args.answer, "max_chars": args.max_chars, "pause_after_ms": 0},
    )
    plan = plan_response["plan"]

    audio_variants = []
    failed_gates = []
    for variant in DEFAULT_VARIANTS:
        rendered_chunks = []
        for chunk in plan["chunks"]:
            label = f"{args.label_prefix}_{args.qra_id}_{variant['id']}_{chunk['index']:02d}"
            payload = {
                "text": chunk["text"],
                "label": label,
                "delivery_stage": variant["delivery_stage"],
            }
            if args.ref_audio:
                payload["ref_audio"] = args.ref_audio
            result = post_json(f"{base_url}/synthesize", payload)
            audio_value = str(result.get("audio"))
            audio = host_path_for_audio(
                audio_value,
                container_out_prefix=args.container_out_prefix,
                host_out_dir=args.host_out_dir,
            )
            metrics = result.get("metrics") or {}
            if not result.get("ok"):
                failed_gates.append(f"{variant['id']}_chunk_{chunk['index']}_synthesis_ok")
            if not audio.exists():
                failed_gates.append(f"{variant['id']}_chunk_{chunk['index']}_audio_exists")
            rendered_chunks.append(
                {
                    "index": chunk["index"],
                    "text": chunk["text"],
                    "text_sha256": sha256_text(chunk["text"]),
                    "delivery_stage": variant["delivery_stage"],
                    "pause_after_ms": variant["pause_after_ms"],
                    "audio": audio_value,
                    "audio_sha256": sha256_file(audio) if audio.exists() else None,
                    "duration_seconds": metrics.get("duration_seconds"),
                    "metrics": metrics,
                }
            )
        audio_variants.append(
            {
                "id": variant["id"],
                "name": variant["name"],
                "default": variant.get("default", False),
                "blessed": not failed_gates,
                "emotion_arc": {
                    "delivery_stage": variant["delivery_stage"],
                    "humanization_role": variant["name"],
                },
                "pause_profile": {
                    "pause_after_ms": variant["pause_after_ms"],
                    "generation_delay_removed": True,
                },
                "chunks": rendered_chunks,
            }
        )

    entry = {
        "id": args.qra_id,
        "memory_key": args.memory_key or args.qra_id,
        "memory_keys": [args.memory_key or args.qra_id],
        "blessed": not failed_gates,
        "question_text": args.question,
        "question_normalized": " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in args.question).split()),
        "answer_text": args.answer,
        "answer_text_sha256": sha256_text(args.answer),
        "max_chars": min(args.max_chars, 300),
        "audio_variant_target_count": 5,
        "audio_variants": audio_variants,
        "evidence": {
            "source": "qra_review_approved",
            "trust_boundary": "only approved/blessed QRAs should use instant playback",
        },
    }
    ledger = load_ledger(args.ledger)
    entries = [item for item in ledger.get("entries", []) if item.get("id") != args.qra_id]
    entries.append(entry)
    ledger.update({"schema_version": "blessed_qra_response_cache.v1", "enabled": True, "entries": entries})
    args.ledger.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    receipt = {
        "ok": not failed_gates,
        "mocked": False,
        "live": True,
        "health": health,
        "ledger": str(args.ledger),
        "qra_id": args.qra_id,
        "variant_count": len(audio_variants),
        "chunk_count": len(plan["chunks"]),
        "failed_gates": failed_gates,
    }
    print(json.dumps(receipt, sort_keys=True))
    return 0 if receipt["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
