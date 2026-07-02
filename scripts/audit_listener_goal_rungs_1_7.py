#!/usr/bin/env python3
"""Audit live receipt evidence for Chatterbox listener goal rungs 1-7."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_RECEIPTS = {
    "full_live": "/tmp/chatterbox-fork-agent-out/full-live-sanity-20260702T140317Z-creation-hook/full-live-sanity.json",
    "rung7_combined": "/tmp/chatterbox-fork-agent-out/rung7-horus-factory-stress-youtube-20260702T192914Z/rung7-combined.json",
    "realtimestt_vad": "/tmp/chatterbox-fork-agent-out/rung7-horus-factory-stress-youtube-20260702T192914Z/realtimestt-listener-bridge-vad-realtime-30s.json",
    "primary_speaker_gate": "/tmp/chatterbox-fork-agent-out/primary-speaker-gate-20260702T150040Z/suite-summary.json",
    "unknown_speaker": "/tmp/chatterbox-speaker-memory-rungs-20260702T1722Z/rung1_unknown_factory_identity.json",
    "known_speaker_recall": "/tmp/chatterbox-speaker-memory-rungs-20260702T1800Z/rung5_known_horus_post_writeback_recall.json",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def require(condition: bool, failed: list[str], gate: str) -> None:
    if not condition:
        failed.append(gate)


def receipt_ok(receipt: dict[str, Any]) -> bool:
    return receipt.get("ok") is True and receipt.get("live") is True and receipt.get("mocked") is False and not receipt.get("failed_gates")


def child_by_name(receipt: dict[str, Any], name: str) -> dict[str, Any] | None:
    for child in receipt.get("children") or []:
        if child.get("name") == name:
            return child
    return None


def child_receipt_path(receipt: dict[str, Any], name: str) -> Path | None:
    child = child_by_name(receipt, name)
    if not child:
        return None
    path = child.get("receipt_path") or child.get("out")
    return Path(path) if path else None


def audit(args: argparse.Namespace) -> dict[str, Any]:
    receipt_paths = {
        key: Path(getattr(args, key) or value)
        for key, value in DEFAULT_RECEIPTS.items()
    }
    loaded: dict[str, dict[str, Any]] = {}
    failed_gates: list[str] = []
    for key, path in receipt_paths.items():
        require(path.exists(), failed_gates, f"{key}_receipt_exists")
        if path.exists():
            try:
                loaded[key] = load_json(path)
            except Exception as exc:  # noqa: BLE001 - preserve receipt read failure in audit output
                failed_gates.append(f"{key}_receipt_json_readable")
                loaded[key] = {"error_type": type(exc).__name__, "error": str(exc)}

    full = loaded.get("full_live", {})
    rung7 = loaded.get("rung7_combined", {})
    rstt = loaded.get("realtimestt_vad", {})
    gate = loaded.get("primary_speaker_gate", {})
    unknown = loaded.get("unknown_speaker", {})
    known = loaded.get("known_speaker_recall", {})

    stream_cancel_path = child_receipt_path(full, "stream_cancel")
    turn_controls_path = child_receipt_path(full, "turn_controls")
    tau_voice_path = child_receipt_path(full, "tau_voice_render")
    listener_qra_path = child_receipt_path(full, "listener_memory_tau_qra")
    child_receipts: dict[str, dict[str, Any]] = {}
    for key, path in {
        "stream_cancel": stream_cancel_path,
        "turn_controls": turn_controls_path,
        "tau_voice_render": tau_voice_path,
        "listener_memory_tau_qra": listener_qra_path,
    }.items():
        require(path is not None and path.exists(), failed_gates, f"{key}_child_receipt_exists")
        if path is not None and path.exists():
            child_receipts[key] = load_json(path)

    stream_cancel = child_receipts.get("stream_cancel", {})
    turn_controls = child_receipts.get("turn_controls", {})
    tau_voice = child_receipts.get("tau_voice_render", {})
    listener_qra = child_receipts.get("listener_memory_tau_qra", {})

    requirements: list[dict[str, Any]] = []

    def add_requirement(rung: int, name: str, gates: list[str], evidence: dict[str, Any], proves: list[str], does_not_prove: list[str]) -> None:
        requirements.append(
            {
                "rung": rung,
                "name": name,
                "ok": not gates,
                "failed_gates": gates,
                "evidence": evidence,
                "proves": proves,
                "does_not_prove": does_not_prove,
            }
        )
        failed_gates.extend(f"rung{rung}_{gate_name}" for gate_name in gates)

    gates: list[str] = []
    require(rung7.get("schema") == "chatterbox.conversation_ladder.rung7.listener_contract.v1", gates, "listener_schema")
    require(receipt_ok(rung7), gates, "combined_receipt_ok_live_unmocked")
    require(len(rung7.get("listener_events") or []) > 0, gates, "listener_events_present")
    require(len(rung7.get("heard_text_ledger") or []) > 0, gates, "heard_text_ledger_present")
    add_requirement(
        1,
        "listener contract and JSON event schema",
        gates,
        {"receipt": str(receipt_paths["rung7_combined"]), "listener_event_count": len(rung7.get("listener_events") or [])},
        ["Rung 7 listener contract emits auditable JSON events and heard-text ledger entries."],
        ["Does not prove physical microphone capture."],
    )

    events = [event.get("type") for event in rstt.get("events") or []]
    gates = []
    require(receipt_ok(rstt), gates, "realtimestt_receipt_ok_live_unmocked")
    require(rstt.get("schema") == "chatterbox.realtimestt.listener_bridge.v1", gates, "realtimestt_schema")
    require((rstt.get("services") or {}).get("realtimestt", {}).get("endpointing_mode") == "vad_wait_audio", gates, "automatic_vad_endpointing")
    require("realtimestt.vad_start" in events and "realtimestt.vad_stop" in events, gates, "vad_start_stop_events")
    require((rstt.get("feed_summary") or {}).get("realtime_feed") is True, gates, "realtime_feed")
    add_requirement(
        2,
        "real audio-file frame ingestion through RealtimeSTT VAD",
        gates,
        {
            "receipt": str(receipt_paths["realtimestt_vad"]),
            "feed_summary": rstt.get("feed_summary"),
            "endpointing_mode": (rstt.get("services") or {}).get("realtimestt", {}).get("endpointing_mode"),
        },
        ["RealtimeSTT accepted real WAV frames and emitted automatic VAD recording boundaries."],
        ["Does not prove browser WebRTC or physical microphone capture."],
    )

    gates = []
    transcript = ((rstt.get("transcript") or {}).get("text") or "").strip()
    require(bool(transcript), gates, "transcript_present")
    require(len(rstt.get("asr_executor_calls") or []) >= 1, gates, "live_asr_executor_called")
    require("realtimestt.executor_transcribed" in events, gates, "executor_event_present")
    add_requirement(
        3,
        "ASR transcript event generation",
        gates,
        {"receipt": str(receipt_paths["realtimestt_vad"]), "transcript_prefix": transcript[:160], "executor_calls": len(rstt.get("asr_executor_calls") or [])},
        ["Live OpenAI-compatible Whisper executor produced final transcript text through the listener bridge."],
        ["Does not prove semantic correctness beyond the configured stress utterance."],
    )

    speaker = rung7.get("speaker_resolution") or {}
    verification = rung7.get("primary_speaker_verification") or {}
    gates = []
    require(speaker.get("schema") == "memory.speaker_resolution.v1", gates, "speaker_resolution_schema")
    require(speaker.get("status") == "known", gates, "speaker_status_known")
    require(speaker.get("speaker_id") == "horus_lupercal", gates, "speaker_id_horus")
    require(verification.get("primary_speaker_match") is True, gates, "primary_speaker_match")
    require((rung7.get("memory_intent") or {}).get("action") in {"QUERY", "CLARIFY"}, gates, "memory_intent_present")
    add_requirement(
        4,
        "speaker evidence and memory /speaker/resolve integration",
        gates,
        {"receipt": str(receipt_paths["rung7_combined"]), "speaker_resolution": speaker, "primary_speaker_similarity": verification.get("similarity")},
        ["Listener speaker evidence round-tripped through memory /speaker/resolve and identified Horus Lupercal."],
        ["Does not prove raw audio embedding correctness outside the configured enrollment/candidate files."],
    )

    unknown_speaker = unknown.get("speaker_resolution") or {}
    unknown_intent = unknown.get("memory_intent") or {}
    known_speaker = known.get("speaker_resolution") or {}
    known_recall = known.get("speaker_memory_recall") or {}
    gates = []
    require(unknown_speaker.get("status") == "unknown", gates, "unknown_speaker_status")
    require(unknown_speaker.get("allow_personal_memory") is False, gates, "unknown_speaker_blocks_personal_memory")
    require(unknown_intent.get("action") == "CLARIFY", gates, "unknown_speaker_intent_clarify")
    require((unknown_speaker.get("identity_prompt") or {}).get("count", 0) >= 20, gates, "identity_prompt_variants")
    require(known_speaker.get("status") == "known", gates, "known_speaker_status")
    require(known_speaker.get("speaker_id") == "horus_lupercal", gates, "known_speaker_id")
    require(known_recall.get("found") is True, gates, "known_speaker_recall_found")
    require("speaker:horus_lupercal" in (known_recall.get("request") or {}).get("tags", []), gates, "known_speaker_recall_tags")
    add_requirement(
        5,
        "known Horus speaker-scoped recall and unknown fail-closed clarification",
        gates,
        {
            "known_receipt": str(receipt_paths["known_speaker_recall"]),
            "unknown_receipt": str(receipt_paths["unknown_speaker"]),
            "known_top_key": ((known_recall.get("items") or [{}])[0]).get("_key"),
            "unknown_identity_prompt": (unknown_speaker.get("identity_prompt") or {}).get("text"),
        },
        ["Known Horus turns use speaker-scoped recall tags; unknown turns route to identity clarification."],
        ["Does not prove every ambiguous multi-speaker case."],
    )

    final_control = turn_controls.get("final_control") or {}
    gates = []
    require(receipt_ok(stream_cancel), gates, "stream_cancel_receipt_ok_live_unmocked")
    require(stream_cancel.get("old_turn_bytes_after_cancel") == 0, gates, "old_turn_bytes_after_cancel_zero")
    require(receipt_ok(turn_controls), gates, "turn_controls_receipt_ok_live_unmocked")
    require(final_control.get("cancelled") is True, gates, "turn_cancelled")
    require(final_control.get("stopped") is True, gates, "turn_stopped")
    require(final_control.get("stale_chunks_should_skip") is True, gates, "stale_chunks_skip")
    require(receipt_ok(tau_voice), gates, "tau_voice_render_receipt_ok_live_unmocked")
    add_requirement(
        6,
        "Chatterbox turn-manager integration with cancellable chunked rendering",
        gates,
        {
            "stream_cancel_receipt": str(stream_cancel_path),
            "turn_controls_receipt": str(turn_controls_path),
            "tau_voice_render_receipt": str(tau_voice_path),
            "old_turn_bytes_after_cancel": stream_cancel.get("old_turn_bytes_after_cancel"),
            "final_control": final_control,
        },
        ["Cancel/duck/stop controls mark stale turns and old-turn bytes stop after cancel while Tau voice rendering remains live."],
        ["Does not prove subjective interruption feel."],
    )

    stress = rung7.get("stress_fixture") or {}
    claims = (rung7.get("claims") or {}).get("proves") or []
    raw_primary_cases = gate.get("cases") or {}
    primary_cases = list(raw_primary_cases.values()) if isinstance(raw_primary_cases, dict) else list(raw_primary_cases)
    gates = []
    require(receipt_ok(rung7), gates, "stress_rung7_receipt_ok_live_unmocked")
    require((stress.get("output_audio") or {}).get("duration_seconds") == 30.0, gates, "stress_duration_30s")
    require(stress.get("components", {}).get("noise") is not None, gates, "stress_noise_component")
    require(stress.get("components", {}).get("competing") is not None, gates, "stress_competing_component")
    require("stress_fixture_mixes_primary_speaker_with_background_or_competing_audio" in claims, gates, "stress_claim_present")
    require(gate.get("mocked") is False and not gate.get("failed_gates"), gates, "primary_gate_suite_unmocked_no_failed_gates")
    require(
        any(
            case.get("primary_speaker_match") is False and case.get("render_request_created") is False
            for case in primary_cases
        ),
        gates,
        "non_primary_suppression_case",
    )
    require(receipt_ok(listener_qra), gates, "listener_memory_tau_qra_receipt_ok_live_unmocked")
    add_requirement(
        7,
        "receipt-backed Horus factory-noise and competing/female voice stress",
        gates,
        {
            "stress_receipt": str(receipt_paths["rung7_combined"]),
            "realtimestt_vad_receipt": str(receipt_paths["realtimestt_vad"]),
            "primary_gate_receipt": str(receipt_paths["primary_speaker_gate"]),
            "listener_memory_tau_qra_receipt": str(listener_qra_path),
            "stress_output_audio": stress.get("output_audio"),
            "primary_gate_case_count": len(primary_cases),
        },
        ["Configured stress fixture mixes Horus with factory noise and Embry competing voice; primary-speaker gate has suppress cases; listener-memory-Tau-QRA chain is live."],
        ["Does not prove generalized factory robustness or overlapping diarization beyond these configured receipts."],
    )

    ok = not failed_gates and all(item["ok"] for item in requirements)
    return {
        "schema": "chatterbox.listener_goal_rungs_1_7_audit.v1",
        "ok": ok,
        "mocked": False,
        "live": ok,
        "started_at_utc": utc_now(),
        "ended_at_utc": utc_now(),
        "receipt_paths": {key: str(path) for key, path in receipt_paths.items()},
        "child_receipt_paths": {
            "stream_cancel": str(stream_cancel_path) if stream_cancel_path else None,
            "turn_controls": str(turn_controls_path) if turn_controls_path else None,
            "tau_voice_render": str(tau_voice_path) if tau_voice_path else None,
            "listener_memory_tau_qra": str(listener_qra_path) if listener_qra_path else None,
        },
        "requirements": requirements,
        "failed_gates": failed_gates,
        "proof_scope": [
            "file/frame based listener input",
            "RealtimeSTT automatic VAD endpointing for configured stress WAV",
            "OpenAI-compatible Whisper ASR executor",
            "memory /speaker/resolve known and unknown routing",
            "speaker-scoped Horus recall",
            "cancel/duck/stop turn controls and stream cancel",
            "configured Horus plus factory-noise plus competing-voice stress receipts",
        ],
        "does_not_prove": [
            "physical microphone capture",
            "browser WebRTC transport",
            "native RealtimeSTT faster-whisper path",
            "generalized factory-noise robustness beyond configured fixtures",
            "overlapping-speaker diarization",
            "subjective voice quality or interruption feel",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, type=Path)
    for key, value in DEFAULT_RECEIPTS.items():
        parser.add_argument(f"--{key.replace('_', '-')}", default=value)
    args = parser.parse_args()
    result = audit(args)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": result["ok"], "live": result["live"], "mocked": result["mocked"], "failed_gates": result["failed_gates"], "out": str(args.out)}, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
