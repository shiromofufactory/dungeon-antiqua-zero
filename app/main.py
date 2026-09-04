"""Initialize Pyxel resources and start Dungeon Antiqua ZERO."""

from __future__ import annotations

from pathlib import Path

import pyxel

from game import (
    FPS,
    GAME_ERRORS,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    Game,
)
from rendering import PaletteShifter, create_default_palette_shifter
from state import DisplayMode, Settings

APP_ROOT = Path(__file__).resolve().parent
WINDOW_TITLE = "Dungeon Antiqua ZERO"


def initialize_game(settings: Settings) -> PaletteShifter:
    """Initialize the window and common resources for one game process."""

    if not isinstance(settings, Settings):
        raise TypeError("settings must be Settings")
    init_options: dict[str, object] = {
        "title": WINDOW_TITLE,
        "fps": FPS,
        "quit_key": pyxel.KEY_NONE,
    }
    if settings.screen_scale != 5:
        init_options["display_scale"] = settings.screen_scale
    pyxel.init(SCREEN_WIDTH, SCREEN_HEIGHT, **init_options)
    pyxel.load(str(APP_ROOT / "assets.pyxres"))
    pyxel.load_pal(str(APP_ROOT / "assets.pyxpal"))
    if settings.screen_scale == 5:
        pyxel.fullscreen(True)
    if settings.display_mode is DisplayMode.SMOOTH:
        pyxel.screen_mode(1)
    return create_default_palette_shifter()


def run_game() -> None:
    """Create the current game flow and connect it to Pyxel callbacks."""

    settings = Game.settings_from_environment()
    palette_shifter = initialize_game(settings)
    game = Game(settings=settings, palette_shifter=palette_shifter)
    pyxel.run(game.update, game.draw)


def main() -> int:
    """Normalize expected startup failures into a command exit code."""

    try:
        run_game()
        return 0
    except GAME_ERRORS as error:
        print(error)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
