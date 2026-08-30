from __future__ import annotations

import unittest
from unittest.mock import Mock, call, patch

from tools._bootstrap import APP_ROOT
from tools.screen_mocks.menu import (
    FACES_IMAGE_ID,
    MENU_COMMANDS,
    PARTY_FACE_SIZE,
    PARTY_FACE_X,
    PARTY_FACE_Y,
    PARTY_MEMBER_ROW_HEIGHT,
    PARTY_RECOVERY_TEXT_X,
    PARTY_TEXT_X,
    PARTY_WINDOW_GRID,
    MenuScreenMock,
    TextCatalog,
    TRANSPARENT_INDEX,
    localized_menu_texts,
)
from input import Direction, InputButton, InputState
from member import FormationRow
from state import Language
from ui import (
    DEFAULT_TEXT_COLOR,
    DISABLED_COLOR,
    NEGATIVE_COLOR,
    POSITIVE_COLOR,
)


class MenuScreenMockTest(unittest.TestCase):
    @patch("tools.screen_mocks.menu.pyxel.run")
    @patch("tools.screen_mocks.menu.create_mock_input_reader")
    @patch("tools.screen_mocks.menu.initialize_screen_mock")
    @patch("tools.screen_mocks.menu.WindowFactory")
    @patch("tools.screen_mocks.menu.ImageResources")
    @patch("tools.screen_mocks.menu.FontResources")
    def test_creates_five_member_main_window_and_da2_side_windows(
        self,
        fonts_class: Mock,
        images_class: Mock,
        window_factory_class: Mock,
        initialize: Mock,
        create_input_reader: Mock,
        _run: Mock,
    ) -> None:
        fonts = fonts_class.return_value
        font = fonts.font_for.return_value
        fonts.baseline_offset_for.return_value = 0
        factory = window_factory_class.return_value
        party_window = Mock()
        command_window = Mock()
        info_window = Mock()
        close_guide_window = Mock()
        factory.create.side_effect = (
            party_window,
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
        images_class.return_value.image.assert_called_once_with(FACES_IMAGE_ID)
        self.assertIs(mock.faces, images_class.return_value.image.return_value)
        self.assertEqual(
            fonts.font_for.call_args_list,
            [
                call(Language.JAPANESE),
                call(Language.JAPANESE),
            ],
        )
        window_factory_class.assert_called_once_with(font)
        party_args = factory.create.call_args_list[0].args
        self.assertEqual(party_args[:4], PARTY_WINDOW_GRID)
        party_texts = {(text.x, text.y): text for text in party_args[4]}
        self.assertEqual(
            [member.definition.key for member in mock.party],
            ["Fiora", "Cerion", "Alvan", "Elika", "Ragna"],
        )
        self.assertEqual(
            [member.formation_row for member in mock.party],
            [
                FormationRow.FRONT,
                FormationRow.BACK,
                FormationRow.FRONT,
                FormationRow.BACK,
                FormationRow.FRONT,
            ],
        )
        self.assertEqual(party_texts[(PARTY_TEXT_X, 2)].text, "フィオラ")
        self.assertEqual(
            party_texts[(PARTY_TEXT_X, 5)].text,
            "ＨＰ　　４４／　４４",
        )
        self.assertEqual(
            party_texts[(PARTY_TEXT_X, 8)].text,
            "ＭＰ　　１２／　１２",
        )
        self.assertEqual(party_texts[(PARTY_TEXT_X, 13)].text, "セリオン")
        self.assertEqual(party_texts[(PARTY_TEXT_X, 24)].text, "アルヴァン")
        self.assertEqual(party_texts[(PARTY_TEXT_X, 35)].text, "エリカ")
        self.assertEqual(party_texts[(PARTY_TEXT_X, 46)].text, "ラグナ")
        self.assertEqual(
            party_texts[(PARTY_TEXT_X, 52)].color,
            DISABLED_COLOR,
        )

        args = factory.create.call_args_list[1].args
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
        self.assertIs(mock.party_window, party_window)
        self.assertIs(mock.info_window, info_window)
        self.assertIs(mock.close_guide_window, close_guide_window)
        self.assertEqual(
            mock.windows,
            [party_window, command_window, info_window, close_guide_window],
        )
        info_args = factory.create.call_args_list[2].args
        self.assertEqual(info_args[:4], (48, 30, 16, 27))
        self.assertEqual(
            [(text.text, text.x, text.y) for text in info_args[4]],
            [
                ("Ｇｏｌｄ", 2, 2),
                ("　　　　　０", 2, 5),
                ("けいけんち", 2, 8),
                ("　　　　　０", 2, 11),
                ("なんいど", 2, 14),
                ("ノーマル", 4, 17),
                ("プレイじかん", 2, 20),
                ("　００：００", 2, 23),
            ],
        )

        guide_call = factory.create.call_args_list[3]
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
        self.assertEqual(japanese["menu.member.hp"], "ＨＰ")
        self.assertEqual(japanese["menu.member.mp"], "ＭＰ")
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

    def test_party_hp_uses_shared_recovery_colors(self) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        mock.settings = Mock(language=Language.JAPANESE)
        mock.texts = TextCatalog.from_json(APP_ROOT / "data" / "texts.json")
        text_factory = Mock()
        text_factory.create.side_effect = (
            lambda text, x, y, **kwargs: Mock(
                text=text,
                x=x,
                y=y,
                color=kwargs.get("color", DEFAULT_TEXT_COLOR),
            )
        )

        for amount, expected_text, expected_color in (
            (2, "（＋２）", POSITIVE_COLOR),
            (-2, "（－２）", NEGATIVE_COLOR),
        ):
            with self.subTest(amount=amount):
                member = Mock(
                    hp=40,
                    max_hp=44,
                    mp=12,
                    max_mp=12,
                    heal_and_poison_amount=amount,
                )
                member.definition.localized_name.return_value = "フィオラ"
                member.status.return_value = ""

                texts = mock._party_window_texts(
                    (member,),
                    localized_menu_texts(mock.texts, Language.JAPANESE),
                    text_factory,
                )

                recovery = next(
                    text for text in texts if text.x == PARTY_RECOVERY_TEXT_X
                )
                self.assertEqual(recovery.text, expected_text)
                self.assertEqual(recovery.color, expected_color)

    def test_shared_semantic_color_numbers_match_palette_roles(self) -> None:
        self.assertEqual(DISABLED_COLOR, 3)
        self.assertEqual(POSITIVE_COLOR, 29)
        self.assertEqual(NEGATIVE_COLOR, 45)

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

    @patch("tools.screen_mocks.menu.pyxel.blt")
    def test_draws_windows_and_offsets_back_row_faces(self, blt: Mock) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        party_window = Mock()
        side_window = Mock()
        mock.windows = (party_window, side_window)
        mock.party_window = party_window
        mock.faces = object()
        front = Mock(
            is_front_row=True,
            face_position=Mock(x=0, y=0),
        )
        back = Mock(
            is_front_row=False,
            face_position=Mock(x=32, y=0),
        )
        mock.party = (front, back)

        mock.draw()

        party_window.draw.assert_called_once_with()
        side_window.draw.assert_called_once_with()
        self.assertEqual(
            blt.call_args_list,
            [
                call(
                    PARTY_FACE_X[True],
                    PARTY_FACE_Y,
                    mock.faces,
                    0,
                    0,
                    PARTY_FACE_SIZE,
                    PARTY_FACE_SIZE,
                    TRANSPARENT_INDEX,
                ),
                call(
                    PARTY_FACE_X[False],
                    PARTY_FACE_Y + PARTY_MEMBER_ROW_HEIGHT * 4,
                    mock.faces,
                    32,
                    0,
                    PARTY_FACE_SIZE,
                    PARTY_FACE_SIZE,
                    TRANSPARENT_INDEX,
                ),
            ],
        )


if __name__ == "__main__":
    unittest.main()
