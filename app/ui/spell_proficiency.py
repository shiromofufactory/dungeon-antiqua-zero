"""Small spell proficiency display shared by field spell menus."""

from __future__ import annotations

from spell import SPELL_TYPE_ICON_TAGS, SpellType
from systems.spell_progression import MenuSpellProficiencyGrowth
from ui.text_format import pad

PROFICIENCY_ANIMATION_FRAME_COUNT = 6
PROFICIENCY_WINDOW_SIZE_GRID = (14, 7)
PROFICIENCY_TEXT_X = 2
PROFICIENCY_TEXT_Y = 2


def spell_proficiency_text(
    spell_type: SpellType, total: int, *, previous_total: int | None = None
) -> str:
    level, progress = divmod(total, 100)
    icon = SPELL_TYPE_ICON_TAGS.get(spell_type, "")
    numbers = f"{pad(level, 1, fill='0')}－{pad(progress, 2, fill='0')}"
    if previous_total is not None and level > previous_total // 100:
        return f"{icon}%COL_POSITIVE%{numbers}%COL_END%"
    return f"{icon}{numbers}"


def displayed_proficiency_total(
    growth: MenuSpellProficiencyGrowth, frame: int
) -> int:
    return growth.before_total + (
        growth.applied_amount * frame // PROFICIENCY_ANIMATION_FRAME_COUNT
    )


__all__ = [
    "PROFICIENCY_ANIMATION_FRAME_COUNT",
    "PROFICIENCY_TEXT_X",
    "PROFICIENCY_TEXT_Y",
    "PROFICIENCY_WINDOW_SIZE_GRID",
    "displayed_proficiency_total",
    "spell_proficiency_text",
]
