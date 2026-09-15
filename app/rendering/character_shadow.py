"""Draw the shared 16x16 shadow used below character sprites."""

from __future__ import annotations

from typing import Any


CHARACTER_SHADOW_BANK = 0
CHARACTER_SHADOW_SOURCE_X = 80
CHARACTER_SHADOW_SOURCE_Y = 144
CHARACTER_SHADOW_SIZE = 16
CHARACTER_SHADOW_COLKEY = 1


def draw_character_shadow(pyxel_api: Any, x: int, y: int) -> None:
    """Draw one character shadow at its destination cell."""

    pyxel_api.blt(
        x,
        y,
        CHARACTER_SHADOW_BANK,
        CHARACTER_SHADOW_SOURCE_X,
        CHARACTER_SHADOW_SOURCE_Y,
        CHARACTER_SHADOW_SIZE,
        CHARACTER_SHADOW_SIZE,
        CHARACTER_SHADOW_COLKEY,
    )


__all__ = [
    "CHARACTER_SHADOW_BANK",
    "CHARACTER_SHADOW_COLKEY",
    "CHARACTER_SHADOW_SIZE",
    "CHARACTER_SHADOW_SOURCE_X",
    "CHARACTER_SHADOW_SOURCE_Y",
    "draw_character_shadow",
]
