"""Draw text containing tags for icons stored in the common image bank."""

from __future__ import annotations

from dataclasses import dataclass
import re
from types import MappingProxyType
from typing import Any

import pyxel

from .colors import BLUE_TEXT_COLOR

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


@dataclass(frozen=True)
class TextColor:
    """Change the text color without consuming display width."""

    tag: str
    color: int


@dataclass(frozen=True)
class TextFontSpan:
    """Apply one font and baseline offset to a source text range."""

    start: int
    end: int
    font: Any
    text_y_offset: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.start, int) or not isinstance(self.end, int):
            raise TypeError("font span positions must be integers")
        if self.start < 0 or self.end <= self.start:
            raise ValueError("font span must be a non-empty forward range")
        if self.font is None:
            raise ValueError("font span font must not be None")
        if not isinstance(self.text_y_offset, int):
            raise TypeError("font span text_y_offset must be an integer")


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
    "FAVORED": (152, 24),
    "GAMEPAD_A": (160, 16),
    "GAMEPAD_B": (168, 16),
    "GAMEPAD_X": (176, 16),
    "GAMEPAD_Y": (184, 16),
    "KEY_Z": (160, 24),
    "KEY_X": (168, 24),
    "KEY_S": (176, 24),
    "KEY_TAB": (184, 24),
}

TEXT_ICONS = MappingProxyType(
    {
        f"%{name}%": TextIcon(f"%{name}%", u, v)
        for name, (u, v) in _ICON_COORDINATES.items()
    }
)
TEXT_COLORS = MappingProxyType(
    {
        "%COL_BLUE%": TextColor("%COL_BLUE%", BLUE_TEXT_COLOR),
        "%COL_END%": TextColor("%COL_END%", 5),
    }
)

_TAG_PATTERN = re.compile(r"%[A-Z][A-Z0-9_]*%")


def split_tagged_text(text: str) -> tuple[str | TextIcon | TextColor, ...]:
    """Split text into literal text and known icon or color tags.

    Unknown and malformed tags remain literal so ordinary percent signs and
    future content do not disappear from the screen.
    """

    if not isinstance(text, str):
        raise TypeError("text must be a string")

    return tuple(
        part for part, _start, _end in _split_tagged_text_with_offsets(text)
    )


def _split_tagged_text_with_offsets(
    text: str,
) -> tuple[tuple[str | TextIcon | TextColor, int, int], ...]:
    parts: list[tuple[str | TextIcon | TextColor, int, int]] = []
    position = 0
    for match in _TAG_PATTERN.finditer(text):
        tag = TEXT_ICONS.get(match.group()) or TEXT_COLORS.get(match.group())
        if tag is None:
            continue
        if position < match.start():
            parts.append(
                (
                    text[position : match.start()],
                    position,
                    match.start(),
                )
            )
        parts.append((tag, match.start(), match.end()))
        position = match.end()
    if position < len(text):
        parts.append((text[position:], position, len(text)))
    return tuple(parts)


def draw_tagged_text(
    x: int,
    y: int,
    text: str,
    color: int,
    font: Any | None = None,
    *,
    shadow_color: int | None = 0,
    text_y_offset: int = 0,
    font_spans: tuple[TextFontSpan, ...] = (),
) -> None:
    """Draw text and icons, vertically offsetting only text glyphs."""

    cursor_x = x
    current_color = color
    parts = _split_tagged_text_with_offsets(text)
    for part_index, (part, start, end) in enumerate(parts):
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
            cursor_x += ICON_SIZE
            continue
        if isinstance(part, TextColor):
            current_color = part.color
            continue

        styled_runs = _styled_text_runs(
            text,
            start,
            end,
            font,
            text_y_offset,
            font_spans,
        )
        for run_index, (run, run_font, run_y_offset) in enumerate(styled_runs):
            text_y = y + run_y_offset
            if shadow_color is not None:
                pyxel.text(cursor_x, text_y + 1, run, shadow_color, run_font)
            pyxel.text(cursor_x, text_y, run, current_color, run_font)
            if run_index < len(styled_runs) - 1 or part_index < len(parts) - 1:
                cursor_x += _text_width(run, run_font)


def _styled_text_runs(
    text: str,
    start: int,
    end: int,
    default_font: Any | None,
    default_y_offset: int,
    font_spans: tuple[TextFontSpan, ...],
) -> tuple[tuple[str, Any | None, int], ...]:
    runs: list[tuple[str, Any | None, int]] = []
    run_start = start
    run_style: tuple[Any | None, int] | None = None
    for index in range(start, end):
        style = (default_font, default_y_offset)
        for span in font_spans:
            if span.start <= index < span.end:
                style = (span.font, span.text_y_offset)
                break
        if run_style is None:
            run_style = style
        elif style != run_style:
            runs.append((text[run_start:index], *run_style))
            run_start = index
            run_style = style
    if run_style is not None:
        runs.append((text[run_start:end], *run_style))
    return tuple(runs)


def _text_width(text: str, font: Any | None) -> int:
    if font is not None:
        return font.text_width(text)
    return pyxel.FONT_WIDTH * len(text)
