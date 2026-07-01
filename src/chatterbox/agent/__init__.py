"""Agent-facing helpers for Chatterbox Turbo."""

from .chunking import build_render_plan, split_spoken_chunks
from .presets import DEFAULT_GENERATION_PARAMS, STAGE_PRESETS, generation_params_for_stage

__all__ = [
    "DEFAULT_GENERATION_PARAMS",
    "STAGE_PRESETS",
    "build_render_plan",
    "generation_params_for_stage",
    "split_spoken_chunks",
]
