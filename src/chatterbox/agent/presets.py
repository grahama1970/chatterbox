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


# Per-tone calibration for audible emotion realization (chatterbox#22).
# intensity/valence feed the base-affect knobs (top-weighted response curve, so
# emotional extremes get extreme values); tempo adds a deterministic duration
# axis so pace-of-speech separates tones the f0/energy axes cannot.
# Active only when a request opts into emotion_realization=audible.
TONE_CALIBRATION: dict[str, dict[str, float]] = {
    "neutral_warm": {"intensity": 0.4, "valence": 0.3, "tempo": 1.0},
    "calm_precise": {"intensity": 0.3, "valence": 0.1, "tempo": 0.93},
    "careful_concerned": {"intensity": 0.55, "valence": -0.45, "tempo": 0.94},
    "serious_low_energy": {"intensity": 0.1, "valence": -0.9, "tempo": 0.85},
    "memory_confident": {"intensity": 0.7, "valence": 0.6, "tempo": 1.04},
    "memory_uncertain": {"intensity": 0.65, "valence": -0.45, "tempo": 0.95},
    "curious_searching": {"intensity": 0.8, "valence": 0.4, "tempo": 1.06},
    "playful_light": {"intensity": 0.85, "valence": 0.75, "tempo": 1.12},
    "relieved": {"intensity": 0.75, "valence": 0.65, "tempo": 1.0},
    "firm_boundary": {"intensity": 0.95, "valence": -0.85, "tempo": 0.97},
    "identity_clarification": {"intensity": 0.75, "valence": -0.2, "tempo": 1.0},
    "one_at_a_time_interrupt": {"intensity": 0.9, "valence": -0.7, "tempo": 1.15},
    "deflect_calm": {"intensity": 0.6, "valence": -0.65, "tempo": 0.92},
    "grief_safe": {"intensity": 0.3, "valence": -0.7, "tempo": 0.87},
    "wait_presence": {"intensity": 0.2, "valence": 0.0, "tempo": 0.9},
}


PACE_TEMPO_FACTORS: dict[str, float] = {
    "slow": 0.85,
    "measured": 0.92,
    "neutral": 1.0,
    "default": 1.0,
    "brisk": 1.08,
    "fast": 1.18,
}


def pace_tempo_factor(pace: str | None) -> float | None:
    """Tempo factor for a requested pace, or None when the value is unknown."""
    return PACE_TEMPO_FACTORS.get(normalize_voice_token(pace))


# The nine paralinguistic event tags the Turbo model consumes natively. Turbo
# realizes these as acoustic events (chatterbox#24: n=3 with [laugh] measured
# [4.32, 5.24, 4.32]s vs [4.24, 3.76, 3.36]s without -- non-overlapping, ~0.84s
# mean delta, so the tag is a real event and not silently stripped). The base
# model has no tag vocabulary and synthesizes an inline tag as literal text.
CHATTERBOX_EVENT_TAGS: tuple[str, ...] = (
    "[clear throat]",
    "[sigh]",
    "[shush]",
    "[cough]",
    "[groan]",
    "[sniff]",
    "[gasp]",
    "[chuckle]",
    "[laugh]",
)

#: Backends that consume CHATTERBOX_EVENT_TAGS natively. A backend outside this
#: set speaks an inline tag as the literal word.
TAG_CONSUMING_BACKENDS: frozenset[str] = frozenset({"chatterbox_turbo"})


def detect_event_tags(text: str | None) -> list[str]:
    """Native event tags present in the render text, in first-appearance order."""
    if not text:
        return []
    lowered = text.lower()
    found = [(lowered.find(tag), tag) for tag in CHATTERBOX_EVENT_TAGS if tag in lowered]
    return [tag for _, tag in sorted(found)]


