"""QRA creation audio hook tests.

These are fixture/dry-run checks only. They do not prove live Chatterbox
generation; live proof comes from the smoke receipts.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def load_hook_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "qra_creation_audio_hook.py"
    spec = importlib.util.spec_from_file_location("qra_creation_audio_hook", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_qra_creation_event_extracts_nested_review_and_audio_policy() -> None:
    hook = load_hook_module()

    fields = hook.qra_fields_from_event(
        {
            "event_id": "evt-1",
            "qra": {
                "qra_id": "qra-1",
                "memory_key": "mem-1",
                "problem": "What should Embry say?",
                "solution": "Say the approved answer.",
                "review": {"status": "approved"},
                "audio": {"auto_generate": True, "variant_count": 5},
            },
        }
    )

    assert fields["qra_id"] == "qra-1"
    assert fields["memory_key"] == "mem-1"
    assert fields["review_status"] == "approved"
    assert fields["question"] == "What should Embry say?"
    assert fields["answer"] == "Say the approved answer."
    assert fields["auto_generate_audio"] is True
    assert fields["variant_count"] == 5


def test_qra_creation_hook_dry_run_receipt_is_mocked(tmp_path: Path, monkeypatch) -> None:
    hook = load_hook_module()
    event = tmp_path / "qra-event.json"
    receipt = tmp_path / "receipt.json"
    event.write_text(
        json.dumps(
            {
                "qra": {
                    "id": "qra-1",
                    "memory_key": "mem-1",
                    "question": "Question?",
                    "answer": "Answer.",
                    "review_status": "approved",
                    "audio": {"auto_generate": True, "variant_count": 5},
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "qra_creation_audio_hook.py",
            "--event",
            str(event),
            "--receipt",
            str(receipt),
            "--ledger",
            str(tmp_path / "ledger.json"),
            "--host-out-dir",
            str(tmp_path),
            "--dry-run",
        ],
    )

    assert hook.main() == 0
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["mocked"] is True
    assert payload["live"] is False
    assert payload["child"]["dry_run"] is True
    assert payload["child_receipt"]["variant_count"] == 5


def test_qra_creation_hook_fails_closed_for_unapproved_qra(tmp_path: Path, monkeypatch) -> None:
    hook = load_hook_module()
    event = tmp_path / "qra-event.json"
    receipt = tmp_path / "receipt.json"
    event.write_text(
        json.dumps(
            {
                "qra": {
                    "id": "qra-1",
                    "memory_key": "mem-1",
                    "question": "Question?",
                    "answer": "Answer.",
                    "review_status": "draft",
                    "audio": {"auto_generate": True, "variant_count": 5},
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "qra_creation_audio_hook.py",
            "--event",
            str(event),
            "--receipt",
            str(receipt),
            "--dry-run",
        ],
    )

    assert hook.main() == 1
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert payload["ok"] is False
    assert payload["live"] is False
    assert payload["child"] is None
    assert "review_status_approved" in payload["failed_gates"]
