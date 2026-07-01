"""Chatterbox Turbo generation presets for voice-agent delivery stages."""

from __future__ import annotations

from typing import Any


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
