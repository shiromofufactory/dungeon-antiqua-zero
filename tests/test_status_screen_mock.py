from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from tools.screen_mocks.status import (
    Language,
    TRANSPARENT_INDEX,
    Settings,
    StatusScreenMock,
    next_language,
)


class StatusScreenMockTest(unittest.TestCase):
    def test_language_sequence_wraps_after_simplified_chinese(self) -> None:
        self.assertEqual(next_language(Language.JAPANESE), Language.ENGLISH)
        self.assertEqual(
            next_language(Language.ENGLISH),
            Language.SIMPLIFIED_CHINESE,
        )
        self.assertEqual(
            next_language(Language.SIMPLIFIED_CHINESE),
            Language.JAPANESE,
        )

    def test_first_three_lines_use_localized_member_identity(self) -> None:
        with (
            patch("tools.screen_mocks.status.pyxel.init"),
            patch("tools.screen_mocks.status.pyxel.load"),
            patch("tools.screen_mocks.status.pyxel.load_pal"),
            patch("tools.screen_mocks.status.pyxel.run"),
            patch("tools.screen_mocks.status.ImageResources") as images,
            patch("tools.screen_mocks.status.FontResources") as fonts,
            patch("tools.screen_mocks.status.WindowFactory") as factory,
        ):
            images.return_value.image.return_value = object()
            fonts.return_value.font_for.return_value = object()

            StatusScreenMock()

        texts = tuple(factory.return_value.create.call_args.args[4])
        self.assertEqual(
            [item.text for item in texts[:3]],
            ["フィオラ", "ようせい", "おんな"],
        )

    def test_confirm_cycles_language_and_rebuilds_identity_window(self) -> None:
        mock = StatusScreenMock.__new__(StatusScreenMock)
        mock.settings = Settings()
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = Mock(
            confirm=Mock(triggered=True),
            cancel=Mock(triggered=False),
        )
        mock._rebuild_identity_window = Mock()

        mock.update()

        self.assertEqual(mock.settings.language, Language.ENGLISH)
        mock._rebuild_identity_window.assert_called_once_with()

    def test_english_identity_lines_are_rebuilt_as_fullwidth_text(self) -> None:
        with (
            patch("tools.screen_mocks.status.pyxel.init"),
            patch("tools.screen_mocks.status.pyxel.load"),
            patch("tools.screen_mocks.status.pyxel.load_pal"),
            patch("tools.screen_mocks.status.pyxel.run"),
            patch("tools.screen_mocks.status.ImageResources") as images,
            patch("tools.screen_mocks.status.FontResources") as fonts,
        ):
            images.return_value.image.return_value = object()
            fonts.return_value.font_for.return_value = object()
            mock = StatusScreenMock()

        mock.settings = mock.settings.with_language(Language.ENGLISH)
        mock._rebuild_identity_window()

        self.assertEqual(
            [item.text for item in mock.windows[0].texts[:3]],
            ["Ｆｉｏｒａ", "Ｆａｉｒｙ", "Ｆｅｍａｌｅ"],
        )

    def test_cancel_quits_without_changing_language(self) -> None:
        mock = StatusScreenMock.__new__(StatusScreenMock)
        mock.settings = Settings()
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = Mock(
            confirm=Mock(triggered=False),
            cancel=Mock(triggered=True),
        )
        mock._rebuild_identity_window = Mock()

        with patch("tools.screen_mocks.status.pyxel.quit") as quit_mock:
            mock.update()

        quit_mock.assert_called_once_with()
        self.assertEqual(mock.settings.language, Language.JAPANESE)
        mock._rebuild_identity_window.assert_not_called()

    def test_draws_all_windows_before_face(self) -> None:
        mock = StatusScreenMock.__new__(StatusScreenMock)
        mock.faces = object()
        first_window = Mock()
        second_window = Mock()
        mock.windows = (first_window, second_window)
        draw_order: list[str] = []

        first_window.draw.side_effect = lambda: draw_order.append("first_window")
        second_window.draw.side_effect = lambda: draw_order.append("second_window")

        with patch(
            "tools.screen_mocks.status.pyxel.blt",
            side_effect=lambda *args: draw_order.append("face"),
        ) as blt:
            mock.draw()

        self.assertEqual(draw_order, ["first_window", "second_window", "face"])
        blt.assert_called_once_with(
            16,
            8,
            mock.faces,
            0,
            0,
            32,
            32,
            TRANSPARENT_INDEX,
        )


if __name__ == "__main__":
    unittest.main()
