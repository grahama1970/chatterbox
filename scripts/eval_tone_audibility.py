"""Agentic eval: emotion/tone tags must produce measurably different audio.

Protocol (per case): render a same-parameter noise floor (N identical requests
against the live server), then render two contrasting arms. Every metric is
computed from the produced wav files with numpy — never from the echoed
request. A case passes only when at least one acoustic metric's between-arm
group delta exceeds that metric's same-parameter spread.

Cases:
  pace            slow vs fast on chatterbox_turbo (deterministic time stretch)
  affect          high-arousal vs low-arousal via intensity/valence on
                  chatterbox_base_affect (exaggeration/cfg_weight honored)
  tone_alone      firm_boundary vs grief_safe with ONLY the tone tag set.
                  This is the built-in-emotion contract: a bare tone tag must
                  be audible. It fails until tone auto-routes through the
                  affect channel (currently request-only on chatterbox_turbo).
  receipt_honesty no renders; asserts /health voice_delivery_effect never
                  claims effect for request-only fields.

Exit 0 on pass, 1 on measured failure, 2 on infrastructure error.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
import urllib.request
import wave
from pathlib import Path

import numpy as np

DEFAULT_BASE_URL = "http://localhost:8018"
TEXT = (
    "I need you to hear the difference in my voice, not just read it in the receipt. "
    "This sentence is long enough to measure pitch, energy, and rate."
)
F0_MIN_HZ, F0_MAX_HZ = 60.0, 400.0


def render(base_url: str, out_root: Path, label: str, body_extra: dict) -> Path:
    body = {"answer_text": TEXT, "label": label, **body_extra}
    req = urllib.request.Request(
        f"{base_url}/synthesize-batch",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=900) as resp:
        receipt = json.load(resp)
    if not receipt.get("ok"):
        raise RuntimeError(f"render {label} not ok: {receipt.get('failed_gates')}")
    container_path = receipt["finished_response_audio"]
    host_path = Path(container_path.replace("/out/", str(out_root) + "/"))
    if not host_path.exists():
        raise RuntimeError(f"rendered wav missing on host: {host_path}")
    return host_path


def wav_metrics(path: Path) -> dict[str, float]:
    with contextlib.closing(wave.open(str(path), "rb")) as w:
        sr = w.getframerate()
        raw = w.readframes(w.getnframes())
        width = w.getsampwidth()
    dtype = {2: np.int16, 4: np.int32}[width]
    x = np.frombuffer(raw, dtype=dtype).astype(np.float64)
    x /= float(np.iinfo(dtype).max)
    duration = len(x) / sr
    rms = float(np.sqrt(np.mean(np.square(x)))) if len(x) else 0.0

    frame, hop = 2048, 1024
    lag_lo, lag_hi = int(sr / F0_MAX_HZ), int(sr / F0_MIN_HZ)
    f0s: list[float] = []
    energy_gate = 0.5 * rms
    for start in range(0, len(x) - frame, hop):
        seg = x[start : start + frame]
        if np.sqrt(np.mean(np.square(seg))) < energy_gate:
            continue
        seg = seg - seg.mean()
        ac = np.correlate(seg, seg, mode="full")[frame - 1 :]
        if ac[0] <= 0:
            continue
        window = ac[lag_lo:lag_hi]
        if not len(window):
            continue
        lag = lag_lo + int(np.argmax(window))
        if ac[lag] / ac[0] > 0.3:
            f0s.append(sr / lag)
    f0_median = float(np.median(f0s)) if f0s else 0.0
    return {"duration_s": round(duration, 3), "rms": round(rms, 5), "f0_median_hz": round(f0_median, 1)}


def group(paths: list[Path]) -> dict[str, list[float]]:
    per = [wav_metrics(p) for p in paths]
    return {k: [m[k] for m in per] for k in per[0]}


def spread(values: list[float]) -> float:
    return round(max(values) - min(values), 4)


def mean(values: list[float]) -> float:
    return sum(values) / len(values)


CASES: dict[str, dict] = {
    "pace": {
        "floor": {"tone": "neutral_warm"},
        "arm_a": {"tone": "neutral_warm", "pace": "slow"},
        "arm_b": {"tone": "neutral_warm", "pace": "fast"},
    },
    "affect": {
        "floor": {"tone": "neutral_warm", "voice_delivery": {"intensity": 0.5, "valence": 0.0}},
        "arm_a": {"tone": "firm_boundary", "voice_delivery": {"intensity": 0.9, "valence": -0.8}},
        "arm_b": {"tone": "grief_safe", "voice_delivery": {"intensity": 0.2, "valence": -0.2}},
    },
    "tone_alone": {
        "floor": {"tone": "neutral_warm"},
        "arm_a": {"tone": "firm_boundary"},
        "arm_b": {"tone": "grief_safe"},
    },
}


def run_case(case: str, base_url: str, out_root: Path, floor_n: int, arm_n: int) -> dict:
    spec = CASES[case]
    # Interleave floor/arm renders round-robin so slow session-scale drift in
    # the renderer lands in the noise floor instead of masquerading as an arm
    # effect (observed: sequential blocks let f0 drift read as tone separation).
    schedule: list[tuple[str, int, dict]] = []
    for i in range(1, max(floor_n, arm_n) + 1):
        if i <= floor_n:
            schedule.append(("floor", i, spec["floor"]))
        if i <= arm_n:
            schedule.append(("a", i, spec["arm_a"]))
            schedule.append(("b", i, spec["arm_b"]))
    paths: dict[str, list[Path]] = {"floor": [], "a": [], "b": []}
    for group_name, i, body in schedule:
        paths[group_name].append(render(base_url, out_root, f"eval-{case}-{group_name}-{i:02d}", body))
    floor_paths, arm_a_paths, arm_b_paths = paths["floor"], paths["a"], paths["b"]
    floor_g, a_g, b_g = group(floor_paths), group(arm_a_paths), group(arm_b_paths)
    per_metric = {}
    for metric in floor_g:
        noise = spread(floor_g[metric])
        delta = round(abs(mean(a_g[metric]) - mean(b_g[metric])), 4)
        per_metric[metric] = {
            "floor_values": floor_g[metric],
            "floor_spread": noise,
            "arm_a_values": a_g[metric],
            "arm_b_values": b_g[metric],
            "arm_group_delta": delta,
            "exceeds_floor": delta > noise,
        }
    return {
        "case": case,
        "arms": {"a": spec["arm_a"], "b": spec["arm_b"]},
        "metrics": per_metric,
        "pass": any(m["exceeds_floor"] for m in per_metric.values()),
    }


def run_receipt_honesty(base_url: str) -> dict:
    with urllib.request.urlopen(f"{base_url}/health", timeout=30) as resp:
        health = json.load(resp)
    fields = health["voice_delivery_effect"]["fields"]
    checks = {
        "pace_declared_applied": fields["pace"]["status"] == "applied",
        "tone_not_silently_claimed": fields["tone"]["status"] != "applied"
        or "audible" in json.dumps(fields["tone"]).lower(),
        "pause_strategy_status_present": bool(fields["pause_strategy"]["status"]),
        "every_field_has_status": all("status" in f for f in fields.values()),
    }
    return {"case": "receipt_honesty", "checks": checks, "pass": all(checks.values())}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, choices=[*CASES, "receipt_honesty"])
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--out-root", default=str(Path(__file__).resolve().parent.parent / "logs"))
    parser.add_argument("--floor-n", type=int, default=6)
    parser.add_argument("--arm-n", type=int, default=3)
    args = parser.parse_args()
    try:
        if args.case == "receipt_honesty":
            result = run_receipt_honesty(args.base_url)
        else:
            result = run_case(args.case, args.base_url, Path(args.out_root), args.floor_n, args.arm_n)
    except Exception as exc:  # noqa: BLE001 - infrastructure failure must be distinct from measured failure
        print(json.dumps({"case": args.case, "error": f"{type(exc).__name__}: {exc}"}))
        return 2
    print(json.dumps(result, indent=1))
    print(f"RESULT: {'PASS' if result['pass'] else 'FAIL'} ({args.case})")
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
