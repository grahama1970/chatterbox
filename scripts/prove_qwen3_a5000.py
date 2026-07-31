#!/usr/bin/env python3
"""Live RTX A5000 proof for the experimental qwen3_tts backend (issue #13)."""

from __future__ import annotations

import json
import statistics
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from uuid import uuid4

BASE = "http://127.0.0.1:8018"
CANONICAL_TEXT = "The evidence is incomplete, so this claim cannot be released."
SIDECAR_CONTAINER = "qwen3-tts-sidecar"
AGENT_CONTAINER = "chatterbox-fork-agent-server"


def post(path: str, body: dict, timeout: int = 1800):
    req = urllib.request.Request(
        f"{BASE}{path}", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def sidecar(path: str, method: str = "GET", timeout_s: int = 1800):
    cmd = ["docker", "exec", AGENT_CONTAINER, "/usr/bin/python3.11", "-c", (
        "import json,urllib.request;"
        f"req=urllib.request.Request('http://127.0.0.1:8019{path}',"
        f"data=(b'{{}}' if '{method}'=='POST' else None),"
        "headers={'Content-Type':'application/json'},"
        f"method='{method}');"
        f"print(urllib.request.urlopen(req, timeout={timeout_s}).read().decode())"
    )]
    return json.loads(subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s + 30, check=True).stdout)


