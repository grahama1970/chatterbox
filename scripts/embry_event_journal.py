#!/usr/bin/env python3
"""Append-only event journal utilities for Embry voice proof rungs."""

from __future__ import annotations

import hashlib
import json
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REQUIRED_EVENT_FIELDS = {
    "schema",
    "event_id",
    "session_id",
    "sequence",
    "trace_id",
    "type",
    "component",
    "occurred_at",
    "source",
    "payload",
}

REQUIRED_SOURCE_FIELDS = {"live", "mocked", "transport"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_head(repo: Path) -> str | None:
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, text=True, capture_output=True, timeout=10)
    except Exception:
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def git_dirty(repo: Path) -> bool | None:
    try:
        result = subprocess.run(["git", "status", "--short"], cwd=repo, text=True, capture_output=True, timeout=10)
    except Exception:
        return None
    return bool(result.stdout.strip()) if result.returncode == 0 else None


def validate_event(event: dict[str, Any], *, expected_sequence: int | None = None) -> list[str]:
    failures: list[str] = []
    missing = sorted(REQUIRED_EVENT_FIELDS - set(event))
    failures.extend([f"event_missing_{field}" for field in missing])
    source = event.get("source") if isinstance(event.get("source"), dict) else {}
    missing_source = sorted(REQUIRED_SOURCE_FIELDS - set(source))
    failures.extend([f"event_source_missing_{field}" for field in missing_source])
    if event.get("schema") != "embry.event.v1":
        failures.append("event_schema_embry_event_v1")
    if expected_sequence is not None and event.get("sequence") != expected_sequence:
        failures.append("event_sequence_monotonic")
    if source.get("mocked") is True and source.get("live") is True:
        failures.append("event_source_live_and_mocked_conflict")
    return failures


class EventJournal:
    def __init__(self, path: Path, *, session_id: str, trace_id: str, repo: Path | None = None) -> None:
        self.path = path
        self.session_id = session_id
        self.trace_id = trace_id
        self.repo = repo or Path.cwd()
        self.sequence = 0
        self.validation_failures: list[str] = []
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("", encoding="utf-8")

    def append(
        self,
        event_type: str,
        *,
        component: str,
        payload: dict[str, Any],
        source: dict[str, Any],
        turn_id: str | None = None,
        parent_event_id: str | None = None,
        artifacts: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        self.sequence += 1
        event = {
            "schema": "embry.event.v1",
            "event_id": f"evt_{uuid.uuid4().hex}",
            "session_id": self.session_id,
            "sequence": self.sequence,
            "trace_id": self.trace_id,
            "turn_id": turn_id,
            "parent_event_id": parent_event_id,
            "type": event_type,
            "component": component,
            "occurred_at": utc_now(),
            "ingested_at": utc_now(),
            "source": source,
            "payload": payload,
            "artifacts": artifacts or [],
            "provenance": {
                "repo": str(self.repo),
                "git_head": git_head(self.repo),
                "git_dirty": git_dirty(self.repo),
            },
        }
        self.validation_failures.extend(validate_event(event, expected_sequence=self.sequence))
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")
        return event

    def hash(self) -> str:
        return sha256_file(self.path)

    def read_events(self) -> list[dict[str, Any]]:
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]