VOICE_DELIVERY_EFFECT: dict[str, Any] = {
    "schema": "chatterbox.voice_delivery_effect.v1",
    "engine": "chatterbox_turbo",
    "fields": {
        "pace": {
            "status": "applied",
            "mechanism": "phase_vocoder_time_stretch",
            "tempo_factors": PACE_TEMPO_FACTORS,
            "unknown_value_behavior": "request_only",
            "proof_metric": "duration_seconds scales by 1/tempo_factor; see per-render pace_effect receipt",
        },
        "tone": {
            "status": "audible_with_emotion_realization_audible__request_only_on_default_fast_path",
            "reason": (
                "On the default turbo fast path, tone maps to STAGE_PRESETS which shift "
                "only sampling params; measured acoustic shifts are below same-parameter "
                "stochastic spread, and the params that move affect (exaggeration, "
                "cfg_weight) are ignored by Turbo."
            ),
            "audible_channel": (
                "Set emotion_realization=audible (request field or voice_delivery key) and "
                "the tone alone routes through TONE_CALIBRATION -> chatterbox_base_affect "
                "knobs plus a per-tone tempo, with no knob knowledge required. Explicit "
                "intensity/valence or use_base_emotion also route audibly, as before."
            ),
            "default_policy": (
                "Default is fast (turbo) for latency compatibility with live chat; override "
                "per request or via CHATTERBOX_EMOTION_REALIZATION_DEFAULT=audible."
            ),
            "calibration": "TONE_CALIBRATION; pairwise distinguishability matrix published by the tone_matrix eval case",
        },
        "intensity_valence": {
            "status": "intensity_applied_on_chatterbox_base_affect__valence_perceptually_inert",
            "valence_inertness": {
                "declared": True,
                "evidence": (
                    "Full raw-knob sweep on /synthesize-emotion (cfg_weight 0.1-0.9, "
                    "temperature 0.5-1.1, exaggeration 0.3-1.1; interleaved floor n=4) "
                    "scored by the audeering dimensional model: every axis's perceived-"
                    "valence sweep range (0.043-0.075) fell inside the same-parameter "
                    "floor spread (0.082). No generation knob moves perceived valence "
                    "on the Chatterbox engines. Receipt: docs/proofs/valence_sweep_20260804.json (chatterbox#23)."
                ),
                "consumer_guidance": (
                    "Treat requested valence as engine-internal metadata, not a perceptual "
                    "promise. Perceived tone differentiation comes from arousal (intensity) "
                    "and tempo. A valence-capable engine is future work."
                ),
            },
            "mechanism": "intensity scales exaggeration (0.3+0.9*intensity, clamped 0.3-1.4); negative valence lowers cfg_weight (0.5-0.2*max(0,-valence), clamped 0.3-0.5)",
            "response_curve": {
                "summary": (
                    "Response is nonlinear and top-weighted: audible change is measured "
                    "only near the top of the intensity range. Small deltas sit below the "
                    "renderer's own same-parameter noise floor."
                ),
                "measured": {
                    "audible": "intensity 0.9 / valence -0.8 vs intensity 0.2 / valence -0.2 separated f0_median by 66.6 Hz against an 8.1 Hz same-parameter floor and rms by 3.5x its floor (eval_tone_audibility affect case, 2026-08-04)",
                    "inaudible": "single-axis deltas of 0.25-0.32 intensity from a 0.5 floor moved no metric past a 4-repeat noise floor (persona-dream measurement, chatterbox#21)",
                },
                "consumer_guidance": "Use large intensity/valence contrasts (>=0.5 apart) for audibly distinct arms; do not expect fine-grained gradations to be audible.",
                "perceptual_validation": (
                    "Held-out dimensional emotion model (audeering MSP-Podcast wav2vec2): "
                    "perceived arousal rank-correlates with requested intensity at Spearman "
                    "0.96 across all 15 calibrated tones; perceived valence does NOT track "
                    "the requested valence knob (Spearman ~0.08) -- arousal is the single "
                    "perceptually verified affect dimension. See the machine_listener eval case."
                ),
            },
            "per_render_receipt": "affect_effect (chatterbox.affect_effect.v1)",
        },
        "pause_strategy": {
            "status": "request_only",
            "reason": "No synthesis code path consumes pause_strategy.",
            "audible_channel": "Use per-chunk pause_after_ms, which inserts real silence when segments are combined.",
        },
        "chatterbox_tags": {
            "status": "request_only",
            "reason": (
                "The voice_delivery.chatterbox_tags LIST remains request-only metadata; "
                "invented tokens such as [firm] or [breath] are not model vocabulary. "
                "INLINE tags in the text are different: see paralinguistic_tags."
            ),
        },
        "paralinguistic_tags": {
            "status": "applied_on_tag_consuming_backend__literal_text_elsewhere",
            "accepted_tags": list(CHATTERBOX_EVENT_TAGS),
            "mechanism": "native model vocabulary on chatterbox_turbo; no separate channel",
            "affect_tradeoff": {
                "declared": True,
                "summary": (
                    "Tag realization and the arousal knob axis live on different backends "
                    "and cannot both be applied to one render. chatterbox_turbo consumes "
                    "the event tags but ignores exaggeration/cfg_weight; "
                    "chatterbox_base_affect honors those knobs but speaks the tag as a "
                    "literal word."
                ),
                "resolution": (
                    "When inline event tags are present and tone-derived calibration is the "
                    "only affect source, the render stays on the tag-consuming backend and "
                    "carries the backend-independent TONE_CALIBRATION tempo axis. The "
                    "intensity/valence knob axis is then NOT applied and affect_effect "
                    "reports applied=false with the backend reason."
                ),
                "consumer_override": (
                    "Set voice_delivery.tag_realization='literal' to prefer the arousal "
                    "knobs instead; the render then routes to chatterbox_base_affect and "
                    "tag_handling reports tags_interpreted=false, so a consumer that cannot "
                    "accept a spoken tag word fails closed on the receipt."
                ),
                "explicit_knob_conflict": (
                    "Explicit intensity/valence/use_base_emotion always win the routing, "
                    "because they are a direct instruction. With inline tags present that "
                    "combination is declared unsatisfiable in tags_interpreted_reason "
                    "rather than silently resolved."
                ),
            },
            "proof_metric": "per-render tag_handling receipt; ASR transcript must not contain the tag word on a tag-consuming path",
        },
    },
    "consumer_guidance": (
        "Treat any field not marked applied as receipt metadata. Echo-back of a "
        "request field is never evidence of acoustic effect; only a per-render "
        "*_effect receipt with applied=true is."
    ),
}


#: Template only. Per-render receipts are finalized against the backend actually
#: used, because tag realization is a property of the path, not of the server.
CHATTERBOX_TAG_HANDLING: dict[str, Any] = {
    "schema": "chatterbox.tag_handling.v1",
    "dedicated_tag_channel": "native_event_tags_on_tag_consuming_backend",
    "accepted_tags": list(CHATTERBOX_EVENT_TAGS),
    "tag_consuming_backends": sorted(TAG_CONSUMING_BACKENDS),
    "unknown_tag_behavior": "synthesized_as_literal_text",
    "inline_text_tag_behavior": "consumed_natively_on_tag_consuming_backend__literal_text_on_other_backends",
    "applied_tags": [],
    "detected_tags": [],
    "tags_interpreted": False,
    "tags_interpreted_reason": "no_backend_selected_yet",
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
