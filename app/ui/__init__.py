"""Reusable user-interface drawing components."""

from .colors import (
    BLUE_TEXT_COLOR,
    DISABLED_COLOR,
    NEGATIVE_COLOR,
    POSITIVE_COLOR,
    RESERVE_MEMBER_TEXT_COLOR,
)
from .localized_text import LocalizedWindowTextFactory
from .input_icons import input_icon_tag
from .tagged_text import (
    TEXT_COLORS,
    TEXT_ICONS,
    TextColor,
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
    WINDOW_ANIMATION_FRAME_COUNT,
    Window,
    WindowCursor,
    WindowFactory,
    WindowState,
    WindowText,
)


__all__ = [
    "BLUE_TEXT_COLOR",
    "CursorTarget",
    "DEFAULT_TEXT_COLOR",
    "DISABLED_COLOR",
    "LocalizedWindowTextFactory",
    "NEGATIVE_COLOR",
    "TEXT_GRID_X",
    "TEXT_GRID_Y",
    "TEXT_COLORS",
    "TEXT_ICONS",
    "TextColor",
    "TextIcon",
    "TextFontSpan",
    "POSITIVE_COLOR",
    "RESERVE_MEMBER_TEXT_COLOR",
    "Window",
    "WINDOW_ANIMATION_FRAME_COUNT",
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
