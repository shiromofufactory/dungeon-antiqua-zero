from __future__ import annotations

import unittest
from unittest.mock import Mock, call, patch

from tools._bootstrap import APP_ROOT
from tools.screen_mocks.menu import (
    MENU_COMMANDS,
    MenuScreenMock,
    TextCatalog,
    localized_menu_texts,
)
from input import Direction, InputButton, InputState
from state import Language


class MenuScreenMockTest(unittest.TestCase):
    @patch("tools.screen_mocks.menu.pyxel.run")
    @patch("tools.screen_mocks.menu.create_mock_input_reader")
    @patch("tools.screen_mocks.menu.initialize_screen_mock")
    @patch("tools.screen_mocks.menu.WindowFactory")
    @patch("tools.screen_mocks.menu.FontResources")
    def test_creates_da2_command_window(
        self,
        fonts_class: Mock,
        window_factory_class: Mock,
        initialize: Mock,
        create_input_reader: Mock,
        _run: Mock,
    ) -> None:
        fonts = fonts_class.return_value
        font = fonts.font_for.return_value
        fonts.baseline_offset_for.return_value = 0
        factory = window_factory_class.return_value
        command_window = Mock()
        info_window = Mock()
        close_guide_window = Mock()
        factory.create.side_effect = (
            command_window,
            info_window,
            close_guide_window,
        )
        cursor = command_window.set_cursor.return_value

        mock = MenuScreenMock()

        initialize.assert_called_once_with(
            "Dungeon Antiqua ZERO Menu Screen Mock"
        )
        self.assertIs(mock.input_reader, create_input_reader.return_value)
        self.assertEqual(
            fonts.font_for.call_args_list,
            [
                call(Language.JAPANESE),
                call(Language.JAPANESE),
            ],
        )
        window_factory_class.assert_called_once_with(font)
        args = factory.create.call_args_list[0].args
        self.assertEqual(args[:4], (48, 0, 16, 30))
        self.assertEqual(
            [(text.text, text.x, text.y) for text in args[4]],
            [
                (label, 4, 2 + index * 3)
                for index, label in enumerate(
                    (
                        "アイテム",
                        "じゅもん",
                        "そうび",
                        "スキル",
                        "ステータス",
                        "ならびかえ",
                        "じょうほう",
                        "せってい",
                        "セーブ",
                    )
                )
            ],
        )
        cursor_targets = command_window.set_cursor.call_args.args[0]
        self.assertEqual(
            [(target.key, target.x, target.y) for target in cursor_targets],
            [
                (key, 2, 2 + index * 3)
                for index, (key, _) in enumerate(MENU_COMMANDS)
            ],
        )
        self.assertIs(mock.command_window, command_window)
        self.assertIs(mock.command_cursor, cursor)
        self.assertIs(mock.info_window, info_window)
        self.assertIs(mock.close_guide_window, close_guide_window)
        self.assertEqual(
            mock.windows,
            [command_window, info_window, close_guide_window],
        )
        info_args = factory.create.call_args_list[1].args
        self.assertEqual(info_args[:4], (48, 30, 16, 27))
        self.assertEqual(
            [(text.text, text.x, text.y) for text in info_args[4]],
            [
                ("Ｇｏｌｄ", 2, 2),
                ("　　　　　０", 2, 5),
                ("けいけんち", 2, 8),
                ("　　　　　０", 2, 11),
                ("なんいど", 2, 14),
                ("　ノーマル", 2, 17),
                ("プレイじかん", 2, 20),
                ("　００：００", 2, 23),
            ],
        )

        guide_call = factory.create.call_args_list[2]
        self.assertEqual(guide_call.args[:4], (48, 57, 16, 4))
        self.assertEqual(
            [(text.text, text.x, text.y) for text in guide_call.args[4]],
            [("%KEY_X%：とじる", 2, 0)],
        )
        self.assertTrue(guide_call.kwargs["transparent"])

    def test_all_menu_terms_are_available_in_each_language(self) -> None:
        catalog = TextCatalog.from_json(APP_ROOT / "data" / "texts.json")

        japanese = localized_menu_texts(catalog, Language.JAPANESE)
        english = localized_menu_texts(catalog, Language.ENGLISH)
        chinese = localized_menu_texts(
            catalog,
            Language.SIMPLIFIED_CHINESE,
        )

        self.assertEqual(japanese["menu.command.item"], "アイテム")
        self.assertEqual(japanese["menu.info.experience"], "けいけんち")
        self.assertEqual(
            japanese["menu.close_guide"],
            "%CANCEL%：とじる",
        )
        self.assertEqual(english["menu.command.item"], "Ｉｔｅｍ")
        self.assertEqual(
            english["menu.info.experience"],
            "ＥＸＰ",
        )
        self.assertEqual(
            english["menu.close_guide"],
            "%CANCEL%：Ｃｌｏｓｅ",
        )
        self.assertEqual(chinese["menu.command.item"], "道具")
        self.assertEqual(chinese["menu.info.experience"], "经验值")
        self.assertEqual(
            chinese["menu.close_guide"],
            "%CANCEL%：关闭",
        )
        self.assertEqual(set(japanese), set(english))
        self.assertEqual(set(japanese), set(chinese))

    def test_update_passes_logical_navigation_to_command_window(self) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState(
            navigation=Direction.DOWN,
            held_direction=Direction.DOWN,
        )
        mock.command_window = Mock()

        mock.update()

        mock.command_window.update.assert_called_once_with(Direction.DOWN)

    def test_cancel_quits_before_updating_command_window(self) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState(
            cancel=InputButton(triggered=True, held=True)
        )
        mock.command_window = Mock()

        with patch("tools.screen_mocks.menu.pyxel.quit") as quit_game:
            mock.update()

        quit_game.assert_called_once_with()
        mock.command_window.update.assert_not_called()

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
