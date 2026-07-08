#!/usr/bin/env python3
"""Live proof that blocked memory answers do not reach Chatterbox audio."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run_cmd(cmd: list[str], *, timeout_s: int) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        result = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout_s)
        return {
            "cmd": cmd,
            "returncode": result.returncode,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
            "stdout_tail": result.stdout[-12000:],
            "stderr_tail": result.stderr[-4000:],
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "cmd": cmd,
            "returncode": 124,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
            "stdout_tail": (exc.stdout or "")[-12000:] if isinstance(exc.stdout, str) else "",
            "stderr_tail": (exc.stderr or "")[-4000:] if isinstance(exc.stderr, str) else "",
            "timed_out": True,
        }


def load_blocked_cases(answerability_receipt: Path, *, limit: int | None) -> list[dict[str, Any]]:
    receipt = json.loads(answerability_receipt.read_text(encoding="utf-8"))
    cases = [
        case
        for case in receipt.get("cases", [])
        if (case.get("answerability") or {}).get("decision") == "block_before_speech" and case.get("final_response")
    ]
    return cases[:limit] if limit is not None else cases


def run_block_case(
    case: dict[str, Any],
    *,
    out_dir: Path,
    base_url: str,
    timeout_s: int,
) -> dict[str, Any]:
    case_id = str(case["id"])
    case_dir = out_dir / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = case_dir / "tau-voice-render-block.json"
    answerability = dict(case.get("answerability") or {})
    cmd = [
        "python3",
        "scripts/smoke_tau_voice_render.py",
        "--base-url",
        base_url,
        "--out",
        str(receipt_path),
        "--question",
        str(case.get("question") or ""),
        "--answer-text",
        str(case.get("final_response") or ""),
        "--answerability-json",
        json.dumps(answerability, sort_keys=True),
        "--voice-delivery-json",
        json.dumps({"tone": "careful_concerned", "delivery_stage": "blocked_answer", "pause_after_ms": 0}),
        "--no-use-blessed-qra-cache",
        "--expect-answerability-block",
        "--timeout-s",
        str(timeout_s),
    ]
    child = run_cmd(cmd, timeout_s=timeout_s + 30)
    receipt: dict[str, Any] = {}
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        receipt = {"read_error": f"{type(exc).__name__}: {exc}"}
    failed: list[str] = []
    if child["returncode"] != 0:
        failed.append("tau_voice_render_block_command_ok")
    if receipt.get("ok") is not True:
        failed.append("tau_voice_render_block_receipt_ok")
    response = receipt.get("response") if isinstance(receipt.get("response"), dict) else {}
    if response.get("ok") is not False:
        failed.append("blocked_response_ok_false")
    response_gates = response.get("failed_gates") if isinstance(response.get("failed_gates"), list) else []
    tau_gates = (response.get("tau_voice_render_request") or {}).get("failed_gates") if isinstance(response.get("tau_voice_render_request"), dict) else []
    if not any("answerability_blocks_speech" in str(gate) for gate in [*response_gates, *tau_gates]):
        failed.append("answerability_blocks_speech_gate_present")
    if response.get("finished_response_audio"):
        failed.append("no_finished_response_audio")
    audio_metrics = ((receipt.get("artifacts") or {}).get("finished_response_audio_metrics") or {})
    if audio_metrics.get("exists") is True:
        failed.append("no_finished_response_audio_file")
    return {
        "id": case_id,
        "question": case.get("question"),
        "blocked_answer_text": case.get("final_response"),
        "answerability": answerability,
        "ok": not failed,
        "mocked": False,
        "live": bool(receipt.get("live")),
        "receipt": str(receipt_path),
        "child": child,
        "failed_gates": failed,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--answerability-receipt", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--base-url", default="http://127.0.0.1:8018")
    parser.add_argument("--timeout-s", default=120, type=int)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    started = time.perf_counter()
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    cases = load_blocked_cases(args.answerability_receipt, limit=args.limit)
    results = [run_block_case(case, out_dir=out_dir, base_url=args.base_url, timeout_s=args.timeout_s) for case in cases]
    failed_gates = [f"{result['id']}:{gate}" for result in results for gate in result["failed_gates"]]
    receipt = {
        "schema": "embry.answerability_runtime_block.v1",
        "ok": not failed_gates,
        "mocked": False,
        "live": all(result["live"] for result in results),
        "base_url": args.base_url,
        "answerability_receipt": str(args.answerability_receipt),
        "started_at_utc": datetime.fromtimestamp(time.time() - (time.perf_counter() - started), timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "ended_at_utc": utc_now(),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "case_count": len(results),
        "results": results,
        "failed_gates": failed_gates,
        "claims": {
            "proves": [
                "tau_voice_render_rejects_blocked_memory_answerability",
                "blocked_memory_answers_do_not_create_chatterbox_finished_audio",
            ]
            if not failed_gates
            else [],
            "does_not_prove": [
                "RealtimeSTT_audio_ingress",
                "memory_service_natively_blocks_answers",
                "Tau_agent_handoff_runtime_policy",
                "Chat_UX_sync",
                "orb_sync",
                "replay",
                "interruption",
            ],
        },
    }
    (out_dir / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": receipt["ok"], "live": receipt["live"], "mocked": receipt["mocked"], "receipt": str(out_dir / "receipt.json")}, indent=2))
    return 0 if receipt["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