def main() -> int:
    receipt: dict = {"mocked": False, "live": True, "proof_scope": "qwen3_tts_backend_rtx_a5000_live"}
    failed: list[str] = []

    smi = subprocess.run(
        ["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    receipt["environment"] = {"gpu": smi, "agent_container": AGENT_CONTAINER, "sidecar_container": SIDECAR_CONTAINER}

    started = time.perf_counter()
    load = sidecar("/load", "POST")
    receipt["cold_load_from_cache"] = {"load_seconds": load.get("load_seconds"), "wall_s": round(time.perf_counter() - started, 3), "vram": load.get("vram")}
    receipt["cold_load_including_download_seconds_earlier_run"] = 48.878
    health = sidecar("/health")
    caps = sidecar("/capabilities")
    receipt["sidecar_health"] = health
    receipt["sidecar_capabilities"] = caps
    if not health.get("model_loaded"):
        failed.append("sidecar_model_loaded")

    # Warm renders: voice clone with the Embry reference through the agent API.
    warm: list[dict] = []
    for index in range(5):
        t0 = time.perf_counter()
        status, render = post("/synthesize", {"text": CANONICAL_TEXT, "label": f"qwen_live_warm_{index}", "backend": "qwen3_tts"})
        wall = round(time.perf_counter() - t0, 3)
        warm.append({
            "status": status, "ok": render.get("ok"), "wall_s": wall,
            "generation_seconds": render.get("generation_seconds"),
            "duration_seconds": render.get("duration_seconds"),
            "realtime_factor": render.get("realtime_factor"),
            "engine": render.get("engine"), "backend": render.get("backend"),
            "output_format": render.get("output_format"),
        })
        if not render.get("ok") or render.get("engine") != "qwen3_tts":
            failed.append(f"warm_render_{index}_ok")
    walls = sorted(item["wall_s"] for item in warm)
    receipt["warm_renders"] = warm
    receipt["latency_note"] = "non-streaming adapter: TTFA equals full synthesis wall time by design (capability true_incremental_streaming=false)"
    receipt["ttfa_full_synth_p50_s"] = statistics.median(walls)
    receipt["ttfa_full_synth_p95_s"] = walls[max(0, int(len(walls) * 0.95) - 1)] if len(walls) > 1 else walls[0]

    status, structured = post("/synthesize", {"text": CANONICAL_TEXT, "label": "qwen_live_affect", "backend": "qwen3_tts", "voice_delivery": {"intensity": 0.7, "valence": -0.4}})
    receipt["structured_delivery_request"] = {"status": status, "detail": structured.get("detail")}
    if status != 422 or "backend_capability_unsupported" not in str(structured.get("detail", {}).get("reason")):
        failed.append("structured_delivery_typed_unsupported")

    # Mid-stream cancel through the qwen backend: stale-output fencing + manifest terminal.
    turn = f"turn-qwen-{uuid4().hex[:8]}"
    stream_req = urllib.request.Request(
        f"{BASE}/synthesize-batch-stream",
        data=json.dumps({
            "answer_text": CANONICAL_TEXT + " " + CANONICAL_TEXT + " " + CANONICAL_TEXT,
            "max_chars": 80, "pause_after_ms": 0, "completion_cue": "", "include_completion_cue": False,
            "crossfade_ms": 0, "use_blessed_qra_cache": False, "backend": "qwen3_tts",
            "turn_id": turn, "label": "qwen_live_stream_cancel",
        }).encode(), headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(stream_req, timeout=1800) as response:
        stream_id = response.headers.get("X-Stream-Id")
        response.read(1920)
        post(f"/turn/{turn}/cancel", {"reason": "qwen live proof", "old_turn_id": turn}, timeout=30)
        rest = response.read()
    time.sleep(0.5)
    with urllib.request.urlopen(f"{BASE}/stream-manifest/{stream_id}", timeout=30) as r:
        manifest = json.loads(r.read())["manifest"]
    receipt["mid_stream_cancel"] = {
        "stream_id": stream_id,
        "post_cancel_drained_bytes": len(rest),
        "terminal": manifest["terminal"],
        "manifest_backend": manifest["backend"],
    }
    if manifest["terminal"]["status"] != "cancelled":
        failed.append("stream_cancel_terminal_cancelled")
    if manifest["backend"].get("id") != "qwen3_tts":
        failed.append("stream_manifest_backend_qwen")

    unload = sidecar("/unload", "POST", timeout_s=120)
    health_after_unload = sidecar("/health")
    t0 = time.perf_counter()
    status, reload_render = post("/synthesize", {"text": CANONICAL_TEXT, "label": "qwen_live_reload", "backend": "qwen3_tts"})
    receipt["unload_reload"] = {
        "unload": unload, "model_loaded_after_unload": health_after_unload.get("model_loaded"),
        "reload_render_ok": reload_render.get("ok"), "reload_wall_s": round(time.perf_counter() - t0, 3),
    }
    if health_after_unload.get("model_loaded") is not False:
        failed.append("unload_effective")
    if not reload_render.get("ok"):
        failed.append("reload_render_ok")

    subprocess.run(["docker", "stop", SIDECAR_CONTAINER], capture_output=True, check=True)
    status, down = post("/synthesize", {"text": CANONICAL_TEXT, "label": "qwen_live_down", "backend": "qwen3_tts"}, timeout=120)
    status_t, turbo = post("/synthesize", {"text": CANONICAL_TEXT, "label": "qwen_live_turbo_check"}, timeout=600)
    receipt["no_silent_fallback"] = {
        "qwen_down_ok": down.get("ok"), "qwen_down_engine": down.get("engine"),
        "qwen_down_error_present": "qwen_sidecar_unavailable" in str(down.get("error")),
        "turbo_still_ok": turbo.get("ok"), "turbo_engine": turbo.get("engine"),
    }
    if down.get("ok") is not False or down.get("engine") != "qwen3_tts":
        failed.append("qwen_down_fails_on_qwen")
    if "qwen_sidecar_unavailable" not in str(down.get("error")):
        failed.append("qwen_down_typed_error")
    if turbo.get("ok") is not True or turbo.get("engine") != "chatterbox_turbo":
        failed.append("turbo_unaffected")
    subprocess.run(["bash", "scripts/start_qwen_sidecar_docker.sh"], capture_output=True, check=True)

    receipt["failed_gates"] = failed
    receipt["ok"] = not failed
    out = Path("docs/QWEN3_TTS_A5000_PROOF_20260731.json")
    out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": receipt["ok"], "failed_gates": failed, "p50_s": receipt["ttfa_full_synth_p50_s"], "p95_s": receipt["ttfa_full_synth_p95_s"], "vram_resident_mb": (health.get("vram") or {}).get("resident_mb")}, sort_keys=True))
    return 0 if receipt["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
