#!/usr/bin/env python3
"""Live listener -> memory/QRA -> Tau render -> Chatterbox cache smoke."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_SEED_QUERY = "When should SI-7(8) be used in satellite operations?"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run_cmd(cmd: list[str], *, timeout: int, env: dict[str, str] | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    result = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout, env=env)
    return {
        "cmd": cmd,
        "returncode": result.returncode,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "stdout_tail": result.stdout[-4000:],
        "stderr_tail": result.stderr[-4000:],
    }


def post_json(url: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def memory_recall(memory_url: str, query: str, *, k: int, timeout_s: int) -> dict[str, Any]:
    return post_json(
        f"{memory_url.rstrip('/')}/recall",
        {
            "q": query,
            "collections": ["sparta_qra"],
            "k": k,
        },
        timeout_s,
    )


def qra_text(item: dict[str, Any], *names: str) -> str:
    for name in names:
        value = item.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8018")
    parser.add_argument("--memory-url", default="http://127.0.0.1:8601")
    parser.add_argument("--asr-openai-base-url", default="http://127.0.0.1:9000")
    parser.add_argument("--api-key-env", default="WHISPER_API_KEY")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--seed-query", default=DEFAULT_SEED_QUERY)
    parser.add_argument("--memory-k", default=5, type=int)
    parser.add_argument("--memory-timeout-s", default=20, type=int)
    parser.add_argument("--max-input-wer", default=0.25, type=float)
    parser.add_argument("--host-out-dir", default="/tmp/chatterbox-fork-agent-out", type=Path)
    parser.add_argument("--ledger", default="/tmp/chatterbox-fork-agent-out/_blessed_qra_ledger.json", type=Path)
    parser.add_argument("--variant", default="gentle")
    parser.add_argument("--timeout-s", default=420, type=int)
    args = parser.parse_args()

    started = time.perf_counter()
    py = sys.executable
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    failed_gates: list[str] = []
    children: dict[str, Any] = {}

    api_key = os.getenv(args.api_key_env)
    if not api_key:
        failed_gates.append("asr_api_key_env_present")

    seed_recall = None
    try:
        seed_recall = memory_recall(args.memory_url, args.seed_query, k=args.memory_k, timeout_s=args.memory_timeout_s)
        write_json(out_dir / "seed-memory-recall.json", seed_recall)
        if not seed_recall.get("found"):
            failed_gates.append("seed_memory_found")
        if seed_recall.get("should_scan"):
            failed_gates.append("seed_memory_should_scan_false")
    except Exception as exc:  # noqa: BLE001
        seed_recall = {"error_type": type(exc).__name__, "error": str(exc)}
        write_json(out_dir / "seed-memory-recall.json", seed_recall)
        failed_gates.append("seed_memory_recall_ok")

    seed_item = ((seed_recall or {}).get("items") or [{}])[0]
    seed_key = str(seed_item.get("_key") or "")
    seed_question = qra_text(seed_item, "problem", "question") or args.seed_query
    if not seed_key:
        failed_gates.append("seed_memory_key_present")
    if not seed_question:
        failed_gates.append("seed_memory_question_present")

    question_wav = out_dir / "listener-qra-question.wav"
    espeak_cmd = ["espeak-ng", "-w", str(question_wav), "-s", "140", "-v", "en-us", seed_question]
    espeak = run_cmd(espeak_cmd, timeout=60)
    children["espeak_question"] = espeak
    if espeak["returncode"] != 0 or not question_wav.exists():
        failed_gates.append("question_wav_generated")

    rung7_path = out_dir / "rung7" / "rung7.json"
    rung7_env = os.environ.copy()
    rung7_cmd = [
        py,
        "scripts/smoke_conversation_ladder.py",
        "--rung",
        "7",
        "--fixture",
        str(question_wav),
        "--expected-transcript",
        seed_question,
        "--response-text",
        "I hear you. Let me route that.",
        "--run-id",
        f"combined-rung7-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        "--session-id",
        "combined-listener-memory-tau",
        "--turn-id",
        "combined-turn-1",
        "--out",
        str(rung7_path),
        "--asr-openai-base-url",
        args.asr_openai_base_url,
        "--api-key-env",
        args.api_key_env,
        "--max-input-wer",
        str(args.max_input_wer),
    ]
    rung7 = run_cmd(rung7_cmd, timeout=args.timeout_s, env=rung7_env)
    children["rung7"] = {**rung7, "cmd": [part if part != api_key else "<redacted>" for part in rung7_cmd]}
    if rung7["returncode"] != 0:
        failed_gates.append("rung7_command_ok")
    try:
        rung7_receipt = json.loads(rung7_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        rung7_receipt = {"error_type": type(exc).__name__, "error": str(exc)}
        failed_gates.append("rung7_receipt_read")
    if not rung7_receipt.get("ok"):
        failed_gates.append("rung7_receipt_ok")
    heard_text = ((rung7_receipt.get("heard_text_ledger") or [{}])[0]).get("final_text") or ""
    if not heard_text:
        failed_gates.append("heard_text_present")

    runtime_recall = None
    try:
        runtime_recall = memory_recall(args.memory_url, heard_text, k=args.memory_k, timeout_s=args.memory_timeout_s)
        write_json(out_dir / "runtime-memory-recall.json", runtime_recall)
        if not runtime_recall.get("found"):
            failed_gates.append("runtime_memory_found")
        if runtime_recall.get("should_scan"):
            failed_gates.append("runtime_memory_should_scan_false")
    except Exception as exc:  # noqa: BLE001
        runtime_recall = {"error_type": type(exc).__name__, "error": str(exc)}
        write_json(out_dir / "runtime-memory-recall.json", runtime_recall)
        failed_gates.append("runtime_memory_recall_ok")

    memory_item = ((runtime_recall or {}).get("items") or [{}])[0]
    memory_key = str(memory_item.get("_key") or "")
    memory_question = qra_text(memory_item, "problem", "question")
    memory_answer = qra_text(memory_item, "answer", "solution")
    if not memory_key:
        failed_gates.append("runtime_memory_key_present")
    if not memory_answer:
        failed_gates.append("runtime_memory_answer_present")

    qra_id = memory_key or f"combined-qra-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    qra_event = {
        "schema": "tau.qra_creation_event.v1",
        "event_id": f"combined-qra-event-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        "qra": {
            "qra_id": qra_id,
            "memory_key": memory_key or qra_id,
            "question": heard_text or memory_question or seed_question,
            "answer": memory_answer or "No answer available.",
            "review_status": "approved",
            "audio": {
                "auto_generate": True,
                "variant_count": 5,
                "variant_policy": "embry_five_arcs",
            },
        },
    }
    qra_event_path = out_dir / "qra-creation-event.json"
    write_json(qra_event_path, qra_event)

    hook_receipt_path = out_dir / "qra-creation-audio-hook.json"
    hook_cmd = [
        py,
        "scripts/qra_creation_audio_hook.py",
        "--event",
        str(qra_event_path),
        "--receipt",
        str(hook_receipt_path),
        "--base-url",
        args.base_url,
        "--ledger",
        str(args.ledger),
        "--label-prefix",
        "combined_listener_memory_tau",
        "--host-out-dir",
        str(args.host_out_dir),
    ]
    hook = run_cmd(hook_cmd, timeout=args.timeout_s)
    children["qra_creation_audio_hook"] = hook
    hook_receipt = {}
    try:
        hook_receipt = json.loads(hook_receipt_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        hook_receipt = {"error_type": type(exc).__name__, "error": str(exc)}
    if hook["returncode"] != 0 or not hook_receipt.get("ok"):
        failed_gates.append("qra_creation_audio_hook_ok")

    bless_receipt = hook_receipt.get("child_receipt") or {}
    write_json(out_dir / "bless-qra-audio-variants.json", bless_receipt)
    if int(bless_receipt.get("variant_count") or 0) < 5:
        failed_gates.append("qra_creation_audio_variant_count_5")

    tau_path = out_dir / "tau-voice-render.json"
    tau_cmd = [
        py,
        "scripts/smoke_tau_voice_render.py",
        "--base-url",
        args.base_url,
        "--out",
        str(tau_path),
        "--question",
        heard_text or memory_question or seed_question,
        "--answer-text",
        memory_answer or "No answer available.",
        "--blessed-qra-memory-key",
        memory_key or qra_id,
        "--blessed-qra-memory-similarity",
        "1.0",
        "--blessed-qra-memory-review-status",
        "approved",
        "--blessed-qra-variant",
        args.variant,
        "--memory-receipt",
        str(out_dir / "runtime-memory-recall.json"),
        "--listener-receipt",
        str(rung7_path),
        "--expect-cache-hit",
    ]
    tau = run_cmd(tau_cmd, timeout=args.timeout_s)
    children["tau_voice_render"] = tau
    if tau["returncode"] != 0:
        failed_gates.append("tau_voice_render_command_ok")
    try:
        tau_receipt = json.loads(tau_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        tau_receipt = {"error_type": type(exc).__name__, "error": str(exc)}
        failed_gates.append("tau_voice_render_receipt_read")
    if not tau_receipt.get("ok"):
        failed_gates.append("tau_voice_render_receipt_ok")

    receipt = {
        "schema": "chatterbox.listener_memory_tau_qra_smoke.v1",
        "ok": not failed_gates,
        "mocked": False,
        "live": not failed_gates,
        "started_at_utc": datetime.fromtimestamp(
            time.time() - (time.perf_counter() - started),
            timezone.utc,
        ).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "ended_at_utc": utc_now(),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "seed_query": args.seed_query,
        "heard_text": heard_text,
        "memory_gate": {
            "key": memory_key,
            "question": memory_question,
            "answer_sha256": __import__("hashlib").sha256((memory_answer or "").encode("utf-8")).hexdigest(),
            "recall_found": (runtime_recall or {}).get("found"),
            "recall_confidence": (runtime_recall or {}).get("confidence"),
            "review_status_for_smoke": "approved",
            "similarity_for_blessed_qra_gate": 1.0,
        },
        "artifacts": {
            "question_wav": str(question_wav),
            "seed_memory_recall": str(out_dir / "seed-memory-recall.json"),
            "rung7_receipt": str(rung7_path),
            "runtime_memory_recall": str(out_dir / "runtime-memory-recall.json"),
            "qra_creation_event": str(qra_event_path),
            "qra_creation_audio_hook_receipt": str(hook_receipt_path),
            "bless_qra_receipt": str(out_dir / "bless-qra-audio-variants.json"),
            "tau_voice_render_receipt": str(tau_path),
        },
        "children": children,
        "rung7": {
            "ok": rung7_receipt.get("ok"),
            "live": rung7_receipt.get("live"),
            "failed_gates": rung7_receipt.get("failed_gates"),
            "transcript": ((rung7_receipt.get("heard_text_ledger") or [{}])[0]).get("final_text"),
            "wer": ((rung7_receipt.get("input_asr") or {}).get("gate") or {}).get("wer"),
        },
        "qra_creation_audio_hook": {
            "ok": hook_receipt.get("ok"),
            "live": hook_receipt.get("live"),
            "failed_gates": hook_receipt.get("failed_gates"),
            "review_status": hook_receipt.get("review_status"),
            "auto_generate_audio": hook_receipt.get("auto_generate_audio"),
            "variant_target_count": hook_receipt.get("variant_target_count"),
        },
        "bless_qra": bless_receipt,
        "tau_voice_render": {
            "ok": tau_receipt.get("ok"),
            "live": tau_receipt.get("live"),
            "failed_gates": tau_receipt.get("failed_gates"),
            "cache_hit": (((tau_receipt.get("response") or {}).get("blessed_qra_cache") or {}).get("hit")),
            "memory_gate_passed": ((((tau_receipt.get("response") or {}).get("blessed_qra_cache") or {}).get("memory_gate") or {}).get("passed")),
            "variant_id": ((tau_receipt.get("response") or {}).get("cache_material") or {}).get("variant_id"),
            "finished_audio_metrics": (tau_receipt.get("artifacts") or {}).get("finished_response_audio_metrics"),
        },
        "failed_gates": failed_gates,
        "claims": {
            "proves": [
                "listener_heard_text_can_drive_live_memory_qra_recall",
                "approved_qra_creation_event_can_generate_five_embry_audio_variants",
                "tau_voice_render_can_play_blessed_qra_audio_for_the_same_memory_key",
            ]
            if not failed_gates
            else [],
            "does_not_prove": [
                "production_memory_gpt_review_policy",
                "subjective_voice_quality",
                "live_microphone_or_webrtc_transport",
                "globally_correct_qra_ranking",
            ],
        },
    }
    write_json(out_dir / "listener-memory-tau-qra.json", receipt)
    print(
        json.dumps(
            {
                "ok": receipt["ok"],
                "mocked": receipt["mocked"],
                "live": receipt["live"],
                "out": str(out_dir / "listener-memory-tau-qra.json"),
                "failed_gates": failed_gates,
            },
            sort_keys=True,
        )
    )
    return 0 if receipt["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
