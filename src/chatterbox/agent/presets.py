"""Chatterbox Turbo generation presets for voice-agent delivery stages."""

from __future__ import annotations

from typing import Any


ALLOWED_TONES = {
    "neutral_warm",
    "calm_precise",
    "careful_concerned",
    "serious_low_energy",
    "memory_confident",
    "memory_uncertain",
    "curious_searching",
    "playful_light",
    "relieved",
    "firm_boundary",
    "identity_clarification",
    "one_at_a_time_interrupt",
    "deflect_calm",
    "grief_safe",
    "wait_presence",
}

TONE_TO_DELIVERY_STAGE: dict[str, str] = {
    "neutral_warm": "neutral",
    "calm_precise": "neutral",
    "careful_concerned": "slightly_concerned",
    "serious_low_energy": "neutral",
    "memory_confident": "satisfied",
    "memory_uncertain": "slightly_concerned",
    "curious_searching": "holding",
    "playful_light": "positive",
    "relieved": "satisfied",
    "firm_boundary": "deflecting",
    "identity_clarification": "clarifying",
    "one_at_a_time_interrupt": "deflecting",
    "deflect_calm": "deflecting",
    "grief_safe": "slightly_concerned",
    "wait_presence": "holding",
}

DELIVERY_STAGE_ALIASES: dict[str, str] = {
    "setup": "neutral",
    "slightly_concerned": "slightly_concerned",
    "neutral": "neutral",
    "positive": "positive",
    "satisfied": "satisfied",
    "clarify": "clarifying",
    "clarifying": "clarifying",
    "boundary": "deflecting",
    "interrupted": "deflecting",
    "deflect": "deflecting",
    "deflecting": "deflecting",
    "wait": "holding",
    "holding": "holding",
    "closing": "closing",
}

DEFAULT_GENERATION_PARAMS: dict[str, float | int | bool] = {
    "temperature": 0.8,
    "top_p": 0.95,
    "top_k": 1000,
    "repetition_penalty": 1.2,
    "norm_loudness": True,
}


STAGE_PRESETS: dict[str, dict[str, float | int | bool]] = {
    "slightly_concerned": {
        "temperature": 0.72,
        "top_p": 0.90,
        "top_k": 900,
        "repetition_penalty": 1.22,
        "norm_loudness": True,
    },
    "neutral": {
        "temperature": 0.80,
        "top_p": 0.95,
        "top_k": 1000,
        "repetition_penalty": 1.20,
        "norm_loudness": True,
    },
    "positive": {
        "temperature": 0.90,
        "top_p": 0.97,
        "top_k": 1100,
        "repetition_penalty": 1.16,
        "norm_loudness": True,
    },
    "satisfied": {
        "temperature": 0.84,
        "top_p": 0.96,
        "top_k": 1000,
        "repetition_penalty": 1.18,
        "norm_loudness": True,
    },
    "holding": {
        "temperature": 0.76,
        "top_p": 0.93,
        "top_k": 900,
        "repetition_penalty": 1.2,
        "norm_loudness": True,
    },
    "clarifying": {
        "temperature": 0.78,
        "top_p": 0.94,
        "top_k": 950,
        "repetition_penalty": 1.2,
        "norm_loudness": True,
    },
    "deflecting": {
        "temperature": 0.70,
        "top_p": 0.90,
        "top_k": 900,
        "repetition_penalty": 1.24,
        "norm_loudness": True,
    },
    "closing": {
        "temperature": 0.82,
        "top_p": 0.95,
        "top_k": 1000,
        "repetition_penalty": 1.18,
        "norm_loudness": True,
    },
}


def normalize_voice_token(value: str | None) -> str:
    if not value:
        return ""
    return "".join(ch.lower() for ch in value.strip() if ch.isalnum() or ch in "_-")


def normalize_tone(value: str | None) -> str:
    requested = normalize_voice_token(value)
    return requested if requested in ALLOWED_TONES else "neutral_warm"


def normalize_delivery_stage(value: str | None) -> str | None:
    requested = normalize_voice_token(value)
    if not requested:
        return None
    return DELIVERY_STAGE_ALIASES.get(requested, "neutral")


def delivery_stage_for_tone(tone: str | None) -> str:
    return TONE_TO_DELIVERY_STAGE.get(normalize_tone(tone), "neutral")


def effective_delivery_stage(*, tone: str | None, delivery_stage: str | None) -> str:
    return normalize_delivery_stage(delivery_stage) or delivery_stage_for_tone(tone)


TURBO_SUPPORTED_PARAMS = {
    "temperature",
    "top_p",
    "top_k",
    "repetition_penalty",
    "norm_loudness",
}


TURBO_IGNORED_PARAMS = {
    "exaggeration",
    "cfg_weight",
    "min_p",
}


CHATTERBOX_TAG_HANDLING: dict[str, Any] = {
    "schema": "chatterbox.tag_handling.v1",
    "dedicated_tag_channel": "unsupported",
    "accepted_tags": [],
    "unknown_tag_behavior": "ignored",
    "inline_text_tag_behavior": "synthesized_as_literal_text",
    "applied_tags": [],
    "tags_interpreted": False,
}


STAGE_PRESET_AFFECT_STATUS: dict[str, Any] = {
    "schema": "chatterbox.stage_preset_affect_status.v1",
    "status": "not_validated_as_affect_channel",
    "summary": "Turbo stage presets are delivery/generation presets; current n=5 four-arm evidence measured preset-driven shifts below same-parameter stochastic spread.",
    "evidence": {
        "receipt": "/home/graham/workspace/experiments/agent-skills-main/skills/persona-dream/reports/goal_v4/four_arm/four_arm_acoustic_receipt.v2.json",
        "duration_s_flat_spread": 1.36,
        "f0_sd_hz_flat_spread": 21.21,
        "f0_range_hz_flat_spread": 60.85,
    },
    "consumer_guidance": "Do not treat STAGE_PRESETS as a reliable affect channel without fresh receipt evidence clearing same-parameter variance.",
}


def generation_params_for_stage(
    delivery_stage: str | None,
    overrides: dict[str, Any] | None = None,
) -> dict[str, float | int | bool]:
    """Return Turbo generation params for a stage plus validated overrides."""
    params = dict(DEFAULT_GENERATION_PARAMS)
    if delivery_stage:
        params.update(STAGE_PRESETS.get(delivery_stage, {}))
    for key, value in (overrides or {}).items():
        if value is None:
            continue
        if key in TURBO_IGNORED_PARAMS:
            raise ValueError(f"{key} is ignored by Chatterbox Turbo")
        if key not in TURBO_SUPPORTED_PARAMS:
            raise ValueError(f"{key} is not a supported Chatterbox Turbo generation parameter")
        params[key] = value
    return params
