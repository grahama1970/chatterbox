"""Persisted stream receipts with exactly-one terminal outcome (issue #10).

A manifest is written atomically (tmp file + os.replace) at stream admission
and after every recorded event, so a crash can never leave a half-written or
falsely-completed receipt on disk.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STREAM_RECEIPT_SCHEMA = "chatterbox.stream_receipt.v1"
TERMINAL_STATES = ("completed", "cancelled", "failed")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class StreamManifest:
    """Single-writer stream receipt. Not safe for concurrent writers."""

    def __init__(self, path: Path, *, stream_id: str, header: dict[str, Any]):
        self.path = Path(path)
        self.stream_id = stream_id
        self._data: dict[str, Any] = {
            "schema": STREAM_RECEIPT_SCHEMA,
            "stream_id": stream_id,
            "admitted_at_utc": utc_now(),
            "status": "streaming",
            "terminal": None,
            "events": [],
            **header,
        }
        self._terminal_written = False
        self._flush()

    @property
    def terminal(self) -> dict[str, Any] | None:
        return self._data["terminal"]

    def record(self, event: str, **fields: Any) -> None:
        self._data["events"].append({"event": event, "at_utc": utc_now(), **fields})
        self._flush()

    def finalize(
        self,
        status: str,
        *,
        reason: str | None = None,
        failed_gates: list[str] | None = None,
        **totals: Any,
    ) -> bool:
        """Record the terminal outcome. Returns False for late/duplicate candidates.

        A losing candidate is appended as an audit event and can never
        overwrite or duplicate the terminal state.
        """
        if status not in TERMINAL_STATES:
            raise ValueError(f"unknown terminal status: {status}")
        if self._terminal_written:
            self._data["events"].append(
                {
                    "event": "late_terminal_candidate_ignored",
                    "at_utc": utc_now(),
                    "requested_status": status,
                    "requested_reason": reason,
                }
            )
            self._flush()
            return False
        self._terminal_written = True
        self._data["status"] = status
        self._data["terminal"] = {
            "status": status,
            "reason": reason,
            "failed_gates": failed_gates or [],
            "at_utc": utc_now(),
            **totals,
        }
        self._data["events"].append(
            {"event": "terminal", "at_utc": utc_now(), "status": status, "reason": reason}
        )
        self._flush()
        return True

    def _flush(self) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(self._data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)


def validate_stream_manifest(
    manifest: dict[str, Any],
    *,
    expected_render_plan_digest: str | None = None,
) -> list[str]:
    """Reason codes for a manifest read back from disk; empty means valid."""
    failures: list[str] = []
    if manifest.get("schema") != STREAM_RECEIPT_SCHEMA:
        failures.append("schema_matches")
    if not manifest.get("stream_id"):
        failures.append("stream_id_present")
    terminal = manifest.get("terminal")
    status = manifest.get("status")
    if terminal is None:
        failures.append("terminal_state_present")
    else:
        if terminal.get("status") not in TERMINAL_STATES:
            failures.append("terminal_status_known")
        if terminal.get("status") != status:
            failures.append("status_matches_terminal")
        published_bytes = terminal.get("published_bytes")
        if published_bytes is not None:
            if not isinstance(published_bytes, int) or published_bytes < 0 or published_bytes % 2 != 0:
                failures.append("published_bytes_possible")
    terminal_events = [
        event
        for event in manifest.get("events") or []
        if event.get("event") == "terminal"
    ]
    if len(terminal_events) > 1:
        failures.append("exactly_one_terminal_event")
    if expected_render_plan_digest is not None and manifest.get("render_plan_digest") != expected_render_plan_digest:
        failures.append("render_plan_digest_matches")
    return failures
