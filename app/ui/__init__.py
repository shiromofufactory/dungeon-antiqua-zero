"""Reusable user-interface drawing components."""

from .colors import DISABLED_COLOR, NEGATIVE_COLOR, POSITIVE_COLOR
from .localized_text import LocalizedWindowTextFactory
from .input_icons import input_icon_tag
from .tagged_text import (
    TEXT_ICONS,
    TextFontSpan,
    TextIcon,
    draw_tagged_text,
    split_tagged_text,
)
from .text_format import format_play_time, pad, spacing
from .window import (
    CursorTarget,
    DEFAULT_TEXT_COLOR,
    TEXT_GRID_X,
    TEXT_GRID_Y,
    Window,
    WindowCursor,
    WindowFactory,
    WindowState,
    WindowText,
)


__all__ = [
    "CursorTarget",
    "DEFAULT_TEXT_COLOR",
    "DISABLED_COLOR",
    "LocalizedWindowTextFactory",
    "NEGATIVE_COLOR",
    "TEXT_GRID_X",
    "TEXT_GRID_Y",
    "TEXT_ICONS",
    "TextIcon",
    "TextFontSpan",
    "POSITIVE_COLOR",
    "Window",
    "WindowCursor",
    "WindowFactory",
    "WindowState",
    "WindowText",
    "draw_tagged_text",
    "format_play_time",
    "input_icon_tag",
    "pad",
    "spacing",
    "split_tagged_text",
]
