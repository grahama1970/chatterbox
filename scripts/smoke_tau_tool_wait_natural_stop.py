#!/usr/bin/env python3
"""Live proof for a Tau voice-render natural stop phrase during a tool wait.

This does not prove the full Tau agent selected the wait. It proves that a
Tau-shaped voice-render request carrying the wait decision can make Chatterbox
speak the natural holding phrase and preserve the receipt fields required by
the speech audit.
"""

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
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chatterbox.agent.conversation import wait_decision_for_expected_delay


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
        return {"path": str(path), "exists": False, "bytes": 0}
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


def build_tau_payload(args: argparse.Namespace, wait_decision: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    phrase = str(wait_decision["text"])
    voice_delivery = {
        "tone": args.tone,
        "delivery_stage": "holding",
        "pace": "brief",
        "pause_strategy": "natural_tool_wait_stop",
        "source": "tau.tool_wait",
    }
    return {
        "schema": "tau.voice_render_request.v1",
        "run_id": args.run_id,
        "conversation_id": args.conversation_id,
        "turn_id": args.turn_id,
        "route": "tau_tool_wait_natural_stop",
        "active_domain_persona": "embry",
        "question_text": args.question,
        "question_text_sha256": sha256_text(args.question),
        "memory_route_decision": {
            "called": False,
            "reason": "tool_wait_boundary_no_memory_answer_yet",
        },
        "answerability_decision": {
            "decision": "wait_for_tool",
            "tool_name": args.tool_name,
            "expected_wait_ms": args.expected_wait_ms,
            "source": "tau.tool_wait",
        },
        "voice_delivery": voice_delivery,
        "speakable_chunks": [
            {
                "chunk_id": f"{args.turn_id}-natural-stop-1",
                "text": phrase,
                "text_sha256": sha256_text(phrase),
                "tone": args.tone,
                "delivery_stage": "holding",
                "pace": "brief",
                "pause_strategy": "natural_tool_wait_stop",
                "pause_after_ms": 0,
                "interruptible": True,
                "max_chars": 300,
            }
        ],
        "tone": args.tone,
        "delivery_stage": "holding",
        "pace": "brief",
        "pause_strategy": "natural_tool_wait_stop",
        "interruptible": True,
        "use_blessed_qra_cache": False,
        "require_blessed_qra_memory_gate": False,
        "turn_control_policy": {
            "old_turn_id": args.old_turn_id,
            "cancel_requested": True,
            "stale_old_turn_chunks_should_skip": True,
        },
        "external_evidence": {
            "tau_tool_wait_decision": wait_decision,
            "interruption_policy": {
                "natural_stop_required": True,
                "keeps_existing_work_alive": True,
                "old_turn_id": args.old_turn_id,
                "new_turn_id": args.turn_id,
            },
        },
        "receipt_root": str(out_dir),
        "label": args.label,
        "include_completion_cue": False,
        "crossfade_ms": 0,
        "asr_verify": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8018")
    parser.add_argument("--out-dir", default="/tmp/chatterbox-fork-agent-out/tau-tool-wait-natural-stop/latest", type=Path)
    parser.add_argument("--host-out-dir", default="/tmp/chatterbox-fork-agent-out", type=Path)
    parser.add_argument("--container-out-dir", default="/out")
    parser.add_argument("--timeout-s", default=180, type=int)
    parser.add_argument("--wait-health-s", default=120, type=int)
    parser.add_argument("--expected-wait-ms", default=9000, type=int)
    parser.add_argument("--variant-offset", default=2, type=int)
    parser.add_argument("--run-id", default=f"tau-tool-wait-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}")
    parser.add_argument("--conversation-id", default="embry-tool-wait-natural-stop")
    parser.add_argument("--old-turn-id", default="turn-tool-wait-old")
    parser.add_argument("--turn-id", default="turn-tool-wait-holding")
    parser.add_argument("--label", default="tau_tool_wait_natural_stop")
    parser.add_argument("--tool-name", default="brave-search")
    parser.add_argument("--tone", default="calm_precise")
    parser.add_argument("--question", default="Can you research the latest voice listener options while I interrupt?")
    args = parser.parse_args()

    started = time.perf_counter()
    base_url = args.base_url.rstrip("/")
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    failed_gates: list[str] = []

    health, health_error = wait_for_health(base_url, args.wait_health_s)
    if not health:
        failed_gates.append("chatterbox_health_ok")

    wait_decision = wait_decision_for_expected_delay(
        args.expected_wait_ms,
        variant_offset=args.variant_offset,
        conversation_tone="focused",
        user_mood="neutral",
        allow_hum=False,
    )
    phrase = wait_decision.get("text")
    if not phrase:
        failed_gates.append("wait_decision_text_present")

    payload = build_tau_payload(args, wait_decision, out_dir)
    (out_dir / "tau_voice_render_request.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    status_code = None
    response = None
    post_error = None
    if health and phrase:
        status_code, response, post_error = post_json(f"{base_url}/tau/voice-render", payload, args.timeout_s)
        if status_code != 200:
            failed_gates.append("tau_voice_render_http_200")
        if not response or response.get("ok") is not True:
            failed_gates.append("tau_voice_render_response_ok")
        tau_request = (response or {}).get("tau_voice_render_request") or {}
        if tau_request.get("route") != "tau_tool_wait_natural_stop":
            failed_gates.append("tau_voice_render_route_preserved")
        if (tau_request.get("voice_delivery") or {}).get("delivery_stage") != "holding":
            failed_gates.append("tau_voice_render_delivery_stage_holding")

    finished_audio = map_container_path(
        (response or {}).get("finished_response_audio") if response else None,
        args.container_out_dir,
        args.host_out_dir,
    )
    metrics = wav_metrics(finished_audio)
    if not metrics.get("exists"):
        failed_gates.append("finished_audio_exists")
    if int(metrics.get("bytes") or 0) <= 44:
        failed_gates.append("finished_audio_non_empty")
    if float(metrics.get("duration_seconds") or 0) <= 0:
        failed_gates.append("finished_audio_duration_positive")

    natural_stop = {
        "phrase": phrase,
        "phrase_sha256": sha256_text(str(phrase)) if phrase else None,
        "phrase_observed": bool(phrase and response and response.get("ok") is True),
        "delivery_stage": "holding",
        "keeps_existing_work_alive": True,
        "old_turn_id": args.old_turn_id,
        "new_turn_id": args.turn_id,
    }
    if natural_stop["phrase_sha256"] != wait_decision.get("text_sha256"):
        failed_gates.append("natural_stop_phrase_matches_wait_decision")

    receipt = {
        "schema": "chatterbox.tau_tool_wait_natural_stop.v1",
        "ok": not failed_gates,
        "status": "passed" if not failed_gates else "failed",
        "mocked": False,
        "live": bool(health and response and status_code == 200),
        "used_ui": False,
        "used_mock_transcript": False,
        "used_typed_prompt": False,
        "base_url": base_url,
        "started_at_utc": datetime.fromtimestamp(
            time.time() - (time.perf_counter() - started),
            timezone.utc,
        ).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "ended_at_utc": utc_now(),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "health": health,
        "health_error": health_error,
        "wait_decision": wait_decision,
        "natural_stop": natural_stop,
        "status_code": status_code,
        "post_error": post_error,
        "tau_voice_render_request_path": str(out_dir / "tau_voice_render_request.json"),
        "tau_voice_render_response": response,
        "audio_metrics": metrics,
        "failed_gates": failed_gates,
        "claims": {
            "proves": [
                "tau_voice_render_ingress_can_speak_tool_wait_natural_stop_phrase",
                "natural_stop_phrase_is_tied_to_wait_decision",
                "chatterbox_audio_artifact_exists_for_tool_wait_holding_phrase",
            ]
            if not failed_gates
            else [],
            "does_not_prove": [
                "full Tau agent selected the wait",
                "RealtimeSTT audio ingress",
                "browser microphone capture",
                "speaker identity",
                "Chat UX synchronization",
                "orb synchronization",
                "human-perceived speaker audibility",
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
