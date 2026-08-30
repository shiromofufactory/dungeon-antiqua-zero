"""Small platform helpers shared by independently runnable screen mocks."""

from __future__ import annotations

import pyxel

from tools._bootstrap import APP_ROOT
from input import InputBindings, PyxelInputReader

SCREEN_WIDTH = 256
SCREEN_HEIGHT = 240
FPS = 60


def initialize_screen_mock(title: str) -> None:
    """Initialize Pyxel and load the common bank and palette resources."""

    if not isinstance(title, str) or not title:
        raise ValueError("title must be a non-empty string")
    pyxel.init(
        SCREEN_WIDTH,
        SCREEN_HEIGHT,
        title=title,
        fps=FPS,
    )
    pyxel.load(str(APP_ROOT / "assets.pyxres"))
    pyxel.load_pal(str(APP_ROOT / "assets.pyxpal"))


def create_mock_input_reader() -> PyxelInputReader:
    """Create the common mock bindings, including Q as an exit key."""

    return PyxelInputReader(
        InputBindings.default().with_cancel(pyxel.KEY_Q)
    )


__all__ = [
    "FPS",
    "SCREEN_HEIGHT",
    "SCREEN_WIDTH",
    "create_mock_input_reader",
    "initialize_screen_mock",
]
