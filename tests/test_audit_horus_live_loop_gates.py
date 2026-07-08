from pathlib import Path
import os

from scripts.audit_horus_live_loop_gates import resolve_receipt_path


def test_resolve_receipt_path_uses_latest_glob_match(tmp_path: Path) -> None:
    older = tmp_path / "older" / "receipt.json"
    newer = tmp_path / "newer" / "receipt.json"
    older.parent.mkdir()
    newer.parent.mkdir()
    older.write_text("{}\n", encoding="utf-8")
    newer.write_text("{}\n", encoding="utf-8")
    os.utime(older, (1000, 1000))
    os.utime(newer, (2000, 2000))

    resolved = resolve_receipt_path(str(tmp_path / "*" / "receipt.json"))

    assert resolved == newer


def test_resolve_receipt_path_preserves_literal_missing_path(tmp_path: Path) -> None:
    literal = tmp_path / "missing.json"

    assert resolve_receipt_path(str(literal)) == literal
