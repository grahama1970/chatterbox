import json
from pathlib import Path

import pytest

from scripts.audit_horus_live_loop_gates import (
    interruption_causal_lineage,
    load_manifest,
    receipt_matches_manifest,
    same_lineage,
    transcript_similarity,
)


def write_manifest(tmp_path: Path, **updates: object) -> Path:
    manifest = {
        "schema": "embry.voice_run_manifest.v1",
        "run_id": "run-test",
        "session_id": "session-test",
        "listener_authority": "unix_pipewire_realtimestt",
        "repo_commits": {"chatterbox": "deadbeef"},
        "turn_ids": ["turn-test"],
        "receipts": {
            "listener": [
                {
                    "kind": "browser_realtimestt",
                    "path": str(tmp_path / "listener.json"),
                    "sha256": "0" * 64,
                    "session_id": "session-test",
                    "turn_id": "turn-test",
                    "expected_transcript": "embry ingress proof alpha seven",
                }
            ]
        },
    }
    manifest.update(updates)
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_manifest_requires_explicit_literal_receipt_paths(tmp_path: Path) -> None:
    path = write_manifest(tmp_path)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["receipts"]["listener"][0]["path"] = str(tmp_path / "*" / "listener.json")
    path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="manifest_receipt_path_invalid"):
        load_manifest(path)


def test_manifest_rejects_receipt_from_different_session(tmp_path: Path) -> None:
    path = write_manifest(tmp_path)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["receipts"]["listener"][0]["session_id"] = "stale-session"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="manifest_receipt_session_mismatch"):
        load_manifest(path)


def test_gibberish_nonempty_stt_fails_quality_gate() -> None:
    score = transcript_similarity(
        "Form a smirk station, loop, bank check on the Z-sand, but...",
        "embry ingress proof alpha seven",
    )

    assert score < 0.75


def test_expected_stt_passes_normalized_quality_gate() -> None:
    score = transcript_similarity(
        "Embry ingress proof, alpha seven.",
        "embry ingress proof alpha seven",
    )

    assert score == 1.0


@pytest.mark.parametrize(
    ("left", "right"),
    [
        (
            {"session_id": "session-a", "turn_id": "turn-a"},
            {"session_id": "session-a", "turn_id": "turn-b"},
        ),
        (
            {"session_id": "session-a", "turn_id": "turn-a"},
            {"session_id": "session-b", "turn_id": "turn-a"},
        ),
        (
            {"session_id": "session-a", "turn_id": None},
            {"session_id": "session-a", "turn_id": None},
        ),
    ],
)
def test_chat_orb_and_interruption_slices_require_same_turn_lineage(
    left: dict[str, str | None], right: dict[str, str | None]
) -> None:
    assert same_lineage(left, right) is False


def test_shared_session_and_turn_lineage_passes() -> None:
    left = {"session_id": "session-a", "turn_id": "turn-a"}
    right = {"session_id": "session-a", "turn_id": "turn-a"}

    assert same_lineage(left, right) is True


def test_unix_listener_authority_receipt_requires_hash_and_payload_lineage(tmp_path: Path) -> None:
    receipt = {"session_id": "session-a", "turn_id": "turn-a"}
    path = tmp_path / "listener.json"
    path.write_text(json.dumps(receipt), encoding="utf-8")
    import hashlib

    entry = {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "session_id": "session-a",
        "turn_id": "turn-a",
    }
    assert receipt_matches_manifest(entry, receipt) is True
    entry["sha256"] = "f" * 64
    assert receipt_matches_manifest(entry, receipt) is False


def test_interruption_causal_lineage_spans_distinct_turns() -> None:
    old_entry = {"session_id": "session-a", "turn_id": "turn-old"}
    new_entry = {"session_id": "session-a", "turn_id": "turn-new"}
    cancel = {"session_id": "session-a", "interruption_id": "interrupt-a", "old_turn_id": "turn-old"}
    overlap = {"session_id": "session-a", "interruption_id": "interrupt-a", "new_turn_id": "turn-new"}
    assert interruption_causal_lineage(old_entry, new_entry, cancel, overlap) is True


def test_interruption_causal_lineage_rejects_same_turn_or_cross_session() -> None:
    old_entry = {"session_id": "session-a", "turn_id": "turn-old"}
    cancel = {"session_id": "session-a", "interruption_id": "interrupt-a", "old_turn_id": "turn-old"}
    same_turn = {"session_id": "session-a", "turn_id": "turn-old"}
    overlap = {"session_id": "session-a", "interruption_id": "interrupt-a", "new_turn_id": "turn-old"}
    assert interruption_causal_lineage(old_entry, same_turn, cancel, overlap) is False
    overlap["session_id"] = "session-b"
    assert interruption_causal_lineage(old_entry, {"session_id": "session-b", "turn_id": "turn-new"}, cancel, overlap) is False
