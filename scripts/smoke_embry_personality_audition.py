#!/usr/bin/env python3
"""Render and audibly play Embry boundary-line personality variants."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


VARIANTS = [
    ("flat_baseline", "Hey, one at a time?", "one_at_a_time_interrupt"),
    (
        "warm_boundary",
        "Hey, one at a time. I want to hear you both, but I need one voice first.",
        "one_at_a_time_interrupt",
    ),
    ("embry_playful", "Kai, wait. One at a time, or I am going to lose the thread.", "playful_light"),
    ("embry_firm", "Hold on. One at a time. Horus, I have you first.", "firm_boundary"),
    (
        "embry_human",
        "Hey. One at a time, please. I am listening, but I cannot split two voices cleanly yet.",
        "careful_concerned",
    ),
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run_cmd(cmd: list[str], *, timeout: int) -> dict[str, Any]:
    started = time.perf_counter()
    result = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)
    return {
        "cmd": cmd,
        "returncode": result.returncode,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "stdout_tail": result.stdout[-4000:],
        "stderr_tail": result.stderr[-4000:],
    }


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"error_type": type(exc).__name__, "error": str(exc)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--base-url", default="http://127.0.0.1:8018")
    parser.add_argument("--playback-sink-target", default="64")
    parser.add_argument("--timeout-s", default=240, type=int)
    args = parser.parse_args()

    started = time.perf_counter()
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    failed_gates: list[str] = []
    variant_receipts: list[dict[str, Any]] = []

    for name, text, tone in VARIANTS:
        render_receipt = out_dir / f"{name}.json"
        wav = out_dir / f"{name}.wav"
        voice_delivery = json.dumps({"tone": tone, "delivery_stage": "boundary", "pause_after_ms": 120})
        render_cmd = [
            "python3",
            "scripts/smoke_tau_voice_render.py",
            "--base-url",
            args.base_url,
            "--out",
            str(render_receipt),
            "--question",
            "Two people are speaking at once.",
            "--answer-text",
            text,
            "--blessed-qra-memory-key",
            f"personality-{name}",
            "--blessed-qra-memory-similarity",
            "1.0",
            "--blessed-qra-memory-review-status",
            "approved",
            "--voice-delivery-json",
            voice_delivery,
            "--no-use-blessed-qra-cache",
            "--timeout-s",
            str(args.timeout_s),
        ]
        render_run = run_cmd(render_cmd, timeout=args.timeout_s + 60)
        render_data = read_json(render_receipt)
        source = Path(str(((render_data.get("artifacts") or {}).get("finished_response_audio_host")) or ""))
        copied = False
        if source.exists():
            shutil.copy2(source, wav)
            copied = True
        play_run = None
        if copied:
            play_run = run_cmd(["pw-play", "--target", args.playback_sink_target, str(wav)], timeout=120)
        variant_failed: list[str] = []
        if render_run["returncode"] != 0 or not render_data.get("ok"):
            variant_failed.append("tau_render_ok")
        if not copied:
            variant_failed.append("wav_copied")
        if play_run is None or play_run["returncode"] != 0:
            variant_failed.append("audible_playback_ok")
        failed_gates.extend([f"{name}:{gate}" for gate in variant_failed])
        variant_receipts.append(
            {
                "id": name,
                "text": text,
                "tone": tone,
                "render_receipt": str(render_receipt),
                "wav": str(wav) if copied else None,
                "render": render_run,
                "play": play_run,
                "failed_gates": variant_failed,
            }
        )

    receipt = {
        "schema": "chatterbox.embry_personality_audition.v1",
        "ok": not failed_gates,
        "mocked": False,
        "live": not failed_gates,
        "started_at_utc": datetime.fromtimestamp(
            time.time() - (time.perf_counter() - started),
            timezone.utc,
        ).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "ended_at_utc": utc_now(),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "playback_sink_target": args.playback_sink_target,
        "variants": variant_receipts,
        "failed_gates": failed_gates,
        "claims": {
            "proves": [
                "Embry boundary variants render through live Tau/Chatterbox",
                "Embry boundary variants are played audibly through the configured sink",
            ]
            if not failed_gates
            else [],
            "does_not_prove": [
                "human_acceptance_of_personality",
                "automatic_prosody_quality_scoring",
                "best_final_boundary_copy",
            ],
        },
    }
    out_path = out_dir / "personality-audition.json"
    out_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": receipt["ok"],
                "mocked": receipt["mocked"],
                "live": receipt["live"],
                "out": str(out_path),
                "variant_count": len(variant_receipts),
                "failed_gates": failed_gates,
            },
            sort_keys=True,
        )
    )
    return 0 if receipt["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
