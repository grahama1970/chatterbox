import json
from pathlib import Path

from scripts.embry_event_journal import EventJournal, validate_event


def test_event_journal_appends_monotonic_events(tmp_path: Path) -> None:
    journal = EventJournal(tmp_path / "events.ndjson", session_id="s1", trace_id="t1", repo=Path.cwd())

    first = journal.append(
        "session.started.v1",
        component="test",
        payload={"scenario": "smoke"},
        source={"live": True, "mocked": False, "transport": "unit"},
    )
    second = journal.append(
        "proof.receipt.v1",
        component="test",
        payload={"ok": True},
        source={"live": True, "mocked": False, "transport": "unit"},
        parent_event_id=first["event_id"],
    )

    events = [json.loads(line) for line in (tmp_path / "events.ndjson").read_text(encoding="utf-8").splitlines()]
    assert [event["sequence"] for event in events] == [1, 2]
    assert second["parent_event_id"] == first["event_id"]
    assert journal.validation_failures == []
    assert len(journal.hash()) == 64


def test_validate_event_rejects_missing_source_fields() -> None:
    failures = validate_event(
        {
            "schema": "embry.event.v1",
            "event_id": "evt_1",
            "session_id": "s1",
            "sequence": 1,
            "trace_id": "t1",
            "type": "session.started.v1",
            "component": "test",
            "occurred_at": "2026-07-08T00:00:00Z",
            "source": {"live": True},
            "payload": {},
        },
        expected_sequence=1,
    )

    assert "event_source_missing_mocked" in failures
    assert "event_source_missing_transport" in failures
