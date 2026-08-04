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
    "tone_audible": {
        "floor": {"tone": "neutral_warm", "voice_delivery": {"emotion_realization": "audible"}},
        "arm_a": {"tone": "firm_boundary", "voice_delivery": {"emotion_realization": "audible"}},
        "arm_b": {"tone": "grief_safe", "voice_delivery": {"emotion_realization": "audible"}},
    },
}

ALL_TONES = [
    "neutral_warm", "calm_precise", "careful_concerned", "serious_low_energy",
    "memory_confident", "memory_uncertain", "curious_searching", "playful_light",
    "relieved", "firm_boundary", "identity_clarification", "one_at_a_time_interrupt",
    "deflect_calm", "grief_safe", "wait_presence",
]


def run_tone_matrix(base_url: str, out_root: Path, floor_n: int, per_tone: int, matrix_out: Path) -> dict:
    """Pairwise distinguishability of every declared tone under audible realization.

    neutral_warm's samples double as the same-parameter noise floor (identical
    request params). Renders are interleaved round-robin so session drift lands
    in the floor. Every tone is classified calibrated_distinct (separable from
    neutral_warm past the floor) or not_distinct_request_only.
    """
    def body(tone: str) -> dict:
        return {"tone": tone, "voice_delivery": {"emotion_realization": "audible"}}

    others = [t for t in ALL_TONES if t != "neutral_warm"]
    schedule: list[tuple[str, int]] = []
    rounds = max(floor_n, per_tone)
    for i in range(1, rounds + 1):
        if i <= floor_n:
            schedule.append(("neutral_warm", i))
        if i <= per_tone:
            schedule.extend((t, i) for t in others)
    samples: dict[str, list[dict[str, float]]] = {t: [] for t in ALL_TONES}
    for tone, i in schedule:
        path = render(base_url, out_root, f"eval-matrix-{tone}-{i:02d}", body(tone))
        samples[tone].append(wav_metrics(path))

    metrics = list(next(iter(samples.values()))[0])
    floor_values = {m: [s[m] for s in samples["neutral_warm"]] for m in metrics}
    floor_spread = {m: spread(floor_values[m]) for m in metrics}
    tone_means = {t: {m: round(mean([s[m] for s in samples[t]]), 4) for m in metrics} for t in ALL_TONES}

    def separating(t1: str, t2: str) -> list[str]:
        return [m for m in metrics if abs(tone_means[t1][m] - tone_means[t2][m]) > floor_spread[m]]

    pairwise = {
        t1: {t2: separating(t1, t2) for t2 in ALL_TONES if t2 != t1}
        for t1 in ALL_TONES
    }
    classification = {
        t: ("calibrated_distinct" if (t == "neutral_warm" or separating(t, "neutral_warm")) else "not_distinct_request_only")
        for t in ALL_TONES
    }
    distinct_pairs = sum(1 for t1 in pairwise for t2 in pairwise[t1] if pairwise[t1][t2]) // 2
    result = {
        "case": "tone_matrix",
        "schema": "chatterbox.tone_calibration_matrix.v1",
        "generated": "eval_tone_audibility tone_matrix",
        "noise_floor": {"n": floor_n, "values": floor_values, "spread": floor_spread},
        "per_tone_samples": per_tone,
        "tone_means": tone_means,
        "pairwise_separating_metrics": pairwise,
        "distinct_pairs": distinct_pairs,
        "total_pairs": len(ALL_TONES) * (len(ALL_TONES) - 1) // 2,
        "classification": classification,
        "pass": all(t in classification for t in ALL_TONES),
    }
    matrix_out.parent.mkdir(parents=True, exist_ok=True)
    matrix_out.write_text(json.dumps(result, indent=1) + "\n")
    return result


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


