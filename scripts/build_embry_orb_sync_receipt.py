#!/usr/bin/env python3
"""Build an orb-sync linkage receipt from a direct Chatterbox orb proof."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_SOURCE_PROOF = Path("/tmp/embry-orb-direct-speak-proof.json")
DEFAULT_SCREENSHOT = Path("/tmp/embry-orb-direct-speak-proof.png")
DEFAULT_OUT_DIR = Path("/tmp/chatterbox-fork-agent-out/orb-sync-current/orb-direct-speak")


def sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def build_receipt(source_proof_path: Path, screenshot_path: Path) -> dict[str, Any]:
    source = read_json(source_proof_path)
    result = source["result"]
    authority = result["audioAuthority"]
    artifact_id = str(authority["artifactId"])
    samples = source.get("samples") or []
    bound_samples = [sample for sample in samples if str(sample.get("orbSpeechBound")).lower() == "true"]
    nonzero_samples = [sample for sample in samples if _float(sample.get("orbAudioLevel")) > 0]
    envelope = authority.get("envelope") or {}
    envelope_frames = envelope.get("frames") or []
    screenshot_exists = screenshot_path.exists()
    audio_path = Path(str(authority["path"]))
    playback = authority.get("localPlayback") or {}

    receipt = {
        "schema": "chatterbox.embry_orb_sync_receipt.v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mocked": False,
        "live": True,
        "ok": True,
        "proof_scope": "direct_chatterbox_speech_orb_envelope_binding",
        "source_proof": {
            "path": str(source_proof_path),
            "sha256": sha256_file(source_proof_path),
        },
        "turn_id": artifact_id,
        "audio_artifact_id": artifact_id,
        "audio_artifact": {
            "id": artifact_id,
            "path": str(audio_path),
            "url": authority.get("url"),
            "sha256": authority.get("sha256") or (sha256_file(audio_path) if audio_path.exists() else None),
            "duration_ms": authority.get("durationMs"),
        },
        "playback": {
            "audio_artifact_id": artifact_id,
            "started_at_epoch_ms": playback.get("startedAtEpochMs") or result.get("startedAtMs"),
            "driver": playback.get("driver"),
            "command": playback.get("command"),
            "target": playback.get("target"),
            "pid": playback.get("pid"),
        },
        "orb": {
            "authority": "server-envelope",
            "envelope_frame_count": len(envelope_frames),
            "max_level": source.get("maxLevel"),
            "bound_sample_count": len(bound_samples),
            "nonzero_audio_sample_count": len(nonzero_samples),
            "sample_count": len(samples),
            "unique_states": sorted(set(str(sample.get("orbState")) for sample in samples if sample.get("orbState"))),
        },
        "screenshot": {
            "path": str(screenshot_path),
            "exists": screenshot_exists,
            "sha256": sha256_file(screenshot_path) if screenshot_exists else None,
        },
        "claims": {
            "proves": [
                "direct_chatterbox_audio_artifact_bound_to_orb_server_envelope",
                "orb_samples_include_bound_nonzero_audio_levels",
            ],
            "does_not_prove": [
                "RealtimeSTT ingress",
                "speaker identity correctness",
                "memory/Tau routing",
                "browser shared Chat UX session replay",
                "human subjective orb quality",
            ],
        },
    }
    failed_gates: list[str] = []
    if not screenshot_exists:
        failed_gates.append("screenshot_file_exists")
    if not audio_path.exists():
        failed_gates.append("audio_artifact_file_exists")
    if not receipt["playback"]["started_at_epoch_ms"]:
        failed_gates.append("playback_started_at_epoch_ms_present")
    if len(envelope_frames) <= 0:
        failed_gates.append("orb_envelope_frames_present")
    if _float(receipt["orb"]["max_level"]) <= 0:
        failed_gates.append("orb_max_level_positive")
    if len(nonzero_samples) <= 0:
        failed_gates.append("orb_nonzero_audio_samples_present")
    if len(bound_samples) <= 0:
        failed_gates.append("orb_bound_samples_present")
    receipt["failed_gates"] = failed_gates
    receipt["ok"] = not failed_gates
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-proof", type=Path, default=DEFAULT_SOURCE_PROOF)
    parser.add_argument("--screenshot", type=Path, default=DEFAULT_SCREENSHOT)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    receipt = build_receipt(args.source_proof, args.screenshot)
    out = args.out or args.out_dir / "orb-sync-receipt.json"
    out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(out)
    return 0 if receipt["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
