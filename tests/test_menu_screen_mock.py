from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from tools.screen_mocks.menu import MenuScreenMock


class MenuScreenMockTest(unittest.TestCase):
    @patch("tools.screen_mocks.menu.pyxel.run")
    @patch("tools.screen_mocks.menu.pyxel.load_pal")
    @patch("tools.screen_mocks.menu.pyxel.load")
    @patch("tools.screen_mocks.menu.pyxel.init")
    @patch("tools.screen_mocks.menu.WindowFactory")
    @patch("tools.screen_mocks.menu.FontResources")
    @patch("tools.screen_mocks.menu.Settings")
    def test_creates_one_empty_full_screen_window(
        self,
        settings_class: Mock,
        fonts_class: Mock,
        window_factory_class: Mock,
        _init: Mock,
        _load: Mock,
        _load_pal: Mock,
        _run: Mock,
    ) -> None:
        settings = settings_class.return_value
        fonts = fonts_class.return_value
        font = fonts.font_for.return_value
        factory = window_factory_class.return_value
        window = factory.create.return_value

        mock = MenuScreenMock()

        fonts.font_for.assert_called_once_with(settings.language)
        window_factory_class.assert_called_once_with(font)
        factory.create.assert_called_once_with(0, 0, 64, 60)
        self.assertEqual(mock.windows, [window])

    def test_draws_all_windows(self) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        first_window = Mock()
        second_window = Mock()
        mock.windows = (first_window, second_window)

        mock.draw()

        first_window.draw.assert_called_once_with()
        second_window.draw.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
