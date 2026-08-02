#!/usr/bin/env python3
"""Live smoke for Chatterbox consuming Tau's voice-render v2 contract.

The smoke reads Tau's canonical v2 fixture, sends it through Chatterbox's
existing `/tau/voice-render` FastAPI route, renders through the real
blessed-QRA file path, then reads back the lineage digest and v2 control
receipts. It intentionally avoids starting a parallel v2 endpoint.
"""

from __future__ import annotations

import argparse
import json
import wave
from pathlib import Path
from typing import Any

from starlette.testclient import TestClient

import chatterbox.agent.server as server


def write_tiny_wav(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(24000)
        handle.writeframes(b"\x00\x00" * 2400)


def load_tau_fixture(tau_repo: Path) -> dict[str, Any]:
    fixture_path = tau_repo / "docs/contracts/voice/fixtures/v2-positive.json"
    return json.loads(fixture_path.read_text(encoding="utf-8"))


def write_blessed_ledger(path: Path, *, question_text: str, answer_text: str) -> str:
    audio_path = path.parent / "blessed-v2.wav"
    write_tiny_wav(audio_path)
    variant_id = "variant-live-v2"
    ledger = {
        "schema_version": server.BLESSED_QRA_SCHEMA_VERSION,
        "enabled": True,
        "entries": [
            {
                "id": "tau-v2-live-readback",
                "blessed": True,
                "question_text": question_text,
                "answer_text": answer_text,
                "audio_variants": [
                    {
                        "id": variant_id,
                        "name": "Tau v2 live readback",
                        "default": True,
                        "blessed": True,
                        "chunks": [
                            {
                                "index": 1,
                                "text": answer_text,
                                "delivery_stage": "recoverable_blocker",
                                "pause_after_ms": 0,
                                "audio": str(audio_path),
                                "audio_sha256": server.sha256_file(audio_path),
                            }
                        ],
                    }
                ],
            }
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return variant_id


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-live", action="store_true")
    parser.add_argument(
        "--tau-repo",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "tau",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("docs/proofs/tickets/issue-11-v2-consumer-20260802/live-smoke"),
    )
    args = parser.parse_args()
    if not args.allow_live:
        parser.error("--allow-live is required so this cannot be mistaken for a unit test")

    out_dir = args.out_dir.resolve()
    fixture = load_tau_fixture(args.tau_repo.resolve())
    payload = fixture["envelope"]
    segment_text = payload["v2"]["segments"][0]["text"]
    ledger_path = out_dir / "_blessed_qra_ledger.json"
    variant_id = write_blessed_ledger(
        ledger_path,
        question_text=payload["question_text"],
        answer_text=segment_text,
    )

    payload.update(
        {
            "use_blessed_qra_cache": True,
            "require_blessed_qra_memory_gate": False,
            "blessed_qra_variant": variant_id,
            "blessed_qra_preserve_pauses": True,
            "include_completion_cue": False,
            "crossfade_ms": 0,
            "label": "issue-11-v2-live",
        }
    )
    server.OUT_DIR = out_dir
    server.BLESSED_QRA_LEDGER_PATH = ledger_path
    server.tau_response_controls.clear()

    client = TestClient(server.app)
    response = client.post("/tau/voice-render", json=payload)
    body = response.json() if response.content else {}
    controls = []
    control_target = payload["v2"]["control_target"]
    controls.append(
        client.post(
            f"/turn/{control_target['turn_id']}/cancel",
            json={**control_target, "reason": "stale wrong response", "response_id": "wrong-response"},
        ).json()
    )
    controls.append(
        client.post(
            f"/turn/{control_target['turn_id']}/cancel",
            json={**control_target, "reason": "current response"},
        ).json()
    )
    controls.append(
        client.post(
            f"/turn/{control_target['turn_id']}/cancel",
            json={
                **control_target,
                "reason": "duplicate cancel",
                "expected_cancel_epoch": control_target["expected_cancel_epoch"] + 1,
            },
        ).json()
    )

    finished_audio = Path(str(body.get("finished_response_audio", "")))
    failed_gates = []
    if response.status_code != 200:
        failed_gates.append("tau_voice_render_http_200")
    if not body.get("ok"):
        failed_gates.append("tau_voice_render_ok")
    if body.get("request_lineage_digest") != fixture["request_lineage_digest"]:
        failed_gates.append("request_lineage_digest_matches_tau_fixture")
    if body.get("consumer_digest_matches") is not True:
        failed_gates.append("consumer_digest_matches")
    if not finished_audio.exists() or finished_audio.stat().st_size <= 44:
        failed_gates.append("finished_response_audio_non_empty")
    if controls[0].get("ok") is not False or controls[0].get("control", {}).get("reason") != "stale_response_id":
        failed_gates.append("stale_response_id_rejected")
    if controls[1].get("ok") is not True or controls[1].get("control", {}).get("reason") != "current_response":
        failed_gates.append("current_response_cancel_accepted")
    if controls[2].get("ok") is not True or controls[2].get("control", {}).get("idempotent") is not True:
        failed_gates.append("duplicate_cancel_idempotent")

    receipt = {
        "schema": "chatterbox.tau_voice_render_v2_live_smoke.v1",
        "mocked": False,
        "live": True,
        "tau_fixture": str(args.tau_repo / "docs/contracts/voice/fixtures/v2-positive.json"),
        "http_status": response.status_code,
        "response": body,
        "controls": controls,
        "ledger_path": str(ledger_path),
        "out_dir": str(out_dir),
        "finished_response_audio": str(finished_audio),
        "failed_gates": failed_gates,
        "ok": not failed_gates,
    }
    receipt_path = out_dir / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": receipt["ok"], "receipt": str(receipt_path), "failed_gates": failed_gates}))
    return 0 if receipt["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
