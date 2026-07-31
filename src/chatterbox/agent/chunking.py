"""Sentence-aware render planning for chunk-level Chatterbox synthesis."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

RENDER_PLAN_SCHEMA = "chatterbox.render_plan.v1"

DEFAULT_ARC = [
    {
        "stage": "slightly_concerned",
        "tone": "careful and focused",
        "role": "acknowledge uncertainty and set up the answer",
    },
    {
        "stage": "neutral",
        "tone": "plain and precise",
        "role": "deliver the main factual structure",
    },
    {
        "stage": "positive",
        "tone": "clearer and more confident",
        "role": "show the answer is resolving",
    },
    {
        "stage": "satisfied",
        "tone": "settled and lightly pleased",
        "role": "close with the usable answer",
    },
]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def split_spoken_chunks(text: str, *, max_chars: int = 300) -> list[str]:
    """Split text into sentence-aware chunks around max_chars.

    This intentionally uses a lightweight regex splitter to avoid making the
    always-on agent server depend on a downloaded spaCy pipeline.
    """
    normalized = " ".join(text.split())
    if not normalized:
        return []
    sentences = [
        item.strip()
        for item in re.split(r"(?<=[.!?])\s+", normalized)
        if item.strip()
    ]
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        if len(sentence) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_split_long_sentence(sentence, max_chars=max_chars))
            continue
        if current and len(current) + 1 + len(sentence) > max_chars:
            chunks.append(current)
            current = sentence
        elif current:
            current = f"{current} {sentence}"
        else:
            current = sentence
    if current:
        chunks.append(current)
    return chunks


def _split_long_sentence(sentence: str, *, max_chars: int) -> list[str]:
    parts = [
        part.strip()
        for part in re.split(r"(?<=[;:,-])\s+", sentence)
        if part.strip()
    ]
    if not parts:
        parts = [sentence]
    chunks: list[str] = []
    current = ""
    for part in parts:
        if len(part) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_split_by_words(part, max_chars=max_chars))
            continue
        if current and len(current) + 1 + len(part) > max_chars:
            chunks.append(current)
            current = part
        elif current:
            current = f"{current} {part}"
        else:
            current = part
    if current:
        chunks.append(current)
    return chunks


def _split_by_words(text: str, *, max_chars: int) -> list[str]:
    chunks: list[str] = []
    current = ""
    for word in text.split():
        if current and len(current) + 1 + len(word) > max_chars:
            chunks.append(current)
            current = word
        elif current:
            current = f"{current} {word}"
        else:
            current = word
    if current:
        chunks.append(current)
    return chunks


def stage_for_chunk(index: int, total: int, arc: list[dict[str, str]] | None = None) -> dict[str, str]:
    stages = arc or DEFAULT_ARC
    if total <= 1:
        return dict(stages[-1])
    stage_index = round(((index - 1) / (total - 1)) * (len(stages) - 1))
    return dict(stages[max(0, min(stage_index, len(stages) - 1))])


def build_render_plan(
    answer_text: str,
    *,
    max_chars: int = 300,
    pause_after_ms: int = 250,
    completion_cue: str | None = None,
    arc: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    requested_max_chars = max_chars
    effective_max_chars = min(max_chars, 300)
    chunks = split_spoken_chunks(answer_text, max_chars=effective_max_chars)
    planned_chunks = []
    total = len(chunks)
    for index, text in enumerate(chunks, start=1):
        stage = stage_for_chunk(index, total, arc=arc)
        planned_chunks.append(
            {
                "index": index,
                "total": total,
                "text": text,
                "text_sha256": sha256_text(text),
                "char_len": len(text),
                "delivery_stage": stage["stage"],
                "delivery_tone": stage["tone"],
                "delivery_role": stage["role"],
                "tone": None,
                "requested_tone": None,
                "requested_delivery_stage": None,
                "pace": None,
                "pause_strategy": None,
                "arc_position": round(index / total, 3) if total else 0.0,
                "pause_after_ms": pause_after_ms if index < total else 0,
                "can_interrupt_after": True,
            }
        )
    return {
        "answer_text": answer_text,
        "answer_text_sha256": sha256_text(answer_text),
        "max_chars": effective_max_chars,
        "requested_max_chars": requested_max_chars,
        "chunking_strategy": {
            "name": "sentence_aware_turbo_safety",
            "target_max_chars": effective_max_chars,
            "requested_max_chars": requested_max_chars,
            "turbo_safety_recommended_max_chars": 300,
            "safety_activated": (
                requested_max_chars > effective_max_chars
                or len(answer_text) > effective_max_chars
                or any(len(chunk) > effective_max_chars for chunk in chunks)
            ),
            "hard_cap_enforced": True,
            "splitter": "regex_sentence_then_clause_then_words",
            "does_not_split_inside_words": True,
        },
        "chunks": planned_chunks,
        "chunk_count": len(planned_chunks),
        "completion_cue": completion_cue,
        "completion_cue_sha256": sha256_text(completion_cue) if completion_cue else None,
    }


def render_plan_digest(plan: dict[str, Any]) -> str:
    """Stable digest over the identity-bearing plan fields.

    Excludes presentation-only fields so semantically identical plans produced
    by different entry points hash identically.
    """
    material = {
        "schema": RENDER_PLAN_SCHEMA,
        "answer_text_sha256": plan.get("answer_text_sha256"),
        "completion_cue_sha256": plan.get("completion_cue_sha256"),
        "chunking_strategy": (plan.get("chunking_strategy") or {}).get("name"),
        "max_chars": plan.get("max_chars"),
        "chunks": [
            {
                "index": chunk.get("index"),
                "text_sha256": chunk.get("text_sha256"),
                "delivery_stage": chunk.get("delivery_stage"),
                "tone": chunk.get("tone"),
                "pace": chunk.get("pace"),
                "pause_strategy": chunk.get("pause_strategy"),
                "pause_after_ms": chunk.get("pause_after_ms"),
                "can_interrupt_after": chunk.get("can_interrupt_after"),
            }
            for chunk in plan.get("chunks") or []
        ],
    }
    canonical = json.dumps(material, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def declared_chunk_hash_failures(chunks: list[dict[str, Any]] | None) -> list[str]:
    """Reason codes for caller chunks whose declared text hash does not match.

    Uses the same `chunk_{index}_text_sha256_matches` reason code as the Tau
    voice-render entry point so every entry point fails closed identically.
    """
    failures: list[str] = []
    for index, chunk in enumerate(chunks or [], start=1):
        declared = chunk.get("text_sha256")
        if not declared:
            continue
        text = " ".join(str(chunk.get("text") or "").split())
        if declared != sha256_text(text):
            failures.append(f"chunk_{index}_text_sha256_matches")
    return failures


def compile_render_plan(
    *,
    answer_text: str,
    render_chunks: list[dict[str, Any]] | None = None,
    max_chars: int = 300,
    pause_after_ms: int = 250,
    completion_cue: str | None = None,
    arc: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Single side-effect-free plan compiler shared by every render entry point.

    Caller-supplied `render_chunks` win over `answer_text` splitting; the
    returned plan always carries the versioned schema and a stable digest.
    """
    if render_chunks:
        plan = build_render_plan_from_chunks(
            render_chunks,
            max_chars=max_chars,
            fallback_pause_after_ms=pause_after_ms,
            completion_cue=completion_cue,
        )
    else:
        plan = build_render_plan(
            answer_text,
            max_chars=max_chars,
            pause_after_ms=pause_after_ms,
            completion_cue=completion_cue,
            arc=arc,
        )
    plan["plan_schema"] = RENDER_PLAN_SCHEMA
    plan["render_plan_digest"] = render_plan_digest(plan)
    return plan


