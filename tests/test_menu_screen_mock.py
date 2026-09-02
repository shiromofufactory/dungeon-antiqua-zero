from __future__ import annotations

from contextlib import nullcontext
import json
import unittest
from unittest.mock import Mock, call, patch

from tools._bootstrap import APP_ROOT
from tools.screen_mocks.menu import (
    ALERT_CHANNEL,
    ALERT_SOUND_ID,
    FACES_IMAGE_ID,
    FIELD_BACKGROUND_IMAGE_ID,
    FORMATION_ARROW_COLKEY,
    FORMATION_ARROW_FRAME_DURATION,
    FORMATION_ARROW_HEIGHT,
    FORMATION_ARROW_LEFT_X,
    FORMATION_ARROW_RIGHT_X,
    FORMATION_ARROW_WIDTH,
    FORMATION_ARROW_Y,
    MENU_COMMANDS,
    MENU_BGM_ID,
    MENU_MOCK_SETTINGS_ENV,
    PARTY_FACE_SIZE,
    PARTY_FACE_X,
    PARTY_FACE_Y,
    PARTY_CURSOR_X,
    PARTY_CURSOR_Y,
    PARTY_MEMBER_ROW_HEIGHT,
    PARTY_MEMBER_ROW_HEIGHT_WITHOUT_RESERVE,
    PARTY_NAME_TEXT_X,
    PARTY_POINT_TEXT_X,
    PARTY_RECOVERY_TEXT_X,
    PARTY_WINDOW_GRID,
    RESERVE_MEMBER_Y_OFFSET_GRID,
    SE_PREVIEW_SOUND_ID,
    SETTINGS_GUIDE_Y,
    SETTINGS_LABEL_X,
    SETTINGS_ROWS,
    SETTINGS_VALUE_X,
    SETTINGS_WINDOW_GRID,
    SORT_SOURCE_CURSOR_X_OFFSET,
    MenuAlertEffect,
    MenuScreenChange,
    MenuScreenMock,
    TextCatalog,
    TRANSPARENT_INDEX,
    localized_menu_texts,
)
from input import Direction, InputButton, InputState
from member import BATTLE_PARTY_MEMBER_COUNT, FormationRow
from rendering import DIMMED_PALETTE, DEFAULT_FADE_FRAME_COUNT, FadeThroughBlack
from state import DisplayMode, Language, SaveData, Settings
from ui import (
    DEFAULT_TEXT_COLOR,
    DISABLED_COLOR,
    NEGATIVE_COLOR,
    POSITIVE_COLOR,
    RESERVE_MEMBER_TEXT_COLOR,
)


