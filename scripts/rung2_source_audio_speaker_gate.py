#!/usr/bin/env python3
"""Focused Rung 2 proof for source-audio Horus speaker gating.

This runner does not use browser audio, Tau, memory, Chatterbox generation,
Chat UX, orb sync, replay, or interruption. It checks only whether the current
local speaker-segment evidence can accept an independent Horus sample while
failing closed on non-Horus audio.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.embry_proof_context import add_proof_context_arguments, append_event
from scripts.embry_proof_context import apply_proof_context, proof_context_from_args
from scripts.smoke_speaker_segment_evidence import run as run_segment_evidence
from scripts.smoke_speaker_segment_evidence import sha256_file, wav_metrics


DEFAULT_HORUS_AUDIO = Path(
    "/home/graham/workspace/experiments/agent-skills/receipts/"
    "voice_agent_bakeoff/agent_voice_refs/horus_v2_agent_ref_6s.wav"
)
DEFAULT_EMBRY_AUDIO = Path(
    "/home/graham/workspace/experiments/chatterbox/persona_dream_voice_refs/"
    "embry_authorized_ref_30s_8s.wav"
)
DEFAULT_GENERIC_CAPTURE = Path(
    "/tmp/embry-live-e2e/rung1-20260708T105423Z-hello-alpha7781-pw-fixed/captured.wav"
)
DEFAULT_HORUS_ENROLLMENT = Path(
    "/home/graham/workspace/experiments/agent-skills-loop2-shared/skills/"
    "persona-dream/voice_clone_candidates/horus_kling_clone_candidate.wav"
)
DEFAULT_EMBRY_ENROLLMENT = Path(
    "/home/graham/workspace/experiments/agent-skills-loop2-shared/skills/"
    "persona-dream/voice_clone_candidates/embry_kling_clone_candidate.wav"
)
DEFAULT_OUT_ROOT = Path("/tmp/embry-live-e2e")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def default_run_id() -> str:
    return "rung2-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def case_accepts_horus(case_receipt: dict[str, Any], min_primary_ratio: float) -> bool:
    summary = case_receipt.get("summary") or {}
    return bool(case_receipt.get("ok")) and float(summary.get("horus_ratio") or 0.0) >= min_primary_ratio


def case_has_dependency_error(case_receipt: dict[str, Any]) -> bool:
    failed = set(case_receipt.get("failed_gates") or [])
    return "speaker_segment_dependencies_available" in failed


def build_segment_args(
    *,
    audio: Path,
    out: Path,
    args: argparse.Namespace,
) -> argparse.Namespace:
    return argparse.Namespace(
        audio=audio,
        out=out,
        horus_enrollment=args.horus_enrollment,
        embry_enrollment=args.embry_enrollment,
        window_s=args.window_s,
        hop_s=args.hop_s,
        min_window_rms=args.min_window_rms,
        min_primary_margin=args.min_primary_margin,
        min_primary_ratio=args.min_primary_ratio,
        min_voiced_segments=args.min_voiced_segments,
    )


def run_case(
    *,
    name: str,
    role: str,
    audio: Path,
    expected: str,
    out_dir: Path,
    args: argparse.Namespace,
) -> dict[str, Any]:
    out_path = out_dir / f"{name}.speaker_segment_receipt.json"
    started = time.perf_counter()
    receipt = run_segment_evidence(build_segment_args(audio=audio, out=out_path, args=args))
    out_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    accepts_horus = case_accepts_horus(receipt, args.min_primary_ratio)
    if expected == "accept_horus":
        case_ok = accepts_horus
        failed_gate = None if case_ok else "expected_horus_was_not_accepted"
    elif expected == "reject_horus":
        case_ok = not accepts_horus
        failed_gate = None if case_ok else "non_horus_audio_was_accepted_as_horus"
    else:
        raise ValueError(f"unsupported expected case: {expected}")
    return {
        "name": name,
        "role": role,
        "expected": expected,
        "ok": case_ok,
        "accepts_horus": accepts_horus,
        "failed_gate": failed_gate,
        "audio": wav_metrics(audio) if audio.exists() else {"path": str(audio), "exists": False},
        "receipt_path": str(out_path),
        "summary": receipt.get("summary") or {},
        "failed_gates": receipt.get("failed_gates") or [],
        "dependency_error": case_has_dependency_error(receipt),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    started = time.perf_counter()
    run_id = args.run_id or default_run_id()
    out_dir = (args.out_root / run_id).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    proof_context = proof_context_from_args(args, component="rung2_source_audio_speaker_gate", default_case_id="rung2_source_audio_speaker_gate")
    failed_gates: list[str] = []
    cases: list[dict[str, Any]] = []
    append_event(proof_context, "rung2_source_audio_speaker_gate.started", payload={"run_id": run_id})

    receipt: dict[str, Any] = {
        "schema": "embry.rung2_source_audio_speaker_gate.v1",
        "proof_rung": "02_source_audio_horus_speaker_gate",
        "run_id": run_id,
        "ok": False,
        "mocked": False,
        "live": False,
        "started_at_utc": utc_now(),
        "out_dir": str(out_dir),
        "inputs": {
            "horus_audio": str(args.horus_audio.resolve()),
            "embry_audio": str(args.embry_audio.resolve()),
            "generic_non_horus_audio": str(args.generic_non_horus_audio.resolve()),
            "horus_enrollment": str(args.horus_enrollment.resolve()),
            "embry_enrollment": str(args.embry_enrollment.resolve()),
            "min_primary_margin": args.min_primary_margin,
            "min_primary_ratio": args.min_primary_ratio,
        },
        "artifacts": {},
        "cases": cases,
        "failed_gates": failed_gates,
        "acceptance": {},
        "claims": {
            "proves": [],
            "does_not_prove": [
                "pyannote_diarization",
                "overlapping_speaker_separation",
                "browser_mic_or_webrtc_capture",
                "physical_room_microphone_capture",
                "memory_or_tau_routing",
                "chatterbox_generation_from_live_stt",
                "chat_ux_sync",
                "orb_sync",
                "replay",
                "interruption",
            ],
        },
    }

    required_paths = {
        "horus_audio": args.horus_audio,
        "embry_audio": args.embry_audio,
        "generic_non_horus_audio": args.generic_non_horus_audio,
        "horus_enrollment": args.horus_enrollment,
        "embry_enrollment": args.embry_enrollment,
    }
    for key, path in required_paths.items():
        if not path.exists():
            failed_gates.append(f"{key}_exists")

    if not failed_gates:
        receipt["artifacts"] = {key: wav_metrics(path) for key, path in required_paths.items()}
        hashes = {key: sha256_file(path) for key, path in required_paths.items()}
        if hashes["horus_audio"] == hashes["horus_enrollment"]:
            failed_gates.append("horus_candidate_independent_from_enrollment")
        if hashes["embry_audio"] == hashes["embry_enrollment"]:
            failed_gates.append("embry_candidate_independent_from_enrollment")
        if hashes["generic_non_horus_audio"] in {hashes["horus_enrollment"], hashes["embry_enrollment"]}:
            failed_gates.append("generic_negative_independent_from_enrollments")

    if not failed_gates:
        cases.extend(
            [
                run_case(
                    name="positive_horus",
                    role="horus_candidate",
                    audio=args.horus_audio,
                    expected="accept_horus",
                    out_dir=out_dir,
                    args=args,
                ),
                run_case(
                    name="negative_embry",
                    role="embry_candidate",
                    audio=args.embry_audio,
                    expected="reject_horus",
                    out_dir=out_dir,
                    args=args,
                ),
                run_case(
                    name="negative_generic_non_horus",
                    role="generic_non_horus_capture",
                    audio=args.generic_non_horus_audio,
                    expected="reject_horus",
                    out_dir=out_dir,
                    args=args,
                ),
            ]
        )
        for case in cases:
            if case["dependency_error"]:
                failed_gates.append("speaker_segment_dependencies_available")
            if not case["ok"] and case["failed_gate"]:
                failed_gates.append(f"{case['name']}:{case['failed_gate']}")

    acceptance = {
        "horus_candidate_accepted": any(
            case["name"] == "positive_horus" and case["accepts_horus"] for case in cases
        ),
        "embry_candidate_rejected": any(
            case["name"] == "negative_embry" and not case["accepts_horus"] for case in cases
        ),
        "generic_non_horus_rejected": any(
            case["name"] == "negative_generic_non_horus" and not case["accepts_horus"] for case in cases
        ),
        "source_audio_identity_proven": False,
        "used_ui": False,
        "used_mock_transcript": False,
        "used_typed_prompt": False,
    }
    acceptance["source_audio_identity_proven"] = (
        acceptance["horus_candidate_accepted"]
        and acceptance["embry_candidate_rejected"]
        and acceptance["generic_non_horus_rejected"]
    )
    receipt["acceptance"] = acceptance
    receipt["ok"] = not failed_gates and acceptance["source_audio_identity_proven"]
    receipt["live"] = bool(cases) and not any(case["dependency_error"] for case in cases)
    if receipt["ok"]:
        receipt["claims"]["proves"] = [
            "independent_horus_audio_is_accepted_by_current_speaker_gate",
            "embry_audio_is_rejected_as_non_horus",
            "generic_non_horus_audio_is_rejected_as_non_horus",
        ]
    receipt["failed_gates"] = failed_gates
    receipt["ended_at_utc"] = utc_now()
    receipt["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
    receipt_path = out_dir / "rung2_source_audio_speaker_gate_receipt.json"
    receipt["receipt_path"] = str(receipt_path)
    append_event(
        proof_context,
        "rung2_source_audio_speaker_gate.ended",
        payload={"ok": receipt["ok"], "failed_gates": failed_gates},
        artifacts=[{"path": str(receipt_path), "role": "receipt"}],
    )
    apply_proof_context(
        receipt,
        proof_context,
        proof_scope=["native_child_turn_context"],
        does_not_prove=receipt["claims"]["does_not_prove"],
    )
    if proof_context.event_journal is not None:
        receipt["event_journal_sha256"] = sha256_file(proof_context.event_journal)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id")
    parser.add_argument("--out-root", default=DEFAULT_OUT_ROOT, type=Path)
    parser.add_argument("--horus-audio", default=DEFAULT_HORUS_AUDIO, type=Path)
    parser.add_argument("--embry-audio", default=DEFAULT_EMBRY_AUDIO, type=Path)
    parser.add_argument("--generic-non-horus-audio", default=DEFAULT_GENERIC_CAPTURE, type=Path)
    parser.add_argument("--horus-enrollment", default=DEFAULT_HORUS_ENROLLMENT, type=Path)
    parser.add_argument("--embry-enrollment", default=DEFAULT_EMBRY_ENROLLMENT, type=Path)
    parser.add_argument("--window-s", default=2.4, type=float)
    parser.add_argument("--hop-s", default=1.2, type=float)
    parser.add_argument("--min-window-rms", default=0.003, type=float)
    parser.add_argument("--min-primary-margin", default=0.12, type=float)
    parser.add_argument("--min-primary-ratio", default=0.5, type=float)
    parser.add_argument("--min-voiced-segments", default=1, type=int)
    add_proof_context_arguments(parser)
    args = parser.parse_args()
    receipt = run(args)
    print(
        json.dumps(
            {
                "ok": receipt["ok"],
                "live": receipt["live"],
                "mocked": receipt["mocked"],
                "failed_gates": receipt["failed_gates"],
                "receipt_path": receipt["receipt_path"],
            },
            sort_keys=True,
        )
    )
    return 0 if receipt["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
