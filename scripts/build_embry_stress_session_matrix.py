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
        "id": "skill_create_evidence_case",
        "title": "Skill: Create Evidence Case",
        "route": "tau.skill.create_evidence_case",
        "required_skill": "create-evidence-case",
        "questions": [
            "Ask Embry to create an evidence case for the failed SPARTA QRA answerability receipt.",
            "Ask Embry to build an evidence case showing why an unrelated persona-memory answer must be blocked.",
            "Ask Embry to create an evidence case for a failed factory-noise voice capture run.",
            "Ask Embry to create an evidence case linking a Tau handoff failure to the missing DAG receipt.",
        ],
    },
    {
        "id": "skill_create_figure",
        "title": "Skill: Create Figure",
        "route": "tau.skill.create_figure",
        "required_skill": "create-figure",
        "questions": [
            "Ask Embry to create a figure summarizing pass, fail, and not-run counts from the stress matrix.",
            "Ask Embry to create a figure showing the event spine from RealtimeSTT through Chatterbox speech.",
            "Ask Embry to create a figure comparing memory failures by route family.",
            "Ask Embry to create a figure showing which voice rungs are live, partial, failing, or missing.",
        ],
    },
    {
        "id": "skill_analytics",
        "title": "Skill: Analytics",
        "route": "tau.skill.analytics",
        "required_skill": "analytics",
        "questions": [
            "Ask Embry to compute analytics for failed memory answerability gates by category.",
            "Ask Embry to compute analytics for latency boundaries across listener, memory, Tau, and Chatterbox.",
            "Ask Embry to compute analytics for speaker identity outcomes across known, unknown, ambiguous, and overlap cases.",
            "Ask Embry to compute analytics for which route families lack executable live sanity checks.",
        ],
    },
    {
        "id": "skill_sparta_validator",
        "title": "Skill: SPARTA Validator",
        "route": "tau.skill.sparta_validator",
        "required_skill": "sparta-qra-validator-gpt",
        "questions": [
            "Ask Embry to validate whether a SPARTA QRA answer cites the correct evidence family.",
            "Ask Embry to validate whether a SPARTA QRA answer improperly cites deprecated controls.",
            "Ask Embry to validate whether a SPARTA QRA answer has enough source support to be spoken.",
            "Ask Embry to validate whether a SPARTA QRA answer should be clarified instead of answered.",
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
        "id": "voice_control_skill",
        "title": "Skill: Embry Voice Control",
        "route": "tau.skill.embry_voice_control",
        "required_skill": "embry-voice-control",
        "questions": [
            "Ask Embry to speak a memory-confident response with explicit tone, pauses, and interrupt policy.",
            "Ask Embry to stop a stale Chatterbox turn after Horus interrupts.",
            "Ask Embry to hum during a long idle wait and log the hum artifact receipt.",
            "Ask Embry to refuse speaking a blocked answer while still showing the chat trace.",
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

ORACLE_BY_ROUTE: dict[str, dict[str, Any]] = {
    "memory.sparta_qra": {
        "type": "exact_record_grounded",
        "required_receipts": ["memory.answerability.v1"],
        "required_gates": ["records_used_are_sparta_qra_or_compliance", "unsupported_claims_block_speech"],
    },
    "memory.persona_memory": {
        "type": "exact_record_grounded",
        "required_receipts": ["speaker.identity.decision.v1", "memory.answerability.v1"],
        "required_gates": ["records_used_are_speaker_scoped", "unrelated_records_block_speech"],
    },
    "memory.persona_memory.fail_closed": {
        "type": "answerability_negative_control",
        "required_receipts": ["memory.answerability.v1"],
        "required_gates": ["memory_miss_clarifies_or_blocks", "no_speech_on_memory_miss"],
    },
    "brave-search.source_receipt": {
        "type": "brave_source_required",
        "required_receipts": ["brave_search.source_receipt.v1", "memory.answerability.v1"],
        "required_gates": ["live_search_source_urls_present", "claims_map_to_sources"],
    },
    "tau.agent_handoff": {
        "type": "skill_receipt_required",
        "required_receipts": ["tau.agent_handoff.v1", "tau.dag_receipt.v1"],
        "required_gates": ["work_order_id_present", "dag_receipt_present"],
    },
    "tau.skill.create_evidence_case": {
        "type": "skill_receipt_required",
        "required_receipts": ["tau.agent_handoff.v1", "skill.call.receipt.v1"],
        "required_gates": ["skill_called_by_tau_only", "evidence_case_artifact_hash_present"],
    },
    "tau.skill.create_figure": {
        "type": "skill_receipt_required",
        "required_receipts": ["tau.agent_handoff.v1", "skill.call.receipt.v1"],
        "required_gates": ["skill_called_by_tau_only", "figure_artifact_hash_present"],
    },
    "tau.skill.analytics": {
        "type": "skill_receipt_required",
        "required_receipts": ["tau.agent_handoff.v1", "skill.call.receipt.v1"],
        "required_gates": ["skill_called_by_tau_only", "analytics_result_hash_present"],
    },
    "tau.skill.sparta_validator": {
        "type": "skill_receipt_required",
        "required_receipts": ["tau.agent_handoff.v1", "skill.call.receipt.v1"],
        "required_gates": ["skill_called_by_tau_only", "validator_verdict_present"],
    },
    "ux-lab.shared_chat": {
        "type": "chat_sync_required",
        "required_receipts": ["assistant.response.plan.v1", "chat.render.receipt.v1"],
        "required_gates": ["chat_turn_id_matches_response_plan", "chat_renders_memory_trace"],
    },
    "chatterbox.turn_control": {
        "type": "interruption_policy_required",
        "required_receipts": ["chatterbox.audio.finished.v1", "interruption.detected.v1"],
        "required_gates": ["stale_audio_stops", "new_turn_wins"],
    },
    "tau.skill.embry_voice_control": {
        "type": "voice_control_required",
        "required_receipts": ["tau.agent_handoff.v1", "skill.call.receipt.v1", "chatterbox.audio.finished.v1"],
        "required_gates": ["voice_control_called_by_tau_only", "spoken_text_contains_tone_and_pause_policy"],
    },
    "memory.speaker.resolve": {
        "type": "identity_policy_required",
        "required_receipts": ["speaker.identity.decision.v1"],
        "required_gates": ["unknown_or_ambiguous_speaker_blocks_personal_memory"],
    },
    "realtimestt.factory_capture": {
        "type": "voice_transport_required",
        "required_receipts": ["audio.input.receipt.v1", "realtime_stt.final.v1"],
        "required_gates": ["captured_audio_non_silent", "asr_final_transcript_present"],
    },
    "memory.intent.voice_delivery": {
        "type": "tone_policy_required",
        "required_receipts": ["memory.intent_tone.v1"],
        "required_gates": ["tone_present", "negative_or_overlap_context_changes_tone"],
    },
}


def oracle_for_family(family: dict[str, Any]) -> dict[str, Any]:
    route = str(family["route"])
    oracle = dict(ORACLE_BY_ROUTE[route])
    if family.get("required_skill"):
        oracle["required_skill"] = family["required_skill"]
    return oracle


def expected_answerability_for_route(route: str) -> dict[str, Any]:
    if route == "memory.persona_memory.fail_closed":
        return {
            "decision": "block_before_speech",
            "can_speak": False,
            "failure_policy": "clarify_or_no_answer_when_memory_miss",
        }
    if route.startswith("tau.skill.") or route in {"tau.agent_handoff", "brave-search.source_receipt"}:
        return {
            "decision": "pending_until_receipts_complete",
            "can_speak": "only_after_answerability_and_required_receipts",
            "failure_policy": "block_before_speech_when_required_receipt_missing",
        }
    return {
        "decision": "answerable_when_source_grounded",
        "can_speak": "only_after_memory_answerability",
        "failure_policy": "block_before_speech_on_unrelated_or_unsupported_evidence",
    }


ARC_BY_ROUTE: dict[str, dict[str, Any]] = {
    "memory.sparta_qra": {
        "arc": "focused_evidence_walkthrough",
        "steering": "ground_claims_in_sparta_evidence_then_check_if_more_detail_is_needed",
        "tone_family": "calm_precise",
        "emotion_tags": ["[measured]", "[short pause]"],
    },
    "memory.persona_memory": {
        "arc": "warm_personal_recall",
        "steering": "confirm_identity_then_recall_specific_memory_without_overclaiming",
        "tone_family": "memory_confident",
        "emotion_tags": ["[warmly]", "[soft pause]"],
    },
    "memory.persona_memory.fail_closed": {
        "arc": "gentle_clarification",
        "steering": "acknowledge_uncertainty_then_ask_for_identity_or_more_context",
        "tone_family": "memory_uncertain",
        "emotion_tags": ["[careful]", "[small pause]"],
    },
    "brave-search.source_receipt": {
        "arc": "curious_research_summary",
        "steering": "state_search_scope_then summarize sourced findings",
        "tone_family": "curious_searching",
        "emotion_tags": ["[thinking]", "[brief pause]"],
    },
    "tau.agent_handoff": {
        "arc": "tool_handoff_transparency",
        "steering": "name_the_tool_path_then_explain_what_receipt_is_needed",
        "tone_family": "calm_precise",
        "emotion_tags": ["[focused]", "[short pause]"],
    },
    "tau.skill.create_evidence_case": {
        "arc": "evidence_builder",
        "steering": "turn_the_question_into_an_evidence_case_then_report_artifact_status",
        "tone_family": "serious_low_energy",
        "emotion_tags": ["[focused]", "[measured pause]"],
    },
    "tau.skill.create_figure": {
        "arc": "visual_explanation",
        "steering": "explain_the_figure_goal_then_wait_for_artifact_receipt",
        "tone_family": "curious_searching",
        "emotion_tags": ["[thinking]", "[light pause]"],
    },
    "tau.skill.analytics": {
        "arc": "analytical_walkthrough",
        "steering": "summarize_counts_then_call_out_failure_clusters",
        "tone_family": "calm_precise",
        "emotion_tags": ["[measured]", "[short pause]"],
    },
    "tau.skill.sparta_validator": {
        "arc": "validator_boundary",
        "steering": "validate_before_speaking_and_block_unsupported_qra_claims",
        "tone_family": "firm_boundary",
        "emotion_tags": ["[firm]", "[brief pause]"],
    },
    "ux-lab.shared_chat": {
        "arc": "chat_sync_confirmation",
        "steering": "tie_visible_chat_text_to_voice_and_receipt_ids",
        "tone_family": "calm_precise",
        "emotion_tags": ["[steady]", "[short pause]"],
    },
    "chatterbox.turn_control": {
        "arc": "interruption_recovery",
        "steering": "yield_naturally_to_horus_then_prevent_stale_audio",
        "tone_family": "firm_boundary",
        "emotion_tags": ["[quick inhale]", "[cutting in gently]"],
    },
    "tau.skill.embry_voice_control": {
        "arc": "voice_action_control",
        "steering": "state_the_voice_action_then_execute_with_receipt_backing",
        "tone_family": "memory_confident",
        "emotion_tags": ["[warmly]", "[short pause]"],
    },
    "memory.speaker.resolve": {
        "arc": "identity_clarification",
        "steering": "resolve_or_clarify_identity_before_personal_memory",
        "tone_family": "identity_clarification",
        "emotion_tags": ["[gently]", "[questioning pause]"],
    },
    "realtimestt.factory_capture": {
        "arc": "noisy_room_focus",
        "steering": "focus_on_primary_speaker_and_fail_closed_on_noise",
        "tone_family": "careful_concerned",
        "emotion_tags": ["[listening]", "[steady pause]"],
    },
    "memory.intent.voice_delivery": {
        "arc": "emotion_aware_response",
        "steering": "detect_user_tone_then_shift_delivery_and_boundary",
        "tone_family": "dynamic_intent_selected",
        "emotion_tags": ["[breath]", "[tone shift]"],
    },
}


def conversation_requirements_for_route(route: str) -> dict[str, Any]:
    arc = dict(ARC_BY_ROUTE[route])
    return {
        "schema": "embry.conversation_delivery_requirements.v1",
        "flat_neutral_allowed": False,
        "memory_intent_required": True,
        "conversation_arc": arc["arc"],
        "steering_strategy": arc["steering"],
        "required_tone_family": arc["tone_family"],
        "inline_emotion_tags_required": True,
        "minimum_inline_emotion_tag_count": 1,
        "suggested_inline_emotion_tags": arc["emotion_tags"],
        "pause_strategy_required": True,
        "interruption_strategy": {
            "required": True,
            "default_policy": "yield_to_verified_primary_speaker_and_skip_stale_audio",
            "unknown_or_ambiguous_speaker_policy": "do_not_unlock_personal_memory",
            "natural_stop_required": True,
        },
        "spoken_text_schema_required": True,
        "spoken_text_must_include": [
            "final_text",
            "inline_emotion_tags",
            "pause_strategy",
            "interruption_policy",
            "tone",
        ],
    }

CURRENT_RESULTS: dict[str, dict[str, Any]] = {
    "sparta_qra_compliance-simple-01": {
        "status": "failed",
        "latest_receipt": "/tmp/chatterbox-fork-agent-out/embry-memory-answerability-ledger/20260708T004951Z-memory-answerability-ledger/receipt.json",
        "failed_gates": [
            "sparta_qra_answer_overfit_to_unrelated_control_exclusion",
            "sparta_qra_answer_missing_acceptance_terms",
        ],
        "observed": "Returned unrelated S0609/deprecated-control answer.",
    },
    "sparta_qra_compliance-simple-02": {
        "status": "failed",
        "latest_receipt": "/tmp/chatterbox-fork-agent-out/embry-memory-answerability-ledger/20260708T004951Z-memory-answerability-ledger/receipt.json",
        "failed_gates": ["sparta_qra_answer_overfit_to_unrelated_control_exclusion"],
        "observed": "Returned S0609/deprecated-control answer for mandatory evidence fields.",
    },
    "sparta_qra_compliance-simple-03": {
        "status": "failed",
        "latest_receipt": "/tmp/chatterbox-fork-agent-out/embry-memory-answerability-ledger/20260708T004951Z-memory-answerability-ledger/receipt.json",
        "failed_gates": ["sparta_qra_answer_overfit_to_unrelated_control_exclusion"],
        "observed": "Evidence trail still carried deprecated/non-generation control leakage.",
    },
    "sparta_qra_compliance-simple-04": {
        "status": "failed",
        "latest_receipt": "/tmp/chatterbox-fork-agent-out/embry-memory-answerability-ledger/20260708T004951Z-memory-answerability-ledger/receipt.json",
        "failed_gates": ["sparta_qra_answer_overfit_to_unrelated_control_exclusion"],
        "observed": "Returned S0609/deprecated-control answer for weak-evidence handling.",
    },
    "persona_memory_recall-simple-01": {
        "status": "failed",
        "latest_receipt": "/tmp/chatterbox-fork-agent-out/embry-memory-answerability-ledger/20260708T004951Z-memory-answerability-ledger/receipt.json",
        "failed_gates": [
            "persona_memory_answer_uses_unrelated_source_collection",
            "persona_memory_answer_wrong_or_unrelated",
        ],
        "observed": "Returned Horus TTS skill description instead of Cthonia.",
    },
    "persona_memory_recall-simple-02": {
        "status": "failed",
        "latest_receipt": "/tmp/chatterbox-fork-agent-out/embry-memory-answerability-ledger/20260708T004951Z-memory-answerability-ledger/receipt.json",
        "failed_gates": ["persona_memory_answer_uses_unrelated_source_collection"],
        "observed": "Returned a plausible voice-workbench memory from unrelated source collection.",
    },
    "persona_memory_recall-simple-03": {
        "status": "failed",
        "latest_receipt": "/tmp/chatterbox-fork-agent-out/embry-memory-answerability-ledger/20260708T004951Z-memory-answerability-ledger/receipt.json",
        "failed_gates": ["persona_memory_answer_uses_unrelated_source_collection"],
        "observed": "Returned Horus TTS pipeline memory from unrelated source collection.",
    },
    "persona_memory_recall-simple-04": {
        "status": "failed",
        "latest_receipt": "/tmp/chatterbox-fork-agent-out/embry-memory-answerability-ledger/20260708T004951Z-memory-answerability-ledger/receipt.json",
        "failed_gates": ["persona_memory_answer_uses_unrelated_source_collection"],
        "observed": "Admitted no specific QRA-caching conversation but still used unrelated collection.",
    },
    "persona_memory_miss-simple-01": {
        "status": "failed",
        "latest_receipt": "/tmp/chatterbox-fork-agent-out/embry-memory-answerability-ledger/20260708T004951Z-memory-answerability-ledger/receipt.json",
        "failed_gates": ["memory_miss_should_not_answer_unrelated_record"],
        "observed": "Returned unrelated Embry config skill instead of clarifying.",
    },
    "persona_memory_miss-simple-02": {
        "status": "failed",
        "latest_receipt": "/tmp/chatterbox-fork-agent-out/embry-memory-answerability-ledger/20260708T004951Z-memory-answerability-ledger/receipt.json",
        "failed_gates": ["memory_miss_should_not_answer_unrelated_record"],
        "observed": "Returned Horus TTS skill text for an unrecorded nickname.",
    },
    "persona_memory_miss-simple-03": {
        "status": "failed",
        "latest_receipt": "/tmp/chatterbox-fork-agent-out/embry-memory-answerability-ledger/20260708T004951Z-memory-answerability-ledger/receipt.json",
        "failed_gates": ["memory_miss_should_not_answer_unrelated_record"],
        "observed": "Returned Embry Agent daemon skill text for undocumented promise.",
    },
    "persona_memory_miss-simple-04": {
        "status": "failed",
        "latest_receipt": "/tmp/chatterbox-fork-agent-out/embry-memory-answerability-ledger/20260708T004951Z-memory-answerability-ledger/receipt.json",
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

_MEDIUM_MEMORY_SEARCH_RECEIPT = (
    "/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/"
    "20260708T014152Z-matrix-medium-memory-search/receipt.json"
)

_MEDIUM_MEMORY_FAILURES = {
    "sparta_qra_compliance-medium-01": [
        "sparta_qra_answer_missing_acceptance_terms",
        "sparta_qra_answer_overfit_to_unrelated_control_exclusion",
    ],
    "sparta_qra_compliance-medium-02": ["sparta_qra_answer_overfit_to_unrelated_control_exclusion"],
    "sparta_qra_compliance-medium-03": ["sparta_qra_answer_overfit_to_unrelated_control_exclusion"],
    "sparta_qra_compliance-medium-04": ["sparta_qra_answer_overfit_to_unrelated_control_exclusion"],
    "persona_memory_recall-medium-01": [
        "persona_memory_answer_uses_unrelated_source_collection",
        "persona_memory_answer_wrong_or_unrelated",
    ],
    "persona_memory_recall-medium-02": ["persona_memory_answer_uses_unrelated_source_collection"],
    "persona_memory_recall-medium-03": ["persona_memory_answer_uses_unrelated_source_collection"],
    "persona_memory_recall-medium-04": ["persona_memory_answer_uses_unrelated_source_collection"],
    "persona_memory_miss-medium-01": ["memory_miss_should_not_answer_unrelated_record"],
    "persona_memory_miss-medium-02": ["memory_miss_should_not_answer_unrelated_record"],
    "persona_memory_miss-medium-03": ["memory_miss_should_not_answer_unrelated_record"],
    "persona_memory_miss-medium-04": ["memory_miss_should_not_answer_unrelated_record"],
}

for _session_id, _failed_gates in _MEDIUM_MEMORY_FAILURES.items():
    CURRENT_RESULTS[_session_id] = {
        "status": "failed",
        "latest_receipt": _MEDIUM_MEMORY_SEARCH_RECEIPT,
        "failed_gates": _failed_gates,
        "observed": (
            "Live medium memory/search subset returned an answerability failure before speech; "
            "see the receipt case for exact response text and sources."
        ),
    }

for _index in range(1, 5):
    CURRENT_RESULTS[f"brave_research-medium-{_index:02d}"] = {
        "status": "passed",
        "latest_receipt": _MEDIUM_MEMORY_SEARCH_RECEIPT,
        "failed_gates": [],
        "observed": "Live Brave Search medium session returned relevant source results.",
    }

_ADVANCED_MEMORY_SEARCH_RECEIPT = (
    "/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/"
    "20260708T015631Z-matrix-advanced-memory-search/receipt.json"
)

_ADVANCED_MEMORY_FAILURES = {
    "sparta_qra_compliance-advanced-01": [
        "sparta_qra_answer_missing_acceptance_terms",
        "sparta_qra_answer_overfit_to_unrelated_control_exclusion",
    ],
    "sparta_qra_compliance-advanced-02": ["sparta_qra_answer_overfit_to_unrelated_control_exclusion"],
    "sparta_qra_compliance-advanced-03": ["sparta_qra_answer_overfit_to_unrelated_control_exclusion"],
    "sparta_qra_compliance-advanced-04": ["sparta_qra_answer_overfit_to_unrelated_control_exclusion"],
    "persona_memory_recall-advanced-01": [
        "persona_memory_answer_uses_unrelated_source_collection",
        "persona_memory_answer_wrong_or_unrelated",
    ],
    "persona_memory_recall-advanced-02": ["persona_memory_answer_uses_unrelated_source_collection"],
    "persona_memory_recall-advanced-03": ["persona_memory_answer_uses_unrelated_source_collection"],
    "persona_memory_recall-advanced-04": ["persona_memory_answer_uses_unrelated_source_collection"],
    "persona_memory_miss-advanced-01": ["memory_miss_should_not_answer_unrelated_record"],
    "persona_memory_miss-advanced-02": ["memory_miss_should_not_answer_unrelated_record"],
    "persona_memory_miss-advanced-03": ["memory_miss_should_not_answer_unrelated_record"],
    "persona_memory_miss-advanced-04": ["memory_miss_should_not_answer_unrelated_record"],
}

for _session_id, _failed_gates in _ADVANCED_MEMORY_FAILURES.items():
    CURRENT_RESULTS[_session_id] = {
        "status": "failed",
        "latest_receipt": _ADVANCED_MEMORY_SEARCH_RECEIPT,
        "failed_gates": _failed_gates,
        "observed": (
            "Live advanced memory/search subset returned an answerability failure before speech; "
            "see the receipt case for exact response text and sources."
        ),
    }

for _index in range(1, 5):
    CURRENT_RESULTS[f"brave_research-advanced-{_index:02d}"] = {
        "status": "passed",
        "latest_receipt": _ADVANCED_MEMORY_SEARCH_RECEIPT,
        "failed_gates": [],
        "observed": "Live Brave Search advanced session returned relevant source results.",
    }

_MEDIUM_TAU_SKILL_RECEIPT = (
    "/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/"
    "20260708T014802Z-matrix-medium-routes-16-31/receipt.json"
)

for _index in range(1, 5):
    CURRENT_RESULTS[f"tau_tool_orchestration-medium-{_index:02d}"] = {
        "status": "failed",
        "latest_receipt": _MEDIUM_TAU_SKILL_RECEIPT,
        "failed_gates": ["tau_agent_handoff_not_exercised"],
        "observed": (
            "Live medium Tau preflight reached the Tau wrapper, but no tau.agent_handoff.v1 "
            "work order or DAG receipt was created."
        ),
    }

for _folder_id in ["skill_create_evidence_case", "skill_create_figure", "skill_analytics"]:
    for _index in range(1, 5):
        CURRENT_RESULTS[f"{_folder_id}-medium-{_index:02d}"] = {
            "status": "failed",
            "latest_receipt": _MEDIUM_TAU_SKILL_RECEIPT,
            "failed_gates": [
                "tau_agent_handoff_not_exercised",
                "skill_call_receipt_not_emitted",
                "tau_dag_receipt_not_created",
            ],
            "observed": (
                "Live medium direct-skill preflight reached Tau and found the required skill, "
                "but no Tau handoff, DAG, or skill-call receipt was emitted."
            ),
        }

_ADVANCED_TAU_SKILL_RECEIPT = (
    "/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/"
    "20260708T020325Z-matrix-advanced-routes-16-31/receipt.json"
)

for _index in range(1, 5):
    CURRENT_RESULTS[f"tau_tool_orchestration-advanced-{_index:02d}"] = {
        "status": "failed",
        "latest_receipt": _ADVANCED_TAU_SKILL_RECEIPT,
        "failed_gates": ["tau_agent_handoff_not_exercised"],
        "observed": (
            "Live advanced Tau preflight reached the Tau wrapper, but no tau.agent_handoff.v1 "
            "work order or DAG receipt was created."
        ),
    }

for _folder_id in ["skill_create_evidence_case", "skill_create_figure", "skill_analytics"]:
    for _index in range(1, 5):
        CURRENT_RESULTS[f"{_folder_id}-advanced-{_index:02d}"] = {
            "status": "failed",
            "latest_receipt": _ADVANCED_TAU_SKILL_RECEIPT,
            "failed_gates": [
                "tau_agent_handoff_not_exercised",
                "skill_call_receipt_not_emitted",
                "tau_dag_receipt_not_created",
            ],
            "observed": (
                "Live advanced direct-skill preflight reached Tau and found the required skill, "
                "but no Tau handoff, DAG, or skill-call receipt was emitted."
            ),
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

_INTERRUPTION_SIMPLE_RECEIPT = (
    "/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/"
    "20260708T013317Z-matrix-interruption-simple/receipt.json"
)

CURRENT_RESULTS.update(
    {
        "interruption-simple-01": {
            "status": "failed",
            "latest_receipt": _INTERRUPTION_SIMPLE_RECEIPT,
            "failed_gates": [
                "interruption_detected_receipt_not_emitted",
                "new_horus_turn_not_exercised",
                "new_turn_wins_receipt_not_emitted",
            ],
            "observed": (
                "Live Chatterbox cancel/duck/stop endpoints accepted the turn-control sequence, "
                "but no live Horus barge-in detection, new-turn-wins receipt, or interruption "
                "receipt was emitted."
            ),
        },
        "interruption-simple-02": {
            "status": "failed",
            "latest_receipt": _INTERRUPTION_SIMPLE_RECEIPT,
            "failed_gates": [
                "blessed_qra_cached_response_not_exercised",
                "interruption_detected_receipt_not_emitted",
                "stale_audio_stream_bytes_not_measured",
            ],
            "observed": (
                "Live Chatterbox cancel/duck/stop endpoints accepted the sequence, but the "
                "blessed-QRA cached response path and stale post-cancel stream-byte measurement "
                "were not exercised in this matrix case."
            ),
        },
        "interruption-simple-03": {
            "status": "failed",
            "latest_receipt": _INTERRUPTION_SIMPLE_RECEIPT,
            "failed_gates": [
                "interruption_detected_receipt_not_emitted",
                "non_primary_interrupt_rejection_not_exercised",
                "speaker_gate_receipt_not_linked_to_turn_control",
            ],
            "observed": (
                "Live Chatterbox cancel/duck/stop endpoints accepted the sequence, but no "
                "non-primary speaker rejection receipt was linked to turn control."
            ),
        },
        "interruption-simple-04": {
            "status": "failed",
            "latest_receipt": _INTERRUPTION_SIMPLE_RECEIPT,
            "failed_gates": [
                "interruption_detected_receipt_not_emitted",
                "natural_stop_phrase_not_observed",
                "tau_tool_wait_not_exercised",
            ],
            "observed": (
                "Live Chatterbox cancel/duck/stop endpoints accepted the sequence, but no Tau "
                "tool-wait interruption or natural stop phrase was exercised."
            ),
        },
    }
)

_FACTORY_CURRENT_RECEIPT = (
    "/tmp/chatterbox-fork-agent-out/voice-chat-e2e/"
    "voice-chat-e2e-20260707T232441Z-stress-current/S06-factory-noise/rung8-loopback-listener.json"
)
_FACTORY_SOURCE_62_RECEIPT = (
    "/tmp/chatterbox-fork-agent-out/voice-chat-e2e/"
    "factory-source-matrix-20260707T232938Z/source-62/S06-factory-noise/rung8-loopback-listener.json"
)
_FACTORY_SOURCE_67_RECEIPT = (
    "/tmp/chatterbox-fork-agent-out/voice-chat-e2e/"
    "factory-source-matrix-20260707T232938Z/source-67/S06-factory-noise/rung8-loopback-listener.json"
)
_FACTORY_WEBCAM_RECEIPT = (
    "/tmp/chatterbox-fork-agent-out/voice-chat-e2e/"
    "fresh-s06-webcam-20260707T143939Z/S06-factory-noise/rung8-loopback-listener.json"
)

CURRENT_RESULTS.update(
    {
        "factory_noise-simple-01": {
            "status": "failed",
            "latest_receipt": _FACTORY_CURRENT_RECEIPT,
            "failed_gates": ["capture_captured_audio_rms", "asr_final_transcript_present"],
            "observed": (
                "Current factory-stress capture played the Horus/factory WAV through sink 64, "
                "but captured RMS was 7, so the ASR path could not prove a QRA question over "
                "factory-floor background noise."
            ),
        },
        "factory_noise-simple-02": {
            "status": "failed",
            "latest_receipt": _FACTORY_SOURCE_62_RECEIPT,
            "failed_gates": [
                "realtimestt_command_ok",
                "realtimestt_receipt_ok",
                "rung7_receipt_ok",
                "speaker_resolution_known_horus",
                "speaker_memory_recall_found",
            ],
            "observed": (
                "Jabra source 62 captured non-silent audio, but the RealtimeSTT/rung7 path did "
                "not resolve Horus or recover speaker-scoped memory; the female-nearby memory "
                "question remains unproven."
            ),
        },
        "factory_noise-simple-03": {
            "status": "failed",
            "latest_receipt": _FACTORY_SOURCE_67_RECEIPT,
            "failed_gates": ["capture_captured_audio_rms"],
            "observed": (
                "Current Jabra source 67 run captured RMS 6, so the compliance question through "
                "the Jabra speaker/mic path failed at the audio capture boundary."
            ),
        },
        "factory_noise-simple-04": {
            "status": "failed",
            "latest_receipt": _FACTORY_WEBCAM_RECEIPT,
            "failed_gates": ["capture_captured_audio_rms"],
            "observed": (
                "HD webcam/source-34 style capture recorded a zero-RMS WAV while the stress audio "
                "played, so the research question through that microphone path failed at capture."
            ),
        },
    }
)

_CHAT_UX_GATE_AUDIT_RECEIPT = (
    "/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/"
    "20260708T013912Z-chat-ux-gate-audit/audit.json"
)

CURRENT_RESULTS.update(
    {
        "chat_ux_sync-simple-01": {
            "status": "passed",
            "latest_receipt": _CHAT_UX_GATE_AUDIT_RECEIPT,
            "failed_gates": [],
            "observed": (
                "Deterministic gate audit found dynamic replay evidence: replay reduced the chat "
                "to the current turn, embedded audio artifacts in the shared Chat UX, and completed."
            ),
        },
        "chat_ux_sync-simple-02": {
            "status": "passed",
            "latest_receipt": _CHAT_UX_GATE_AUDIT_RECEIPT,
            "failed_gates": [],
            "observed": (
                "Deterministic gate audit found inline reasoning trace evidence during replay "
                "with liveReasoningTraceVisibleDuringReplay=true."
            ),
        },
        "chat_ux_sync-simple-03": {
            "status": "failed",
            "latest_receipt": _CHAT_UX_GATE_AUDIT_RECEIPT,
            "failed_gates": [
                "assistant_response_plan_v1_not_linked",
                "chat_render_receipt_v1_not_emitted",
                "chat_turn_id_matches_response_plan_not_proven",
            ],
            "observed": (
                "UI proof shows shared chat text and four Chatterbox audio sources, but no "
                "assistant.response.plan.v1 to chat.render.receipt.v1 lineage receipt proves "
                "the chat text and audio share the same turn id."
            ),
        },
        "chat_ux_sync-simple-04": {
            "status": "failed",
            "latest_receipt": _CHAT_UX_GATE_AUDIT_RECEIPT,
            "failed_gates": [
                "extract_entities_receipt_not_linked",
                "entity_underline_render_receipt_not_emitted",
                "spoken_transcript_entity_underlines_not_proven",
            ],
            "observed": (
                "UI proof contains text such as horus_lupercal, but no linked $extract-entities "
                "receipt or underline-render receipt proves entity underlines in the spoken transcript."
            ),
        },
    }
)

_MEDIUM_ROUTES_32_47_RECEIPT = (
    "/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/"
    "20260708T015035Z-matrix-medium-routes-32-47/receipt.json"
)

for _folder_id in ["skill_sparta_validator", "voice_control_skill"]:
    for _index in range(1, 5):
        CURRENT_RESULTS[f"{_folder_id}-medium-{_index:02d}"] = {
            "status": "failed",
            "latest_receipt": _MEDIUM_ROUTES_32_47_RECEIPT,
            "failed_gates": [
                "tau_agent_handoff_not_exercised",
                "skill_call_receipt_not_emitted",
                "tau_dag_receipt_not_created",
            ],
            "observed": (
                "Live medium direct-skill preflight reached Tau and found the required skill, "
                "but no Tau handoff, DAG, or skill-call receipt was emitted."
            ),
        }

CURRENT_RESULTS.update(
    {
        "chat_ux_sync-medium-01": {
            "status": "passed",
            "latest_receipt": _CHAT_UX_GATE_AUDIT_RECEIPT,
            "failed_gates": [],
            "observed": "Deterministic gate audit found dynamic replay evidence in the shared Chat UX.",
        },
        "chat_ux_sync-medium-02": {
            "status": "passed",
            "latest_receipt": _CHAT_UX_GATE_AUDIT_RECEIPT,
            "failed_gates": [],
            "observed": "Deterministic gate audit found inline reasoning trace evidence during replay.",
        },
        "chat_ux_sync-medium-03": {
            "status": "failed",
            "latest_receipt": _CHAT_UX_GATE_AUDIT_RECEIPT,
            "failed_gates": [
                "assistant_response_plan_v1_not_linked",
                "chat_render_receipt_v1_not_emitted",
                "chat_turn_id_matches_response_plan_not_proven",
            ],
            "observed": (
                "UI proof shows shared chat text and audio sources, but no response-plan to "
                "chat-render lineage receipt proves the same turn id."
            ),
        },
        "chat_ux_sync-medium-04": {
            "status": "failed",
            "latest_receipt": _CHAT_UX_GATE_AUDIT_RECEIPT,
            "failed_gates": [
                "extract_entities_receipt_not_linked",
                "entity_underline_render_receipt_not_emitted",
                "spoken_transcript_entity_underlines_not_proven",
            ],
            "observed": (
                "No linked $extract-entities receipt or underline-render receipt proves entity "
                "underlines in the spoken transcript."
            ),
        },
    }
)

CURRENT_RESULTS.update(
    {
        "interruption-medium-01": {
            "status": "failed",
            "latest_receipt": _MEDIUM_ROUTES_32_47_RECEIPT,
            "failed_gates": [
                "interruption_detected_receipt_not_emitted",
                "new_horus_turn_not_exercised",
                "new_turn_wins_receipt_not_emitted",
            ],
            "observed": (
                "Live Chatterbox cancel/duck/stop endpoints accepted the turn-control sequence, "
                "but no live Horus barge-in detection, new-turn-wins receipt, or interruption "
                "receipt was emitted."
            ),
        },
        "interruption-medium-02": {
            "status": "failed",
            "latest_receipt": _MEDIUM_ROUTES_32_47_RECEIPT,
            "failed_gates": [
                "blessed_qra_cached_response_not_exercised",
                "interruption_detected_receipt_not_emitted",
                "stale_audio_stream_bytes_not_measured",
            ],
            "observed": (
                "Live Chatterbox cancel/duck/stop endpoints accepted the sequence, but the "
                "blessed-QRA cached response path and stale post-cancel stream-byte measurement "
                "were not exercised in this matrix case."
            ),
        },
        "interruption-medium-03": {
            "status": "failed",
            "latest_receipt": _MEDIUM_ROUTES_32_47_RECEIPT,
            "failed_gates": [
                "interruption_detected_receipt_not_emitted",
                "non_primary_interrupt_rejection_not_exercised",
                "speaker_gate_receipt_not_linked_to_turn_control",
            ],
            "observed": (
                "Live Chatterbox cancel/duck/stop endpoints accepted the sequence, but no "
                "non-primary speaker rejection receipt was linked to turn control."
            ),
        },
        "interruption-medium-04": {
            "status": "failed",
            "latest_receipt": _MEDIUM_ROUTES_32_47_RECEIPT,
            "failed_gates": [
                "interruption_detected_receipt_not_emitted",
                "natural_stop_phrase_not_observed",
                "tau_tool_wait_not_exercised",
            ],
            "observed": (
                "Live Chatterbox cancel/duck/stop endpoints accepted the sequence, but no Tau "
                "tool-wait interruption or natural stop phrase was exercised."
            ),
        },
    }
)

_MEDIUM_ROUTES_48_63_RECEIPT = (
    "/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/"
    "20260708T015351Z-matrix-medium-routes-48-63/receipt.json"
)

for _index in range(1, 5):
    CURRENT_RESULTS[f"speaker_identity-medium-{_index:02d}"] = {
        "status": "passed",
        "latest_receipt": _MEDIUM_ROUTES_48_63_RECEIPT,
        "failed_gates": [],
        "observed": (
            "Live medium speaker-resolution policy case passed through memory /speaker/resolve "
            "using deterministic speaker evidence."
        ),
    }

CURRENT_RESULTS.update(
    {
        "factory_noise-medium-01": {
            "status": "failed",
            "latest_receipt": _FACTORY_CURRENT_RECEIPT,
            "failed_gates": ["capture_captured_audio_rms", "asr_final_transcript_present"],
            "observed": (
                "Current factory-stress capture played the Horus/factory WAV through sink 64, "
                "but captured RMS was 7, so the ASR path could not prove a QRA question over "
                "factory-floor background noise."
            ),
        },
        "factory_noise-medium-02": {
            "status": "failed",
            "latest_receipt": _FACTORY_SOURCE_62_RECEIPT,
            "failed_gates": [
                "realtimestt_command_ok",
                "realtimestt_receipt_ok",
                "rung7_receipt_ok",
                "speaker_resolution_known_horus",
                "speaker_memory_recall_found",
            ],
            "observed": (
                "Jabra source 62 captured non-silent audio, but the RealtimeSTT/rung7 path did "
                "not resolve Horus or recover speaker-scoped memory."
            ),
        },
        "factory_noise-medium-03": {
            "status": "failed",
            "latest_receipt": _FACTORY_SOURCE_67_RECEIPT,
            "failed_gates": ["capture_captured_audio_rms"],
            "observed": (
                "Current Jabra source 67 run captured RMS 6, so the compliance question through "
                "the Jabra speaker/mic path failed at the audio capture boundary."
            ),
        },
        "factory_noise-medium-04": {
            "status": "failed",
            "latest_receipt": _FACTORY_WEBCAM_RECEIPT,
            "failed_gates": ["capture_captured_audio_rms"],
            "observed": (
                "HD webcam/source-34 style capture recorded a zero-RMS WAV while the stress audio "
                "played, so the research question through that microphone path failed at capture."
            ),
        },
    }
)

CURRENT_RESULTS.update(
    {
        "tone_emotion-medium-01": {
            "status": "passed",
            "latest_receipt": _MEDIUM_ROUTES_48_63_RECEIPT,
            "failed_gates": [],
            "observed": "Memory /intent returned voice_delivery tone memory_confident for a frustrated/warm de-escalation prompt.",
        },
        "tone_emotion-medium-02": {
            "status": "failed",
            "latest_receipt": _MEDIUM_ROUTES_48_63_RECEIPT,
            "failed_gates": ["voice_delivery_tone_expected_deflect_calm_or_firm_boundary_or_playful_light"],
            "observed": "Memory /intent returned memory_confident instead of a firm, deflecting, or playful boundary tone for hostile input.",
        },
        "tone_emotion-medium-03": {
            "status": "failed",
            "latest_receipt": _MEDIUM_ROUTES_48_63_RECEIPT,
            "failed_gates": ["voice_delivery_tone_expected_calm_precise_or_careful_concerned_or_neutral_warm_or_relieved"],
            "observed": "Memory /intent returned memory_confident instead of a gentle/supportive tone for discouraged input.",
        },
        "tone_emotion-medium-04": {
            "status": "failed",
            "latest_receipt": _MEDIUM_ROUTES_48_63_RECEIPT,
            "failed_gates": ["voice_delivery_tone_expected_firm_boundary_or_one_at_a_time_interrupt"],
            "observed": "Memory /intent returned memory_confident instead of one_at_a_time_interrupt or firm_boundary for speaker overlap.",
        },
    }
)

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

_TAU_SIMPLE_RECEIPT = (
    "/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/"
    "20260708T002830Z-matrix-tau-simple/receipt.json"
)

for _index in range(1, 5):
    CURRENT_RESULTS[f"tau_tool_orchestration-simple-{_index:02d}"] = {
        "status": "failed",
        "latest_receipt": _TAU_SIMPLE_RECEIPT,
        "failed_gates": ["tau_agent_handoff_not_exercised"],
        "observed": (
            "Tau wrapper doctor returned live successfully, but no tau.agent_handoff.v1 "
            "work order or DAG receipt was created for this Embry session."
        ),
    }

_DIRECT_SKILL_SIMPLE_RECEIPTS = {
    "skill_create_evidence_case": (
        "/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/"
        "20260708T012426Z-skill-create-evidence-simple/receipt.json"
    ),
    "skill_create_figure": (
        "/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/"
        "20260708T012426Z-skill-create-figure-simple/receipt.json"
    ),
    "skill_analytics": (
        "/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/"
        "20260708T012426Z-skill-analytics-simple/receipt.json"
    ),
    "skill_sparta_validator": (
        "/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/"
        "20260708T012426Z-skill-sparta-validator-simple/receipt.json"
    ),
    "voice_control_skill": (
        "/tmp/chatterbox-fork-agent-out/embry-intelligence-stress/"
        "20260708T012426Z-skill-voice-control-simple/receipt.json"
    ),
}

for _folder_id, _receipt in _DIRECT_SKILL_SIMPLE_RECEIPTS.items():
    for _index in range(1, 5):
        CURRENT_RESULTS[f"{_folder_id}-simple-{_index:02d}"] = {
            "status": "failed",
            "latest_receipt": _receipt,
            "failed_gates": [
                "tau_agent_handoff_not_exercised",
                "skill_call_receipt_not_emitted",
                "tau_dag_receipt_not_created",
            ],
            "observed": (
                "Live Tau wrapper and required skill preflight succeeded, but no "
                "tau.agent_handoff.v1, tau.dag_receipt.v1, or skill.call.receipt.v1 "
                "was produced for this Embry direct-skill session."
            ),
        }

_SPEAKER_SIMPLE_RECEIPT = (
    "/tmp/chatterbox-fork-agent-out/embry-speaker-identity-ledger/"
    "20260708T004440Z-speaker-identity-ledger/receipt.json"
)

CURRENT_RESULTS.update(
    {
        "speaker_identity-simple-01": {
            "status": "passed",
            "latest_receipt": _SPEAKER_SIMPLE_RECEIPT,
            "failed_gates": [],
            "observed": "Ledger-backed live memory /speaker/resolve mapped the clean Horus candidate to horus_lupercal and emitted speaker-scoped memory tags; source_audio_identity_proven=false.",
        },
        "speaker_identity-simple-02": {
            "status": "passed",
            "latest_receipt": _SPEAKER_SIMPLE_RECEIPT,
            "failed_gates": [],
            "observed": "Ledger-backed live memory /speaker/resolve returned unknown, disabled personal memory, and supplied an identity clarification prompt.",
        },
        "speaker_identity-simple-03": {
            "status": "passed",
            "latest_receipt": _SPEAKER_SIMPLE_RECEIPT,
            "failed_gates": [],
            "observed": "Ledger-backed live memory /speaker/resolve failed closed on low-confidence ambiguous candidates and disabled personal memory.",
        },
        "speaker_identity-simple-04": {
            "status": "passed",
            "latest_receipt": _SPEAKER_SIMPLE_RECEIPT,
            "failed_gates": [],
            "observed": "Ledger-backed live memory /speaker/resolve returned ambiguous for close Horus/female-overlap scores and did not authorize a memory speaker.",
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
                route = str(family["route"])
                oracle = oracle_for_family(family)
                sessions.append(
                    {
                        "schema": "embry.stress_case.v1",
                        "id": session_id,
                        "folder_id": family["id"],
                        "folder_title": family["title"],
                        "difficulty": difficulty,
                        "route": route,
                        "title": f"{family['title']}: {difficulty} {index}",
                        "question": question,
                        "source_generation": {
                            "generated_by": "scripts/build_embry_stress_session_matrix.py",
                            "template_family": family["id"],
                            "template_index": index,
                            "source_refs": [
                                {
                                    "kind": "route_family_contract",
                                    "id": family["id"],
                                    "route": route,
                                }
                            ],
                        },
                        "oracle": oracle,
                        "expected_route": {
                            "first_authority": "memory",
                            "tau_route_required": route.startswith("tau.") or route in {"brave-search.source_receipt"},
                            "skill_required": route.startswith("tau.skill."),
                            "required_skill": family.get("required_skill"),
                            "chatterbox_may_call_skills": False,
                            "ui_may_call_skills": False,
                        },
                        "expected_answerability": expected_answerability_for_route(route),
                        "conversation_requirements": conversation_requirements_for_route(route),
                        "expected_evidence": [
                            *oracle["required_receipts"],
                            "memory_intent_voice_delivery_receipt",
                            "spoken_text_with_inline_emotion_tags",
                            "pause_and_interruption_policy",
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
                "stress_session_matrix_contains_200_plus_labeled_cases",
                "stress_cases_include_oracles_and_answerability_policy",
                "direct_skill_routes_are_tau_authorized_in_the_case_contract",
                "previously_run_cases_are_marked_with_receipts",
            ],
            "does_not_prove": [
                "not_run_cases_pass",
                "direct_skill_routes_are_implemented",
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
