"""Interruptible voice-conversation harness for Chatterbox agent testing.

This module does not perform ASR, memory recall, or factual reasoning. It
exercises the turn-control layer around a running Chatterbox agent server:
queue answer chunks, synthesize the first chunk, simulate a user interruption,
skip stale old-turn chunks, synthesize a natural recovery utterance, and write a
receipt proving what was spoken or skipped.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from chatterbox.agent.chunking import build_render_plan


INTERRUPTION_ACKNOWLEDGEMENTS = [
    "Got it. I'll stop there.",
    "Okay, switching.",
    "I hear you. Let me redirect.",
    "Right, let me answer that instead.",
    "Okay. Give me a second to re-check the right thread.",
    "Stopping that answer. Let me shift.",
    "Got it. I'm changing direction.",
    "Okay, I caught that.",
    "Understood. I'll pivot.",
    "Right. Let me restart from your correction.",
    "Okay, stopping that thread.",
    "I hear the correction. One second.",
    "Got it. Let me reframe it.",
    "Okay. I'll take the new question.",
    "Right, switching to that now.",
    "Got it. Let me check the better path.",
    "Okay, I won't keep going on that answer.",
    "I hear you. Let me answer the new part.",
    "Right. Give me a second to redirect.",
    "Okay, new direction.",
]

LOW_BUFFER_FILLERS = [
    "Hmm.",
    "Okay.",
    "Let me check.",
    "I'm looking now.",
    "One moment.",
    "Got it.",
    "I see.",
    "Checking that.",
    "Looking into it.",
    "I'm pulling that up.",
    "Almost there.",
    "I have part of it.",
    "That's coming in now.",
    "I'm still checking.",
    "Still with you.",
    "I found something.",
    "Let me verify that.",
    "One check is still running.",
    "I have enough to start.",
    "Here's what I'm seeing.",
    "Hmm. Give me another second.",
    "I'm still here. I'm checking one more thing.",
    "Hold on. I have part of it.",
    "Give me one more second.",
]

WAIT_RESPONSE_RULES = [
    {
        "min_wait_ms": 700,
        "max_wait_ms": 2000,
        "recommended_idle_action": "speak_filler",
        "texts": [
            "Hmm.",
            "Okay.",
            "Let me check.",
            "One moment.",
            "I see.",
        ],
    },
    {
        "min_wait_ms": 2000,
        "max_wait_ms": 5000,
        "recommended_idle_action": "speak_progress",
        "texts": [
            "I'm looking now.",
            "Checking that.",
            "Looking into it.",
            "I'm pulling that up.",
            "Still with you.",
            "That's coming in now.",
        ],
    },
    {
        "min_wait_ms": 5000,
        "max_wait_ms": 8000,
        "recommended_idle_action": "speak_longer_progress",
        "texts": [
            "I have part of it.",
            "I'm still checking.",
            "Let me verify that.",
            "I have enough to start.",
            "Here's what I'm seeing.",
            "Hmm. Give me another second.",
        ],
    },
    {
        "min_wait_ms": 8000,
        "max_wait_ms": None,
        "recommended_idle_action": "speak_then_optional_hum",
        "texts": [
            "I'm still here. I'm checking one more thing.",
            "Hold on. I have part of it.",
            "Give me one more second.",
            "One check is still running.",
            "This will take a little while. You can grab coffee if you want.",
            "This is a longer check. I'll keep working and come back with the answer.",
            "I need a bit more time on this one. I'll stay with it.",
            "This is going to take a minute, so I'll keep checking in.",
        ],
    },
]


ETA_RESPONSE_RULES = [
    {
        "min_wait_ms": 700,
        "max_wait_ms": 2000,
        "texts": [
            "About another second.",
            "I should have it almost immediately.",
        ],
    },
    {
        "min_wait_ms": 2000,
        "max_wait_ms": 5000,
        "texts": [
            "Probably three to five more seconds.",
            "Give me a few more seconds.",
        ],
    },
    {
        "min_wait_ms": 5000,
        "max_wait_ms": 12000,
        "texts": [
            "Probably under ten seconds.",
            "I need a little more time, probably less than ten seconds.",
        ],
    },
    {
        "min_wait_ms": 12000,
        "max_wait_ms": None,
        "texts": [
            "This may take a bit longer. I'll keep checking in.",
            "This is a longer one, likely more than ten seconds.",
        ],
    },
]


def wait_responses_for_expected_delay(expected_wait_ms: int) -> list[str]:
    """Return appropriate cached filler candidates for an expected wait."""
    if expected_wait_ms < 700:
        return []
    for rule in WAIT_RESPONSE_RULES:
        max_wait_ms = rule["max_wait_ms"]
        if expected_wait_ms >= rule["min_wait_ms"] and (max_wait_ms is None or expected_wait_ms < max_wait_ms):
            return list(rule["texts"])
    return []


def eta_responses_for_expected_delay(expected_wait_ms: int) -> list[str]:
    """Return cached ETA response candidates for a human ETA interruption."""
    for rule in ETA_RESPONSE_RULES:
        max_wait_ms = rule["max_wait_ms"]
        if expected_wait_ms >= rule["min_wait_ms"] and (max_wait_ms is None or expected_wait_ms < max_wait_ms):
            return list(rule["texts"])
    return ["I should have it almost immediately."]


INTERNAL_SPOKEN_TERMS = {
    "turn_id",
    "stale chunk",
    "json stream",
    "receipt",
    "memory row",
    "voice coordinator",
    "queued audio",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def post_json(url: str, payload: dict[str, Any], timeout: int = 180) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


async def post_json_async(url: str, payload: dict[str, Any], timeout: int = 180) -> dict[str, Any]:
    return await asyncio.to_thread(post_json, url, payload, timeout)


@dataclass
class EventRecorder:
    path: Path
    conversation_id: str
    sequence: int = 0
    events: list[dict[str, Any]] = field(default_factory=list)

    def emit(
        self,
        event_type: str,
        *,
        turn_id: str,
        phase: str,
        status: str,
        artifact_path: str | None = None,
        text: str | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        self.sequence += 1
        event = {
            "type": event_type,
            "conversation_id": self.conversation_id,
            "turn_id": turn_id,
            "sequence": self.sequence,
            "phase": phase,
            "status": status,
            "timestamp": utc_now(),
            "artifact_path": artifact_path,
            "text_sha256": sha256_text(text) if text is not None else None,
            **extra,
        }
        self.events.append(event)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")
        return event


def acknowledgement_for_interrupt(user_text: str, variant_offset: int = 0) -> str:
    if any(word in user_text.lower() for word in ("stop", "cancel", "enough")):
        choices = [
            "Okay, stopping.",
            "Got it. I'll stop there.",
            "Okay, I won't keep going on that answer.",
        ]
        return choices[variant_offset % len(choices)]
    return INTERRUPTION_ACKNOWLEDGEMENTS[variant_offset % len(INTERRUPTION_ACKNOWLEDGEMENTS)]


def has_internal_terms(text: str) -> bool:
    lower = text.lower()
    return any(term in lower for term in INTERNAL_SPOKEN_TERMS)


async def synthesize_chunk(
    *,
    base_url: str,
    turn_id: str,
    chunk_id: str,
    text: str,
    label: str,
    delivery_stage: str,
    recorder: EventRecorder,
) -> dict[str, Any]:
    recorder.emit(
        "tts.submitted",
        turn_id=turn_id,
        phase="tts",
        status="submitted",
        text=text,
        chunk_id=chunk_id,
        delivery_stage=delivery_stage,
    )
    result = await post_json_async(
        f"{base_url.rstrip('/')}/synthesize",
        {
            "text": text,
            "label": label,
            "delivery_stage": delivery_stage,
        },
    )
    recorder.emit(
        "speech.played",
        turn_id=turn_id,
        phase="playback",
        status="played" if result.get("ok") else "failed",
        artifact_path=result.get("audio"),
        text=text,
        chunk_id=chunk_id,
        delivery_stage=delivery_stage,
        duration_seconds=result.get("duration_seconds"),
        failed_gates=result.get("failed_gates") or [],
    )
    return result


async def run_interruption_scenario(
    *,
    base_url: str,
    out_dir: Path,
    question: str,
    first_answer: str,
    interrupt_text: str,
    new_answer: str,
    conversation_id: str = "embry-interruption-smoke",
    variant_offset: int = 0,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    events_path = out_dir / "task-events.jsonl"
    if events_path.exists():
        events_path.unlink()
    recorder = EventRecorder(events_path, conversation_id=conversation_id)
    failed_gates: list[str] = []

    old_turn_id = f"turn-{uuid4().hex[:8]}"
    new_turn_id = f"turn-{uuid4().hex[:8]}"
    started = time.perf_counter()

    old_plan = build_render_plan(
        first_answer,
        max_chars=135,
        pause_after_ms=300,
        completion_cue="Anything else you need?",
    )
    recorder.emit("turn.started", turn_id=old_turn_id, phase="turn", status="started", text=question)
    for chunk in old_plan["chunks"]:
        recorder.emit(
            "speech.queued",
            turn_id=old_turn_id,
            phase="speech_queue",
            status="queued",
            text=chunk["text"],
            chunk_id=f"old-answer-{chunk['index']}",
            delivery_stage=chunk["delivery_stage"],
            can_interrupt_after=chunk["can_interrupt_after"],
        )

    spoken_results: list[dict[str, Any]] = []
    stale_skipped: list[dict[str, Any]] = []
    first_chunk = old_plan["chunks"][0]
    spoken_results.append(
        await synthesize_chunk(
            base_url=base_url,
            turn_id=old_turn_id,
            chunk_id="old-answer-1",
            text=first_chunk["text"],
            label="interruption_smoke_old_answer_1",
            delivery_stage=first_chunk["delivery_stage"],
            recorder=recorder,
        )
    )

    recorder.emit(
        "interruption.requested",
        turn_id=old_turn_id,
        phase="barge_in",
        status="requested",
        text=interrupt_text,
        old_turn_id=old_turn_id,
        new_turn_id=new_turn_id,
    )
    recorder.emit(
        "playback.stopped",
        turn_id=old_turn_id,
        phase="playback",
        status="stopped_for_interruption",
        old_turn_id=old_turn_id,
        new_turn_id=new_turn_id,
    )

    for chunk in old_plan["chunks"][1:]:
        event = recorder.emit(
            "speech.stale_skipped",
            turn_id=old_turn_id,
            phase="speech_queue",
            status="skipped",
            text=chunk["text"],
            chunk_id=f"old-answer-{chunk['index']}",
            old_turn_id=old_turn_id,
            new_turn_id=new_turn_id,
        )
        stale_skipped.append(event)

    acknowledgement = acknowledgement_for_interrupt(interrupt_text, variant_offset=variant_offset)
    recorder.emit("turn.started", turn_id=new_turn_id, phase="turn", status="started", text=interrupt_text)
    recorder.emit(
        "speech.queued",
        turn_id=new_turn_id,
        phase="speech_queue",
        status="queued",
        text=acknowledgement,
        chunk_id="interrupt-ack",
        delivery_stage="holding",
    )
    ack_result = await synthesize_chunk(
        base_url=base_url,
        turn_id=new_turn_id,
        chunk_id="interrupt-ack",
        text=acknowledgement,
        label="interruption_smoke_interrupt_ack",
        delivery_stage="holding",
        recorder=recorder,
    )
    spoken_results.append(ack_result)

    new_plan = build_render_plan(new_answer, max_chars=160, pause_after_ms=250)
    first_new_chunk = new_plan["chunks"][0]
    recorder.emit(
        "speech.queued",
        turn_id=new_turn_id,
        phase="speech_queue",
        status="queued",
        text=first_new_chunk["text"],
        chunk_id="new-answer-1",
        delivery_stage=first_new_chunk["delivery_stage"],
    )
    spoken_results.append(
        await synthesize_chunk(
            base_url=base_url,
            turn_id=new_turn_id,
            chunk_id="new-answer-1",
            text=first_new_chunk["text"],
            label="interruption_smoke_new_answer_1",
            delivery_stage=first_new_chunk["delivery_stage"],
            recorder=recorder,
        )
    )
    recorder.emit("turn.final", turn_id=new_turn_id, phase="turn", status="final")

    stale_chunk_ids = {event["chunk_id"] for event in stale_skipped}
    submitted_chunk_ids = {
        event["chunk_id"]
        for event in recorder.events
        if event["type"] == "tts.submitted"
    }
    if not stale_skipped:
        failed_gates.append("stale_chunks_skipped_after_interruption")
    if stale_chunk_ids & submitted_chunk_ids:
        failed_gates.append("stale_chunks_not_submitted_to_tts")
    if not ack_result.get("ok"):
        failed_gates.append("interrupt_ack_tts_ok")
    if int(((ack_result.get("metrics") or {}).get("bytes")) or 0) <= 44:
        failed_gates.append("interrupt_ack_audio_non_empty")
    if has_internal_terms(acknowledgement):
        failed_gates.append("interrupt_ack_no_internal_terms")
    if not any(event["type"] == "interruption.requested" for event in recorder.events):
        failed_gates.append("interruption_event_present")

    receipt = {
        "ok": not failed_gates,
        "mocked": False,
        "live": True,
        "conversation_id": conversation_id,
        "old_turn_id": old_turn_id,
        "new_turn_id": new_turn_id,
        "question": question,
        "interrupt_text": interrupt_text,
        "acknowledgement": acknowledgement,
        "acknowledgement_sha256": sha256_text(acknowledgement),
        "acknowledgement_variants_available": len(INTERRUPTION_ACKNOWLEDGEMENTS),
        "old_plan": old_plan,
        "new_plan": new_plan,
        "spoken_results": spoken_results,
        "stale_skipped_count": len(stale_skipped),
        "stale_skipped_chunk_ids": sorted(stale_chunk_ids),
        "submitted_chunk_ids": sorted(submitted_chunk_ids),
        "events_path": str(events_path),
        "event_count": len(recorder.events),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "failed_gates": failed_gates,
    }
    (out_dir / "final-response.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt
