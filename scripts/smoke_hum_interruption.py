#!/usr/bin/env python3
"""Prove a long-wait hum can be interrupted and followed by Embry speech.

This smoke is local playback evidence, not ASR/VAD proof. It asks the
Chatterbox wait policy for a long predicted job, starts a cached hum track with
PipeWire, interrupts the hum process after a short delay, and plays a cached
Embry interruption acknowledgement.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from chatterbox.agent.conversation import wait_decision_for_expected_delay


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def audio_file_metrics(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "exists": path.exists(),
        "bytes": path.stat().st_size if path.exists() else 0,
    }


def terminate_process(proc: subprocess.Popen, timeout_s: float = 2.0) -> dict[str, Any]:
    if proc.poll() is not None:
        return {"already_exited": True, "returncode": proc.returncode}
    proc.terminate()
    try:
        proc.wait(timeout=timeout_s)
        return {"terminated": True, "returncode": proc.returncode}
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=timeout_s)
        return {"terminated": False, "killed": True, "returncode": proc.returncode}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--hum-audio", default="/mnt/storage12tb/media/personas/embry/hum-cache/hawaiian_war_chant.wav", type=Path)
    parser.add_argument(
        "--ack-audio",
        default=(
            "/home/graham/workspace/experiments/agent-skills/receipts/voice_agent_bakeoff/"
            "chatterbox_fork_agent_server/20260701T214417Z-voice-cache-out/"
            "voice_cache_001_got_it_i_ll_stop_there.wav"
        ),
        type=Path,
    )
    parser.add_argument("--expected-wait-ms", default=9000, type=int)
    parser.add_argument("--interrupt-after-s", default=3.0, type=float)
    parser.add_argument("--playback-cmd", default=shutil.which("pw-play") or "")
    args = parser.parse_args()

    failed_gates: list[str] = []
    if not args.playback_cmd:
        failed_gates.append("playback_command_available")
    if not args.hum_audio.exists() or args.hum_audio.stat().st_size <= 44:
        failed_gates.append("hum_audio_non_empty")
    if not args.ack_audio.exists() or args.ack_audio.stat().st_size <= 44:
        failed_gates.append("ack_audio_non_empty")

    decision = wait_decision_for_expected_delay(args.expected_wait_ms, variant_offset=4, allow_hum=True)
    if not decision["should_start_hum"]:
        failed_gates.append("decision_starts_hum")
    if not decision["hum"]["start_muted"]:
        failed_gates.append("hum_starts_muted")
    if not decision["hum"]["interstitials"]["can_interrupt_hum"]:
        failed_gates.append("hum_interstitial_can_interrupt")

    playback: dict[str, Any] = {}
    started = time.perf_counter()
    if not failed_gates:
        hum_proc = subprocess.Popen([args.playback_cmd, str(args.hum_audio)])
        playback["hum_pid"] = hum_proc.pid
        time.sleep(args.interrupt_after_s)
        playback["hum_interrupt"] = terminate_process(hum_proc)
        playback["hum_played_before_interrupt_s"] = round(time.perf_counter() - started, 3)
        if playback["hum_interrupt"].get("returncode") is None:
            failed_gates.append("hum_process_stopped")
        ack_started = time.perf_counter()
        ack = subprocess.run([args.playback_cmd, str(args.ack_audio)], text=True, capture_output=True, timeout=20)
        playback["ack_returncode"] = ack.returncode
        playback["ack_elapsed_s"] = round(time.perf_counter() - ack_started, 3)
        playback["ack_stdout"] = ack.stdout[-1000:]
        playback["ack_stderr"] = ack.stderr[-1000:]
        if ack.returncode != 0:
            failed_gates.append("ack_playback_ok")

    receipt = {
        "ok": not failed_gates,
        "mocked": False,
        "live": True,
        "created_at_utc": utc_now(),
        "proof_scope": "local_pipewire_playback_interrupts_cached_hum_then_plays_cached_embry_ack",
        "does_not_prove": [
            "microphone VAD detected interruption",
            "real memory latency prediction ran",
            "hum mixer ducking volume was acoustically measured",
            "Chatterbox rendered new audio during this smoke",
        ],
        "expected_wait_ms": args.expected_wait_ms,
        "interrupt_after_s": args.interrupt_after_s,
        "wait_decision": decision,
        "hum_audio": audio_file_metrics(args.hum_audio),
        "ack_audio": audio_file_metrics(args.ack_audio),
        "playback": playback,
        "failed_gates": failed_gates,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": receipt["ok"], "out": str(args.out), "failed_gates": failed_gates}, indent=2))
    if failed_gates:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
