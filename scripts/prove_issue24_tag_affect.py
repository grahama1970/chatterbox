#!/usr/bin/env python3
"""Live proof for chatterbox#24: calibrated tone and native paralinguistic tags
on one render.

Renders through the real agent server, transcribes with Whisper small.en, and
writes a receipt. Nothing here is mocked; every claim in the receipt comes from
a render that actually happened.

Usage:
    python3 scripts/prove_issue24_tag_affect.py --base-url http://127.0.0.1:8018
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import tempfile
import urllib.request
import wave
from pathlib import Path
from typing import Any

TAGGED = "That is genuinely funny. [laugh] Anyway, let me get back to what I was saying."
UNTAGGED = "That is genuinely funny. Anyway, let me get back to what I was saying."
LITERAL_WORD = "laugh"


def post(base_url: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        base_url + path,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=600) as response:
        return json.load(response)


def render(base_url: str, label: str, text: str, voice_delivery: dict[str, Any]) -> dict[str, Any]:
    return post(
        base_url,
        "/synthesize-batch",
        {"label": label, "answer_text": text, "voice_delivery": voice_delivery},
    )


def host_path(container_path: str, out_root: Path) -> Path:
    return out_root / Path(container_path).relative_to("/out")


def duration_seconds(path: Path) -> float:
    with wave.open(str(path)) as handle:
        return round(handle.getnframes() / handle.getframerate(), 3)


def transcribe(path: Path) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            [
                "whisper", str(path),
                "--model", "small.en",
                "--device", "cpu",
                "--output_format", "txt",
                "--output_dir", tmp,
            ],
            check=True,
            capture_output=True,
        )
        return (Path(tmp) / f"{path.stem}.txt").read_text().strip()


def rank_sum_test(treatment: list[float], control: list[float]) -> dict[str, Any]:
    """One-sided Mann-Whitney rank-sum test that treatment > control.

    The renderer is explicitly non-deterministic (stochasticity receipt:
    deterministic_audio=false, seed_supported=false), so a strict
    min(treatment) > max(control) criterion on a handful of samples tests
    sample spread rather than the effect -- at n=3 per arm the smallest
    reachable p-value is 0.05, so that criterion cannot clear a 0.01 bar at all.

    Enumerates the exact permutation distribution of the rank sum when that is
    tractable, and falls back to the tie-corrected normal approximation above
    200k combinations. No third-party dependency either way.
    """
    from collections import Counter
    from itertools import combinations

    pooled = sorted(treatment + control)
    ranks: dict[float, float] = {}
    for value in set(pooled):
        positions = [index + 1 for index, item in enumerate(pooled) if item == value]
        ranks[value] = sum(positions) / len(positions)  # average rank breaks ties

    all_ranks = [ranks[value] for value in treatment + control]
    observed = sum(ranks[value] for value in treatment)
    n_treatment, n_control = len(treatment), len(control)
    total = n_treatment + n_control

    if math.comb(total, n_treatment) <= 200_000:
        distribution = [sum(subset) for subset in combinations(all_ranks, n_treatment)]
        at_least_as_extreme = sum(1 for value in distribution if value >= observed)
        method = "exact_one_sided_permutation_rank_sum"
        p_value = at_least_as_extreme / len(distribution)
    else:
        # Exact enumeration is not tractable at this n; use the tie-corrected
        # normal approximation to the rank-sum distribution.
        mean = n_treatment * (total + 1) / 2
        tie_term = sum(count**3 - count for count in Counter(pooled).values())
        variance = (n_treatment * n_control / 12) * (
            (total + 1) - tie_term / (total * (total - 1))
        )
        z = (observed - mean - 0.5) / math.sqrt(variance)  # continuity-corrected
        p_value = 0.5 * math.erfc(z / math.sqrt(2))
        method = "normal_approximation_rank_sum_tie_corrected"

    pairs = [(t, c) for t in treatment for c in control]
    dominance = sum(1.0 if t > c else 0.5 if t == c else 0.0 for t, c in pairs) / len(pairs)
    return {
        "test": method,
        "n_treatment": n_treatment,
        "n_control": n_control,
        "rank_sum": round(observed, 2),
        "p_value": round(p_value, 6),
        "common_language_effect_size": round(dominance, 3),
    }


def first_chunk(result: dict[str, Any]) -> str:
    for segment in result.get("segments") or result.get("chunks") or []:
        if segment.get("audio"):
            return segment["audio"]
    raise SystemExit(f"no chunk audio in response: {json.dumps(result)[:400]}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8018")
    parser.add_argument("--out-root", default="logs", help="host path mounted as /out")
    parser.add_argument("--repeats", type=int, default=16, help="renders per arm for the duration test")
    parser.add_argument("--output", default="docs/proofs/issue24_tag_affect.json")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Required. This script only renders against a real server; there is no mock mode.",
    )
    args = parser.parse_args()
    if not args.live:
        parser.error("pass --live: this proof renders against a real server and has no mock mode")

    health = json.load(urllib.request.urlopen(args.base_url + "/health", timeout=30))
    if not health.get("model_loaded") or health.get("mocked"):
        raise SystemExit(f"server is not live with a loaded model: {health}")

    out_root = Path(args.out_root).resolve()
    tone = "playful_light"
    audible = {"tone": tone, "emotion_realization": "audible"}
    cases: dict[str, dict[str, Any]] = {}

    # The closure case: calibrated tone AND a consumed tag on one render.
    for name, text, delivery in [
        ("both_tone_and_tag", TAGGED, audible),
        ("tag_realization_literal_optout", TAGGED, {**audible, "tag_realization": "literal"}),
        ("explicit_knobs_conflict", TAGGED, {"tone": tone, "intensity": 0.9, "valence": -0.8}),
    ]:
        result = render(args.base_url, f"issue24_{name}", text, delivery)
        chunk = (result.get("segments") or result.get("chunks"))[0]
        wav = host_path(first_chunk(result), out_root)
        transcript = transcribe(wav)
        tag_handling = result.get("tag_handling") or {}
        cases[name] = {
            "request_voice_delivery": delivery,
            "backend": (result.get("backend") or {}).get("id"),
            "engine": result.get("engine"),
            "tag_handling": tag_handling,
            "pace_effect": chunk.get("pace_effect"),
            "affect_effect": chunk.get("affect_effect"),
            "transcript": transcript,
            "literal_tag_word_present": LITERAL_WORD in transcript.lower(),
            "audio": str(wav),
            "duration_seconds": duration_seconds(wav),
        }

    # The tag must be a real acoustic event, not silently stripped.
    durations: dict[str, list[float]] = {"with_tag": [], "without_tag": []}
    for index in range(args.repeats):
        for key, text in (("with_tag", TAGGED), ("without_tag", UNTAGGED)):
            result = render(args.base_url, f"issue24_dur_{key}_{index}", text, audible)
            durations[key].append(duration_seconds(host_path(first_chunk(result), out_root)))

    with_tag, without_tag = durations["with_tag"], durations["without_tag"]
    tag_event_test = rank_sum_test(with_tag, without_tag)
    both = cases["both_tone_and_tag"]
    both_pace = both["pace_effect"] or {}
    both_affect = both["affect_effect"] or {}
    receipt = {
        "schema": "chatterbox.issue24_tag_affect_proof.v1",
        "issue": "grahama1970/chatterbox#24",
        "text_tagged": TAGGED,
        "text_untagged": UNTAGGED,
        "tone": tone,
        "cases": cases,
        "duration_check": {
            "with_tag_seconds": with_tag,
            "without_tag_seconds": without_tag,
            "mean_delta_seconds": round(sum(with_tag) / len(with_tag) - sum(without_tag) / len(without_tag), 3),
            "ranges_non_overlapping": min(with_tag) > max(without_tag),
            "significance": tag_event_test,
            "criterion": (
                "p_value < 0.01 and a positive mean delta. The ticket's original n=3 "
                "min>max criterion is reported as ranges_non_overlapping but is not "
                "gated: the renderer is non-deterministic by its own stochasticity "
                "receipt, so strict non-overlap of small samples tests sample spread "
                "rather than the effect."
            ),
        },
        "gates": {
            "both_render_uses_tag_consuming_backend": both["backend"] == "chatterbox_turbo",
            "both_render_reports_tags_interpreted": both["tag_handling"].get("tags_interpreted") is True,
            "both_render_applied_the_tag": both["tag_handling"].get("applied_tags") == ["[laugh]"],
            "both_render_has_no_literal_tag_word": not both["literal_tag_word_present"],
            # The tone half of "both": calibration must actually reach the audio.
            "both_render_applied_tone_calibration": (
                both_pace.get("applied") is True and both_pace.get("tempo_source") == "tone_calibration"
            ),
            "both_render_affect_receipt_names_the_tradeoff": (
                both_affect.get("knob_source") == "tone_calibration_deferred_to_tag_realization"
                and both_affect.get("applied") is False
            ),
            "optout_reports_tags_not_interpreted": (
                cases["tag_realization_literal_optout"]["tag_handling"].get("tags_interpreted") is False
            ),
            "optout_receipt_matches_literal_audio": (
                cases["tag_realization_literal_optout"]["literal_tag_word_present"] is True
            ),
            "explicit_knobs_declare_conflict": (
                "unsatisfiable"
                in (cases["explicit_knobs_conflict"]["tag_handling"].get("tags_interpreted_reason") or "")
            ),
            "tag_is_a_real_event": (
                tag_event_test["p_value"] < 0.01
                and sum(with_tag) / len(with_tag) > sum(without_tag) / len(without_tag)
            ),
        },
    }
    receipt["ok"] = all(receipt["gates"].values())

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt["gates"], indent=2))
    print(f"ok={receipt['ok']} receipt={output}")
    return 0 if receipt["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
