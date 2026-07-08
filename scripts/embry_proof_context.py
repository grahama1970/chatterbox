#!/usr/bin/env python3
"""Shared proof context for Embry voice proof runners."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class ProofContext:
    component: str
    session_id: str | None
    turn_id: str | None
    case_id: str | None
    parent_event_id: str | None
    event_journal: Path | None
    receipt_dir: Path | None
    artifact_dir: Path | None
    live: bool
    mocked: bool

    @property
    def active(self) -> bool:
        return bool(self.session_id or self.turn_id or self.event_journal)


def add_proof_context_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--session-id", default=os.getenv("EMBRY_SESSION_ID"))
    parser.add_argument("--turn-id", default=os.getenv("EMBRY_TURN_ID"))
    parser.add_argument("--case-id", default=os.getenv("EMBRY_CASE_ID"))
    parser.add_argument("--parent-event-id", default=os.getenv("EMBRY_PARENT_EVENT_ID"))
    parser.add_argument("--event-journal", type=Path, default=Path(os.getenv("EMBRY_EVENT_JOURNAL")) if os.getenv("EMBRY_EVENT_JOURNAL") else None)
    parser.add_argument("--receipt-dir", type=Path, default=Path(os.getenv("EMBRY_RECEIPT_DIR")) if os.getenv("EMBRY_RECEIPT_DIR") else None)
    parser.add_argument("--artifact-dir", type=Path, default=Path(os.getenv("EMBRY_ARTIFACT_DIR")) if os.getenv("EMBRY_ARTIFACT_DIR") else None)
    parser.add_argument("--live", action=argparse.BooleanOptionalAction, default=env_bool("EMBRY_LIVE", True))
    parser.add_argument("--mocked", action=argparse.BooleanOptionalAction, default=env_bool("EMBRY_MOCKED", False))


def proof_context_from_args(args: argparse.Namespace, *, component: str, default_case_id: str | None = None) -> ProofContext:
    return ProofContext(
        component=component,
        session_id=getattr(args, "session_id", None),
        turn_id=getattr(args, "turn_id", None),
        case_id=getattr(args, "case_id", None) or default_case_id,
        parent_event_id=getattr(args, "parent_event_id", None),
        event_journal=getattr(args, "event_journal", None),
        receipt_dir=getattr(args, "receipt_dir", None),
        artifact_dir=getattr(args, "artifact_dir", None),
        live=bool(getattr(args, "live", True)),
        mocked=bool(getattr(args, "mocked", False)),
    )


def journal_line_count(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def append_event(
    context: ProofContext,
    event_type: str,
    *,
    payload: dict[str, Any],
    source: dict[str, Any] | None = None,
    artifacts: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    if not context.event_journal:
        return None
    context.event_journal.parent.mkdir(parents=True, exist_ok=True)
    sequence = journal_line_count(context.event_journal) + 1
    event = {
        "schema": "embry.event.v1",
        "event_id": f"evt_{uuid.uuid4().hex}",
        "session_id": context.session_id,
        "sequence": sequence,
        "trace_id": f"trace_{context.session_id or 'child'}",
        "turn_id": context.turn_id,
        "parent_event_id": context.parent_event_id,
        "type": event_type,
        "component": context.component,
        "occurred_at": utc_now(),
        "ingested_at": utc_now(),
        "source": source or {"live": context.live, "mocked": context.mocked, "transport": "native_child_proof_context"},
        "payload": payload,
        "artifacts": artifacts or [],
    }
    with context.event_journal.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")
    return event


def apply_proof_context(
    receipt: dict[str, Any],
    context: ProofContext,
    *,
    proof_scope: list[str] | None = None,
    does_not_prove: list[str] | None = None,
) -> dict[str, Any]:
    if context.session_id is not None:
        receipt["session_id"] = context.session_id
    if context.turn_id is not None:
        receipt["turn_id"] = context.turn_id
        receipt["native_turn_id"] = context.turn_id
    if context.case_id is not None:
        receipt["case_id"] = context.case_id
    if context.parent_event_id is not None:
        receipt["parent_event_id"] = context.parent_event_id
        receipt["parent_turn_id"] = context.turn_id
    if context.event_journal is not None:
        receipt["event_journal_path"] = str(context.event_journal)
        receipt["event_journal_sha256"] = sha256_file(context.event_journal)
    if context.receipt_dir is not None:
        receipt["receipt_dir"] = str(context.receipt_dir)
    if context.artifact_dir is not None:
        receipt["artifact_dir"] = str(context.artifact_dir)
    if proof_scope is not None:
        existing = list(receipt.get("proof_scope") or [])
        receipt["proof_scope"] = [*existing, *[item for item in proof_scope if item not in existing]]
    if does_not_prove is not None:
        existing = list(receipt.get("does_not_prove") or [])
        receipt["does_not_prove"] = [*existing, *[item for item in does_not_prove if item not in existing]]
    return receipt
