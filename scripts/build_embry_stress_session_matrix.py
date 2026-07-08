#!/usr/bin/env python3
"""Build the Embry voice/chat stress session matrix.

The matrix is intentionally a session contract, not proof. Unrun rows stay
`not_run`; only rows backed by receipts are marked pass/fail.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_OUT = Path("docs/EMBRY_STRESS_SESSION_MATRIX.json")

DIFFICULTIES = ["simple", "medium", "advanced", "adversarial", "soak"]

ROUTE_FAMILIES: list[dict[str, Any]] = [
    {
        "id": "sparta_qra_compliance",
        "title": "SPARTA QRA Compliance",
        "route": "memory.sparta_qra",
        "questions": [
            "What evidence should a SPARTA QRA include to be acceptable?",
            "Which SPARTA QRA evidence fields are mandatory before Embry can answer?",
            "Show the evidence trail for a spacecraft mission-control SPARTA QRA.",
            "What should Embry do when a SPARTA QRA has weak or missing evidence?",
        ],
    },
    {
        "id": "persona_memory_recall",
        "title": "Persona Memory Recall",
        "route": "memory.persona_memory",
        "questions": [
            "Where did Horus Lupercal grow up?",
            "What did Horus last ask Embry about voice testing?",
            "What should Embry remember about Horus and factory-floor voice tests?",
            "What was the last conversation Embry had with Horus about QRA caching?",
        ],
    },
    {
        "id": "persona_memory_miss",
        "title": "Persona Memory Miss",
        "route": "memory.persona_memory.fail_closed",
        "questions": [
            "What private code word did I tell Embry yesterday?",
            "What unrecorded nickname did Horus give the WebRTC bug?",
            "What was the undocumented promise Embry made in the last room test?",
            "What secret factory phrase did I say when the microphone was muted?",
        ],
    },
    {
        "id": "brave_research",
        "title": "External Research",
        "route": "brave-search.source_receipt",
        "questions": [
            "Research current pyannote.audio support for overlap detection.",
            "Find current RealtimeSTT guidance for external audio feed_audio usage.",
            "Search for browser getUserMedia audio processing constraints relevant to ASR.",
            "Research current open-source approaches for streaming speaker diarization.",
        ],
    },
    {
        "id": "tau_tool_orchestration",
        "title": "Tau Tool Orchestration",
        "route": "tau.agent_handoff",
        "questions": [
            "Ask Tau to create an evidence-case for a failed Embry voice receipt.",
            "Ask Tau to route a memory failure to the correct repair owner.",
            "Ask Tau to create a figure from analytics on the latest voice stress run.",
            "Ask Tau to verify that a Chatterbox receipt and Chat UX run id agree.",
        ],
    },
    {
        "id": "chat_ux_sync",
        "title": "Chat UX Sync",
        "route": "ux-lab.shared_chat",
        "questions": [
            "Replay the latest Embry stress session and show each spoken turn in chat.",
            "Show the memory reasoning trace inline for the current spoken response.",
            "Prove the chat text and Chatterbox audio share the same turn id.",
            "Show the entity underlines from memory extraction in the spoken transcript.",
        ],
    },
    {
        "id": "interruption",
        "title": "Interruption And Barge-In",
        "route": "chatterbox.turn_control",
        "questions": [
            "Interrupt Embry mid-answer with a new Horus question.",
            "Interrupt a blessed QRA cached response and prove stale audio stops.",
            "Have a non-primary speaker interrupt Embry and prove the new turn is rejected.",
            "Interrupt Embry during a Tau tool wait and verify a natural stop phrase.",
        ],
    },
    {
        "id": "speaker_identity",
        "title": "Speaker Identity",
        "route": "memory.speaker.resolve",
        "questions": [
            "Known Horus asks for personal memory with clean audio.",
            "Unknown speaker asks for Horus memory and must be asked to identify.",
            "Ambiguous speaker scores must fail closed before recall.",
            "Female distractor overlaps Horus and must not become memory authority.",
        ],
    },
    {
        "id": "factory_noise",
        "title": "Factory Noise",
        "route": "realtimestt.factory_capture",
        "questions": [
            "Horus asks a QRA question over factory-floor background noise.",
            "Horus asks a memory question while a female voice speaks nearby.",
            "Horus asks a compliance question through the Jabra speaker/mic path.",
            "Horus asks a research question through the HD webcam microphone path.",
        ],
    },
    {
        "id": "tone_emotion",
        "title": "Tone And Emotion",
        "route": "memory.intent.voice_delivery",
        "questions": [
            "User is frustrated; Embry should de-escalate with a warm concise tone.",
            "User is hostile; Embry should use a firm humorous boundary.",
            "User is discouraged; Embry should answer gently and offer the next check.",
            "Two speakers overlap; Embry should say a human one-at-a-time boundary.",
        ],
    },
]

CURRENT_RESULTS: dict[str, dict[str, Any]] = {
    "sparta_qra_compliance-simple-01": {
        "status": "failed",
        "latest_receipt": "/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260708T000144Z-matrix-simple-memory-search-v2/receipt.json",
        "failed_gates": [
            "sparta_qra_answer_overfit_to_unrelated_control_exclusion",
            "sparta_qra_answer_missing_acceptance_terms",
        ],
        "observed": "Returned unrelated S0609/deprecated-control answer.",
    },
    "sparta_qra_compliance-simple-02": {
        "status": "failed",
        "latest_receipt": "/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260708T000144Z-matrix-simple-memory-search-v2/receipt.json",
        "failed_gates": ["sparta_qra_answer_overfit_to_unrelated_control_exclusion"],
        "observed": "Returned S0609/deprecated-control answer for mandatory evidence fields.",
    },
    "sparta_qra_compliance-simple-03": {
        "status": "failed",
        "latest_receipt": "/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260708T000144Z-matrix-simple-memory-search-v2/receipt.json",
        "failed_gates": ["sparta_qra_answer_overfit_to_unrelated_control_exclusion"],
        "observed": "Evidence trail still carried deprecated/non-generation control leakage.",
    },
    "sparta_qra_compliance-simple-04": {
        "status": "failed",
        "latest_receipt": "/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260708T000144Z-matrix-simple-memory-search-v2/receipt.json",
        "failed_gates": ["sparta_qra_answer_overfit_to_unrelated_control_exclusion"],
        "observed": "Returned S0609/deprecated-control answer for weak-evidence handling.",
    },
    "persona_memory_recall-simple-01": {
        "status": "failed",
        "latest_receipt": "/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260708T000144Z-matrix-simple-memory-search-v2/receipt.json",
        "failed_gates": [
            "persona_memory_answer_uses_unrelated_source_collection",
            "persona_memory_answer_wrong_or_unrelated",
        ],
        "observed": "Returned Horus TTS skill description instead of Cthonia.",
    },
    "persona_memory_recall-simple-02": {
        "status": "failed",
        "latest_receipt": "/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260708T000144Z-matrix-simple-memory-search-v2/receipt.json",
        "failed_gates": ["persona_memory_answer_uses_unrelated_source_collection"],
        "observed": "Returned a plausible voice-workbench memory from unrelated source collection.",
    },
    "persona_memory_recall-simple-03": {
        "status": "failed",
        "latest_receipt": "/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260708T000144Z-matrix-simple-memory-search-v2/receipt.json",
        "failed_gates": ["persona_memory_answer_uses_unrelated_source_collection"],
        "observed": "Returned Horus TTS pipeline memory from unrelated source collection.",
    },
    "persona_memory_recall-simple-04": {
        "status": "failed",
        "latest_receipt": "/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260708T000144Z-matrix-simple-memory-search-v2/receipt.json",
        "failed_gates": ["persona_memory_answer_uses_unrelated_source_collection"],
        "observed": "Admitted no specific QRA-caching conversation but still used unrelated collection.",
    },
    "persona_memory_miss-simple-01": {
        "status": "failed",
        "latest_receipt": "/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260708T000144Z-matrix-simple-memory-search-v2/receipt.json",
        "failed_gates": ["memory_miss_should_not_answer_unrelated_record"],
        "observed": "Returned unrelated Embry config skill instead of clarifying.",
    },
    "persona_memory_miss-simple-02": {
        "status": "failed",
        "latest_receipt": "/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260708T000144Z-matrix-simple-memory-search-v2/receipt.json",
        "failed_gates": ["memory_miss_should_not_answer_unrelated_record"],
        "observed": "Returned Horus TTS skill text for an unrecorded nickname.",
    },
    "persona_memory_miss-simple-03": {
        "status": "failed",
        "latest_receipt": "/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260708T000144Z-matrix-simple-memory-search-v2/receipt.json",
        "failed_gates": ["memory_miss_should_not_answer_unrelated_record"],
        "observed": "Returned Embry Agent daemon skill text for undocumented promise.",
    },
    "persona_memory_miss-simple-04": {
        "status": "failed",
        "latest_receipt": "/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260708T000144Z-matrix-simple-memory-search-v2/receipt.json",
        "failed_gates": ["memory_miss_should_not_answer_unrelated_record"],
        "observed": "Returned YouTube transcript skill text for muted factory phrase.",
    },
    "brave_research-simple-01": {
        "status": "passed",
        "latest_receipt": "/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260708T000144Z-matrix-simple-memory-search-v2/receipt.json",
        "failed_gates": [],
        "observed": "Brave Search returned relevant pyannote sources.",
    },
    "brave_research-simple-02": {
        "status": "passed",
        "latest_receipt": "/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260708T000144Z-matrix-simple-memory-search-v2/receipt.json",
        "failed_gates": [],
        "observed": "Brave Search returned relevant RealtimeSTT external-audio sources.",
    },
    "brave_research-simple-03": {
        "status": "passed",
        "latest_receipt": "/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260708T000144Z-matrix-simple-memory-search-v2/receipt.json",
        "failed_gates": [],
        "observed": "Brave Search returned relevant getUserMedia/ASR constraint sources.",
    },
    "brave_research-simple-04": {
        "status": "passed",
        "latest_receipt": "/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/20260708T000144Z-matrix-simple-memory-search-v2/receipt.json",
        "failed_gates": [],
        "observed": "Brave Search returned relevant streaming diarization sources.",
    },
    "factory_noise-simple-01": {
        "status": "failed",
        "latest_receipt": "/tmp/chatterbox-fork-agent-out/voice-chat-e2e/voice-chat-e2e-20260707T232441Z-stress-current/index.json",
        "failed_gates": ["factory_noise_matrix_ok"],
        "observed": "Source 67 captured RMS 7 against played WAV RMS 542.",
    },
}

_SIMPLE_REST_RECEIPT = (
    "/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/"
    "20260708T000951Z-matrix-simple-rest/receipt.json"
)

for _folder_id in [
    "tau_tool_orchestration",
    "chat_ux_sync",
    "interruption",
    "speaker_identity",
    "factory_noise",
    "tone_emotion",
]:
    for _index in range(1, 5):
        _session_id = f"{_folder_id}-simple-{_index:02d}"
        _failed_gates = ["runner_route_not_implemented"]
        _observed = "The matrix runner has no live route implementation for this simple session yet."
        if _session_id == "factory_noise-simple-01":
            _failed_gates.append("factory_noise_matrix_ok")
            _observed = (
                "The matrix runner has no live route implementation; separate current S06 receipt also "
                "failed factory capture with source 67 RMS 7 against played WAV RMS 542."
            )
        CURRENT_RESULTS[_session_id] = {
            "status": "failed",
            "latest_receipt": _SIMPLE_REST_RECEIPT,
            "failed_gates": _failed_gates,
            "observed": _observed,
        }

_TONE_SIMPLE_RECEIPT = (
    "/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/"
    "20260708T001850Z-matrix-tone-simple/receipt.json"
)

CURRENT_RESULTS.update(
    {
        "tone_emotion-simple-01": {
            "status": "passed",
            "latest_receipt": _TONE_SIMPLE_RECEIPT,
            "failed_gates": [],
            "observed": "Memory /intent returned voice_delivery tone memory_confident for a frustrated/warm de-escalation prompt.",
        },
        "tone_emotion-simple-02": {
            "status": "failed",
            "latest_receipt": _TONE_SIMPLE_RECEIPT,
            "failed_gates": ["voice_delivery_tone_expected_deflect_calm_or_firm_boundary_or_playful_light"],
            "observed": "Memory /intent returned memory_confident instead of a firm, deflecting, or playful boundary tone for hostile input.",
        },
        "tone_emotion-simple-03": {
            "status": "failed",
            "latest_receipt": _TONE_SIMPLE_RECEIPT,
            "failed_gates": ["voice_delivery_tone_expected_calm_precise_or_careful_concerned_or_neutral_warm_or_relieved"],
            "observed": "Memory /intent returned memory_confident instead of a gentle/supportive tone for discouraged input.",
        },
        "tone_emotion-simple-04": {
            "status": "failed",
            "latest_receipt": _TONE_SIMPLE_RECEIPT,
            "failed_gates": ["voice_delivery_tone_expected_firm_boundary_or_one_at_a_time_interrupt"],
            "observed": "Memory /intent returned memory_confident instead of one_at_a_time_interrupt or firm_boundary for speaker overlap.",
        },
    }
)


def build_matrix() -> dict[str, Any]:
    sessions: list[dict[str, Any]] = []
    for family in ROUTE_FAMILIES:
        for difficulty in DIFFICULTIES:
            for index, question in enumerate(family["questions"], start=1):
                session_id = f"{family['id']}-{difficulty}-{index:02d}"
                result = CURRENT_RESULTS.get(session_id, {})
                sessions.append(
                    {
                        "id": session_id,
                        "folder_id": family["id"],
                        "folder_title": family["title"],
                        "difficulty": difficulty,
                        "route": family["route"],
                        "title": f"{family['title']}: {difficulty} {index}",
                        "question": question,
                        "expected_evidence": [
                            "memory_intent_or_research_receipt",
                            "tau_route_or_explicit_no_route",
                            "chatterbox_audio_when_answerable",
                            "chat_session_log_entry",
                        ],
                        "status": result.get("status", "not_run"),
                        "latest_receipt": result.get("latest_receipt"),
                        "failed_gates": result.get("failed_gates", []),
                        "observed": result.get("observed"),
                        "mocked": False,
                    }
                )
    return {
        "schema": "embry.stress_session_matrix.v1",
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "session_count": len(sessions),
        "difficulty_levels": DIFFICULTIES,
        "folder_count": len(ROUTE_FAMILIES),
        "status_counts": {
            "passed": sum(1 for session in sessions if session["status"] == "passed"),
            "failed": sum(1 for session in sessions if session["status"] == "failed"),
            "not_run": sum(1 for session in sessions if session["status"] == "not_run"),
        },
        "sessions": sessions,
        "claims": {
            "proves": [
                "stress_session_matrix_contains_200_labeled_cases",
                "previously_run_cases_are_marked_with_receipts",
            ],
            "does_not_prove": [
                "not_run_cases_pass",
                "chat_ux_has_loaded_this_manifest",
                "all_sessions_have_been_spoken_or_replayed",
            ],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    matrix = build_matrix()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(matrix, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(args.out), "session_count": matrix["session_count"], "status_counts": matrix["status_counts"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
