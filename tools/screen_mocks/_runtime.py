"""Small platform helpers shared by independently runnable screen mocks."""

from __future__ import annotations

import pyxel

from tools._bootstrap import APP_ROOT
from input import InputBindings, PyxelInputReader
from rendering import PaletteShifter, create_default_palette_shifter

SCREEN_WIDTH = 256
SCREEN_HEIGHT = 240
FPS = 60


def initialize_screen_mock(
    title: str,
    *,
    display_scale: int | None = None,
) -> PaletteShifter:
    """Initialize Pyxel and load the common bank and palette resources."""

    if not isinstance(title, str) or not title:
        raise ValueError("title must be a non-empty string")
    if display_scale is not None and (
        isinstance(display_scale, bool)
        or not isinstance(display_scale, int)
        or display_scale <= 0
    ):
        raise ValueError("display_scale must be a positive integer or None")
    # Esc is a logical cancel input in the screen mocks.  Let each mock decide
    # whether cancel closes an overlay or exits instead of Pyxel terminating the
    # process before the update callback can handle it.
    init_options = {"title": title, "fps": FPS, "quit_key": pyxel.KEY_NONE}
    if display_scale is not None:
        init_options["display_scale"] = display_scale
    pyxel.init(SCREEN_WIDTH, SCREEN_HEIGHT, **init_options)
    pyxel.load(str(APP_ROOT / "assets.pyxres"))
    pyxel.load_pal(str(APP_ROOT / "assets.pyxpal"))
    return create_default_palette_shifter()


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
