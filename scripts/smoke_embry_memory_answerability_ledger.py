#!/usr/bin/env python3
"""Ledger-backed Embry memory answerability proof.

This runner turns the known SPARTA/persona/memory-miss failures into an
event-journal receipt. It does not prove runtime integration yet; it proves
whether current live memory responses satisfy the answerability gates that must
exist before Tau/Chatterbox speech.
"""

from __future__ import annotations

import argparse
import json
import time
import uuid
from pathlib import Path
from typing import Any

try:
    from build_embry_stress_session_matrix import build_matrix
    from embry_event_journal import EventJournal, utc_now
    from smoke_embry_intelligence_stress import classify_matrix_answer, post_json
except ModuleNotFoundError:
    from scripts.build_embry_stress_session_matrix import build_matrix
    from scripts.embry_event_journal import EventJournal, utc_now
    from scripts.smoke_embry_intelligence_stress import classify_matrix_answer, post_json


ANSWERABILITY_FOLDERS = {
    "sparta_qra_compliance",
    "persona_memory_recall",
    "persona_memory_miss",
}


def selected_answerability_sessions() -> list[dict[str, Any]]:
    matrix = build_matrix()
    return [
        session
        for session in matrix["sessions"]
        if session.get("difficulty") == "simple" and session.get("folder_id") in ANSWERABILITY_FOLDERS
    ]


def scope_for_route(route: str) -> str:
    if route == "memory.sparta_qra":
        return "sparta_qra"
    return "persona_memory"


def answer_text(answer: dict[str, Any]) -> str:
    payload = answer.get("json") if isinstance(answer.get("json"), dict) else {}
    return str(payload.get("final_response") or payload.get("source_answer") or "").strip()


def answer_sources(answer: dict[str, Any]) -> list[dict[str, Any]]:
    payload = answer.get("json") if isinstance(answer.get("json"), dict) else {}
    sources = payload.get("sources")
    return sources if isinstance(sources, list) else []


def answerability_decision(session: dict[str, Any], answer: dict[str, Any], failed_gates: list[str]) -> dict[str, Any]:
    payload = answer.get("json") if isinstance(answer.get("json"), dict) else {}
    if failed_gates:
        decision = "block_before_speech"
    elif payload.get("can_answer") is False:
        decision = "clarify_or_no_answer"
    else:
        decision = "answerable"
    return {
        "decision": decision,
        "can_answer": payload.get("can_answer"),
        "final_response_present": bool(answer_text(answer)),
        "records_used_count": len(answer_sources(answer)),
        "failed_gates": failed_gates,
        "route": session.get("route"),
    }