def build_render_plan_from_chunks(
    chunks: list[dict[str, Any]],
    *,
    max_chars: int = 300,
    fallback_pause_after_ms: int = 250,
    completion_cue: str | None = None,
) -> dict[str, Any]:
    """Build a render plan from caller-owned chunk boundaries."""
    requested_max_chars = max_chars
    effective_max_chars = min(max_chars, 300)
    planned_chunks = []
    total = len(chunks)
    answer_text_parts = []
    for index, chunk in enumerate(chunks, start=1):
        text = " ".join(str(chunk.get("text") or "").split())
        if not text:
            continue
        answer_text_parts.append(text)
        stage = str(chunk.get("delivery_stage") or stage_for_chunk(index, total)["stage"])
        pause_after_ms = chunk.get("pause_after_ms")
        if pause_after_ms is None:
            pause_after_ms = fallback_pause_after_ms if index < total else 0
        planned_chunks.append(
            {
                "index": index,
                "total": total,
                "text": text,
                "text_sha256": sha256_text(text),
                "char_len": len(text),
                "delivery_stage": stage,
                "delivery_tone": str(chunk.get("tone") or ""),
                "delivery_role": str(chunk.get("role") or f"caller_chunk_{index}"),
                "tone": chunk.get("tone"),
                "requested_tone": chunk.get("requested_tone") or chunk.get("tone"),
                "requested_delivery_stage": chunk.get("requested_delivery_stage") or chunk.get("delivery_stage"),
                "pace": chunk.get("pace"),
                "pause_strategy": chunk.get("pause_strategy"),
                "arc_position": round(index / total, 3) if total else 0.0,
                "pause_after_ms": int(pause_after_ms) if index < total else 0,
                "can_interrupt_after": bool(chunk.get("interruptible", True)),
            }
        )
    answer_text = " ".join(answer_text_parts).strip()
    return {
        "answer_text": answer_text,
        "answer_text_sha256": sha256_text(answer_text),
        "max_chars": effective_max_chars,
        "requested_max_chars": requested_max_chars,
        "chunking_strategy": {
            "name": "caller_supplied_chunks",
            "target_max_chars": effective_max_chars,
            "requested_max_chars": requested_max_chars,
            "turbo_safety_recommended_max_chars": 300,
            "safety_activated": any(len(chunk["text"]) > effective_max_chars for chunk in planned_chunks),
            "hard_cap_enforced": False,
            "splitter": "caller_supplied_speakable_chunks",
            "does_not_split_inside_words": True,
        },
        "chunks": planned_chunks,
        "chunk_count": len(planned_chunks),
        "completion_cue": completion_cue,
        "completion_cue_sha256": sha256_text(completion_cue) if completion_cue else None,
    }
