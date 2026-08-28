"""Draw text containing tags for icons stored in the common image bank."""

from __future__ import annotations

from dataclasses import dataclass
import re
from types import MappingProxyType
from typing import Any

import pyxel

ICON_BANK = 0
ICON_SIZE = 8
ICON_COLKEY = 1
ICON_Y_OFFSET = 3


@dataclass(frozen=True)
class TextIcon:
    """An 8x8 icon that can be embedded in text with a percent-delimited tag."""

    tag: str
    u: int
    v: int


_ICON_COORDINATES = {
    "FIRE": (0, 16),
    "FREEZE": (8, 16),
    "DARK": (16, 16),
    "SLEEP": (24, 16),
    "POISON": (32, 16),
    "PARALIZE": (40, 16),
    "CONFUSE": (48, 16),
    "SILENCE": (56, 16),
    "DEATH": (64, 16),
    "FIRE_DISABLED": (0, 24),
    "FREEZE_DISABLED": (8, 24),
    "DARK_DISABLED": (16, 24),
    "SLEEP_DISABLED": (24, 24),
    "POISON_DISABLED": (32, 24),
    "PARALIZE_DISABLED": (40, 24),
    "CONFUSE_DISABLED": (48, 24),
    "SILENCE_DISABLED": (56, 24),
    "DEATH_DISABLED": (64, 24),
    "RIGHT": (72, 16),
    "LEFT": (80, 16),
    "HEAD": (72, 24),
    "BODY": (80, 24),
    "ARM": (88, 24),
    "UNDEAD": (96, 16),
    "FLY": (96, 24),
    "SWORD": (104, 16),
    "KATANA": (112, 16),
    "KNIFE": (120, 16),
    "SPEAR": (128, 16),
    "AXE": (136, 16),
    "HAMMER": (144, 16),
    "THROWING": (152, 16),
    "ROD": (104, 24),
    "WAND": (112, 24),
    "SHIELD": (120, 24),
    "MYSTIC": (128, 24),
    "SACRED": (136, 24),
    "NETHER": (144, 24),
}

TEXT_ICONS = MappingProxyType(
    {
        f"%{name}%": TextIcon(f"%{name}%", u, v)
        for name, (u, v) in _ICON_COORDINATES.items()
    }
)

_TAG_PATTERN = re.compile(r"%[A-Z][A-Z0-9_]*%")


def split_tagged_text(text: str) -> tuple[str | TextIcon, ...]:
    """Split text into literal text and known icon tags.

    Unknown and malformed tags remain literal so ordinary percent signs and
    future content do not disappear from the screen.
    """

    if not isinstance(text, str):
        raise TypeError("text must be a string")

    parts: list[str | TextIcon] = []
    position = 0
    for match in _TAG_PATTERN.finditer(text):
        icon = TEXT_ICONS.get(match.group())
        if icon is None:
            continue
        _append_literal(parts, text[position : match.start()])
        parts.append(icon)
        position = match.end()
    _append_literal(parts, text[position:])
    return tuple(parts)


def draw_tagged_text(
    x: int,
    y: int,
    text: str,
    color: int,
    font: Any | None = None,
    *,
    shadow_color: int | None = 0,
) -> None:
    """Draw text and icons from left to right."""

    cursor_x = x
    parts = split_tagged_text(text)
    for index, part in enumerate(parts):
        if isinstance(part, TextIcon):
            pyxel.blt(
                cursor_x,
                y + ICON_Y_OFFSET,
                ICON_BANK,
                part.u,
                part.v,
                ICON_SIZE,
                ICON_SIZE,
                ICON_COLKEY,
            )
            if index < len(parts) - 1:
                cursor_x += ICON_SIZE
            continue

        if shadow_color is not None:
            pyxel.text(cursor_x, y + 1, part, shadow_color, font)
        pyxel.text(cursor_x, y, part, color, font)
        if index < len(parts) - 1:
            cursor_x += _text_width(part, font)


def _append_literal(parts: list[str | TextIcon], text: str) -> None:
    if not text:
        return
    if parts and isinstance(parts[-1], str):
        parts[-1] += text
    else:
        parts.append(text)


def _text_width(text: str, font: Any | None) -> int:
    if font is not None:
        return font.text_width(text)
    return pyxel.FONT_WIDTH * len(text)
