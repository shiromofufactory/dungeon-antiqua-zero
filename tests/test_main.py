from __future__ import annotations

import unittest
from unittest.mock import Mock, call, patch

from tools._bootstrap import APP_ROOT

import main as game_main
from game import Game
from rendering import PaletteShifter
from state import DisplayMode, LaunchMode, Settings


class MainTest(unittest.TestCase):
    def test_initializes_window_and_common_assets(self) -> None:
        settings = Settings(screen_scale=4)
        with (
            patch("main.pyxel.init") as init,
            patch("main.pyxel.load") as load,
            patch("main.pyxel.load_pal") as load_pal,
            patch("main.pyxel.fullscreen") as fullscreen,
            patch("main.create_default_palette_shifter") as create_palette,
        ):
            palette = game_main.initialize_game(settings)

        init.assert_called_once_with(
            256,
            240,
            title="Dungeon Antiqua ZERO",
            fps=60,
            quit_key=game_main.pyxel.KEY_NONE,
            display_scale=4,
        )
        self.assertEqual(
            [call(str(APP_ROOT / "assets.pyxres"))],
            load.call_args_list,
        )
        load_pal.assert_called_once_with(str(APP_ROOT / "assets.pyxpal"))
        fullscreen.assert_not_called()
        self.assertIs(palette, create_palette.return_value)

    def test_initializes_fullscreen_smooth_mode(self) -> None:
        settings = Settings(screen_scale=5, display_mode=DisplayMode.SMOOTH)
        with (
            patch("main.pyxel.init") as init,
            patch("main.pyxel.load"),
            patch("main.pyxel.load_pal"),
            patch("main.pyxel.fullscreen") as fullscreen,
            patch("main.pyxel.screen_mode") as screen_mode,
            patch("main.create_default_palette_shifter"),
        ):
            game_main.initialize_game(settings)

        self.assertNotIn("display_scale", init.call_args.kwargs)
        fullscreen.assert_called_once_with(True)
        screen_mode.assert_called_once_with(1)

    def test_connects_game_callbacks_to_pyxel(self) -> None:
        settings = Settings()
        palette = Mock(spec=PaletteShifter)
        game = Mock(spec=Game)
        with (
            patch("main.SettingsRepository") as settings_repository_class,
            patch("main.initialize_game", return_value=palette),
            patch("main.Game", return_value=game) as game_class,
            patch("main.pyxel.run") as run,
        ):
            game_class.settings_from_environment.return_value = settings
            game_main.run_game()

        settings_repository = settings_repository_class.return_value
        game_class.settings_from_environment.assert_called_once_with(
            settings_repository
        )
        game_class.assert_called_once_with(
            settings=settings,
            palette_shifter=palette,
            settings_repository=settings_repository,
            launch_mode=LaunchMode.NORMAL,
        )
        run.assert_called_once_with(game.update, game.draw)

    def test_main_returns_keyboard_interrupt_exit_code(self) -> None:
        with patch("main.run_game", side_effect=KeyboardInterrupt):
            self.assertEqual(game_main.main([]), 130)

    def test_launch_options_select_each_mode(self) -> None:
        for mode in LaunchMode:
            with self.subTest(mode=mode), patch("main.run_game") as run:
                self.assertEqual(game_main.main(["--mode", mode.value]), 0)
                run.assert_called_once_with(mode)
        with patch("main.run_game") as run:
            self.assertEqual(game_main.main([]), 0)
            run.assert_called_once_with(LaunchMode.NORMAL)

    def test_invalid_launch_mode_does_not_initialize_game(self) -> None:
        with (
            patch("main.run_game") as run,
            patch("sys.stderr"),
            self.assertRaises(SystemExit) as error,
        ):
            game_main.main(["--mode", "unknown"])
        self.assertEqual(error.exception.code, 2)
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
