#!/usr/bin/env python3
"""Run the Chatterbox fork live sanity bundle.

This wrapper chains the live checks that matter for the current voice-agent
iteration:

1. ASR-gated batch render with accepted-audio cache fill.
2. ASR-gated batch render with accepted-audio cache hit.
3. PCM chunk-streaming endpoint smoke.
4. Interruption smoke with stale old chunks skipped.
5. Turn control endpoint smoke for cancel, duck, and stop state.
6. Optional listener rung 7 boundary smoke when requested.
7. Optional Tau voice render ingress smoke when requested.
8. Optional listener -> memory/QRA -> Tau render smoke when requested.

The receipt is a bundle index. Child receipts remain the source of detailed
evidence.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


DEFAULT_TEXT = (
    "Hmm. I found the spoken rule now. Say System and Information Integrity first, "
    "then use the short identifier only after the long form is clear. For Embry, "
    "that keeps the answer understandable while preserving traceability."
)


def run_cmd(cmd: list[str], *, timeout: int) -> dict[str, Any]:
    started = time.perf_counter()
    env = os.environ.copy()
    src_path = str(Path.cwd() / "src")
    env["PYTHONPATH"] = f"{src_path}{os.pathsep}{env['PYTHONPATH']}" if env.get("PYTHONPATH") else src_path
    result = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout, env=env)
    return {
        "cmd": cmd,
        "returncode": result.returncode,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "stdout_tail": result.stdout[-4000:],
        "stderr_tail": result.stderr[-4000:],
    }


def reset_cache_dir(cache_dir: Path, container_name: str) -> dict[str, Any]:
    if not cache_dir.exists():
        return {"requested": True, "performed": False, "method": "not_present", "ok": True}
    try:
        shutil.rmtree(cache_dir)
        return {"requested": True, "performed": True, "method": "host_rmtree", "ok": True}
    except PermissionError as exc:
        docker_result = run_cmd(
            [
                "docker",
                "exec",
                container_name,
                "rm",
                "-rf",
                "/out/_accepted_audio_cache",
            ],
            timeout=30,
        )
        return {
            "requested": True,
            "performed": docker_result["returncode"] == 0,
            "method": "docker_exec_rm_rf",
            "ok": docker_result["returncode"] == 0,
            "host_error": f"{type(exc).__name__}: {exc}",
            "docker_result": docker_result,
        }


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def summarize_child(name: str, receipt_path: Path, command: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "name": name,
        "receipt_path": str(receipt_path),
        "command": command,
        "receipt_present": receipt_path.exists(),
        "ok": False,
        "failed_gates": ["receipt_missing"],
    }
    if not receipt_path.exists():
        return summary

    receipt = load_json(receipt_path)
    failed = list(receipt.get("failed_gates") or [])
    summary.update(
        {
            "ok": bool(receipt.get("ok")) and command["returncode"] == 0 and not failed,
            "mocked": receipt.get("mocked"),
            "live": receipt.get("live"),
            "failed_gates": failed,
        }
    )

    if name.startswith("asr_cache"):
        batch = receipt.get("batch") or {}
        chunks = batch.get("chunks") or []
        summary.update(
            {
                "client_elapsed_ms": receipt.get("client_elapsed_ms"),
                "server_elapsed_ms": batch.get("elapsed_ms"),
                "chunk_count": len(chunks),
                "cache_hits": sum(1 for chunk in chunks if (chunk.get("cache") or {}).get("hit")),
                "finished_audio": batch.get("finished_response_audio"),
            }
        )
    elif name == "stream_endpoint":
        summary.update(
            {
                "proof_scope": receipt.get("proof_scope"),
                "does_not_prove": receipt.get("does_not_prove"),
                "first_byte_ms": receipt.get("first_byte_ms"),
                "elapsed_ms": receipt.get("elapsed_ms"),
                "stream_bytes": receipt.get("stream_bytes"),
                "wav_path": receipt.get("wav_path"),
            }
        )
    elif name == "stream_cancel":
        summary.update(
            {
                "proof_scope": receipt.get("proof_scope"),
                "does_not_prove": receipt.get("does_not_prove"),
                "turn_id": receipt.get("turn_id"),
                "baseline_bytes": (receipt.get("baseline_stream") or {}).get("bytes"),
                "old_turn_bytes_after_cancel": receipt.get("old_turn_bytes_after_cancel"),
            }
        )
    elif name == "interruption":
        summary.update(
            {
                "event_count": receipt.get("event_count"),
                "stale_skipped_count": receipt.get("stale_skipped_count"),
                "acknowledgement": receipt.get("acknowledgement"),
                "spoken_result_count": len(receipt.get("spoken_results") or []),
                "events_path": receipt.get("events_path"),
            }
        )
    elif name == "turn_controls":
        summary.update(
            {
                "proof_scope": receipt.get("proof_scope"),
                "does_not_prove": receipt.get("does_not_prove"),
                "turn_id": receipt.get("turn_id"),
                "action_order": receipt.get("action_order"),
                "final_control": {
                    key: (receipt.get("final_control") or {}).get(key)
                    for key in ["cancelled", "stale_chunks_should_skip", "ducked", "stopped"]
                },
            }
        )
    elif name == "listener_rung7":
        artifacts = receipt.get("artifacts") or {}
        summary.update(
            {
                "schema": receipt.get("schema"),
                "listener_frame_count": (artifacts.get("listener_frames") or {}).get("frame_count"),
                "heard_text_ledger_path": artifacts.get("heard_text_ledger_path"),
                "listener_turn_events_path": artifacts.get("listener_turn_events_path"),
                "tau_voice_render_request_schema": (receipt.get("tau_voice_render_request") or {}).get("schema"),
                "does_not_prove": (receipt.get("claims") or {}).get("does_not_prove"),
            }
        )
    elif name == "tau_voice_render":
        artifacts = receipt.get("artifacts") or {}
        response = receipt.get("response") or {}
        summary.update(
            {
                "schema": receipt.get("schema"),
                "status_code": receipt.get("status_code"),
                "cache_hit": (response.get("blessed_qra_cache") or {}).get("hit"),
                "memory_gate_passed": ((response.get("blessed_qra_cache") or {}).get("memory_gate") or {}).get("passed"),
                "variant_id": (response.get("cache_material") or {}).get("variant_id"),
                "tau_voice_render_request_schema": (response.get("tau_voice_render_request") or {}).get("schema"),
                "finished_response_audio_host": artifacts.get("finished_response_audio_host"),
                "finished_response_audio_bytes": (artifacts.get("finished_response_audio_metrics") or {}).get("bytes"),
                "does_not_prove": (receipt.get("claims") or {}).get("does_not_prove"),
            }
        )
    elif name == "listener_memory_tau_qra":
        summary.update(
            {
                "schema": receipt.get("schema"),
                "heard_text": receipt.get("heard_text"),
                "memory_key": (receipt.get("memory_gate") or {}).get("key"),
                "memory_recall_confidence": (receipt.get("memory_gate") or {}).get("recall_confidence"),
                "rung7_wer": (receipt.get("rung7") or {}).get("wer"),
                "variant_count": (receipt.get("bless_qra") or {}).get("variant_count"),
                "cache_hit": (receipt.get("tau_voice_render") or {}).get("cache_hit"),
                "memory_gate_passed": (receipt.get("tau_voice_render") or {}).get("memory_gate_passed"),
                "variant_id": (receipt.get("tau_voice_render") or {}).get("variant_id"),
                "finished_response_audio_bytes": ((receipt.get("tau_voice_render") or {}).get("finished_audio_metrics") or {}).get("bytes"),
                "does_not_prove": (receipt.get("claims") or {}).get("does_not_prove"),
            }
        )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8018")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--wait-health-s", default=240, type=int)
    parser.add_argument("--answer-text", default=DEFAULT_TEXT)
    parser.add_argument("--reset-cache", action="store_true")
    parser.add_argument(
        "--cache-dir",
        default="/tmp/chatterbox-fork-agent-out/_accepted_audio_cache",
        type=Path,
    )
    parser.add_argument("--cache-container", default="chatterbox-fork-agent-server")
    parser.add_argument("--skip-interruption", action="store_true")
    parser.add_argument("--include-listener-rung7", action="store_true")
    parser.add_argument("--listener-fixture", type=Path, default=Path("tests/fixtures/conversation_ladder/rung1_simple.wav"))
    parser.add_argument("--listener-expected-transcript", default="Hello, I am testing the listener.")
    parser.add_argument("--include-tau-voice-render", action="store_true")
    parser.add_argument("--include-listener-memory-tau-qra", action="store_true")
    args = parser.parse_args()

    started = time.perf_counter()
    base_url = args.base_url.rstrip("/")
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    cache_reset = {"requested": args.reset_cache, "performed": False, "method": "not_requested", "ok": True}
    if args.reset_cache and args.cache_dir.exists():
        cache_reset = reset_cache_dir(args.cache_dir, args.cache_container)

    py = sys.executable
    commands: list[tuple[str, Path, list[str], int]] = [
        (
            "asr_cache_fill",
            out_dir / "asr-cache-fill.json",
            [
                py,
                "scripts/smoke_asr_gated_batch.py",
                "--base-url",
                base_url,
                "--wait-health-s",
                str(args.wait_health_s),
                "--out",
                str(out_dir / "asr-cache-fill.json"),
                "--label",
                "full_live_sanity_cache_fill",
                "--answer-text",
                args.answer_text,
            ],
            420,
        ),
        (
            "asr_cache_hit",
            out_dir / "asr-cache-hit.json",
            [
                py,
                "scripts/smoke_asr_gated_batch.py",
                "--base-url",
                base_url,
                "--wait-health-s",
                str(args.wait_health_s),
                "--out",
                str(out_dir / "asr-cache-hit.json"),
                "--label",
                "full_live_sanity_cache_hit",
                "--answer-text",
                args.answer_text,
                "--expect-cache-hit",
            ],
            420,
        ),
        (
            "stream_endpoint",
            out_dir / "stream-endpoint.json",
            [
                py,
                "scripts/smoke_stream_endpoint.py",
                "--base-url",
                base_url,
                "--wait-health-s",
                str(args.wait_health_s),
                "--out",
                str(out_dir / "stream-endpoint.json"),
                "--label",
                "full_live_sanity_stream",
            ],
            420,
        ),
        (
            "stream_cancel",
            out_dir / "stream-cancel.json",
            [
                py,
                "scripts/smoke_stream_turn_cancel.py",
                "--base-url",
                base_url,
                "--wait-health-s",
                str(args.wait_health_s),
                "--out",
                str(out_dir / "stream-cancel.json"),
                "--label",
                "full_live_sanity_stream_cancel",
            ],
            420,
        ),
    ]
    if not args.skip_interruption:
        commands.append(
            (
                "interruption",
                out_dir / "interruption" / "final-response.json",
                [
                    py,
                    "scripts/smoke_interruptible_conversation.py",
                    "--base-url",
                    base_url,
                    "--wait-health-s",
                    str(args.wait_health_s),
                    "--out-dir",
                    str(out_dir / "interruption"),
                ],
                420,
            )
        )
    commands.append(
        (
            "turn_controls",
            out_dir / "turn-controls.json",
            [
                py,
                "scripts/smoke_turn_controls.py",
                "--base-url",
                base_url,
                "--wait-health-s",
                str(args.wait_health_s),
                "--out",
                str(out_dir / "turn-controls.json"),
            ],
            120,
        )
    )
    if args.include_listener_rung7:
        commands.append(
            (
                "listener_rung7",
                out_dir / "listener-rung7" / "rung7.json",
                [
                    py,
                    "scripts/smoke_conversation_ladder.py",
                    "--rung",
                    "7",
                    "--fixture",
                    str(args.listener_fixture),
                    "--expected-transcript",
                    args.listener_expected_transcript,
                    "--response-text",
                    "I hear you. Let me route that.",
                    "--run-id",
                    "full-live-sanity-rung7",
                    "--session-id",
                    "full-live-sanity-listener",
                    "--turn-id",
                    "full-live-sanity-listener-turn",
                    "--out",
                    str(out_dir / "listener-rung7" / "rung7.json"),
                ],
                240,
            )
        )
    if args.include_tau_voice_render:
        commands.append(
            (
                "tau_voice_render",
                out_dir / "tau-voice-render.json",
                [
                    py,
                    "scripts/smoke_tau_voice_render.py",
                    "--base-url",
                    base_url,
                    "--out",
                    str(out_dir / "tau-voice-render.json"),
                    "--wait-health-s",
                    str(args.wait_health_s),
                    "--expect-cache-hit",
                ],
                180,
            )
        )
    if args.include_listener_memory_tau_qra:
        commands.append(
            (
                "listener_memory_tau_qra",
                out_dir / "listener-memory-tau-qra" / "listener-memory-tau-qra.json",
                [
                    py,
                    "scripts/smoke_listener_memory_tau_qra.py",
                    "--base-url",
                    base_url,
                    "--out-dir",
                    str(out_dir / "listener-memory-tau-qra"),
                ],
                900,
            )
        )

    children: list[dict[str, Any]] = []
    failed_gates: list[str] = []
    if args.reset_cache and not cache_reset.get("ok"):
        failed_gates.append("cache_reset_ok")
    for name, receipt_path, cmd, timeout in commands:
        command = run_cmd(cmd, timeout=timeout)
        child = summarize_child(name, receipt_path, command)
        children.append(child)
        if command["returncode"] != 0:
            failed_gates.append(f"{name}:command_returncode")
        if not child["ok"]:
            failed_gates.append(f"{name}:receipt_ok")

    receipt = {
        "ok": not failed_gates,
        "mocked": False,
        "live": True,
        "proof_scope": "live_chatterbox_agent_transport_asr_cache_stream_interrupt_listener_smoke",
        "does_not_prove": [
            "full conversational agent quality",
            "memory retrieval correctness",
            "brave-search integration",
            "listener ASR pass unless --include-listener-rung7 is used and passes",
            "Tau voice render ingress unless --include-tau-voice-render is used and passes",
            "listener-to-memory-to-Tau QRA chain unless --include-listener-memory-tau-qra is used and passes",
            "human subjective voice preference",
        ],
        "base_url": base_url,
        "cache_dir": str(args.cache_dir),
        "cache_reset": cache_reset,
        "cache_container": args.cache_container,
        "cwd": os.getcwd(),
        "children": children,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "failed_gates": failed_gates,
    }
    receipt_path = out_dir / "full-live-sanity.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": receipt["ok"],
                "out": str(receipt_path),
                "children": [
                    {
                        "name": child["name"],
                        "ok": child["ok"],
                        "failed_gates": child["failed_gates"],
                    }
                    for child in children
                ],
                "failed_gates": failed_gates,
                "elapsed_ms": receipt["elapsed_ms"],
            },
            sort_keys=True,
        )
    )
    return 0 if receipt["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
