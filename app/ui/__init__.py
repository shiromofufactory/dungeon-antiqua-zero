"""Reusable user-interface drawing components."""

from .tagged_text import TEXT_ICONS, TextIcon, draw_tagged_text, split_tagged_text
from .window import (
    CursorTarget,
    TEXT_GRID_X,
    TEXT_GRID_Y,
    Window,
    WindowCursor,
    WindowState,
    WindowText,
)


__all__ = [
    "CursorTarget",
    "TEXT_GRID_X",
    "TEXT_GRID_Y",
    "TEXT_ICONS",
    "TextIcon",
    "Window",
    "WindowCursor",
    "WindowState",
    "WindowText",
    "draw_tagged_text",
    "split_tagged_text",
]