class MenuScreenMockTest(unittest.TestCase):
    @patch("tools.screen_mocks.menu.BgmPlayer")
    @patch("tools.screen_mocks.menu.pyxel.run")
    @patch("tools.screen_mocks.menu.create_mock_input_reader")
    @patch("tools.screen_mocks.menu.initialize_screen_mock")
    @patch("tools.screen_mocks.menu.WindowFactory")
    @patch("tools.screen_mocks.menu.ImageResources")
    @patch("tools.screen_mocks.menu.FontResources")
    def test_creates_six_slot_main_window_and_da2_side_windows(
        self,
        fonts_class: Mock,
        images_class: Mock,
        window_factory_class: Mock,
        initialize: Mock,
        create_input_reader: Mock,
        _run: Mock,
        bgm_player_class: Mock,
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
        face_image = object()
        field_background = object()
        images_class.return_value.image.side_effect = (
            face_image,
            field_background,
        )

        mock = MenuScreenMock()

        initialize.assert_called_once_with(
            "Dungeon Antiqua ZERO Menu Screen Mock",
            display_scale=3,
        )
        self.assertIs(mock.input_reader, create_input_reader.return_value)
        self.assertIsInstance(mock.alert, MenuAlertEffect)
        bgm_player_class.assert_called_once_with(volume=3)
        self.assertIs(mock.bgm, bgm_player_class.return_value)
        mock.bgm.play.assert_called_once_with(MENU_BGM_ID)
        self.assertEqual(
            images_class.return_value.image.call_args_list,
            [
                call(FACES_IMAGE_ID),
                call(FIELD_BACKGROUND_IMAGE_ID),
            ],
        )
        self.assertIs(mock.faces, face_image)
        self.assertIs(mock.field_background, field_background)
        self.assertEqual(
            fonts.font_for.call_args_list,
            [
                call(Language.JAPANESE),
                call(Language.ENGLISH),
                call(Language.JAPANESE),
                call(Language.ENGLISH),
                call(Language.JAPANESE),
            ],
        )
        window_factory_class.assert_called_once_with(font)
        party_args = factory.create.call_args_list[0].args
        self.assertEqual(party_args[:4], PARTY_WINDOW_GRID)
        party_texts = {(text.x, text.y): text for text in party_args[4]}
        self.assertEqual(
            [member.definition.key for member in mock.party],
            ["Fiora", "Cerion", "Alvan", "Elika", "Ragna", "Dain"],
        )
        self.assertEqual(
            [member.definition.key for member in mock._main_menu_members()],
            ["Fiora", "Cerion", "Alvan", "Elika", "Ragna", "Dain"],
        )
        self.assertEqual(
            [member.formation_row for member in mock.party],
            [
                FormationRow.FRONT,
                FormationRow.BACK,
                FormationRow.FRONT,
                FormationRow.BACK,
                FormationRow.FRONT,
                FormationRow.FRONT,
            ],
        )
        self.assertEqual(party_texts[(PARTY_NAME_TEXT_X, 2)].text, "フィオラ")
        self.assertEqual(
            party_texts[(PARTY_POINT_TEXT_X, 5)].text,
            "ＨＰ　　４４／　４４",
        )
        self.assertEqual(
            party_texts[(PARTY_POINT_TEXT_X, 8)].text,
            "ＭＰ　　１２／　１２",
        )
        self.assertEqual(party_texts[(PARTY_NAME_TEXT_X, 11)].text, "セリオン")
        self.assertEqual(party_texts[(PARTY_NAME_TEXT_X, 20)].text, "アルヴァン")
        self.assertEqual(party_texts[(PARTY_NAME_TEXT_X, 29)].text, "エリカ")
        self.assertEqual(party_texts[(PARTY_NAME_TEXT_X, 38)].text, "ラグナ")
        self.assertEqual(
            party_texts[(PARTY_POINT_TEXT_X, 44)].color,
            DISABLED_COLOR,
        )
        self.assertEqual(
            party_texts[(PARTY_NAME_TEXT_X, 49)].text,
            "ダイン（ひかえ）",
        )
        self.assertEqual(
            party_texts[(PARTY_NAME_TEXT_X, 49)].color,
            RESERVE_MEMBER_TEXT_COLOR,
        )
        self.assertEqual(
            party_texts[(PARTY_POINT_TEXT_X, 52)].color,
            RESERVE_MEMBER_TEXT_COLOR,
        )
        self.assertEqual(
            party_texts[(PARTY_POINT_TEXT_X, 55)].color,
            RESERVE_MEMBER_TEXT_COLOR,
        )
        self.assertEqual(
            [target.key for target in mock._sort_cursor_targets()],
            list(range(6)),
        )
        self.assertEqual(
            mock._sort_cursor_targets()[-1].y,
            PARTY_CURSOR_Y
            + 5 * PARTY_MEMBER_ROW_HEIGHT
            + RESERVE_MEMBER_Y_OFFSET_GRID,
        )
        five_member_texts = mock._party_window_texts(
            mock.party[:5],
            mock.localized,
            mock.localized_texts,
        )
        five_member_names = [
            text.y
            for text in five_member_texts
            if text.x == PARTY_NAME_TEXT_X
        ]
        self.assertEqual(
            five_member_names,
            [
                2 + index * PARTY_MEMBER_ROW_HEIGHT_WITHOUT_RESERVE
                for index in range(5)
            ],
        )

        args = factory.create.call_args_list[1].args
        self.assertEqual(args[:4], (48, 0, 16, 27))
        self.assertEqual(
            [(text.text, text.x, text.y) for text in args[4]],
            [
                (label, 4, 2 + index * 3)
                for index, label in enumerate(
                    (
                        "アイテム",
                        "じゅもん",
                        "そうび",
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
        self.assertIsNone(mock.party_cursor)
        self.assertIsNone(mock.sort_source_index)
        self.assertIsNone(mock.sort_source_cursor)
        self.assertIsNone(mock.settings_window)
        self.assertIsNone(mock.settings_cursor)
        self.assertIsNone(mock.confirmation_window)
        self.assertIsNone(mock.confirmation_cursor)
        self.assertIsNone(mock.pending_settings_action)
        self.assertFalse(mock.animate_main_windows_with_fade)
        self.assertTrue(mock.showing_field)
        self.assertIsNone(mock.item_screen)
        self.assertIsNone(mock.equipment_screen)
        self.assertIsNone(mock.status_screen)
        self.assertIsNone(mock.spell_screen)
        self.assertEqual(len(mock.spells), 38)
        self.assertEqual(mock.selected_member_index, 0)
        self.assertIs(mock.party_window, party_window)
        self.assertIs(mock.info_window, info_window)
        self.assertIs(mock.close_guide_window, close_guide_window)
        self.assertEqual(
            mock.windows,
            [party_window, command_window, info_window, close_guide_window],
        )
        self.assertTrue(
            all(
                create_call.kwargs["opened"] is False
                for create_call in factory.create.call_args_list
            )
        )
        for window in mock.windows:
            window.open.assert_called_once_with()
        info_args = factory.create.call_args_list[2].args
        self.assertEqual(info_args[:4], (48, 27, 16, 27))
        self.assertEqual(
            [(text.text, text.x, text.y) for text in info_args[4]],
            [
                ("Ｇｏｌｄ", 2, 2),
                ("９９９９９９", 2, 5),
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

        rebuilt_windows = tuple(Mock() for _ in range(4))
        factory.create.reset_mock()
        factory.create.side_effect = rebuilt_windows

        mock._build_main_windows(animate=False)

        self.assertTrue(
            all(
                create_call.kwargs["opened"] is True
                for create_call in factory.create.call_args_list
            )
        )
        for window in rebuilt_windows:
            window.open.assert_not_called()

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
        self.assertEqual(japanese["term.formation.reserve"], "（ひかえ）")
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
        self.assertEqual(
            english["term.formation.reserve"],
            "（Ｒｅｓｅｒｖｅ）",
        )
        self.assertEqual(chinese["menu.command.item"], "道具")
        self.assertEqual(chinese["menu.info.experience"], "经验值")
        self.assertEqual(chinese["term.formation.reserve"], "（替补）")
        self.assertEqual(
            chinese["menu.close_guide"],
            "%CANCEL%：关闭",
        )
        self.assertEqual(japanese["settings.bgm.label"], "ＢＧＭおんりょう")
        self.assertEqual(japanese["settings.se.label"], "ＳＥおんりょう")
        self.assertEqual(
            japanese["settings.guide.language.1"].narrow_spans,
            ((0, 33),),
        )
        self.assertEqual(english["settings.display.smooth"], "Ｓｍｏｏｔｈｅｄ")
        self.assertEqual(chinese["settings.return_title"], "返回标题界面")
        self.assertEqual(set(japanese), set(english))
        self.assertEqual(set(japanese), set(chinese))

    def test_restart_settings_are_restored_from_environment(self) -> None:
        settings = Settings(
            language=Language.SIMPLIFIED_CHINESE,
            bgm_volume=2,
            se_volume=1,
            screen_scale=4,
            display_mode=DisplayMode.SMOOTH,
        )
        with patch.dict(
            "tools.screen_mocks.menu.os.environ",
            {MENU_MOCK_SETTINGS_ENV: json.dumps(settings.to_dict())},
            clear=True,
        ):
            restored = MenuScreenMock._settings_from_environment()

        self.assertEqual(restored, settings)

    @patch("tools.screen_mocks.menu.WindowFactory")
    def test_builds_da2_settings_rows_and_language_guide(
        self,
        window_factory_class: Mock,
    ) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        mock.settings = Settings()
        mock.texts = TextCatalog.from_json(APP_ROOT / "data" / "texts.json")
        mock.localized = localized_menu_texts(
            mock.texts,
            Language.JAPANESE,
        )
        mock.fonts = Mock()
        mock.localized_texts = Mock()
        mock.localized_texts.create.side_effect = (
            lambda text, x, y, **_kwargs: Mock(text=text, x=x, y=y)
        )
        mock.debug_texts = Mock()
        mock.debug_texts.create.side_effect = (
            lambda text, x, y, **_kwargs: Mock(text=text, x=x, y=y)
        )
        factory = window_factory_class.return_value
        window = factory.create.return_value
        cursor = window.set_cursor.return_value
        cursor.selected_key = "language"

        mock._build_settings_window()

        self.assertEqual(SETTINGS_WINDOW_GRID, (4, 12, 56, 36))
        self.assertEqual(factory.create.call_args.args[:4], SETTINGS_WINDOW_GRID)
        self.assertFalse(factory.create.call_args.kwargs["opened"])
        window.open.assert_called_once_with()
        placements = {
            (text.x, text.y): text.text for text in factory.create.call_args.args[4]
        }
        self.assertEqual(placements[(SETTINGS_LABEL_X, 2)], "Ｌａｎｇｕａｇｅ")
        self.assertEqual(placements[(28, 2)], "：")
        self.assertEqual(placements[(SETTINGS_VALUE_X, 2)], "にほんご")
        self.assertEqual(placements[(SETTINGS_LABEL_X, 5)], "ＢＧＭおんりょう")
        self.assertEqual(placements[(SETTINGS_VALUE_X, 5)], "３")
        self.assertEqual(placements[(SETTINGS_LABEL_X, 8)], "ＳＥおんりょう")
        self.assertEqual(placements[(SETTINGS_VALUE_X, 8)], "３")
        self.assertEqual(placements[(SETTINGS_VALUE_X, 11)], "７６８×７２０")
        self.assertEqual(placements[(SETTINGS_VALUE_X, 14)], "ピクセル")
        self.assertEqual(
            placements[(SETTINGS_LABEL_X, 20)],
            "タイトルがめんへ　もどる",
        )
        self.assertEqual(
            placements[(SETTINGS_LABEL_X, 23)],
            "ゲームを　しゅうりょうする",
        )
        debug_text_call = next(
            text_call
            for text_call in mock.debug_texts.create.call_args_list
            if text_call.args[0] == "デバッグメニュー"
        )
        self.assertEqual(debug_text_call.kwargs["color"], NEGATIVE_COLOR)
        self.assertEqual(
            placements[(SETTINGS_LABEL_X, SETTINGS_GUIDE_Y)],
            "げんごを　きりかえられます",
        )

    @patch("tools.screen_mocks.menu.WindowFactory")
    def test_english_return_confirmation_fits_widened_window_on_one_line(
        self,
        window_factory_class: Mock,
    ) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        mock.settings = Settings(language=Language.ENGLISH)
        mock.texts = TextCatalog.from_json(APP_ROOT / "data" / "texts.json")
        mock.localized = localized_menu_texts(
            mock.texts,
            Language.ENGLISH,
        )
        mock.fonts = Mock()
        mock.localized_texts = Mock()
        mock.localized_texts.create.side_effect = (
            lambda text, x, y, **_kwargs: Mock(text=text, x=x, y=y)
        )
        mock.settings_cursor = Mock(active=True)
        factory = window_factory_class.return_value
        factory.create.return_value.set_cursor.return_value = Mock()

        mock._start_confirmation("return_title")

        placements = [
            (text.text, text.x, text.y)
            for text in factory.create.call_args.args[4]
        ]
        self.assertEqual(factory.create.call_args.args[:4], (8, 22, 48, 16))
        self.assertFalse(factory.create.call_args.kwargs["opened"])
        self.assertEqual(
            placements[0],
            ("Ｒｅｔｕｒｎ　ｔｏ　ｔｉｔｌｅ　ｓｃｒｅｅｎ，　ＯＫ？", 4, 2),
        )
        factory.create.return_value.open.assert_called_once_with()

    def test_update_passes_logical_navigation_to_command_window(self) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState(
            navigation=Direction.DOWN,
            held_direction=Direction.DOWN,
        )
        mock.command_window = Mock()
        mock.command_cursor = Mock(selected_key="item")
        mock.party_cursor = None
        mock.alert = Mock()
        mock.settings_cursor = None
        mock.confirmation_cursor = None

        mock.update()

        mock.command_window.update.assert_called_once_with(Direction.DOWN)

    def test_opening_windows_advance_and_block_menu_input(self) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        mock.alert = Mock()
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState(
            navigation=Direction.DOWN,
            held_direction=Direction.DOWN,
        )
        opening_window = Mock(is_animating=True)
        mock.windows = (opening_window,)
        mock.settings_window = None
        mock.confirmation_window = None
        mock.command_window = Mock()

        mock.update()

        opening_window.update.assert_called_once_with()
        mock.command_window.update.assert_not_called()

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
        self.assertEqual(RESERVE_MEMBER_TEXT_COLOR, 4)
        self.assertEqual(POSITIVE_COLOR, 29)
        self.assertEqual(NEGATIVE_COLOR, 45)

    def test_cancel_fades_from_main_menu_to_mock_field(self) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState(
            cancel=InputButton(triggered=True, held=True)
        )
        mock.command_window = Mock()
        mock.command_cursor = Mock(selected_key="item", active=True)
        mock.palette_shifter = Mock(base_colors=(0x000000,))
        mock.showing_field = False
        mock.party_cursor = None
        mock.alert = Mock()
        mock.settings_cursor = None
        mock.confirmation_cursor = None

        mock.update()

        self.assertIs(
            mock.pending_screen_change,
            MenuScreenChange.SHOW_FIELD,
        )
        self.assertFalse(mock.command_cursor.active)
        self.assertFalse(mock.showing_field)
        for _frame in range(DEFAULT_FADE_FRAME_COUNT):
            mock._update_fade()

        self.assertTrue(mock.showing_field)
        self.assertIsNone(mock.pending_screen_change)
        mock.command_window.update.assert_not_called()

    def test_menu_button_fades_from_mock_field_back_to_menu(self) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState(
            menu=InputButton(triggered=True, held=True)
        )
        mock.command_cursor = Mock(active=False)
        mock.palette_shifter = Mock(base_colors=(0x000000,))
        mock.showing_field = True
        mock.alert = Mock()
        window = Mock(is_animating=True)
        mock.windows = (window,)

        mock.update()

        self.assertIs(
            mock.pending_screen_change,
            MenuScreenChange.SHOW_MENU,
        )
        self.assertTrue(mock.showing_field)
        for _frame in range(DEFAULT_FADE_FRAME_COUNT):
            mock._update_fade()

        self.assertFalse(mock.showing_field)
        self.assertTrue(mock.command_cursor.active)
        self.assertIsNone(mock.pending_screen_change)
        window.restart_opening.assert_called_once_with()
        self.assertEqual(window.update.call_count, 2)
        self.assertTrue(mock.animate_main_windows_with_fade)

        for _frame in range(DEFAULT_FADE_FRAME_COUNT):
            mock._update_fade()

        self.assertEqual(window.update.call_count, 8)
        self.assertFalse(mock.animate_main_windows_with_fade)

    @patch("tools.screen_mocks.menu.pyxel.quit")
    def test_cancel_on_mock_field_still_exits_the_mock(self, quit_game: Mock) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState(
            cancel=InputButton(triggered=True, held=True)
        )
        mock.showing_field = True
        mock.alert = Mock()

        mock.update()

        quit_game.assert_called_once_with()

    @patch("tools.screen_mocks.menu.pyxel.cls")
    @patch("tools.screen_mocks.menu.pyxel.camera")
    @patch("tools.screen_mocks.menu.pyxel.blt")
    def test_draw_uses_full_screen_mock_field_background(
        self,
        blt: Mock,
        camera: Mock,
        clear_screen: Mock,
    ) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        mock.showing_field = True
        mock.field_background = object()
        mock.alert = Mock(camera_x=0)

        mock.draw()

        clear_screen.assert_called_once_with(0)
        blt.assert_called_once_with(
            0,
            0,
            mock.field_background,
            0,
            0,
            256,
            240,
        )
        self.assertEqual(camera.call_args_list, [call(0, 0), call()])

    @patch("tools.screen_mocks.menu.pyxel.cls")
    @patch("tools.screen_mocks.menu.pyxel.camera")
    @patch("tools.screen_mocks.menu.pyxel.blt")
    def test_draws_windows_and_offsets_back_row_faces(
        self,
        blt: Mock,
        camera: Mock,
        clear_screen: Mock,
    ) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        party_window = Mock()
        side_window = Mock()
        mock.windows = (party_window, side_window)
        mock.party_window = party_window
        mock.party_cursor = None
        mock.sort_source_cursor = None
        mock.alert = Mock(camera_x=0)
        mock.settings_window = None
        mock.confirmation_window = None
        mock.faces = object()
        mock.palette_shifter = Mock()
        mock.palette_shifter.shifted.return_value = nullcontext()
        front_members = tuple(
            Mock(
                is_front_row=True,
                face_position=Mock(x=index * 32, y=0),
            )
            for index in range(5)
        )
        back = Mock(
            is_front_row=False,
            face_position=Mock(x=160, y=0),
        )
        mock.party = (*front_members, back)

        mock.draw()

        party_window.draw.assert_called_once_with()
        side_window.draw.assert_called_once_with()
        clear_screen.assert_called_once_with(0)
        self.assertEqual(camera.call_args_list, [call(0, 0), call()])
        self.assertEqual(
            blt.call_args_list,
            [
                *(
                    call(
                        PARTY_FACE_X[True],
                        PARTY_FACE_Y + index * PARTY_MEMBER_ROW_HEIGHT * 4,
                        mock.faces,
                        index * 32,
                        0,
                        PARTY_FACE_SIZE,
                        PARTY_FACE_SIZE,
                        TRANSPARENT_INDEX,
                    )
                    for index in range(5)
                ),
                call(
                    PARTY_FACE_X[False],
                    PARTY_FACE_Y
                    + 5 * PARTY_MEMBER_ROW_HEIGHT * 4
                    + RESERVE_MEMBER_Y_OFFSET_GRID * 4,
                    mock.faces,
                    160,
                    0,
                    PARTY_FACE_SIZE,
                    PARTY_FACE_SIZE,
                    TRANSPARENT_INDEX,
                ),
            ],
        )
        mock.palette_shifter.shifted.assert_called_once_with(DIMMED_PALETTE)

    @patch("tools.screen_mocks.menu.pyxel.blt")
    def test_five_member_faces_keep_twelve_pixel_gaps(self, blt: Mock) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        member = Mock(
            is_front_row=True,
            face_position=Mock(x=32, y=0),
        )
        mock.party = tuple(member if index == 1 else Mock() for index in range(5))
        mock.faces = object()

        mock._draw_party_face(1, member)

        blt.assert_called_once_with(
            PARTY_FACE_X[True],
            PARTY_FACE_Y + PARTY_MEMBER_ROW_HEIGHT_WITHOUT_RESERVE * 4,
            mock.faces,
            32,
            0,
            PARTY_FACE_SIZE,
            PARTY_FACE_SIZE,
            TRANSPARENT_INDEX,
        )

    @patch("tools.screen_mocks.menu.pyxel.cls")
    @patch("tools.screen_mocks.menu.pyxel.camera")
    @patch("tools.screen_mocks.menu.pyxel.blt")
    def test_party_faces_wait_until_party_window_is_open(
        self,
        blt: Mock,
        _camera: Mock,
        _clear_screen: Mock,
    ) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        party_window = Mock(is_open=False)
        mock.windows = (party_window,)
        mock.party_window = party_window
        mock.party_cursor = None
        mock.sort_source_cursor = None
        mock.alert = Mock(camera_x=0)
        mock.settings_window = None
        mock.confirmation_window = None
        mock.faces = object()
        mock.party = (Mock(),)

        mock.draw()

        party_window.draw.assert_called_once_with()
        blt.assert_not_called()

    def test_confirming_sort_command_activates_member_cursor(self) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState(
            confirm=InputButton(triggered=True, held=True)
        )
        mock.command_window = Mock()
        mock.command_cursor = Mock(selected_key="sort", active=True)
        mock.party_window = Mock()
        party_cursor = mock.party_window.set_cursor.return_value
        mock.party = tuple(Mock() for _ in range(5))
        mock.party_cursor = None
        mock.sort_source_index = None
        mock.sort_source_cursor = None
        mock.alert = Mock()
        mock.settings_cursor = None
        mock.confirmation_cursor = None

        mock.update()

        targets = mock.party_window.set_cursor.call_args.args[0]
        self.assertEqual(
            [(target.x, target.y, target.key) for target in targets],
            [
                (
                    PARTY_CURSOR_X,
                    PARTY_CURSOR_Y
                    + index * PARTY_MEMBER_ROW_HEIGHT_WITHOUT_RESERVE,
                    index,
                )
                for index in range(5)
            ],
        )
        self.assertIs(mock.party_cursor, party_cursor)
        self.assertFalse(mock.command_cursor.active)
        mock.command_window.update.assert_not_called()

    @patch("tools.screen_mocks.menu.ItemScreenMock")
    def test_confirming_item_command_opens_connected_item_screen(
        self,
        item_screen_class: Mock,
    ) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        input_state = InputState(
            confirm=InputButton(triggered=True, held=True)
        )
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = input_state
        mock.alert = Mock()
        mock.command_window = Mock()
        mock.command_cursor = Mock(selected_key="item", active=True)
        mock.party = (Mock(),)
        mock.items = {"POTION": Mock()}
        mock.inventory_system = Mock()
        mock.spells = {"POTION": Mock()}
        mock.settings = Settings()
        mock.texts = Mock()
        mock.fonts = Mock()
        mock.faces = object()
        mock.palette_shifter = Mock(base_colors=(0x000000,))
        mock.party_cursor = None
        mock.settings_cursor = None
        mock.confirmation_cursor = None
        mock.item_screen = None

        mock.update()

        item_screen_class.assert_not_called()
        self.assertIs(
            mock.pending_screen_change,
            MenuScreenChange.OPEN_ITEM,
        )
        self.assertTrue(mock.fade.is_active)
        self.assertFalse(mock.command_cursor.active)
        for _frame in range(DEFAULT_FADE_FRAME_COUNT):
            mock._update_fade()

        item_screen_class.assert_called_once_with(
            party=mock.party,
            items=mock.items,
            spells=mock.spells,
            settings=mock.settings,
            texts=mock.texts,
            fonts=mock.fonts,
            faces=mock.faces,
            palette_shifter=mock.palette_shifter,
            inventory_system=mock.inventory_system,
            on_invalid_action=mock.alert.start,
        )
        self.assertIs(mock.item_screen, item_screen_class.return_value)
        self.assertIsNone(mock.pending_screen_change)
        mock.command_window.update.assert_not_called()

    def test_cancel_from_item_returns_to_selected_menu_command(self) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        input_state = InputState(
            cancel=InputButton(triggered=True, held=True)
        )
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = input_state
        mock.alert = Mock()
        mock.command_cursor = Mock(active=False)
        mock.palette_shifter = Mock(base_colors=(0x000000,))
        mock.item_screen = Mock()
        mock.item_screen.update.return_value = True

        item_screen = mock.item_screen
        mock.update()

        item_screen.update.assert_called_once_with(input_state)
        self.assertIs(mock.item_screen, item_screen)
        self.assertIs(
            mock.pending_screen_change,
            MenuScreenChange.CLOSE_ITEM,
        )
        for _frame in range(DEFAULT_FADE_FRAME_COUNT):
            mock._update_fade()

        self.assertIsNone(mock.item_screen)
        self.assertTrue(mock.command_cursor.active)

    @patch("tools.screen_mocks.menu.pyxel.camera")
    @patch("tools.screen_mocks.menu.pyxel.cls")
    def test_draw_uses_item_screen_while_item_is_active(
        self,
        clear_screen: Mock,
        camera: Mock,
    ) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        mock.item_screen = Mock()
        mock.alert = Mock(camera_x=-1)

        mock.draw()

        clear_screen.assert_called_once_with(0)
        mock.item_screen.draw.assert_called_once_with()
        self.assertEqual(camera.call_args_list, [call(-1, 0), call()])

    @patch("tools.screen_mocks.menu.EquipmentScreenMock")
    def test_confirming_equipment_command_opens_connected_equipment_screen(
        self,
        equipment_screen_class: Mock,
    ) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        input_state = InputState(confirm=InputButton(triggered=True, held=True))
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = input_state
        mock.alert = Mock()
        mock.command_window = Mock()
        mock.command_cursor = Mock(selected_key="equip", active=True)
        mock.party = (Mock(),)
        mock.items = {"DAGGER": Mock()}
        mock.spells = {"FIRE1": Mock()}
        mock.inventory_system = Mock()
        mock.settings = Settings()
        mock.texts = Mock()
        mock.fonts = Mock()
        mock.faces = object()
        mock.palette_shifter = Mock(base_colors=(0x000000,))
        mock.selected_member_index = 2
        mock.party_cursor = None
        mock.settings_cursor = None
        mock.confirmation_cursor = None
        mock.equipment_screen = None

        mock.update()

        self.assertIs(
            mock.pending_screen_change,
            MenuScreenChange.OPEN_EQUIPMENT,
        )
        for _frame in range(DEFAULT_FADE_FRAME_COUNT):
            mock._update_fade()
        equipment_screen_class.assert_called_once_with(
            party=mock.party,
            items=mock.items,
            spells=mock.spells,
            settings=mock.settings,
            texts=mock.texts,
            fonts=mock.fonts,
            faces=mock.faces,
            inventory_system=mock.inventory_system,
            member_index=2,
            on_invalid_action=mock.alert.start,
        )
        self.assertIs(mock.equipment_screen, equipment_screen_class.return_value)

    def test_cancel_from_equipment_returns_to_menu_and_keeps_member(self) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        input_state = InputState(cancel=InputButton(triggered=True, held=True))
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = input_state
        mock.alert = Mock()
        mock.command_cursor = Mock(active=False)
        mock.palette_shifter = Mock(base_colors=(0x000000,))
        mock.selected_member_index = 0
        mock.equipment_screen = Mock(member_index=3)
        mock.equipment_screen.update.return_value = True
        mock._refresh_party_window_texts = Mock()

        equipment_screen = mock.equipment_screen
        mock.update()

        equipment_screen.update.assert_called_once_with(input_state)
        self.assertIs(
            mock.pending_screen_change,
            MenuScreenChange.CLOSE_EQUIPMENT,
        )
        for _frame in range(DEFAULT_FADE_FRAME_COUNT):
            mock._update_fade()
        self.assertIsNone(mock.equipment_screen)
        self.assertEqual(mock.selected_member_index, 3)
        self.assertTrue(mock.command_cursor.active)
        mock._refresh_party_window_texts.assert_called_once_with()

    @patch("tools.screen_mocks.menu.pyxel.camera")
    @patch("tools.screen_mocks.menu.pyxel.cls")
    def test_draw_uses_equipment_screen_while_equipment_is_active(
        self,
        clear_screen: Mock,
        camera: Mock,
    ) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        mock.equipment_screen = Mock()
        mock.alert = Mock(camera_x=0)

        mock.draw()

        clear_screen.assert_called_once_with(0)
        mock.equipment_screen.draw.assert_called_once_with()
        self.assertEqual(camera.call_args_list, [call(0, 0), call()])

    @patch("tools.screen_mocks.menu.StatusScreenMock")
    def test_confirming_status_command_opens_connected_status_screen(
        self,
        status_screen_class: Mock,
    ) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        input_state = InputState(
            confirm=InputButton(triggered=True, held=True)
        )
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = input_state
        mock.alert = Mock()
        mock.command_window = Mock()
        mock.command_cursor = Mock(selected_key="status", active=True)
        mock.party = (Mock(),)
        mock.settings = Settings()
        mock.texts = Mock()
        mock.fonts = Mock()
        mock.faces = object()
        mock.palette_shifter = Mock(base_colors=(0x000000,))
        mock.selected_member_index = 3
        mock.party_cursor = None
        mock.settings_cursor = None
        mock.confirmation_cursor = None
        mock.status_screen = None

        mock.update()

        status_screen_class.assert_not_called()
        self.assertIs(
            mock.pending_screen_change,
            MenuScreenChange.OPEN_STATUS,
        )
        self.assertTrue(mock.fade.is_active)
        self.assertFalse(mock.command_cursor.active)
        for _frame in range(DEFAULT_FADE_FRAME_COUNT):
            mock._update_fade()

        status_screen_class.assert_called_once_with(
            party=mock.party,
            settings=mock.settings,
            texts=mock.texts,
            fonts=mock.fonts,
            faces=mock.faces,
            member_index=3,
        )
        self.assertIs(mock.status_screen, status_screen_class.return_value)
        self.assertIsNone(mock.pending_screen_change)
        mock.command_window.update.assert_not_called()

    def test_cancel_from_status_returns_to_selected_menu_command(self) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        input_state = InputState(
            cancel=InputButton(triggered=True, held=True)
        )
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = input_state
        mock.alert = Mock()
        mock.settings = Settings()
        mock.command_cursor = Mock(active=False)
        mock.palette_shifter = Mock(base_colors=(0x000000,))
        mock.selected_member_index = 0
        mock.status_screen = Mock(settings=mock.settings, member_index=3)
        mock.status_screen.update.return_value = True

        status_screen = mock.status_screen
        mock.update()

        status_screen.update.assert_called_once_with(input_state)
        self.assertIs(mock.status_screen, status_screen)
        self.assertIs(
            mock.pending_screen_change,
            MenuScreenChange.CLOSE_STATUS,
        )
        for _frame in range(DEFAULT_FADE_FRAME_COUNT):
            mock._update_fade()

        self.assertIsNone(mock.status_screen)
        self.assertTrue(mock.command_cursor.active)
        self.assertEqual(mock.selected_member_index, 3)

    def test_fade_blocks_screen_input_and_restores_palette(self) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        mock.alert = Mock()
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState()
        mock.palette_shifter = Mock(base_colors=(0x000000,))
        mock.fade = FadeThroughBlack()
        mock.fade.start()
        mock.pending_screen_change = MenuScreenChange.OPEN_ITEM
        mock._apply_pending_screen_change = Mock()
        mock.item_screen = Mock()

        for _frame in range(DEFAULT_FADE_FRAME_COUNT * 2):
            mock.update()

        mock.item_screen.update.assert_not_called()
        mock._apply_pending_screen_change.assert_called_once_with()
        self.assertFalse(mock.fade.is_active)
        self.assertEqual(
            mock.palette_shifter.set_global_mix.call_args.kwargs,
            {"base_rate": 1.0, "target_color": 0x000000},
        )

    def test_status_return_rebuilds_changed_language_without_window_animation(
        self,
    ) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        mock.settings = Settings()
        changed_settings = Settings(language=Language.ENGLISH)
        mock.status_screen = Mock(settings=changed_settings, member_index=2)
        mock._build_main_windows = Mock()

        mock._finish_status()

        self.assertEqual(mock.settings, changed_settings)
        self.assertEqual(mock.selected_member_index, 2)
        self.assertIsNone(mock.status_screen)
        mock._build_main_windows.assert_called_once_with(
            selected_command="status",
            animate=False,
        )

    @patch("tools.screen_mocks.menu.pyxel.camera")
    @patch("tools.screen_mocks.menu.pyxel.cls")
    def test_draw_uses_status_screen_while_status_is_active(
        self,
        clear_screen: Mock,
        camera: Mock,
    ) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        mock.status_screen = Mock()
        mock.alert = Mock(camera_x=0)

        mock.draw()

        clear_screen.assert_called_once_with(0)
        mock.status_screen.draw.assert_called_once_with()
        self.assertEqual(camera.call_args_list, [call(0, 0), call()])

    @patch("tools.screen_mocks.menu.SpellScreenMock")
    def test_confirming_spell_command_opens_connected_spell_screen(
        self,
        spell_screen_class: Mock,
    ) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        input_state = InputState(
            confirm=InputButton(triggered=True, held=True)
        )
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = input_state
        mock.alert = Mock()
        mock.command_window = Mock()
        mock.command_cursor = Mock(selected_key="spell", active=True)
        mock.party = (Mock(),)
        mock.spells = {"FIRE1": Mock()}
        mock.settings = Settings()
        mock.texts = Mock()
        mock.fonts = Mock()
        mock.faces = object()
        mock.palette_shifter = Mock(base_colors=(0x000000,))
        mock.selected_member_index = 2
        mock.party_cursor = None
        mock.settings_cursor = None
        mock.confirmation_cursor = None
        mock.spell_screen = None

        mock.update()

        spell_screen_class.assert_not_called()
        self.assertIs(
            mock.pending_screen_change,
            MenuScreenChange.OPEN_SPELL,
        )
        self.assertTrue(mock.fade.is_active)
        self.assertFalse(mock.command_cursor.active)
        for _frame in range(DEFAULT_FADE_FRAME_COUNT):
            mock._update_fade()

        spell_screen_class.assert_called_once_with(
            party=mock.party,
            spells=mock.spells,
            settings=mock.settings,
            texts=mock.texts,
            fonts=mock.fonts,
            faces=mock.faces,
            member_index=2,
        )
        self.assertIs(mock.spell_screen, spell_screen_class.return_value)
        self.assertIsNone(mock.pending_screen_change)
        mock.command_window.update.assert_not_called()

    def test_cancel_from_spell_returns_to_selected_menu_command(self) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        input_state = InputState(
            cancel=InputButton(triggered=True, held=True)
        )
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = input_state
        mock.alert = Mock()
        mock.command_cursor = Mock(active=False)
        mock.palette_shifter = Mock(base_colors=(0x000000,))
        mock.selected_member_index = 0
        mock.spell_screen = Mock(member_index=2)
        mock.spell_screen.update.return_value = True

        spell_screen = mock.spell_screen
        mock.update()

        spell_screen.update.assert_called_once_with(input_state)
        self.assertIs(mock.spell_screen, spell_screen)
        self.assertIs(
            mock.pending_screen_change,
            MenuScreenChange.CLOSE_SPELL,
        )
        for _frame in range(DEFAULT_FADE_FRAME_COUNT):
            mock._update_fade()

        self.assertIsNone(mock.spell_screen)
        self.assertTrue(mock.command_cursor.active)
        self.assertEqual(mock.selected_member_index, 2)

    @patch("tools.screen_mocks.menu.pyxel.camera")
    @patch("tools.screen_mocks.menu.pyxel.cls")
    def test_draw_uses_spell_screen_while_spell_is_active(
        self,
        clear_screen: Mock,
        camera: Mock,
    ) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        mock.spell_screen = Mock()
        mock.alert = Mock(camera_x=0)

        mock.draw()

        clear_screen.assert_called_once_with(0)
        mock.spell_screen.draw.assert_called_once_with()
        self.assertEqual(camera.call_args_list, [call(0, 0), call()])

    def test_field_confirm_opens_shop_key_selector(self) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        mock.alert = Mock()
        mock.input_reader = Mock(
            poll=Mock(
                return_value=InputState(confirm=InputButton(triggered=True))
            )
        )
        mock.fade = FadeThroughBlack()
        mock.shop_screen = None
        mock.shop_selector_cursor = None
        mock.showing_field = True
        mock._start_shop_selector = Mock()

        mock.update()

        mock._start_shop_selector.assert_called_once_with()

    @patch("tools.screen_mocks.menu.pyxel.quit")
    def test_cancel_closes_shop_selector_and_restores_field_input(
        self,
        quit_game: Mock,
    ) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        mock.alert = Mock()
        mock.input_reader = Mock(
            poll=Mock(
                side_effect=(
                    InputState(cancel=InputButton(triggered=True, held=True)),
                    InputState(menu=InputButton(triggered=True, held=True)),
                )
            )
        )
        mock.fade = FadeThroughBlack()
        mock.pending_screen_change = None
        mock.shop_screen = None
        mock.shop_selector_window = Mock()
        selector_cursor = Mock()
        mock.shop_selector_cursor = selector_cursor
        mock.pending_shop = Mock()
        mock.command_cursor = Mock(active=False)
        mock.showing_field = True

        mock.update()

        self.assertIsNone(mock.shop_selector_window)
        self.assertIsNone(mock.shop_selector_cursor)
        self.assertIsNone(mock.pending_shop)
        selector_cursor.update.assert_not_called()
        quit_game.assert_not_called()

        mock.update()

        self.assertIs(mock.pending_screen_change, MenuScreenChange.SHOW_MENU)
        quit_game.assert_not_called()

    def test_shop_selector_reserves_selected_shop_for_fade_transition(self) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        selected_shop = Mock(key="TEST_SHOP")
        mock.alert = Mock()
        mock.input_reader = Mock(
            poll=Mock(
                return_value=InputState(confirm=InputButton(triggered=True))
            )
        )
        mock.fade = FadeThroughBlack()
        mock.pending_screen_change = None
        mock.shop_screen = None
        mock.shop_selector_cursor = Mock(selected_key="TEST_SHOP")
        mock.shops = (selected_shop,)
        mock.showing_field = True

        mock.update()

        self.assertIs(mock.pending_shop, selected_shop)
        self.assertIs(mock.pending_screen_change, MenuScreenChange.OPEN_SHOP)

    @patch("tools.screen_mocks.menu.WindowCursor")
    def test_selecting_fiora_and_reserve_swaps_their_order(
        self,
        window_cursor: Mock,
    ) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        mock.party_window = Mock()
        mock.party_cursor = Mock(selected_key=0)
        mock.party = tuple(
            Mock(key=key) for key in ("Fiora", "b", "c", "d", "e", "reserve")
        )
        mock.sort_source_index = None
        mock.sort_source_cursor = None
        mock.alert = Mock()
        mock._refresh_party_window_texts = Mock()

        mock._confirm_sort_member()
        mock.party_cursor.selected_key = 5
        mock._confirm_sort_member()

        self.assertEqual(
            [member.key for member in mock.party],
            ["reserve", "b", "c", "d", "e", "Fiora"],
        )
        self.assertIsNone(mock.sort_source_index)
        self.assertIsNone(mock.sort_source_cursor)
        mock._refresh_party_window_texts.assert_called_once_with()
        window_cursor.assert_called_once_with(
            mock.party_window,
            (mock._sort_source_target(0),),
            active=False,
            draw_shadow=False,
        )
        self.assertEqual(
            mock._sort_source_target(0).x,
            PARTY_CURSOR_X + SORT_SOURCE_CURSOR_X_OFFSET,
        )

    @patch("tools.screen_mocks.menu.WindowCursor")
    def test_selecting_same_member_changes_formation_row(
        self,
        _window_cursor: Mock,
    ) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        mock.party_window = Mock()
        mock.party_cursor = Mock(selected_key=0)
        front = Mock(is_front_row=True, formation_row=FormationRow.FRONT)
        other_front = Mock(is_front_row=True, formation_row=FormationRow.FRONT)
        mock.party = (front, other_front)
        mock.sort_source_index = None
        mock.sort_source_cursor = None
        mock.alert = Mock()

        mock._confirm_sort_member()
        mock._confirm_sort_member()

        self.assertIs(front.formation_row, FormationRow.BACK)
        self.assertIsNone(mock.sort_source_index)

    @patch("tools.screen_mocks.menu.WindowCursor")
    def test_reserve_is_forced_front_across_two_swaps(
        self,
        _window_cursor: Mock,
    ) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        mock.party_window = Mock()
        mock.party_cursor = Mock()
        front = Mock(
            key="front",
            is_front_row=True,
            formation_row=FormationRow.FRONT,
        )
        back_members = tuple(
            Mock(
                key=f"back-{index}",
                is_front_row=False,
                formation_row=FormationRow.BACK,
            )
            for index in range(4)
        )
        reserve = Mock(
            key="reserve",
            is_front_row=True,
            formation_row=FormationRow.FRONT,
        )
        mock.party = (front, *back_members, reserve)
        mock.sort_source_index = None
        mock.sort_source_cursor = None
        mock.alert = Mock()
        mock._refresh_party_window_texts = Mock()

        mock.party_cursor.selected_key = 1
        mock._confirm_sort_member()
        mock.party_cursor.selected_key = 5
        mock._confirm_sort_member()

        self.assertEqual(mock.party[-1].key, "back-0")
        self.assertIs(mock.party[-1].formation_row, FormationRow.FRONT)

        for index, member in enumerate(mock.party[:5]):
            member.formation_row = (
                FormationRow.FRONT if index == 0 else FormationRow.BACK
            )
        mock.party_cursor.selected_key = 0
        mock._confirm_sort_member()
        mock.party_cursor.selected_key = 5
        mock._confirm_sort_member()

        self.assertEqual(mock.party[-1].key, "front")
        self.assertIs(mock.party[-1].formation_row, FormationRow.FRONT)
        self.assertTrue(
            any(
                member.formation_row is FormationRow.FRONT
                for member in mock.party[:5]
            )
        )

    @patch("tools.screen_mocks.menu.WindowCursor")
    def test_reserve_cannot_be_changed_to_back(
        self,
        _window_cursor: Mock,
    ) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        mock.party_window = Mock()
        mock.party_cursor = Mock(selected_key=5)
        active = tuple(
            Mock(is_front_row=index == 0)
            for index in range(BATTLE_PARTY_MEMBER_COUNT)
        )
        reserve = Mock(
            is_front_row=True,
            formation_row=FormationRow.FRONT,
        )
        mock.party = (*active, reserve)
        mock.sort_source_index = None
        mock.sort_source_cursor = None
        mock.alert = Mock()

        mock._confirm_sort_member()
        mock._confirm_sort_member()

        self.assertIs(reserve.formation_row, FormationRow.FRONT)
        mock.alert.start.assert_called_once_with()

    @patch("tools.screen_mocks.menu.WindowCursor")
    def test_last_front_member_cannot_move_to_back(
        self,
        _window_cursor: Mock,
    ) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        mock.party_window = Mock()
        mock.party_cursor = Mock(selected_key=0)
        front = Mock(is_front_row=True, formation_row=FormationRow.FRONT)
        back = Mock(is_front_row=False, formation_row=FormationRow.BACK)
        mock.party = (front, back)
        mock.sort_source_index = None
        mock.sort_source_cursor = None
        mock.alert = Mock()

        mock._confirm_sort_member()
        mock._confirm_sort_member()

        self.assertIs(front.formation_row, FormationRow.FRONT)
        self.assertIsNone(mock.sort_source_index)
        mock.alert.start.assert_called_once_with()

    def test_cancel_steps_back_from_source_then_from_sort_mode(self) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState(
            cancel=InputButton(triggered=True, held=True)
        )
        mock.command_cursor = Mock(active=False)
        mock.command_window = Mock()
        mock.party_window = Mock()
        mock.party_cursor = Mock()
        mock.sort_source_index = 2
        mock.sort_source_cursor = Mock()
        mock.alert = Mock()
        mock.settings_cursor = None
        mock.confirmation_cursor = None

        mock.update()

        self.assertIsNone(mock.sort_source_index)
        self.assertIsNone(mock.sort_source_cursor)
        self.assertIsNotNone(mock.party_cursor)

        mock.update()

        self.assertIsNone(mock.party_cursor)
        self.assertTrue(mock.command_cursor.active)
        mock.party_window.clear_cursor.assert_called_once_with()

    @patch("tools.screen_mocks.menu.pyxel.play")
    def test_alert_matches_da2_sound_and_three_frame_shake(self, play: Mock) -> None:
        alert = MenuAlertEffect()

        alert.start()

        play.assert_called_once_with(ALERT_CHANNEL, ALERT_SOUND_ID)
        self.assertEqual(alert.camera_x, -1)
        alert.update()
        self.assertEqual(alert.camera_x, 1)
        alert.update()
        self.assertEqual(alert.camera_x, 0)
        alert.update()
        self.assertEqual(alert.camera_x, 0)

    @patch("tools.screen_mocks.menu.pyxel.blt")
    def test_selected_member_draws_blinking_formation_arrow(
        self,
        blt: Mock,
    ) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        mock.sort_source_index = 1
        mock.party_cursor = Mock(selected_key=1)
        mock.party = (
            Mock(is_front_row=True),
            Mock(is_front_row=False),
        )

        with patch(
            "tools.screen_mocks.menu.pyxel.frame_count",
            FORMATION_ARROW_FRAME_DURATION,
        ):
            mock._draw_formation_arrow()

        blt.assert_called_once_with(
            PARTY_FACE_X[False] - FORMATION_ARROW_WIDTH,
            PARTY_FACE_Y
            + PARTY_MEMBER_ROW_HEIGHT_WITHOUT_RESERVE * 4
            + (PARTY_FACE_SIZE - FORMATION_ARROW_HEIGHT) // 2,
            0,
            FORMATION_ARROW_LEFT_X[1],
            FORMATION_ARROW_Y,
            FORMATION_ARROW_WIDTH,
            FORMATION_ARROW_HEIGHT,
            FORMATION_ARROW_COLKEY,
        )

    @patch("tools.screen_mocks.menu.pyxel.blt")
    def test_front_member_draws_right_arrow_when_another_front_remains(
        self,
        blt: Mock,
    ) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        mock.sort_source_index = 0
        mock.party_cursor = Mock(selected_key=0)
        mock.party = (
            Mock(is_front_row=True),
            Mock(is_front_row=True),
        )

        with patch("tools.screen_mocks.menu.pyxel.frame_count", 0):
            mock._draw_formation_arrow()

        self.assertEqual(blt.call_args.args[0], PARTY_FACE_X[True] + PARTY_FACE_SIZE)
        self.assertEqual(blt.call_args.args[3], FORMATION_ARROW_RIGHT_X[0])

    @patch("tools.screen_mocks.menu.pyxel.blt")
    def test_last_front_member_does_not_draw_formation_arrow(
        self,
        blt: Mock,
    ) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        mock.sort_source_index = 0
        mock.party_cursor = Mock(selected_key=0)
        mock.party = (
            Mock(is_front_row=True),
            Mock(is_front_row=False),
        )

        mock._draw_formation_arrow()

        blt.assert_not_called()

    @patch("tools.screen_mocks.menu.pyxel.blt")
    def test_formation_arrow_is_hidden_when_cursor_moves_from_source(
        self,
        blt: Mock,
    ) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        mock.sort_source_index = 0
        mock.party_cursor = Mock(selected_key=1)
        mock.party = (
            Mock(is_front_row=True),
            Mock(is_front_row=True),
        )

        mock._draw_formation_arrow()

        blt.assert_not_called()

    def test_confirming_settings_command_opens_settings_window(self) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState(
            confirm=InputButton(triggered=True, held=True)
        )
        mock.alert = Mock()
        mock.command_window = Mock()
        mock.command_cursor = Mock(selected_key="config", active=True)
        mock.party_cursor = None
        mock.settings_cursor = None
        mock.confirmation_cursor = None
        mock._start_settings = Mock()

        mock.update()

        mock._start_settings.assert_called_once_with()
        mock.command_window.update.assert_not_called()

    def test_debug_settings_row_is_always_available_in_mock(self) -> None:
        self.assertIn(("debug", 17), SETTINGS_ROWS)

    def test_confirming_debug_setting_opens_debug_menu(self) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState(
            confirm=InputButton(triggered=True, held=True)
        )
        mock.alert = Mock()
        mock.windows = ()
        mock.command_cursor = Mock(active=False)
        mock.party_cursor = None
        mock.settings_cursor = Mock(selected_key="debug")
        mock.settings_window = Mock(is_animating=False)
        mock.confirmation_cursor = None
        mock.confirmation_window = None
        mock.debug_screen = None
        mock._start_debug_menu = Mock()

        mock.update()

        mock._start_debug_menu.assert_called_once_with()

    def test_language_setting_cycles_like_da2_and_rebuilds_windows(self) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        mock.settings = Settings()
        mock.settings_cursor = Mock(selected_key="language")
        mock.command_cursor = Mock(active=True)
        mock._build_main_windows = Mock()
        mock._refresh_settings_window = Mock()

        mock._change_setting(-1)

        self.assertIs(mock.settings.language, Language.ENGLISH)
        mock._build_main_windows.assert_called_once_with(
            selected_command="config",
            animate=False,
        )
        self.assertFalse(mock.command_cursor.active)
        mock._refresh_settings_window.assert_called_once_with(
            selected_key="language"
        )

    @patch("tools.screen_mocks.menu.pyxel.play")
    def test_se_setting_wraps_and_plays_da2_preview_sound(self, play: Mock) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        mock.settings = Settings(se_volume=4)
        mock.settings_cursor = Mock(selected_key="se")
        mock._apply_se_volume = Mock()
        mock._refresh_settings_window = Mock()

        mock._change_setting(1)

        self.assertEqual(mock.settings.se_volume, 0)
        mock._apply_se_volume.assert_called_once_with()
        play.assert_called_once_with(ALERT_CHANNEL, SE_PREVIEW_SOUND_ID)
        mock._refresh_settings_window.assert_called_once_with(selected_key="se")

    @patch("tools.screen_mocks.menu.pyxel.play")
    def test_bgm_setting_wraps_and_immediately_changes_volume(
        self,
        play: Mock,
    ) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        mock.settings = Settings(bgm_volume=4)
        mock.settings_cursor = Mock(selected_key="bgm")
        mock.bgm = Mock()
        mock._refresh_settings_window = Mock()

        mock._change_setting(1)

        self.assertEqual(mock.settings.bgm_volume, 0)
        mock.bgm.set_volume.assert_called_once_with(0)
        play.assert_not_called()
        mock._refresh_settings_window.assert_called_once_with(selected_key="bgm")

    def test_screen_size_and_display_settings_wrap_in_both_directions(self) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        mock.settings = Settings(screen_scale=1)
        mock.settings_cursor = Mock(selected_key="screen_size")
        mock._refresh_settings_window = Mock()

        mock._change_setting(-1)

        self.assertEqual(mock.settings.screen_scale, 5)

        mock.settings_cursor.selected_key = "display"
        mock._apply_display_mode = Mock()
        mock._change_setting(1)

        self.assertIs(mock.settings.display_mode, DisplayMode.SMOOTH)
        mock._apply_display_mode.assert_called_once_with()

    def test_moving_settings_cursor_refreshes_text_without_reopening_window(
        self,
    ) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        mock.alert = Mock()
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState(
            navigation=Direction.DOWN,
            held_direction=Direction.DOWN,
        )
        mock.windows = ()
        mock.confirmation_window = None
        mock.confirmation_cursor = None
        mock.settings_cursor = Mock(selected_key="se")
        mock.settings_window = Mock(is_animating=False)
        mock.settings_window.update.return_value = True
        mock._refresh_settings_window = Mock()
        mock._build_settings_window = Mock()

        mock.update()

        mock._refresh_settings_window.assert_called_once_with(selected_key="se")
        mock._build_settings_window.assert_not_called()
        mock.settings_window.open.assert_not_called()

    def test_refreshing_settings_text_keeps_existing_window_open(self) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        mock.settings_window = Mock()
        placement = Mock(
            text="guide",
            x=4,
            y=26,
            color=5,
            font=object(),
            shadow_color=0,
            baseline_offset=3,
            font_spans=(),
        )
        mock._settings_window_texts = Mock(return_value=(placement,))

        mock._refresh_settings_window("se")

        mock.settings_window.clear_texts.assert_called_once_with()
        mock.settings_window.add_text.assert_called_once_with(
            "guide",
            4,
            26,
            color=5,
            font=placement.font,
            shadow_color=0,
            baseline_offset=3,
            font_spans=(),
        )
        mock.settings_window.open.assert_not_called()

    @patch("tools.screen_mocks.menu.pyxel.reset")
    def test_return_to_title_restarts_mock_with_settings(
        self,
        reset: Mock,
    ) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        mock.settings = Settings(
            language=Language.ENGLISH,
            screen_scale=5,
        )
        with patch.dict(
            "tools.screen_mocks.menu.os.environ",
            {"PYXEL_WINDOW_STATE": "old"},
            clear=True,
        ) as environment:
            with patch(
                "tools.screen_mocks.menu.pyxel.WINDOW_STATE_ENV",
                "PYXEL_WINDOW_STATE",
            ):
                mock._restart_mock()

            self.assertNotIn("PYXEL_WINDOW_STATE", environment)
            self.assertEqual(
                json.loads(environment[MENU_MOCK_SETTINGS_ENV]),
                mock.settings.to_dict(),
            )
        reset.assert_called_once_with()

    @patch("tools.screen_mocks.menu.pyxel.quit")
    def test_confirmed_quit_exits_the_mock(self, quit_game: Mock) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        mock.alert = Mock()
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState(
            confirm=InputButton(triggered=True, held=True)
        )
        mock.confirmation_cursor = Mock(selected_key="yes")
        mock.pending_settings_action = "quit"

        mock.update()

        quit_game.assert_called_once_with()

    def test_confirmed_return_to_title_resets_the_mock(self) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        mock.alert = Mock()
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState(
            confirm=InputButton(triggered=True, held=True)
        )
        mock.confirmation_cursor = Mock(selected_key="yes")
        mock.pending_settings_action = "return_title"
        mock._restart_mock = Mock()

        mock.update()

        mock._restart_mock.assert_called_once_with()

    def test_cancel_closes_settings_and_reactivates_command_cursor(self) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        mock.alert = Mock()
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState(
            cancel=InputButton(triggered=True, held=True)
        )
        mock.command_cursor = Mock(active=False)
        mock.settings_window = Mock()
        mock.settings_cursor = Mock()
        mock.confirmation_cursor = None

        mock.update()

        self.assertIsNone(mock.settings_window)
        self.assertIsNone(mock.settings_cursor)
        self.assertTrue(mock.command_cursor.active)

    def test_declining_confirmation_returns_to_settings(self) -> None:
        mock = MenuScreenMock.__new__(MenuScreenMock)
        mock.alert = Mock()
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState(
            confirm=InputButton(triggered=True, held=True)
        )
        mock.confirmation_cursor = Mock(selected_key="no")
        mock.settings_cursor = Mock(active=False)
        mock.confirmation_window = Mock()
        mock.pending_settings_action = "return_title"

        mock.update()

        self.assertIsNone(mock.confirmation_cursor)
        self.assertIsNone(mock.pending_settings_action)
        self.assertTrue(mock.settings_cursor.active)


if __name__ == "__main__":
    unittest.main()
