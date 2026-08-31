"""Shared low-level drawing services used across scenes and overlays."""

from .fade import (
    DEFAULT_FADE_FRAME_COUNT,
    FadeEvent,
    FadePhase,
    FadeThroughBlack,
)
from .palette import (
    DIMMED_PALETTE,
    PaletteShifter,
    create_default_palette_shifter,
    mix_color,
)


__all__ = [
    "DIMMED_PALETTE",
    "DEFAULT_FADE_FRAME_COUNT",
    "FadeEvent",
    "FadePhase",
    "FadeThroughBlack",
    "PaletteShifter",
    "create_default_palette_shifter",
    "mix_color",
]
