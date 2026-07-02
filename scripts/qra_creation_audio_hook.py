#!/usr/bin/env python3
"""Generate blessed Embry audio variants from a QRA creation/review event."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


APPROVED_STATUSES = {"approved", "blessed", "verified"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def pick_text(payload: dict[str, Any], *names: str) -> str:
    for name in names:
        value = payload.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def qra_fields_from_event(event: dict[str, Any]) -> dict[str, Any]:
    qra = event.get("qra") if isinstance(event.get("qra"), dict) else event
    review = qra.get("review") if isinstance(qra.get("review"), dict) else {}
    audio = qra.get("audio") if isinstance(qra.get("audio"), dict) else {}
    return {
        "event_id": pick_text(event, "event_id", "id"),
        "qra_id": pick_text(qra, "qra_id", "id", "_key"),
        "memory_key": pick_text(qra, "memory_key", "_key", "qra_id", "id"),
        "review_status": pick_text(qra, "review_status") or pick_text(review, "status"),
        "question": pick_text(qra, "question", "problem", "prompt"),
        "answer": pick_text(qra, "answer", "solution", "response"),
        "auto_generate_audio": bool(audio.get("auto_generate", qra.get("auto_generate_audio", True))),
        "variant_count": int(audio.get("variant_count", qra.get("audio_variant_target_count", 5)) or 5),
    }


def build_bless_command(args: argparse.Namespace, fields: dict[str, Any]) -> list[str]:
    return [
        sys.executable,
        "scripts/bless_qra_audio_variants.py",
        "--base-url",
        args.base_url,
        "--ledger",
        str(args.ledger),
        "--qra-id",
        fields["qra_id"],
        "--memory-key",
        fields["memory_key"] or fields["qra_id"],
        "--question",
        fields["question"],
        "--answer",
        fields["answer"],
        "--label-prefix",
        args.label_prefix,
        "--host-out-dir",
        str(args.host_out_dir),
    ]


def run_command(cmd: list[str], timeout_s: int) -> dict[str, Any]:
    started = time.perf_counter()
    result = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout_s)
    return {
        "cmd": cmd,
        "returncode": result.returncode,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "stdout_tail": result.stdout[-4000:],
        "stderr_tail": result.stderr[-4000:],
    }


def parse_child_receipt(stdout_tail: str) -> dict[str, Any]:
    json_start = stdout_tail.find("{")
    if json_start < 0:
        return {"ok": False, "failed_gates": ["child_receipt_json_present"]}
    try:
        return json.loads(stdout_tail[json_start:])
    except json.JSONDecodeError as exc:
        return {"ok": False, "failed_gates": ["child_receipt_json_valid"], "error": str(exc)}


def build_receipt(
    *,
    event_path: Path,
    fields: dict[str, Any],
    failed_gates: list[str],
    child: dict[str, Any] | None,
    child_receipt: dict[str, Any] | None,
    skipped_reason: str | None,
    dry_run: bool,
) -> dict[str, Any]:
    return {
        "schema": "chatterbox.qra_creation_audio_hook.v1",
        "created_at": utc_now(),
        "ok": not failed_gates,
        "mocked": bool(dry_run),
        "live": bool(not dry_run and child and child.get("returncode") == 0 and child_receipt and child_receipt.get("ok") and not failed_gates),
        "event_path": str(event_path),
        "qra_id": fields.get("qra_id"),
        "memory_key": fields.get("memory_key"),
        "review_status": fields.get("review_status"),
        "auto_generate_audio": fields.get("auto_generate_audio"),
        "variant_target_count": fields.get("variant_count"),
        "skipped_reason": skipped_reason,
        "child": child,
        "child_receipt": child_receipt,
        "failed_gates": failed_gates,
        "claims": {
            "proves": [
                "approved_qra_creation_event_can_invoke_embry_audio_variant_generation",
                "unapproved_or_disabled_qra_events_fail_closed_before_audio_generation",
            ],
            "does_not_prove": [
                "memory_pipeline_qra_ranking_is_globally_correct",
                "review_policy_is_sufficient_for_all_domains",
                "selected_emotional_variant_is_subjectively_best",
            ],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--base-url", default="http://127.0.0.1:8018")
    parser.add_argument("--ledger", default="/tmp/chatterbox-fork-agent-out/_blessed_qra_ledger.json", type=Path)
    parser.add_argument("--host-out-dir", default="/tmp/chatterbox-fork-agent-out", type=Path)
    parser.add_argument("--label-prefix", default="qra_creation")
    parser.add_argument("--timeout-s", default=420, type=int)
    parser.add_argument("--disable-auto-generation", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    failed_gates: list[str] = []
    event = json.loads(args.event.read_text(encoding="utf-8"))
    fields = qra_fields_from_event(event)
    skipped_reason = None
    child = None
    child_receipt = None

    if not fields["qra_id"]:
        failed_gates.append("qra_id_present")
    if not fields["memory_key"]:
        failed_gates.append("memory_key_present")
    if not fields["question"]:
        failed_gates.append("question_present")
    if not fields["answer"]:
        failed_gates.append("answer_present")
    if fields["variant_count"] != 5:
        failed_gates.append("variant_target_count_5")
    if fields["review_status"].lower() not in APPROVED_STATUSES:
        failed_gates.append("review_status_approved")
        skipped_reason = "review_status_not_approved"
    if args.disable_auto_generation or not fields["auto_generate_audio"]:
        failed_gates.append("auto_generation_enabled")
        skipped_reason = "auto_generation_disabled"

    if not failed_gates:
        cmd = build_bless_command(args, fields)
        if args.dry_run:
            child = {"cmd": cmd, "returncode": 0, "dry_run": True}
            child_receipt = {"ok": True, "variant_count": fields["variant_count"], "dry_run": True}
        else:
            child = run_command(cmd, timeout_s=args.timeout_s)
            child_receipt = parse_child_receipt(str(child.get("stdout_tail") or ""))
            if child.get("returncode") != 0:
                failed_gates.append("bless_qra_audio_variants_command_ok")
            if not child_receipt.get("ok"):
                failed_gates.append("bless_qra_audio_variants_receipt_ok")
            if int(child_receipt.get("variant_count") or 0) != 5:
                failed_gates.append("bless_qra_audio_variants_variant_count_5")

    receipt = build_receipt(
        event_path=args.event,
        fields=fields,
        failed_gates=failed_gates,
        child=child,
        child_receipt=child_receipt,
        skipped_reason=skipped_reason,
        dry_run=args.dry_run,
    )
    write_json(args.receipt, receipt)
    print(json.dumps(receipt, sort_keys=True))
    return 0 if receipt["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
