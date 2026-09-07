"""Shared low-level drawing services used across scenes and overlays."""

from .fade import (
    DEFAULT_FADE_FRAME_COUNT,
    FadeEvent,
    FadePhase,
    FadeThroughBlack,
)
from .field import (
    FIELD_CHARACTER_ANIMATION_INTERVAL,
    FIELD_CHARACTER_ASSET_ID,
    FIELD_CHARACTER_BANK,
    FIELD_CHARACTER_COLKEY,
    FIELD_CHARACTER_FACING_ROWS,
    FIELD_CHARACTER_SIZE,
    FIELD_CHARACTER_SOURCE_X,
    FIELD_CHARACTER_SOURCE_Y,
    FIELD_PROP_ASSET_ID,
    FIELD_TREASURE_ASSET_ID,
    FieldRenderer,
)
from .monster_death import (
    MONSTER_DEATH_BRIGHT_COLOR,
    MONSTER_DEATH_BRIGHTEN_FRAME_COUNT,
    MONSTER_DEATH_DISSOLVE_FRAME_COUNT,
    MONSTER_DEATH_PALETTE,
    MONSTER_DEATH_PALETTE_BASE_RATE,
    MONSTER_DEATH_TINT_COLOR,
    MONSTER_DEATH_TINT_FRAME_COUNT,
    MonsterDeathAnimation,
    MonsterDeathPhase,
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
    "FIELD_CHARACTER_ANIMATION_INTERVAL",
    "FIELD_CHARACTER_ASSET_ID",
    "FIELD_CHARACTER_BANK",
    "FIELD_CHARACTER_COLKEY",
    "FIELD_CHARACTER_FACING_ROWS",
    "FIELD_CHARACTER_SIZE",
    "FIELD_CHARACTER_SOURCE_X",
    "FIELD_CHARACTER_SOURCE_Y",
    "FIELD_PROP_ASSET_ID",
    "FIELD_TREASURE_ASSET_ID",
    "FieldRenderer",
    "MONSTER_DEATH_BRIGHT_COLOR",
    "MONSTER_DEATH_BRIGHTEN_FRAME_COUNT",
    "MONSTER_DEATH_DISSOLVE_FRAME_COUNT",
    "MONSTER_DEATH_PALETTE",
    "MONSTER_DEATH_PALETTE_BASE_RATE",
    "MONSTER_DEATH_TINT_COLOR",
    "MONSTER_DEATH_TINT_FRAME_COUNT",
    "MonsterDeathAnimation",
    "MonsterDeathPhase",
    "PaletteShifter",
    "create_default_palette_shifter",
    "mix_color",
]