def run_session(
    session: dict[str, Any],
    *,
    journal: EventJournal,
    memory_url: str,
    timeout_s: int,
) -> dict[str, Any]:
    turn_id = str(session["id"])
    scope = scope_for_route(str(session["route"]))
    start_event = journal.append(
        "turn.test.started.v1",
        component="memory_answerability_ledger_runner",
        turn_id=turn_id,
        payload={"session": session, "scope": scope},
        source={"live": True, "mocked": False, "transport": "runner"},
    )
    intent_request = {"q": session["question"], "scope": scope, "fast": True}
    intent_event = journal.append(
        "memory.intent.requested.v1",
        component="memory",
        turn_id=turn_id,
        parent_event_id=start_event["event_id"],
        payload=intent_request,
        source={"live": True, "mocked": False, "transport": "memory_http"},
    )
    intent = post_json(f"{memory_url.rstrip('/')}/intent", intent_request, timeout_s)
    journal.append(
        "memory.intent.v1",
        component="memory",
        turn_id=turn_id,
        parent_event_id=intent_event["event_id"],
        payload={"request": intent_request, "response": intent},
        source={"live": bool(intent.get("ok_http")), "mocked": False, "transport": "memory_http"},
    )

    answer_request = {"q": session["question"], "scope": scope, "k": 5}
    answer_request_event = journal.append(
        "memory.query.v1",
        component="memory",
        turn_id=turn_id,
        parent_event_id=start_event["event_id"],
        payload=answer_request,
        source={"live": True, "mocked": False, "transport": "memory_http"},
    )
    answer = post_json(f"{memory_url.rstrip('/')}/answer", answer_request, timeout_s)
    failed_gates = classify_matrix_answer(session, answer)
    sources = answer_sources(answer)
    retrieval_event = journal.append(
        "memory.retrieval.v1",
        component="memory",
        turn_id=turn_id,
        parent_event_id=answer_request_event["event_id"],
        payload={
            "request": answer_request,
            "response": answer,
            "sources": sources,
            "source_count": len(sources),
        },
        source={"live": bool(answer.get("ok_http")), "mocked": False, "transport": "memory_http"},
    )
    decision = answerability_decision(session, answer, failed_gates)
    journal.append(
        "memory.answerability.v1",
        component="memory_answerability_gate",
        turn_id=turn_id,
        parent_event_id=retrieval_event["event_id"],
        payload={
            "session_id": session["id"],
            "question": session["question"],
            "final_response": answer_text(answer),
            "decision": decision,
        },
        source={"live": bool(answer.get("ok_http")), "mocked": False, "transport": "proof_runner_gate"},
    )
    return {
        "id": session["id"],
        "folder_id": session["folder_id"],
        "route": session["route"],
        "question": session["question"],
        "ok": not failed_gates,
        "mocked": False,
        "live": bool(intent.get("ok_http") and answer.get("ok_http")),
        "final_response": answer_text(answer),
        "source_count": len(sources),
        "answerability": decision,
        "failed_gates": failed_gates,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--memory-url", default="http://127.0.0.1:8601")
    parser.add_argument("--timeout-s", default=120, type=int)
    args = parser.parse_args()

    started = time.perf_counter()
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    journal = EventJournal(
        out_dir / "events.ndjson",
        session_id=f"memory-answerability-ledger-{uuid.uuid4().hex[:10]}",
        trace_id=f"trace_{uuid.uuid4().hex}",
        repo=Path(__file__).resolve().parents[1],
    )
    sessions = selected_answerability_sessions()
    journal.append(
        "session.started.v1",
        component="memory_answerability_ledger_runner",
        payload={
            "rung_id": "rung_05_memory_answerability_ledger",
            "scenario_count": len(sessions),
            "memory_url": args.memory_url,
            "proof_scope": "live_memory_answerability_gate_not_runtime_speech_block",
        },
        source={"live": True, "mocked": False, "transport": "runner"},
    )
    cases = [run_session(session, journal=journal, memory_url=args.memory_url, timeout_s=args.timeout_s) for session in sessions]
    failed_gates = [f"{case['id']}:{gate}" for case in cases for gate in case["failed_gates"]]
    if journal.validation_failures:
        failed_gates.extend([f"journal:{gate}" for gate in journal.validation_failures])
    journal.append(
        "proof.receipt.v1",
        component="memory_answerability_ledger_runner",
        payload={
            "rung_id": "rung_05_memory_answerability_ledger",
            "case_count": len(cases),
            "failed_gates": failed_gates,
            "ok": not failed_gates,
        },
        source={"live": all(case["live"] for case in cases), "mocked": False, "transport": "proof_runner"},
    )
    receipt = {
        "schema": "embry.proof.receipt.v1",
        "rung_id": "rung_05_memory_answerability_ledger",
        "status": "pass" if not failed_gates else "fail",
        "ok": not failed_gates,
        "mocked": False,
        "live": all(case["live"] for case in cases),
        "proof_scope": "live_memory_answerability_gate_not_runtime_speech_block",
        "runtime_speech_block_proven": False,
        "started_at_utc": journal.read_events()[0]["occurred_at"],
        "ended_at_utc": utc_now(),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "journal": {
            "path": str(journal.path),
            "sha256": journal.hash(),
            "event_count": len(journal.read_events()),
            "validation_failures": journal.validation_failures,
        },
        "cases": cases,
        "failed_gates": failed_gates,
        "claims": {
            "proves": [
                "memory_answerability_queries_and_failures_are_ledgered",
                "unrelated_memory_answers_are_identified_before_tau_chatterbox_speech",
            ],
            "does_not_prove": [
                "runtime_memory_service_has_native_answerability_policy",
                "Tau_blocks_failed_answers",
                "Chatterbox_speech_is_suppressed_for_failed_answers",
                "RealtimeSTT_audio_ingress",
                "Chat_UX_sync",
                "orb_sync",
                "replay",
                "interruption",
            ],
        },
    }
    (out_dir / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": receipt["ok"], "live": receipt["live"], "mocked": receipt["mocked"], "receipt": str(out_dir / "receipt.json")}, indent=2))
    return 0 if receipt["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