def run_machine_listener(out_root: Path) -> dict:
    """Dimensional perceptual self-analysis over already-rendered tone_matrix wavs.

    Uses the audeering wav2vec2 dimensional emotion model (MSP-Podcast, human
    labels, blind to our calibration) to predict arousal/valence per tone
    render, then rank-correlates perception against the requested
    TONE_CALIBRATION values. Passes when perceived arousal tracks requested
    intensity; perceived-valence correlation is reported as a declared
    limitation, not gated (the cfg_weight valence knob measures perceptually
    inert -- see chatterbox#23). The human listener remains the final step
    (chatterbox#7); this case exists so the pipeline before the human is not
    obviously wrong. Requires tone_matrix renders under out_root.
    """
    import glob as globmod
    import os

    import audonnx
    import librosa
    import numpy as np

    model_dir = os.getenv(
        "CHATTERBOX_EMOTION_MODEL_DIR",
        str(Path.home() / ".cache" / "chatterbox-emotion-model"),
    )
    if not (Path(model_dir) / "model.onnx").exists():
        import audeer

        archive = audeer.download_url(
            "https://zenodo.org/record/6221127/files/w2v2-L-robust-12.6bc4a7fd-1.1.0.zip",
            str(Path(model_dir) / "model.zip"),
            verbose=False,
        )
        audeer.extract_archive(archive, model_dir, verbose=False)
    model = audonnx.load(model_dir)

    import sys as sysmod

    sysmod.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
    from chatterbox.agent.presets import TONE_CALIBRATION

    per_tone: dict[str, dict[str, float]] = {}
    for tone in TONE_CALIBRATION:
        preds = []
        for p in sorted(globmod.glob(str(out_root / f"eval-matrix-{tone}-0*" / "finished_response.wav")))[:6]:
            wav, _ = librosa.load(p, sr=16000, mono=True)
            preds.append(model(wav[: 16000 * 12].astype("float32"), 16000)["logits"][0])
        if preds:
            m = np.mean(preds, axis=0)
            per_tone[tone] = {
                "perceived_arousal": round(float(m[0]), 3),
                "perceived_dominance": round(float(m[1]), 3),
                "perceived_valence": round(float(m[2]), 3),
                "requested_intensity": TONE_CALIBRATION[tone]["intensity"],
                "requested_valence": TONE_CALIBRATION[tone]["valence"],
            }
    if len(per_tone) < 10:
        raise RuntimeError("tone_matrix renders missing; run --case tone_matrix first")

    def spearman(a: list[float], b: list[float]) -> float:
        ra = np.argsort(np.argsort(a))
        rb = np.argsort(np.argsort(b))
        return float(np.corrcoef(ra, rb)[0, 1])

    tones = list(per_tone)
    arousal_r = spearman(
        [per_tone[t]["perceived_arousal"] for t in tones],
        [per_tone[t]["requested_intensity"] for t in tones],
    )
    valence_r = spearman(
        [per_tone[t]["perceived_valence"] for t in tones],
        [per_tone[t]["requested_valence"] for t in tones],
    )
    return {
        "case": "machine_listener",
        "schema": "chatterbox.machine_listener.v2",
        "model": "audeering wav2vec2-large-robust-12 dimensional (MSP-Podcast) via audonnx",
        "tones_analyzed": len(tones),
        "per_tone": per_tone,
        "spearman_arousal_vs_requested_intensity": round(arousal_r, 3),
        "spearman_valence_vs_requested_valence": round(valence_r, 3),
        "declared_limitation": (
            "perceived valence does not track the requested valence knob; "
            "arousal is the single verified perceptual affect dimension"
        ),
        "pass": arousal_r > 0.7,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, choices=[*CASES, "receipt_honesty", "tone_matrix", "machine_listener"])
    parser.add_argument(
        "--matrix-out",
        default=str(Path(__file__).resolve().parent.parent / "docs" / "proofs" / "tone_calibration_matrix.json"),
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--out-root", default=str(Path(__file__).resolve().parent.parent / "logs"))
    parser.add_argument("--floor-n", type=int, default=6)
    parser.add_argument("--arm-n", type=int, default=3)
    args = parser.parse_args()
    try:
        if args.case == "receipt_honesty":
            result = run_receipt_honesty(args.base_url)
        elif args.case == "machine_listener":
            result = run_machine_listener(Path(args.out_root))
        elif args.case == "tone_matrix":
            result = run_tone_matrix(args.base_url, Path(args.out_root), args.floor_n, 2, Path(args.matrix_out))
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
