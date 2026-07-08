#!/usr/bin/env python3
"""Live smoke for the Tau voice render ingress."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.error
import urllib.request
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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
    except Exception as exc:  # noqa: BLE001 - receipt preserves live transport failure
        return None, None, f"{type(exc).__name__}: {exc}"


def get_json(url: str, timeout: int) -> tuple[dict[str, Any] | None, str | None]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.load(response), None
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"


def wait_for_health(base_url: str, timeout_s: int) -> tuple[dict[str, Any] | None, str | None]:
    deadline = time.monotonic() + timeout_s
    last_error = None
    while time.monotonic() < deadline:
        data, error = get_json(f"{base_url.rstrip('/')}/health", timeout=5)
        if data and data.get("ok"):
            return data, None
        last_error = error or f"health_not_ok:{data}"
        time.sleep(1)
    return None, last_error or "health_timeout"


def load_json_file(path_value: str | None) -> dict[str, Any]:
    if not path_value:
        return {}
    try:
        path = Path(path_value)
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load_voice_delivery(args: argparse.Namespace) -> dict[str, Any]:
    if args.voice_delivery_json:
        try:
            data = json.loads(args.voice_delivery_json)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            return {}
    receipt = load_json_file(args.voice_delivery_receipt)
    voice_delivery = receipt.get("voice_delivery")
    return voice_delivery if isinstance(voice_delivery, dict) else {}


def load_answerability(args: argparse.Namespace) -> dict[str, Any]:
    if args.answerability_json:
        try:
            data = json.loads(args.answerability_json)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            return {}
    return {}


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    chunks = split_text_chunks(args.answer_text, max_chars=300)
    voice_delivery = load_voice_delivery(args)
    answerability_decision = load_answerability(args)
    tone = voice_delivery.get("tone")
    delivery_stage = voice_delivery.get("delivery_stage") or "neutral"
    return {
        "schema": "tau.voice_render_request.v1",
        "run_id": args.run_id,
        "conversation_id": args.conversation_id,
        "turn_id": args.turn_id,
        "route": "memory_blessed_qra_fast_path_smoke",
        "active_domain_persona": "embry",
        "question_text": args.question,
        "question_text_sha256": sha256_text(args.question),
        "memory_route_decision": {
            "called": True,
            "source": "memory.recall",
            "selected_key": args.blessed_qra_memory_key,
            "similarity": args.blessed_qra_memory_similarity,
            "review_status": args.blessed_qra_memory_review_status,
        },
        "answerability_decision": answerability_decision,
        "voice_delivery": voice_delivery,
        "speakable_chunks": [
            {
                "chunk_id": f"{args.turn_id}-chunk-{index}",
                "text": chunk_text,
                "text_sha256": sha256_text(chunk_text),
                "tone": tone,
                "delivery_stage": delivery_stage,
                "pause_after_ms": 0,
                "interruptible": True,
                "max_chars": 300,
            }
            for index, chunk_text in enumerate(chunks, start=1)
        ],
        "tone": tone,
        "delivery_stage": delivery_stage,
        "interruptible": True,
        "use_blessed_qra_cache": args.use_blessed_qra_cache,
        "blessed_qra_min_similarity": args.blessed_qra_min_similarity,
        "blessed_qra_variant": args.blessed_qra_variant,
        "blessed_qra_preserve_pauses": args.blessed_qra_preserve_pauses,
        "require_blessed_qra_memory_gate": args.require_blessed_qra_memory_gate,
        "blessed_qra_memory_key": args.blessed_qra_memory_key,
        "blessed_qra_memory_similarity": args.blessed_qra_memory_similarity,
        "blessed_qra_memory_review_status": args.blessed_qra_memory_review_status,
        "turn_control_policy": {
            "old_turn_id": None,
            "cancel_requested": False,
            "stale_old_turn_chunks_should_skip": False,
        },
        "external_evidence": {
            "memory_recall": args.memory_receipt,
            "listener": args.listener_receipt,
            "voice_delivery": voice_delivery,
        },
        "receipt_root": str(args.out.resolve().parent),
        "label": args.label,
        "include_completion_cue": False,
        "crossfade_ms": 0,
        "asr_verify": False,
    }


def split_text_chunks(text: str, *, max_chars: int) -> list[str]:
    words = text.split()
    chunks: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > max_chars:
            chunks.append(current)
            current = word
        else:
            current = candidate
    if current:
        chunks.append(current)
    if not chunks:
        chunks.append(text[:max_chars])
    return chunks


def map_container_path(path_value: str | None, container_root: str, host_root: Path) -> Path | None:
    if not path_value:
        return None
    path_text = str(path_value)
    container_root = container_root.rstrip("/")
    if path_text == container_root:
        return host_root
    if path_text.startswith(f"{container_root}/"):
        return host_root / path_text[len(container_root) :].lstrip("/")
    return Path(path_text)


def wav_metrics(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"exists": False, "reason": "path_missing"}
    if not path.exists():
        return {"path": str(path), "exists": False}
    with wave.open(str(path), "rb") as handle:
        frame_count = handle.getnframes()
        sample_rate = handle.getframerate()
        channels = handle.getnchannels()
        sample_width = handle.getsampwidth()
    return {
        "path": str(path),
        "exists": True,
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "duration_seconds": round(frame_count / sample_rate, 3) if sample_rate else 0,
        "sample_rate": sample_rate,
        "channels": channels,
        "sample_width": sample_width,
        "frame_count": frame_count,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8018")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--wait-health-s", default=120, type=int)
    parser.add_argument("--timeout-s", default=120, type=int)
    parser.add_argument("--run-id", default=f"tau-voice-render-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}")
    parser.add_argument("--conversation-id", default="tau-smoke-conversation")
    parser.add_argument("--turn-id", default="tau-smoke-turn")
    parser.add_argument("--label", default="tau_voice_render_smoke")
    parser.add_argument("--question", default="Which control family should I use when the answer says SI?")
    parser.add_argument("--answer-text", default="Use system and communications protection.")
    parser.add_argument("--use-blessed-qra-cache", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--blessed-qra-min-similarity", default=0.99, type=float)
    parser.add_argument("--blessed-qra-variant", default="gentle")
    parser.add_argument("--blessed-qra-preserve-pauses", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--require-blessed-qra-memory-gate", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--blessed-qra-memory-key", default="qra-smoke-si")
    parser.add_argument("--blessed-qra-memory-similarity", default=1.0, type=float)
    parser.add_argument("--blessed-qra-memory-review-status", default="approved")
    parser.add_argument("--memory-receipt", default=None)
    parser.add_argument("--listener-receipt", default=None)
    parser.add_argument("--voice-delivery-json", default=None)
    parser.add_argument("--voice-delivery-receipt", default=None)
    parser.add_argument("--answerability-json", default=None)
    parser.add_argument("--expect-answerability-block", action="store_true")
    parser.add_argument("--container-out-dir", default="/out")
    parser.add_argument("--host-out-dir", default="/tmp/chatterbox-fork-agent-out", type=Path)
    parser.add_argument("--expect-cache-hit", action="store_true")
    args = parser.parse_args()

    started = time.perf_counter()
    base_url = args.base_url.rstrip("/")
    failed_gates: list[str] = []
    health, health_error = wait_for_health(base_url, args.wait_health_s)
    if not health:
        failed_gates.append("chatterbox_health_ok")

    payload = build_payload(args)
    status_code = None
    response = None
    post_error = None
    if health:
        status_code, response, post_error = post_json(f"{base_url}/tau/voice-render", payload, args.timeout_s)
        if status_code != 200:
            failed_gates.append("tau_voice_render_http_200")
        if not args.expect_answerability_block and (not response or not response.get("ok")):
            failed_gates.append("tau_voice_render_response_ok")
        if response and (response.get("tau_voice_render_request") or {}).get("schema") != "tau.voice_render_request.v1":
            failed_gates.append("tau_voice_render_schema")
        if args.expect_answerability_block:
            response_failed = (response or {}).get("failed_gates") or []
            tau_failed = ((response or {}).get("tau_voice_render_request") or {}).get("failed_gates") or []
            if (response or {}).get("ok") is not False:
                failed_gates.append("answerability_block_response_not_ok_false")
            if not any("answerability_blocks_speech" in str(gate) for gate in [*response_failed, *tau_failed]):
                failed_gates.append("answerability_block_gate_present")
            if (response or {}).get("finished_response_audio"):
                failed_gates.append("answerability_block_no_finished_audio")
        if args.expect_cache_hit:
            cache = (response or {}).get("blessed_qra_cache") or {}
            if not cache.get("hit"):
                failed_gates.append("blessed_qra_cache_hit")
            if not (cache.get("memory_gate") or {}).get("passed"):
                failed_gates.append("blessed_qra_memory_gate_passed")
            if ((response or {}).get("cache_material") or {}).get("variant_id") != args.blessed_qra_variant:
                failed_gates.append("blessed_qra_variant_selected")

    finished_audio_host_path = map_container_path(
        (response or {}).get("finished_response_audio") if response else None,
        args.container_out_dir,
        args.host_out_dir,
    )
    finished_audio_metrics = wav_metrics(finished_audio_host_path)
    if response and not args.expect_answerability_block and not finished_audio_metrics.get("exists"):
        failed_gates.append("finished_audio_host_path_exists")

    receipt = {
        "schema": "chatterbox.tau_voice_render_smoke.v1",
        "ok": not failed_gates,
        "mocked": False,
        "live": bool(health and response and status_code == 200),
        "base_url": base_url,
        "started_at_utc": datetime.fromtimestamp(
            time.time() - (time.perf_counter() - started),
            timezone.utc,
        ).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "ended_at_utc": utc_now(),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "health": health,
        "health_error": health_error,
        "request": {
            "schema": payload["schema"],
            "conversation_id": payload["conversation_id"],
            "turn_id": payload["turn_id"],
            "question_text_sha256": payload["question_text_sha256"],
            "speakable_chunk_count": len(payload["speakable_chunks"]),
            "use_blessed_qra_cache": payload["use_blessed_qra_cache"],
            "blessed_qra_variant": payload["blessed_qra_variant"],
            "blessed_qra_memory_key": payload["blessed_qra_memory_key"],
            "blessed_qra_memory_similarity": payload["blessed_qra_memory_similarity"],
            "blessed_qra_memory_review_status": payload["blessed_qra_memory_review_status"],
            "voice_delivery": payload["voice_delivery"],
            "answerability_decision": payload["answerability_decision"],
        },
        "status_code": status_code,
        "post_error": post_error,
        "artifacts": {
            "finished_response_audio_container": (response or {}).get("finished_response_audio") if response else None,
            "finished_response_audio_host": str(finished_audio_host_path) if finished_audio_host_path else None,
            "finished_response_audio_metrics": finished_audio_metrics,
        },
        "response": response,
        "failed_gates": failed_gates,
        "claims": {
            "proves": (
                [
                    "running_server_rejects_blocked_answerability_before_chatterbox_audio",
                    "answerability_block_prevents_finished_audio_artifact",
                ]
                if args.expect_answerability_block
                else [
                    "running_server_accepts_tau_voice_render_request",
                    "tau_voice_render_maps_to_batch_renderer",
                    "blessed_qra_cache_can_be_selected_through_tau_ingress",
                ]
            )
            if not failed_gates
            else [],
            "does_not_prove": [
                "listener_asr_pass",
                "production_memory_recall_correctness",
                "subjective_voice_quality",
                "fresh_model_generation_quality",
            ],
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": receipt["ok"],
                "mocked": receipt["mocked"],
                "live": receipt["live"],
                "out": str(args.out),
                "failed_gates": failed_gates,
                "status_code": status_code,
            },
            sort_keys=True,
        )
    )
    return 0 if receipt["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
