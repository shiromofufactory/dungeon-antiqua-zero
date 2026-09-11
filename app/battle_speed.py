"""Battle-only agility modifiers shared by party members and monsters."""

from __future__ import annotations


MIN_SPEED_MODIFIER = -1
MAX_SPEED_MODIFIER = 2


def modified_agility(base_agility: int, speed_modifier: int) -> int:
    """Apply ZERO's quarter-step battle speed formula."""

    if isinstance(base_agility, bool) or not isinstance(base_agility, int):
        raise TypeError("base_agility must be an integer")
    if base_agility < 0:
        raise ValueError("base_agility must not be negative")
    if isinstance(speed_modifier, bool) or not isinstance(speed_modifier, int):
        raise TypeError("speed_modifier must be an integer")
    if not MIN_SPEED_MODIFIER <= speed_modifier <= MAX_SPEED_MODIFIER:
        raise ValueError(
            f"speed_modifier must be from {MIN_SPEED_MODIFIER} "
            f"to {MAX_SPEED_MODIFIER}"
        )
    return max(1, base_agility * (4 + speed_modifier) // 4)


__all__ = [
    "MAX_SPEED_MODIFIER",
    "MIN_SPEED_MODIFIER",
    "modified_agility",
]
