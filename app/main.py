"""Initialize Pyxel resources and start Dungeon Antiqua ZERO."""

from __future__ import annotations

from collections.abc import Sequence
import argparse
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
from resources import preload_se
from state import DisplayMode, LaunchMode, Settings
from systems import SettingsRepository

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
    preload_se()
    pyxel.load_pal(str(APP_ROOT / "assets.pyxpal"))
    if settings.screen_scale == 5:
        pyxel.fullscreen(True)
    if settings.display_mode is DisplayMode.SMOOTH:
        pyxel.screen_mode(1)
    return create_default_palette_shifter()


def run_game(launch_mode: LaunchMode = LaunchMode.NORMAL) -> None:
    """Create the current game flow and connect it to Pyxel callbacks."""

    settings_repository = SettingsRepository()
    settings = Game.settings_from_environment(settings_repository)
    palette_shifter = initialize_game(settings)
    game = Game(
        settings=settings,
        palette_shifter=palette_shifter,
        settings_repository=settings_repository,
        launch_mode=launch_mode,
    )
    pyxel.run(game.update, game.draw)


def main(argv: Sequence[str] | None = None) -> int:
    """Normalize expected startup failures into a command exit code."""

    parser = argparse.ArgumentParser(description=WINDOW_TITLE)
    parser.add_argument(
        "--mode",
        choices=tuple(mode.value for mode in LaunchMode),
        default=LaunchMode.NORMAL.value,
        help="起動モード: normal=通常、exhibition=試遊版、demo=体験版、beta=βテスト版",
    )
    arguments = parser.parse_args(argv)
    try:
        run_game(LaunchMode(arguments.mode))
        return 0
    except GAME_ERRORS as error:
        print(error)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
