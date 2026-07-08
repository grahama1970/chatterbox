import argparse
import json
import scripts
from pathlib import Path

from scripts.embry_proof_context import append_event, apply_proof_context, proof_context_from_args


def test_scripts_package_resolves_to_repo() -> None:
    assert Path(scripts.__file__).resolve().parent == Path(__file__).resolve().parents[1] / "scripts"


def test_proof_context_enriches_receipt_and_appends_turn_event(tmp_path: Path) -> None:
    journal = tmp_path / "events.ndjson"
    args = argparse.Namespace(
        session_id="ses_test",
        turn_id="turn_test",
        case_id="case_test",
        parent_event_id="evt_parent",
        event_journal=journal,
        receipt_dir=tmp_path / "receipts",
        artifact_dir=tmp_path / "artifacts",
        live=True,
        mocked=False,
    )
    context = proof_context_from_args(args, component="child_component")

    event = append_event(context, "child.started", payload={"ok": True})
    receipt = apply_proof_context(
        {"schema": "example.v1", "ok": True},
        context,
        proof_scope=["native_child_turn_context"],
        does_not_prove=["browser_mic"],
    )

    assert event is not None
    assert receipt["session_id"] == "ses_test"
    assert receipt["turn_id"] == "turn_test"
    assert receipt["native_turn_id"] == "turn_test"
    assert receipt["parent_event_id"] == "evt_parent"
    assert receipt["event_journal_path"] == str(journal)
    assert receipt["event_journal_sha256"]
    assert receipt["proof_scope"] == ["native_child_turn_context"]
    assert receipt["does_not_prove"] == ["browser_mic"]
    lines = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
    assert lines[0]["turn_id"] == "turn_test"
    assert lines[0]["session_id"] == "ses_test"
    assert lines[0]["source"] == {"live": True, "mocked": False, "transport": "native_child_proof_context"}
