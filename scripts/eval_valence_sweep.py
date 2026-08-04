"""Issue #23 sweep: does ANY generation knob move perceived valence?

Renders fixed text on chatterbox_base via /synthesize-emotion (raw knob
control, no derived-knob clamps), interleaved with same-parameter floor
renders, then scores every wav with the audeering dimensional emotion model.
For each knob axis it reports the perceived-valence range across the sweep vs
the same-parameter perceived-valence spread, plus Spearman rank correlation.

Verdict per axis: 'moves_valence' only when the sweep range exceeds the floor
spread AND |spearman| >= 0.6. Exit 0 always on completed measurement (the
receipt is the deliverable); exit 2 on infrastructure error.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

import audonnx
import librosa
import numpy as np

BASE = "http://localhost:8018"
TEXT = (
    "I need you to hear the difference in my voice, not just read it in the receipt. "
    "This sentence is long enough to measure pitch, energy, and rate."
)
OUT_ROOT = Path(__file__).resolve().parent.parent / "logs"
MODEL_DIR = str(Path.home() / ".cache" / "chatterbox-emotion-model")

DEFAULTS = {"exaggeration": 0.7, "cfg_weight": 0.5, "temperature": 0.7}
AXES = {
    "cfg_weight": [0.1, 0.3, 0.5, 0.7, 0.9],
    "temperature": [0.5, 0.7, 0.9, 1.1],
    "exaggeration": [0.3, 0.5, 0.7, 0.9, 1.1],
}
FLOOR_N = 4
PER_POINT = 2


def render(label: str, params: dict) -> Path:
    body = {"text": TEXT, "label": label, **params}
    req = urllib.request.Request(
        f"{BASE}/synthesize-emotion",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=900) as resp:
        receipt = json.load(resp)
    if not receipt.get("ok"):
        raise RuntimeError(f"{label}: {receipt.get('error')}")
    return Path(str(receipt["audio"]).replace("/out/", str(OUT_ROOT) + "/"))


def main() -> int:
    model = audonnx.load(MODEL_DIR)

    def score(path: Path) -> dict[str, float]:
        wav, _ = librosa.load(str(path), sr=16000, mono=True)
        a, d, v = model(wav[: 16000 * 12].astype("float32"), 16000)["logits"][0]
        return {"arousal": round(float(a), 3), "valence": round(float(v), 3)}

    # Interleave: one floor render between sweep points so drift lands in floor.
    schedule: list[tuple[str, dict]] = []
    points: list[tuple[str, float, int]] = [
        (axis, value, rep)
        for axis, values in AXES.items()
        for value in values
        for rep in range(1, PER_POINT + 1)
    ]
    floor_every = max(1, len(points) // FLOOR_N)
    floor_i = 0
    for idx, (axis, value, rep) in enumerate(points):
        if idx % floor_every == 0 and floor_i < FLOOR_N:
            floor_i += 1
            schedule.append((f"v23-floor-{floor_i:02d}", dict(DEFAULTS)))
        schedule.append((f"v23-{axis}-{value}-{rep}", {**DEFAULTS, axis: value}))
    while floor_i < FLOOR_N:
        floor_i += 1
        schedule.append((f"v23-floor-{floor_i:02d}", dict(DEFAULTS)))

    scores: dict[str, dict[str, float]] = {}
    for label, params in schedule:
        scores[label] = score(render(label, params))
        print(f"rendered {label}: {scores[label]}", file=sys.stderr)

    floor_vals = [scores[f"v23-floor-{i:02d}"]["valence"] for i in range(1, FLOOR_N + 1)]
    floor_spread = round(max(floor_vals) - min(floor_vals), 4)

    def spearman(a: list[float], b: list[float]) -> float:
        ra = np.argsort(np.argsort(a))
        rb = np.argsort(np.argsort(b))
        return float(np.corrcoef(ra, rb)[0, 1])

    axes_report = {}
    for axis, values in AXES.items():
        means = {
            value: round(
                float(np.mean([scores[f"v23-{axis}-{value}-{r}"]["valence"] for r in range(1, PER_POINT + 1)])), 4
            )
            for value in values
        }
        sweep_range = round(max(means.values()) - min(means.values()), 4)
        rho = round(spearman(list(means.keys()), list(means.values())), 3)
        axes_report[axis] = {
            "valence_by_value": means,
            "sweep_range": sweep_range,
            "floor_spread": floor_spread,
            "spearman": rho,
            "verdict": "moves_valence" if sweep_range > floor_spread and abs(rho) >= 0.6 else "inert_for_valence",
        }

    result = {
        "schema": "chatterbox.valence_sweep.v1",
        "engine": "chatterbox_base via /synthesize-emotion (raw knobs, no clamps)",
        "scorer": "audeering wav2vec2 dimensional (MSP-Podcast) via audonnx",
        "floor": {"n": FLOOR_N, "perceived_valence_values": floor_vals, "spread": floor_spread},
        "axes": axes_report,
        "raw_scores": scores,
        "any_axis_moves_valence": any(a["verdict"] == "moves_valence" for a in axes_report.values()),
    }
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
