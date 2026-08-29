"""Reusable user-interface drawing components."""

from .localized_text import LocalizedWindowTextFactory
from .tagged_text import TEXT_ICONS, TextIcon, draw_tagged_text, split_tagged_text
from .window import (
    CursorTarget,
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
    "LocalizedWindowTextFactory",
    "TEXT_GRID_X",
    "TEXT_GRID_Y",
    "TEXT_ICONS",
    "TextIcon",
    "Window",
    "WindowCursor",
    "WindowFactory",
    "WindowState",
    "WindowText",
    "draw_tagged_text",
    "split_tagged_text",
]
