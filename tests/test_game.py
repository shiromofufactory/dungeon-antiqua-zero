from __future__ import annotations

from contextlib import nullcontext
import json
import unittest
from unittest.mock import Mock, call, patch

from tools._bootstrap import APP_ROOT
from battle_command_memory import BattleCommandMemory
from ui.debug_menu import DebugShopTarget, DebugTeleportTarget
from game import (
    ALERT_CHANNEL,
    ALERT_SOUND_ID,
    FIELD_POISON_SE_CHANNEL,
    FIELD_POISON_SE_ID,
    FIELD_FADE_PULSE_MIN_BASE_RATE,
    FIELD_FADE_PULSE_PALETTE,
    FIELD_FADE_PULSE_TARGET_COLOR,
    FIRST_BATTLE_HINT_ID,
    FIRST_DEFEAT_RESTART_HINT_ID,
    FIRST_DUNGEON_EXIT_HINT_ID,
    FIRST_RESULT_HINT_ID,
    FACES_IMAGE_ID,
    INITIAL_GOLD,
    INITIAL_PARTY_KEYS,
    GAME_SETTINGS_ENV,
    FORMATION_ARROW_COLKEY,
    FORMATION_ARROW_FRAME_DURATION,
    FORMATION_ARROW_HEIGHT,
    FORMATION_ARROW_LEFT_X,
    FORMATION_ARROW_RIGHT_X,
    FORMATION_ARROW_WIDTH,
    FORMATION_ARROW_Y,
    MENU_COMMANDS,
    NEW_GAME_EVENT_ID,
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
    PARTY_STATUS_TEXT_X,
    PARTY_WINDOW_GRID,
    RESERVE_MEMBER_Y_OFFSET_GRID,
    SE_CHANNELS,
    SE_PREVIEW_SOUND_ID,
    SITE_MAP_FADE_FRAME_COUNT,
    SITE_NAME_FONT_ROLE,
    SITE_NAME_LABEL_GAP,
    SETTINGS_GUIDE_ROW_HEIGHT,
    SETTINGS_GUIDE_Y,
    SETTINGS_LABEL_X,
    SETTINGS_ROWS,
    SETTINGS_VALUE_X,
    SETTINGS_WINDOW_GRID,
    SORT_SOURCE_CURSOR_X_OFFSET,
    TELEPORT_SOUND_CHANNEL,
    TELEPORT_SOUND_ID,
    WELCOME_BGM_ID,
    WORLD_MAP_ID,
    WORLD_MAP_START_POSITION,
    MenuAlertEffect,
    GameScreenChange,
    Game,
    TextCatalog,
    TRANSPARENT_INDEX,
    localized_menu_texts,
)
from field import FieldActors, FieldPosition
from input import Direction, InputButton, InputState
from localization import Localizer
from member import BATTLE_PARTY_MEMBER_COUNT, FormationRow, Race
from resources import (
    CompiledMap,
    FontRole,
    MapCell,
    MapResourceError,
    MapArrivalPoint,
    MapDestination,
    WorldSite,
)
from rendering import (
    DEFAULT_FADE_FRAME_COUNT,
    DIMMED_PALETTE,
    MONOCHROME_PALETTE,
    FadeThroughBlack,
    FadeEvent,
    FadePhase,
)
from scenes import BattlePhase, BattleResult
from state import DisplayMode, Language, SaveData, Settings
from systems import AUTO_SAVE_SLOT, InventorySystem, SaveSystemError
from ui import (
    DEFAULT_TEXT_COLOR,
    DISABLED_COLOR,
    NEGATIVE_COLOR,
    POSITIVE_COLOR,
    RESERVE_MEMBER_TEXT_COLOR,
    WINDOW_ANIMATION_FRAME_COUNT,
    Window,
    WindowText,
)
from world_sites import WorldSiteCatalog


class GameTest(unittest.TestCase):
    def test_field_fade_activates_once_on_a_dungeon_floor(self) -> None:
        game = Game.__new__(Game)
        game.current_map = Mock(profile="dungeon")
        game.palette_shifter = Mock()
        game.field_fade_active = False
        game.save_data = SaveData(encounter_count=119)

        self.assertTrue(game._activate_field_fade())
        self.assertTrue(game.field_fade_active)
        self.assertEqual(game.field_fade_pulse_frame, 0)
        self.assertEqual(game.save_data.encounter_count, 119)
        self.assertFalse(game._activate_field_fade())

        game._update_field_fade_pulse()

        self.assertEqual(game.field_fade_pulse_frame, 1)
        game.palette_shifter.define_mix.assert_called_with(
            FIELD_FADE_PULSE_PALETTE,
            base_rate=1.0
            - (1.0 - FIELD_FADE_PULSE_MIN_BASE_RATE) / 45,
            target_color=FIELD_FADE_PULSE_TARGET_COLOR,
        )

    def test_field_fade_cannot_activate_outside_a_dungeon(self) -> None:
        game = Game.__new__(Game)
        game.current_map = Mock(profile="town")
        game.palette_shifter = Mock()
        game.field_fade_active = False

        self.assertFalse(game._activate_field_fade())
        self.assertFalse(game.field_fade_active)
        game.palette_shifter.define_mix.assert_not_called()

    def test_birds_draw_above_field_and_below_field_overlays(self) -> None:
        game = Game.__new__(Game)
        game.field = Mock()
        game.field_renderer = Mock()
        game.field_renderer.camera_position.return_value = (32, 48)
        game.field_birds = Mock()
        game._draw_site_name = Mock()
        game.event_message = Mock()
        drawing = Mock()
        drawing.attach_mock(game.field_renderer.draw, "field")
        drawing.attach_mock(game.field_birds.draw, "birds")
        drawing.attach_mock(game._draw_site_name, "site")
        drawing.attach_mock(game.event_message.draw, "message")

        game._draw_field_screen()

        self.assertEqual([entry[0] for entry in drawing.mock_calls],
                         ["field", "birds", "site", "message"])
        self.assertEqual(game.field_birds.draw.call_args.kwargs["camera"], (32, 48))

    @patch("game.FieldActors")
    def test_birds_are_reset_on_map_change_and_only_created_for_worldmap(
        self, actors_class: Mock,
    ) -> None:
        game = Game.__new__(Game)
        game.save_data = SaveData()
        game.images = Mock()
        game.images.entry.return_value = Mock(width=384, height=384)
        game.party = (Mock(definition=Mock(battle_sprite=0)),)
        actors_class.return_value.actors = ()
        game.current_map = Mock(spec=CompiledMap, map_id="worldmap", profile="world")

        game._reset_field_actors()
        first_flock = game.field_birds
        self.assertIsNotNone(first_flock)
        game._reset_field_actors()
        self.assertIsNot(game.field_birds, first_flock)

        for map_id, profile in (("town", "town"), ("cave", "dungeon"),
                                ("other_world", "world")):
            game.current_map = Mock(spec=CompiledMap, map_id=map_id, profile=profile)
            game._reset_field_actors()
            self.assertIsNone(game.field_birds)

    def test_bird_flight_continues_during_messages_and_pauses_during_fades(self) -> None:
        game = Game.__new__(Game)
        game.alert = Mock()
        game.input_reader = Mock()
        game.input_reader.poll.return_value = InputState()
        game._update_fade = Mock(return_value=False)
        game.showing_field = True
        game.field = Mock(world_x=120, world_y=112)
        game.field_renderer = Mock()
        game.field_renderer.camera_position.return_value = (0, 0)
        game.field_birds = Mock()
        game.treasure_message = Mock()
        game.treasure_message.update.return_value = False

        game.update()
        game.field_birds.update.assert_called_once_with(camera=(0, 0), player=(120, 112))
        game.field_birds.update.reset_mock()
        game._update_fade.return_value = True
        game.update()
        game.field_birds.update.assert_not_called()

    def test_field_player_floating_is_derived_from_fairy_race(self) -> None:
        game = Game.__new__(Game)
        game.field_actors = object.__new__(FieldActors)
        game.field_renderer = Mock()
        game.field = object()
        game.field_prop_image = object()
        game.field_actor_character_image = object()
        game.field_actor_pc_character_image = object()
        game.fairy_pc_sprite_indices = frozenset((0, 1, 2))
        game.field_player_character_image = object()
        game.field_treasure_image = object()
        game._draw_site_name = Mock()
        member = Mock()
        member.definition.battle_sprite = 3
        game._field_player_member = Mock(return_value=member)

        for race, key, expected, phase in (
            (Race.FAIRY, "Fiora", True, 77),
            (Race.HUMAN, "Bandana", False, 29),
        ):
            with self.subTest(race=race):
                member.definition.race = race
                member.definition.key = key
                game.field_renderer.draw.reset_mock()

                game._draw_field_screen()

                self.assertIs(
                    game.field_renderer.draw.call_args.kwargs["player_floating"],
                    expected,
                )
                self.assertEqual(
                    game.field_renderer.draw.call_args.kwargs[
                        "player_floating_phase"
                    ],
                    phase,
                )
                self.assertEqual(
                    game.field_renderer.draw.call_args.kwargs[
                        "actor_pc_fairy_sprite_indices"
                    ],
                    frozenset((0, 1, 2)),
                )

    def test_field_fade_draws_only_the_player_with_the_pulsing_palette(self) -> None:
        game = Game.__new__(Game)
        game.field = Mock()
        game.field_renderer = Mock()
        game.field_actors = None
        game.field_fade_active = True
        game.palette_shifter = Mock()
        game._draw_site_name = Mock()

        game._draw_field_screen()

        game.field_renderer.draw.assert_called_once_with(
            game.field,
            player_palette_shifter=game.palette_shifter,
            player_palette_name=FIELD_FADE_PULSE_PALETTE,
        )

    @patch("game.StartMenuOverlay")
    @patch("game.BgmPlayer")
    @patch("game.create_game_input_reader")
    @patch("game.WindowFactory")
    @patch("game.FieldRenderer")
    @patch("game.FieldMovement")
    @patch("game.MapResources")
    @patch("game.ImageResources")
    @patch("game.FontResources")
    def test_creates_initial_party_and_da2_side_windows(
        self,
        fonts_class: Mock,
        images_class: Mock,
        map_resources_class: Mock,
        field_movement_class: Mock,
        field_renderer_class: Mock,
        window_factory_class: Mock,
        create_input_reader: Mock,
        bgm_player_class: Mock,
        start_menu_class: Mock,
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
        images_class.return_value.image.return_value = face_image
        world_map = map_resources_class.return_value.map.return_value
        world_map.sites = ()

        palette_shifter = Mock()
        mock = Game(
            settings=Settings(),
            palette_shifter=palette_shifter,
        )

        self.assertIs(mock.input_reader, create_input_reader.return_value)
        self.assertIs(mock.palette_shifter, palette_shifter)
        self.assertIsInstance(mock.alert, MenuAlertEffect)
        bgm_player_class.assert_called_once_with(volume=3)
        self.assertIs(mock.bgm, bgm_player_class.return_value)
        mock.bgm.play.assert_called_once_with(WELCOME_BGM_ID)
        self.assertEqual(
            images_class.return_value.image.call_args_list,
            [call(FACES_IMAGE_ID)],
        )
        self.assertIs(mock.faces, face_image)
        map_resources_class.return_value.map.assert_called_once_with(WORLD_MAP_ID)
        self.assertEqual(
            (WORLD_MAP_START_POSITION.x, WORLD_MAP_START_POSITION.y),
            (17, 39),
        )
        field_movement_class.assert_called_once_with(
            world_map,
            start=WORLD_MAP_START_POSITION,
        )
        field_renderer_class.assert_called_once_with(
            world_map,
            screen_width=256,
            screen_height=240,
        )
        self.assertIs(mock.world_map, world_map)
        self.assertIs(mock.current_map, world_map)
        self.assertEqual(mock.world_sites.sites, ())
        self.assertEqual(
            mock.texts.text(
                "location.fairy_village",
                Localizer(Language.JAPANESE),
                default="fairy_village",
            ),
            "妖精の里",
        )
        self.assertIs(mock.field, field_movement_class.return_value)
        self.assertIs(mock.field_renderer, field_renderer_class.return_value)
        self.assertEqual(
            fonts.font_for.call_args_list,
            [
                call(Language.JAPANESE),
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
            list(INITIAL_PARTY_KEYS),
        )
        self.assertEqual(
            [member.definition.key for member in mock._main_menu_members()],
            list(INITIAL_PARTY_KEYS),
        )
        self.assertEqual(
            [member.formation_row for member in mock.party],
            [
                FormationRow.FRONT,
                FormationRow.FRONT,
            ],
        )
        self.assertEqual(mock.save_data.gold, INITIAL_GOLD)
        self.assertEqual(dict(mock.inventory_system.quantities), {})
        self.assertEqual(mock.inventory_system.items, ())
        self.assertEqual(party_texts[(PARTY_NAME_TEXT_X, 2)].text, "フィオラ")
        self.assertEqual(
            party_texts[(PARTY_POINT_TEXT_X, 5)].text,
            "ＨＰ　　４４／　４４",
        )
        self.assertEqual(
            party_texts[(PARTY_POINT_TEXT_X, 8)].text,
            "ＭＰ　　１２／　１２",
        )
        self.assertEqual(party_texts[(PARTY_NAME_TEXT_X, 13)].text, "セリオン")
        self.assertEqual(
            [target.key for target in mock._sort_cursor_targets()],
            list(range(2)),
        )
        self.assertEqual(
            mock._sort_cursor_targets()[-1].y,
            PARTY_CURSOR_Y
            + PARTY_MEMBER_ROW_HEIGHT_WITHOUT_RESERVE,
        )

        args = factory.create.call_args_list[1].args
        self.assertEqual(args[:4], (48, 0, 16, 31))
        self.assertEqual(
            [(text.text, text.x, text.y) for text in args[4]],
            [
                (label, 4, 2 + index * 3)
                for index, label in enumerate(
                    (
                        "かいふく",
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
        self.assertFalse(mock.showing_field)
        self.assertIs(mock.start_screen, start_menu_class.return_value)
        self.assertIsNone(mock.item_screen)
        self.assertIsNone(mock.equipment_screen)
        self.assertIsNone(mock.status_screen)
        self.assertIsNone(mock.spell_screen)
        self.assertEqual(len(mock.spells), 40)
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
        self.assertEqual(info_args[:4], (48, 31, 16, 26))
        self.assertEqual(
            [(text.text, text.x, text.y) for text in info_args[4]],
            [
                ("Ｇｏｌｄ", 2, 1),
                ("　　　１００", 2, 4),
                ("けいけんち", 2, 7),
                ("　　　　　０", 2, 10),
                ("なんいど", 2, 13),
                ("ノーマル", 4, 16),
                ("プレイじかん", 2, 19),
                ("　００：００", 2, 22),
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
            catalog.lines(
                "settings.guide.language", Localizer(Language.JAPANESE)
            )[1].narrow_spans,
            (),
        )
        self.assertEqual(english["settings.display.smooth"], "Ｓｍｏｏｔｈｅｄ")
        self.assertEqual(japanese["settings.screen_flash.normal"], "つうじょう")
        self.assertEqual(chinese["settings.screen_flash.reduced"], "减轻")
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
            "game.os.environ",
            {GAME_SETTINGS_ENV: json.dumps(settings.to_dict())},
            clear=True,
        ):
            restored = Game.settings_from_environment()

        self.assertEqual(restored, settings)

    def test_startup_settings_are_restored_from_repository(self) -> None:
        repository = Mock()
        repository.load.return_value = Settings(language=Language.ENGLISH)
        with patch.dict("game.os.environ", {}, clear=True):
            restored = Game.settings_from_environment(repository)

        self.assertIs(restored.language, Language.ENGLISH)
        repository.load.assert_called_once_with()

    @patch("game.WindowFactory")
    def test_builds_da2_settings_rows_and_language_guide(
        self,
        window_factory_class: Mock,
    ) -> None:
        mock = Game.__new__(Game)
        mock.settings = Settings()
        mock.texts = TextCatalog.from_json(APP_ROOT / "data" / "texts.json")
        mock.localized = localized_menu_texts(
            mock.texts,
            Language.JAPANESE,
        )
        japanese_font = object()
        english_font = object()
        mock.fonts = Mock()
        mock.fonts.font_for.side_effect = {
            Language.JAPANESE: japanese_font,
            Language.ENGLISH: english_font,
        }.__getitem__
        mock.fonts.baseline_offset_for.side_effect = {
            Language.JAPANESE: 0,
            Language.ENGLISH: 3,
        }.__getitem__
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

        self.assertEqual(SETTINGS_WINDOW_GRID, (4, 4, 56, 52))
        self.assertEqual(SETTINGS_GUIDE_Y, 41)
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
        self.assertEqual(placements[(SETTINGS_LABEL_X, 17)], "がめんフラッシュ")
        self.assertEqual(placements[(SETTINGS_VALUE_X, 17)], "つうじょう")
        self.assertEqual(
            placements[(SETTINGS_LABEL_X, 20)],
            mock.localized["settings.in_game_hints.label"],
        )
        self.assertEqual(placements[(SETTINGS_VALUE_X, 20)], "オン")
        self.assertEqual(placements[(SETTINGS_LABEL_X, 23)], "コマンドきおく")
        self.assertEqual(placements[(SETTINGS_VALUE_X, 23)], "オン")
        self.assertEqual(placements[(SETTINGS_LABEL_X, 26)], "オートのじゅもん")
        self.assertEqual(placements[(SETTINGS_VALUE_X, 26)], "つかう")
        self.assertEqual(
            placements[(SETTINGS_LABEL_X, 32)],
            "タイトルがめんへ　もどる",
        )
        self.assertEqual(
            placements[(SETTINGS_LABEL_X, 35)],
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
        language_switching = next(
            text
            for text in factory.create.call_args.args[4]
            if text.y == SETTINGS_GUIDE_Y + SETTINGS_GUIDE_ROW_HEIGHT
        )
        self.assertEqual(
            language_switching.text,
            "Ｌａｎｇｕａｇｅ　ｓｗｉｔｃｈｉｎｇ　（ＪＰ　／　ＥＮ　／　ＣＮ）",
        )
        self.assertIs(language_switching.font, english_font)
        self.assertEqual(language_switching.baseline_offset, 3)

    def test_settings_guides_display_all_authored_lines_in_each_language(self) -> None:
        records = json.loads((APP_ROOT / "data" / "texts.json").read_text())
        for record in records:
            if record["text_key"] == "settings.guide.screen_flash":
                for field in ("text_ja", "text_en", "text_zhcn"):
                    record[field].append("SMASH")
        catalog = TextCatalog.from_records(records)
        game = Game.__new__(Game)
        game.texts = catalog
        game.fonts = Mock()
        game.fonts.baseline_offset_for.return_value = 3
        game.localized_texts = Mock()
        game.localized_texts.create.side_effect = (
            lambda text, x, y, **_kwargs: Mock(text=text, x=x, y=y)
        )
        game.debug_texts = game.localized_texts
        for language in Language:
            game.settings = Settings(language=language)
            game.localized = localized_menu_texts(catalog, language)
            for selected_key in (
                "language", "bgm", "se", "screen_size", "display",
                "screen_flash", "in_game_hints", "quit",
            ):
                with self.subTest(language=language, selected_key=selected_key):
                    texts = game._settings_window_texts(selected_key)
                    guide = [text for text in texts if text.y >= SETTINGS_GUIDE_Y]
                    expected = (
                        catalog.lines(
                            f"settings.guide.{selected_key}", Localizer(language)
                        )
                        if selected_key != "quit" else ()
                    )
                    self.assertEqual(
                        [(text.text, text.y) for text in guide],
                        [
                            (line, SETTINGS_GUIDE_Y + i * SETTINGS_GUIDE_ROW_HEIGHT)
                            for i, line in enumerate(expected)
                        ],
                    )
                    if selected_key == "language":
                        self.assertEqual(len(guide), 1 if language is Language.ENGLISH else 2)
                    if selected_key == "screen_flash":
                        self.assertEqual(len(guide), 3)

    @patch("game.WindowFactory")
    def test_english_return_confirmation_fits_widened_window_on_one_line(
        self,
        window_factory_class: Mock,
    ) -> None:
        mock = Game.__new__(Game)
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
        mock = Game.__new__(Game)
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
        mock = Game.__new__(Game)
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
        mock = Game.__new__(Game)
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

    def test_party_condition_uses_name_row_and_negative_color(self) -> None:
        mock = Game.__new__(Game)
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
        member = Mock(
            hp=40,
            max_hp=44,
            mp=12,
            max_mp=12,
            heal_and_poison_amount=-1,
        )
        member.definition.localized_name.return_value = "フィオラ"
        member.status.return_value = "%POISON%どく"

        texts = mock._party_window_texts(
            (member,),
            localized_menu_texts(mock.texts, Language.JAPANESE),
            text_factory,
        )

        condition = next(text for text in texts if text.x == PARTY_STATUS_TEXT_X)
        self.assertEqual((condition.text, condition.y), ("%POISON%どく", 2))
        self.assertEqual(condition.color, NEGATIVE_COLOR)
        member.status.assert_called_once_with(
            Localizer(Language.JAPANESE),
            mock.texts,
        )

    def test_shared_semantic_color_numbers_match_palette_roles(self) -> None:
        self.assertEqual(DISABLED_COLOR, 3)
        self.assertEqual(RESERVE_MEMBER_TEXT_COLOR, 4)
        self.assertEqual(POSITIVE_COLOR, 29)
        self.assertEqual(NEGATIVE_COLOR, 45)

    def test_cancel_fades_from_main_menu_to_field(self) -> None:
        mock = Game.__new__(Game)
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
            GameScreenChange.SHOW_FIELD,
        )
        self.assertFalse(mock.command_cursor.active)
        self.assertFalse(mock.showing_field)
        for _frame in range(DEFAULT_FADE_FRAME_COUNT):
            mock._update_fade()

        self.assertTrue(mock.showing_field)
        self.assertIsNone(mock.pending_screen_change)
        mock.command_window.update.assert_not_called()

    def test_menu_button_fades_from_field_back_to_menu(self) -> None:
        mock = Game.__new__(Game)
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState(
            menu=InputButton(triggered=True, held=True)
        )
        mock.command_cursor = Mock(active=False)
        mock.palette_shifter = Mock(base_colors=(0x000000,))
        mock.showing_field = True
        mock.selected_member_index = 1
        mock.menu_member_selected = True
        mock.alert = Mock()
        window = Mock(is_animating=True)
        mock.windows = (window,)
        mock._refresh_party_window_texts = Mock()
        mock._refresh_info_window_texts = Mock()

        mock.update()

        self.assertIs(
            mock.pending_screen_change,
            GameScreenChange.SHOW_MENU,
        )
        self.assertTrue(mock.showing_field)
        for _frame in range(DEFAULT_FADE_FRAME_COUNT):
            mock._update_fade()

        self.assertFalse(mock.showing_field)
        self.assertEqual(mock.selected_member_index, 0)
        self.assertFalse(mock.menu_member_selected)
        self.assertTrue(mock.command_cursor.active)
        self.assertIsNone(mock.pending_screen_change)
        mock._refresh_party_window_texts.assert_called_once_with()
        mock._refresh_info_window_texts.assert_called_once_with()
        window.restart_opening.assert_called_once_with()
        self.assertEqual(window.update.call_count, 2)
        self.assertTrue(mock.animate_main_windows_with_fade)

        for _frame in range(DEFAULT_FADE_FRAME_COUNT):
            mock._update_fade()

        self.assertEqual(window.update.call_count, 8)
        self.assertFalse(mock.animate_main_windows_with_fade)

    def test_menu_info_refresh_uses_current_shared_experience(self) -> None:
        game = Game.__new__(Game)
        game.save_data = SaveData(gold=45, experience=75)
        game.localized = {
            "menu.info.gold": "Gold",
            "menu.info.experience": "EXP",
            "menu.info.difficulty": "Difficulty",
            "menu.difficulty.normal": "Normal",
            "menu.info.play_time": "Time",
        }
        game.localized_texts = Mock()
        game.localized_texts.create.side_effect = (
            lambda text, x, y: WindowText(text, x, y)
        )
        game.fonts = Mock()
        game.info_window = Mock()

        game._refresh_info_window_texts()

        game.info_window.clear_texts.assert_called_once_with()
        experience_text = game.info_window.add_text.call_args_list[3].args[0]
        self.assertTrue(experience_text.endswith("７５"))

    def test_menu_screen_change_restores_standard_fade_speed(self) -> None:
        mock = Game.__new__(Game)
        mock.fade = FadeThroughBlack(SITE_MAP_FADE_FRAME_COUNT)
        mock.pending_screen_change = None

        mock._begin_screen_change(GameScreenChange.SHOW_MENU)

        self.assertEqual(mock.fade.frame_count, DEFAULT_FADE_FRAME_COUNT)

    @patch("game.pyxel.quit")
    def test_cancel_on_field_has_no_temporary_exit_action(
        self,
        quit_game: Mock,
    ) -> None:
        mock = Game.__new__(Game)
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState(
            cancel=InputButton(triggered=True, held=True)
        )
        mock.showing_field = True
        mock.alert = Mock()
        mock.field = Mock()
        mock._handle_arrived_site = Mock()
        mock._refresh_site_name_label = Mock()

        mock.update()

        quit_game.assert_not_called()
        mock.field.update.assert_called_once_with(None)

    @patch("game.pyxel.cls")
    @patch("game.pyxel.camera")
    def test_draw_uses_compiled_world_map_field(
        self,
        camera: Mock,
        clear_screen: Mock,
    ) -> None:
        mock = Game.__new__(Game)
        mock.showing_field = True
        mock.field = object()
        mock.field_renderer = Mock()
        mock.alert = Mock(camera_x=0)

        mock.draw()

        clear_screen.assert_called_once_with(0)
        mock.field_renderer.draw.assert_called_once_with(mock.field)
        self.assertEqual(camera.call_args_list, [call(0, 0), call()])

    def test_field_passes_held_direction_to_movement(self) -> None:
        mock = Game.__new__(Game)
        mock.alert = Mock()
        mock.input_reader = Mock(
            poll=Mock(return_value=InputState(held_direction=Direction.LEFT))
        )
        mock.fade = FadeThroughBlack()
        mock.shop_screen = None
        mock.showing_field = True
        mock.field = Mock()

        mock.update()

        mock.field.update.assert_called_once_with(Direction.LEFT)

    def test_dungeon_step_applies_member_health_changes_before_encounter(
        self,
    ) -> None:
        calls: list[str] = []
        arrived = FieldPosition(3, 4)
        members = (Mock(), Mock())
        for member in members:
            member.hp = 10
            member.apply_heal_and_poison.side_effect = (
                lambda: calls.append("health")
            )
        mock = Game.__new__(Game)
        mock.current_map = Mock(profile="dungeon")
        mock.party = members
        mock.field = Mock(is_moving=False, arrived_position=arrived)
        mock.field_actors = None
        mock.pending_screen_change = None
        mock._release_latch_blocks_field = Mock(return_value=False)
        mock._try_open_treasure = Mock(return_value=False)
        mock._try_field_trigger = Mock(return_value=False)
        mock._handle_arrived_site = Mock()
        mock._advance_random_encounter = Mock(
            side_effect=lambda: calls.append("encounter") or False
        )
        mock._refresh_site_name_label = Mock()

        mock._update_field(InputState())

        for member in members:
            member.apply_heal_and_poison.assert_called_once_with()
        self.assertEqual(calls, ["health", "health", "encounter"])

    def test_step_health_changes_are_limited_to_dungeons(self) -> None:
        member = Mock()
        mock = Game.__new__(Game)
        mock.party = (member,)

        for profile in ("world", "town"):
            with self.subTest(profile=profile):
                mock.current_map = Mock(profile=profile)
                mock._apply_dungeon_step_health_changes()

        member.apply_heal_and_poison.assert_not_called()

    def test_field_death_message_precedes_random_encounter(self) -> None:
        arrived = FieldPosition(3, 4)
        game = Game.__new__(Game)
        game.current_map = Mock(profile="dungeon")
        game.field = Mock(is_moving=False, arrived_position=arrived)
        game.field_actors = None
        game.pending_screen_change = None
        game.field_condition_message = None
        game._release_latch_blocks_field = Mock(return_value=False)
        game._try_open_treasure = Mock(return_value=False)
        game._try_field_trigger = Mock(return_value=False)
        game._handle_arrived_site = Mock()
        game._apply_dungeon_step_health_changes = Mock(
            side_effect=lambda: setattr(
                game,
                "field_condition_message",
                Mock(),
            )
        )
        game._advance_random_encounter = Mock()
        game._refresh_site_name_label = Mock()

        game._update_field(InputState())

        game._advance_random_encounter.assert_not_called()
        game._refresh_site_name_label.assert_not_called()

    @patch("game.MessageOverlay")
    def test_field_death_is_reported_and_first_recoverable_rear_advances(
        self,
        message_overlay: Mock,
    ) -> None:
        defeated = Mock(
            hp=1,
            paralyzed=False,
            is_front_row=True,
            formation_row=FormationRow.FRONT,
        )
        defeated.definition.localized_name.return_value = "フィオラ"
        defeated.apply_heal_and_poison.side_effect = lambda: setattr(
            defeated,
            "hp",
            0,
        )
        rear = Mock(
            hp=10,
            paralyzed=False,
            is_front_row=False,
            formation_row=FormationRow.BACK,
        )
        rear.definition.localized_name.return_value = "セリオン"
        reserve = Mock(
            hp=10,
            paralyzed=False,
            is_front_row=True,
            formation_row=FormationRow.FRONT,
        )
        reserve.definition.localized_name.return_value = "エリカ"
        game = Game.__new__(Game)
        game.current_map = Mock(profile="dungeon")
        game.party = (defeated, rear, Mock(hp=0), Mock(hp=0), Mock(hp=0), reserve)
        game.settings = Settings(language=Language.JAPANESE)
        game.texts = TextCatalog.from_json(APP_ROOT / "data" / "texts.json")
        game.fonts = object()

        game._apply_dungeon_step_health_changes()

        self.assertFalse(game.field_party_annihilated_pending)
        self.assertIs(rear.formation_row, FormationRow.FRONT)
        self.assertIs(game.field_condition_message, message_overlay.return_value)
        self.assertEqual(
            message_overlay.call_args.kwargs["lines"],
            (
                "フィオラは　力尽きた",
                "セリオンが　前列に進み出た",
            ),
        )

    @patch("game.MessageOverlay")
    def test_field_death_reports_annihilation_when_no_member_is_recoverable(
        self,
        message_overlay: Mock,
    ) -> None:
        defeated = Mock(
            hp=1,
            paralyzed=False,
            is_front_row=True,
            formation_row=FormationRow.FRONT,
        )
        defeated.definition.localized_name.return_value = "フィオラ"
        defeated.apply_heal_and_poison.side_effect = lambda: setattr(
            defeated,
            "hp",
            0,
        )
        game = Game.__new__(Game)
        game.current_map = Mock(profile="dungeon")
        game.party = (defeated,)
        game.settings = Settings(language=Language.JAPANESE)
        game.texts = TextCatalog.from_json(APP_ROOT / "data" / "texts.json")
        game.fonts = object()

        game._apply_dungeon_step_health_changes()

        self.assertTrue(game.field_party_annihilated_pending)
        self.assertEqual(
            message_overlay.call_args.kwargs["lines"],
            (
                "フィオラは　力尽きた",
                "全滅した．．．",
            ),
        )

    def test_closing_field_annihilation_message_begins_defeat_return(
        self,
    ) -> None:
        game = Game.__new__(Game)
        game.field_condition_message = Mock()
        game.field_party_annihilated_pending = True
        game._begin_battle_return = Mock()

        game._finish_field_condition_message()

        self.assertIsNone(game.field_condition_message)
        self.assertFalse(game.field_party_annihilated_pending)
        game._begin_battle_return.assert_called_once_with(BattleResult.DEFEAT)

    def test_field_player_uses_first_recoverable_member(self) -> None:
        defeated = Mock(hp=0, paralyzed=False)
        paralyzed = Mock(hp=10, paralyzed=True)
        recoverable = Mock(hp=10, paralyzed=False)
        game = Game.__new__(Game)
        game.party = (defeated, paralyzed, recoverable)

        self.assertIs(game._field_player_member(), recoverable)

    @patch("game.play_se")
    @patch("game.pyxel.play_pos", return_value=None)
    def test_poison_sound_repeats_while_walking_in_a_dungeon(
        self,
        play_pos: Mock,
        play_se_mock: Mock,
    ) -> None:
        mock = Game.__new__(Game)
        mock.current_map = Mock(profile="dungeon")
        mock.field = Mock(is_moving=True)
        mock.party = (Mock(poisoned=True),)

        mock._play_dungeon_poison_movement_sound()

        play_pos.assert_called_once_with(FIELD_POISON_SE_CHANNEL)
        play_se_mock.assert_called_once_with(FIELD_POISON_SE_ID)

    @patch("game.play_se")
    @patch("game.pyxel.play_pos")
    def test_hp_reducing_equipment_alone_does_not_play_poison_sound(
        self,
        play_pos: Mock,
        play_se_mock: Mock,
    ) -> None:
        mock = Game.__new__(Game)
        mock.current_map = Mock(profile="dungeon")
        mock.field = Mock(is_moving=True)
        mock.party = (Mock(poisoned=False, heal_and_poison_amount=-1),)

        mock._play_dungeon_poison_movement_sound()

        play_pos.assert_not_called()
        play_se_mock.assert_not_called()

    def test_step_event_skips_dungeon_health_changes(self) -> None:
        arrived = FieldPosition(3, 4)
        member = Mock()
        mock = Game.__new__(Game)
        mock.current_map = Mock(profile="dungeon")
        mock.party = (member,)
        mock.field = Mock(is_moving=False, arrived_position=arrived)
        mock.field_actors = None
        mock.pending_screen_change = None
        mock._release_latch_blocks_field = Mock(return_value=False)
        mock._try_open_treasure = Mock(return_value=False)
        mock._try_field_trigger = Mock(return_value=True)

        mock._update_field(InputState())

        member.apply_heal_and_poison.assert_not_called()

    def test_map_exit_step_skips_dungeon_health_changes(self) -> None:
        arrived = FieldPosition(3, 4)
        member = Mock()
        mock = Game.__new__(Game)
        mock.current_map = Mock(profile="dungeon")
        mock.party = (member,)
        mock.field = Mock(is_moving=False, arrived_position=arrived)
        mock.field_actors = None
        mock.pending_screen_change = None
        mock._release_latch_blocks_field = Mock(return_value=False)
        mock._try_open_treasure = Mock(return_value=False)
        mock._try_field_trigger = Mock(return_value=False)
        mock._handle_arrived_site = Mock(
            side_effect=lambda: setattr(
                mock,
                "pending_screen_change",
                GameScreenChange.CHANGE_MAP,
            )
        )
        mock._advance_random_encounter = Mock()
        mock._refresh_site_name_label = Mock()

        mock._update_field(InputState())

        member.apply_heal_and_poison.assert_not_called()
        mock._advance_random_encounter.assert_not_called()

    @patch("game.LocalizedWindowTextFactory")
    def test_nearby_site_name_uses_current_language_text(
        self,
        localized_factory_class: Mock,
    ) -> None:
        site = WorldSite(
            id="sample_town",
            name_text_key="location.sample_town",
            entrance_cells=(MapCell(2, 2),),
            destination=MapDestination("sample_town", "from_world"),
        )
        world_map = object()
        mock = Game.__new__(Game)
        mock.settings = Settings(language=Language.JAPANESE)
        mock.texts = Mock()
        mock.texts.text.return_value = "サンプルの町"
        mock.fonts = Mock()
        mock.world_map = world_map
        mock.current_map = world_map
        mock.world_sites = WorldSiteCatalog((site,))
        mock.field = Mock(position=FieldPosition(5, 2))
        mock.site_name_site = None
        mock.site_name_text = None
        mock._site_name_cache = None
        localized_text = Mock()
        localized_factory_class.from_language.return_value.create.return_value = (
            localized_text
        )

        mock._refresh_site_name_label()

        mock.texts.text.assert_called_once()
        localized_factory_class.from_language.assert_called_once_with(
            mock.fonts,
            Language.JAPANESE,
            role=SITE_NAME_FONT_ROLE,
        )
        localized_factory_class.from_language.return_value.create.assert_called_once_with(
            "サンプルの町",
            0,
            0,
        )
        self.assertIs(mock.site_name_site, site)
        self.assertIs(mock.site_name_text, localized_text)

    @patch("game.draw_tagged_text")
    def test_draws_site_name_below_site_when_player_is_above(
        self,
        draw_text: Mock,
    ) -> None:
        site = WorldSite(
            id="sample_town",
            name_text_key="location.sample_town",
            entrance_cells=(MapCell(4, 5), MapCell(5, 5)),
            destination=MapDestination("sample_town", "from_world"),
        )
        font = Mock()
        font.text_width.return_value = 48
        text = WindowText(
            "サンプルの町",
            0,
            0,
            font=font,
            baseline_offset=1,
        )
        mock = Game.__new__(Game)
        mock.site_name_site = site
        mock.site_name_text = text
        mock.current_map = Mock(tile_size=16)
        mock.settings = Settings(language=Language.JAPANESE)
        mock.fonts = Mock()
        mock.fonts.line_height_for.return_value = 13
        mock.field = Mock(position=FieldPosition(4, 4))
        mock.field_renderer = Mock()
        mock.field_renderer.camera_position.return_value = (32, 48)

        mock._draw_site_name()

        draw_text.assert_called_once_with(
            (64 + 96 - 48) // 2 - 32,
            96 - 48 + SITE_NAME_LABEL_GAP,
            "サンプルの町",
            text.color,
            font,
            shadow_color=text.shadow_color,
            text_y_offset=1,
            font_spans=(),
        )
        mock.fonts.line_height_for.assert_called_once_with(
            Language.JAPANESE,
            role=SITE_NAME_FONT_ROLE,
        )

    @patch("game.draw_tagged_text")
    def test_draws_site_name_above_site_when_player_is_not_above(
        self,
        draw_text: Mock,
    ) -> None:
        site = WorldSite(
            id="sample_town",
            name_text_key="location.sample_town",
            entrance_cells=(MapCell(4, 5), MapCell(5, 5)),
            destination=MapDestination("sample_town", "from_world"),
        )
        font = Mock()
        font.text_width.return_value = 48
        text = WindowText("サンプルの町", 0, 0, font=font)
        mock = Game.__new__(Game)
        mock.site_name_site = site
        mock.site_name_text = text
        mock.current_map = Mock(tile_size=16)
        mock.settings = Settings(language=Language.JAPANESE)
        mock.fonts = Mock()
        mock.fonts.line_height_for.return_value = 13
        mock.field = Mock(position=FieldPosition(4, 6))
        mock.field_renderer = Mock()
        mock.field_renderer.camera_position.return_value = (32, 48)

        mock._draw_site_name()

        draw_text.assert_called_once_with(
            (64 + 96 - 48) // 2 - 32,
            80 - 48 - 13 - SITE_NAME_LABEL_GAP,
            "サンプルの町",
            text.color,
            font,
            shadow_color=text.shadow_color,
            text_y_offset=0,
            font_spans=(),
        )

    @patch("game.pyxel.play")
    @patch("game.FieldRenderer")
    @patch("game.FieldMovement")
    def test_arriving_at_site_changes_map_at_fade_midpoint(
        self,
        field_movement_class: Mock,
        field_renderer_class: Mock,
        play: Mock,
    ) -> None:
        site = WorldSite(
            id="sample_town",
            name_text_key="location.sample_town",
            entrance_cells=(MapCell(2, 2),),
            destination=MapDestination("sample_town", "from_world"),
        )
        arrival = MapArrivalPoint(
            "from_world",
            MapCell(4, 5),
            "left",
            False,
            None,
        )
        world_map = object()
        target_map = Mock(bgm_id="da3-town")
        target_map.sites = ()
        target_map.arrival_point.return_value = arrival
        mock = Game.__new__(Game)
        mock.field = Mock(arrived_position=FieldPosition(2, 2))
        mock.world_map = world_map
        mock.current_map = world_map
        mock.world_sites = WorldSiteCatalog((site,))
        mock.current_sites = mock.world_sites
        mock.map_resources = Mock()
        mock.map_resources.map.return_value = target_map
        mock.travel_system = Mock()
        mock.save_data = SaveData()
        mock.fade = FadeThroughBlack()
        mock.pending_screen_change = None
        mock.pending_site = None
        mock.pending_target_map = None
        mock.pending_target_arrival = None
        mock.bgm = Mock()
        mock.field_fade_active = True
        member = Mock()
        mock.party = (member,)

        mock._handle_arrived_site()

        self.assertIs(
            mock.pending_screen_change,
            GameScreenChange.CHANGE_MAP,
        )
        self.assertEqual(mock.fade.frame_count, SITE_MAP_FADE_FRAME_COUNT)
        mock.travel_system.enter_site.assert_not_called()
        mock._apply_pending_screen_change()
        mock.travel_system.enter_site.assert_called_once_with(mock.save_data, site)
        self.assertTrue(mock.auto_save_after_fade)
        field_movement_class.assert_called_once_with(
            target_map,
            start=FieldPosition(4, 5),
            facing=Direction.LEFT,
        )
        field_renderer_class.assert_called_once_with(
            target_map,
            screen_width=256,
            screen_height=240,
        )
        self.assertIs(mock.current_map, target_map)
        self.assertFalse(mock.field_fade_active)
        mock.bgm.play.assert_called_once_with("da3-town")
        member.recover_world_map_entry_ailments.assert_not_called()
        play.assert_not_called()

    def test_missing_site_map_does_not_mark_site_visited(self) -> None:
        site = WorldSite(
            id="sample_town",
            name_text_key="location.sample_town",
            entrance_cells=(MapCell(2, 2),),
            destination=MapDestination("missing_map", "from_world"),
        )
        world_map = object()
        mock = Game.__new__(Game)
        mock.field = Mock(arrived_position=FieldPosition(2, 2))
        mock.world_map = world_map
        mock.current_map = world_map
        mock.world_sites = WorldSiteCatalog((site,))
        mock.current_sites = mock.world_sites
        mock.map_resources = Mock()
        mock.map_resources.map.side_effect = MapResourceError("missing")
        mock.travel_system = Mock()
        mock.pending_screen_change = None

        mock._handle_arrived_site()

        mock.travel_system.enter_site.assert_not_called()
        self.assertIsNone(mock.pending_screen_change)

    @patch("game.FieldRenderer")
    @patch("game.FieldMovement")
    def test_nonworld_move_source_returns_to_world_without_marking_site_visited(
        self,
        field_movement_class: Mock,
        field_renderer_class: Mock,
    ) -> None:
        exit_site = WorldSite(
            id="exit_to_world",
            name_text_key="location.exit_to_world",
            entrance_cells=(MapCell(2, 2),),
            destination=MapDestination("worldmap", "from_dungeon"),
        )
        arrival = MapArrivalPoint(
            "from_dungeon",
            MapCell(8, 9),
            "down",
            False,
            None,
        )
        dungeon_map = object()
        world_map = Mock(sites=(), bgm_id="da3-field")
        world_map.arrival_point.return_value = arrival
        mock = Game.__new__(Game)
        mock.field = Mock(arrived_position=FieldPosition(2, 2))
        mock.world_map = world_map
        mock.current_map = dungeon_map
        mock.world_sites = WorldSiteCatalog(())
        mock.current_sites = WorldSiteCatalog((exit_site,))
        mock.map_resources = Mock()
        mock.map_resources.map.return_value = world_map
        mock.travel_system = Mock()
        mock.save_data = SaveData()
        mock.fade = FadeThroughBlack()
        mock.pending_screen_change = None
        mock.pending_site = None
        mock.pending_target_map = None
        mock.pending_target_arrival = None
        mock.bgm = Mock()
        members = (Mock(), Mock())
        mock.party = members

        mock._handle_arrived_site()
        mock._apply_pending_screen_change()

        mock.travel_system.enter_site.assert_not_called()
        self.assertTrue(mock.auto_save_after_fade)
        self.assertIs(mock.current_map, world_map)
        self.assertEqual(mock.current_sites.sites, ())
        field_movement_class.assert_called_once_with(
            world_map,
            start=FieldPosition(8, 9),
            facing=Direction.DOWN,
        )
        field_renderer_class.assert_called_once_with(
            world_map,
            screen_width=256,
            screen_height=240,
        )
        mock.bgm.play.assert_called_once_with("da3-field")
        for member in members:
            member.recover_world_map_entry_ailments.assert_called_once_with()

    def test_debug_teleport_targets_use_visited_sites_and_localized_names(
        self,
    ) -> None:
        site = WorldSite(
            id="sample_town",
            name_text_key="location.sample_town",
            entrance_cells=(MapCell(2, 2),),
            destination=MapDestination("sample_town", "from_world"),
        )
        mock = Game.__new__(Game)
        mock.settings = Settings(language=Language.JAPANESE)
        mock.save_data = SaveData(visited_site_ids={"sample_town"})
        mock.travel_system = Mock()
        mock.travel_system.teleport_destinations.return_value = (site,)
        mock.texts = Mock()
        mock.texts.text.return_value = "サンプルの町"

        targets = mock._debug_teleport_targets()

        self.assertEqual(
            targets,
            (DebugTeleportTarget("sample_town", "サンプルの町"),),
        )
        mock.travel_system.teleport_destinations.assert_called_once_with(
            mock.save_data
        )
        self.assertEqual(
            mock.texts.text.call_args.args[0],
            "location.sample_town",
        )
        self.assertIsInstance(mock.texts.text.call_args.args[1], Localizer)

    @patch("game.pyxel.play")
    def test_debug_teleport_stages_destination_and_starts_slow_fade(
        self,
        play: Mock,
    ) -> None:
        destination = MapDestination("worldmap", "sample_town_world")
        arrival = MapArrivalPoint(
            "sample_town_world",
            MapCell(7, 8),
            "down",
            True,
            "sample_town",
        )
        target_map = Mock()
        target_map.arrival_point.return_value = arrival
        mock = Game.__new__(Game)
        mock.save_data = SaveData(visited_site_ids={"sample_town"})
        mock.travel_system = Mock()
        mock.travel_system.teleport_destination.return_value = destination
        mock.map_resources = Mock()
        mock.map_resources.map.return_value = target_map
        mock.pending_site = Mock()
        mock.pending_target_map = None
        mock.pending_target_arrival = None
        mock.pending_screen_change = None
        mock.fade = FadeThroughBlack()

        started = mock._start_debug_teleport("sample_town")

        self.assertTrue(started)
        mock.travel_system.teleport_destination.assert_called_once_with(
            mock.save_data,
            "sample_town",
        )
        self.assertIsNone(mock.pending_site)
        self.assertIs(mock.pending_target_map, target_map)
        self.assertIs(mock.pending_target_arrival, arrival)
        self.assertIs(
            mock.pending_screen_change,
            GameScreenChange.TELEPORT,
        )
        self.assertEqual(mock.pending_teleport_source, "debug")
        self.assertEqual(mock.fade.frame_count, SITE_MAP_FADE_FRAME_COUNT)
        play.assert_called_once_with(TELEPORT_SOUND_CHANNEL, TELEPORT_SOUND_ID)

    @patch("game.pyxel.play")
    def test_field_teleport_uses_the_same_staged_transition(self, play: Mock) -> None:
        destination = MapDestination("worldmap", "sample_town_world")
        arrival = MapArrivalPoint(
            "sample_town_world",
            MapCell(7, 8),
            "down",
            True,
            "sample_town",
        )
        target_map = Mock()
        target_map.arrival_point.return_value = arrival
        mock = Game.__new__(Game)
        mock.save_data = SaveData(visited_site_ids={"sample_town"})
        mock.travel_system = Mock()
        mock.travel_system.teleport_destination.return_value = destination
        mock.map_resources = Mock()
        mock.map_resources.map.return_value = target_map
        mock.pending_site = None
        mock.pending_target_map = None
        mock.pending_target_arrival = None
        mock.pending_screen_change = None
        mock.fade = FadeThroughBlack()

        self.assertTrue(mock._start_field_teleport("sample_town"))

        self.assertEqual(mock.pending_teleport_source, "spell")
        self.assertIs(mock.pending_target_map, target_map)
        self.assertIs(mock.pending_target_arrival, arrival)
        self.assertIs(mock.pending_screen_change, GameScreenChange.TELEPORT)
        play.assert_called_once_with(TELEPORT_SOUND_CHANNEL, TELEPORT_SOUND_ID)

    def test_applying_spell_teleport_closes_spell_menu_and_returns_to_field(
        self,
    ) -> None:
        mock = Game.__new__(Game)
        mock.pending_teleport_source = "spell"
        mock.spell_screen = Mock(member_index=2)
        mock.selected_member_index = 0
        mock._refresh_party_window_texts = Mock()
        mock._apply_pending_map_destination = Mock()
        mock.showing_field = False

        mock._apply_pending_teleport()

        self.assertEqual(mock.selected_member_index, 2)
        self.assertIsNone(mock.spell_screen)
        self.assertTrue(mock.showing_field)
        self.assertIsNone(mock.pending_teleport_source)
        mock._refresh_party_window_texts.assert_called_once_with()
        mock._apply_pending_map_destination.assert_called_once_with()

    def test_applying_item_teleport_closes_item_menu_and_returns_to_field(
        self,
    ) -> None:
        mock = Game.__new__(Game)
        mock.pending_teleport_source = "item"
        mock.item_screen = Mock()
        mock._apply_pending_map_destination = Mock()
        mock.showing_field = False

        mock._apply_pending_teleport()

        self.assertIsNone(mock.item_screen)
        self.assertTrue(mock.showing_field)
        self.assertIsNone(mock.pending_teleport_source)
        mock._apply_pending_map_destination.assert_called_once_with()

    @patch("game.pyxel.channels")
    def test_se_volume_applies_to_every_game_se_channel(
        self,
        channels: Mock,
    ) -> None:
        channel_values = [Mock() for _ in range(max(SE_CHANNELS) + 1)]
        channels.__len__.return_value = len(channel_values)
        channels.__getitem__.side_effect = channel_values.__getitem__
        mock = Game.__new__(Game)
        mock.settings = Settings(se_volume=3)

        mock._apply_se_volume()

        for channel in SE_CHANNELS:
            self.assertEqual(channel_values[channel].gain, 0.15)

    @patch("game.FieldRenderer")
    @patch("game.FieldMovement")
    def test_applying_debug_teleport_returns_directly_to_field(
        self,
        field_movement_class: Mock,
        field_renderer_class: Mock,
    ) -> None:
        arrival = MapArrivalPoint(
            "sample_town_world",
            MapCell(7, 8),
            "left",
            True,
            "sample_town",
        )
        target_map = Mock(sites=(), bgm_id="da3-field")
        member = Mock()
        party = (member,)
        mock = Game.__new__(Game)
        mock.pending_target_map = target_map
        mock.pending_target_arrival = arrival
        mock.pending_teleport_source = "debug"
        mock.world_map = target_map
        mock.debug_screen = Mock(party=party)
        mock.party = ()
        mock._force_reserve_front = Mock()
        mock.selected_member_index = 5
        mock._build_main_windows = Mock()
        mock.command_cursor = Mock(active=False)
        mock.settings_window = Mock()
        mock.settings_cursor = Mock(active=False)
        mock.showing_field = False
        mock._refresh_site_name_label = Mock()
        mock.travel_system = Mock()
        mock.bgm = Mock()

        mock._apply_pending_teleport()

        field_movement_class.assert_called_once_with(
            target_map,
            start=FieldPosition(7, 8),
            facing=Direction.LEFT,
        )
        field_renderer_class.assert_called_once_with(
            target_map,
            screen_width=256,
            screen_height=240,
        )
        self.assertTrue(mock.showing_field)
        self.assertIsNone(mock.debug_screen)
        self.assertIsNone(mock.pending_teleport_source)
        self.assertIsNone(mock.settings_window)
        self.assertIsNone(mock.settings_cursor)
        mock.bgm.play.assert_called_once_with("da3-field")
        member.recover_world_map_entry_ailments.assert_called_once_with()
        self.assertTrue(mock.command_cursor.active)
        self.assertEqual(mock.party, party)
        self.assertEqual(mock.selected_member_index, 0)
        mock.travel_system.enter_site.assert_not_called()

    @patch("game.pyxel.cls")
    @patch("game.pyxel.camera")
    @patch("game.pyxel.blt")
    def test_draws_windows_and_offsets_back_row_faces(
        self,
        blt: Mock,
        camera: Mock,
        clear_screen: Mock,
    ) -> None:
        mock = Game.__new__(Game)
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
                is_dead=False,
                is_front_row=True,
                face_position=Mock(x=index * 32, y=0),
            )
            for index in range(5)
        )
        back = Mock(
            is_dead=False,
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

    @patch("game.pyxel.cls")
    @patch("game.pyxel.camera")
    @patch("game.pyxel.blt")
    def test_dead_main_menu_face_uses_monochrome_palette(
        self,
        blt: Mock,
        _camera: Mock,
        _clear_screen: Mock,
    ) -> None:
        mock = Game.__new__(Game)
        mock.windows = (Mock(is_open=True),)
        mock.party_window = mock.windows[0]
        mock.party_cursor = None
        mock.sort_source_cursor = None
        mock.alert = Mock(camera_x=0)
        mock.settings_window = None
        mock.confirmation_window = None
        mock.faces = object()
        mock.palette_shifter = Mock()
        mock.palette_shifter.shifted.return_value = nullcontext()
        mock.party = (
            Mock(
                is_dead=True,
                is_front_row=True,
                face_position=Mock(x=32, y=0),
            ),
        )

        mock.draw()

        mock.palette_shifter.shifted.assert_called_once_with(MONOCHROME_PALETTE)
        blt.assert_called_once()

    @patch("game.pyxel.blt")
    def test_five_member_faces_keep_twelve_pixel_gaps(self, blt: Mock) -> None:
        mock = Game.__new__(Game)
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

    @patch("game.pyxel.cls")
    @patch("game.pyxel.camera")
    @patch("game.pyxel.blt")
    def test_party_faces_wait_until_party_window_is_open(
        self,
        blt: Mock,
        _camera: Mock,
        _clear_screen: Mock,
    ) -> None:
        mock = Game.__new__(Game)
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
        mock = Game.__new__(Game)
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

    def test_left_shortcut_selects_sort_command_and_activates_member_cursor(
        self,
    ) -> None:
        mock = Game.__new__(Game)
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState(
            navigation=Direction.LEFT,
            held_direction=Direction.LEFT,
        )
        mock.command_window = Mock()
        mock.command_cursor = Mock(selected_key="item", active=True)
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

        mock.command_cursor.select_key.assert_called_once_with("sort")
        self.assertIs(mock.party_cursor, party_cursor)
        self.assertFalse(mock.command_cursor.active)
        mock.command_window.update.assert_not_called()

    @patch("game.ItemMenuOverlay")
    def test_confirming_item_command_opens_connected_item_screen(
        self,
        item_screen_class: Mock,
    ) -> None:
        mock = Game.__new__(Game)
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
        mock._teleport_targets = Mock(return_value=())

        mock.update()

        item_screen_class.assert_not_called()
        self.assertIs(
            mock.pending_screen_change,
            GameScreenChange.OPEN_ITEM,
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
            on_field_fade=mock._activate_field_fade,
            teleport_targets=(),
            on_field_teleport=mock._start_item_teleport,
            on_invalid_action=mock.alert.start,
        )
        self.assertIs(mock.item_screen, item_screen_class.return_value)
        self.assertIsNone(mock.pending_screen_change)
        mock.command_window.update.assert_not_called()

    def test_cancel_from_item_returns_to_selected_menu_command(self) -> None:
        mock = Game.__new__(Game)
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
            GameScreenChange.CLOSE_ITEM,
        )
        for _frame in range(DEFAULT_FADE_FRAME_COUNT):
            mock._update_fade()

        self.assertIsNone(mock.item_screen)
        self.assertTrue(mock.command_cursor.active)

    @patch("game.pyxel.camera")
    @patch("game.pyxel.cls")
    def test_draw_uses_item_screen_while_item_is_active(
        self,
        clear_screen: Mock,
        camera: Mock,
    ) -> None:
        mock = Game.__new__(Game)
        mock.item_screen = Mock()
        mock.alert = Mock(camera_x=-1)

        mock.draw()

        clear_screen.assert_called_once_with(0)
        mock.item_screen.draw.assert_called_once_with()
        self.assertEqual(camera.call_args_list, [call(-1, 0), call()])

    @patch("game.EquipmentMenuOverlay")
    def test_confirming_equipment_command_opens_connected_equipment_screen(
        self,
        equipment_screen_class: Mock,
    ) -> None:
        mock = Game.__new__(Game)
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
            GameScreenChange.OPEN_EQUIPMENT,
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
        mock = Game.__new__(Game)
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
            GameScreenChange.CLOSE_EQUIPMENT,
        )
        for _frame in range(DEFAULT_FADE_FRAME_COUNT):
            mock._update_fade()
        self.assertIsNone(mock.equipment_screen)
        self.assertEqual(mock.selected_member_index, 3)
        self.assertTrue(mock.command_cursor.active)
        mock._refresh_party_window_texts.assert_called_once_with()

    @patch("game.pyxel.camera")
    @patch("game.pyxel.cls")
    def test_draw_uses_equipment_screen_while_equipment_is_active(
        self,
        clear_screen: Mock,
        camera: Mock,
    ) -> None:
        mock = Game.__new__(Game)
        mock.equipment_screen = Mock()
        mock.alert = Mock(camera_x=0)

        mock.draw()

        clear_screen.assert_called_once_with(0)
        mock.equipment_screen.draw.assert_called_once_with()
        self.assertEqual(camera.call_args_list, [call(0, 0), call()])

    @patch("game.StatusMenuOverlay")
    def test_confirming_status_command_opens_connected_status_screen(
        self,
        status_screen_class: Mock,
    ) -> None:
        mock = Game.__new__(Game)
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
            GameScreenChange.OPEN_STATUS,
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
            palette_shifter=mock.palette_shifter,
            member_index=3,
        )
        self.assertIs(mock.status_screen, status_screen_class.return_value)
        self.assertIsNone(mock.pending_screen_change)
        mock.command_window.update.assert_not_called()

    def test_cancel_from_status_returns_to_selected_menu_command(self) -> None:
        mock = Game.__new__(Game)
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
            GameScreenChange.CLOSE_STATUS,
        )
        for _frame in range(DEFAULT_FADE_FRAME_COUNT):
            mock._update_fade()

        self.assertIsNone(mock.status_screen)
        self.assertTrue(mock.command_cursor.active)
        self.assertEqual(mock.selected_member_index, 3)

    @patch("game.InformationMenuOverlay")
    def test_confirming_info_command_opens_connected_information_screen(
        self,
        information_screen_class: Mock,
    ) -> None:
        mock = Game.__new__(Game)
        input_state = InputState(
            confirm=InputButton(triggered=True, held=True)
        )
        mock.input_reader = Mock(poll=Mock(return_value=input_state))
        mock.alert = Mock()
        mock.command_window = Mock()
        mock.command_cursor = Mock(selected_key="info", active=True)
        mock.party_cursor = None
        mock.settings_cursor = None
        mock.confirmation_cursor = None
        mock.information_screen = None
        mock.palette_shifter = Mock(base_colors=(0x000000,))
        mock.monsters = (Mock(),)
        mock.save_data = SaveData(monster_records={"monster": set()})
        mock.items = {"POTION": Mock()}
        mock.settings = Settings()
        mock.texts = Mock()
        mock.event_messages = Mock()
        mock.event_catalog = Mock(missions=())
        mock.fonts = Mock()
        mock.images = Mock()

        mock.update()

        self.assertIs(
            mock.pending_screen_change,
            GameScreenChange.OPEN_INFO,
        )
        self.assertFalse(mock.command_cursor.active)
        for _frame in range(DEFAULT_FADE_FRAME_COUNT):
            mock._update_fade()

        information_screen_class.assert_called_once_with(
            monsters=mock.monsters,
            monster_records=mock.save_data.monster_records,
            items=mock.items,
            logs=mock.save_data.logs,
            mission_message_ids=(),
            settings=mock.settings,
            texts=mock.texts,
            event_messages=mock.event_messages,
            fonts=mock.fonts,
            images=mock.images,
            on_invalid_action=mock.alert.start,
        )
        self.assertIs(
            mock.information_screen,
            information_screen_class.return_value,
        )
        self.assertIsNone(mock.pending_screen_change)

    def test_cancel_from_information_returns_to_info_menu_command(self) -> None:
        mock = Game.__new__(Game)
        input_state = InputState(cancel=InputButton(triggered=True, held=True))
        mock.input_reader = Mock(poll=Mock(return_value=input_state))
        mock.alert = Mock()
        mock.command_cursor = Mock(active=False)
        mock.palette_shifter = Mock(base_colors=(0x000000,))
        mock.information_screen = Mock()
        mock.information_screen.update.return_value = True

        information_screen = mock.information_screen
        mock.update()

        information_screen.update.assert_called_once_with(input_state)
        self.assertIs(
            mock.pending_screen_change,
            GameScreenChange.CLOSE_INFO,
        )
        for _frame in range(DEFAULT_FADE_FRAME_COUNT):
            mock._update_fade()

        self.assertIsNone(mock.information_screen)
        self.assertTrue(mock.command_cursor.active)

    @patch("game.pyxel.camera")
    @patch("game.pyxel.cls")
    def test_draw_uses_information_screen_while_information_is_active(
        self,
        clear_screen: Mock,
        camera: Mock,
    ) -> None:
        mock = Game.__new__(Game)
        mock.information_screen = Mock()
        mock.alert = Mock(camera_x=0)

        mock.draw()

        clear_screen.assert_called_once_with(0)
        mock.information_screen.draw.assert_called_once_with()
        self.assertEqual(camera.call_args_list, [call(0, 0), call()])

    @patch("game.SaveMenuOverlay")
    def test_confirming_save_command_opens_connected_save_screen(
        self,
        save_screen_class: Mock,
    ) -> None:
        mock = Game.__new__(Game)
        input_state = InputState(
            confirm=InputButton(triggered=True, held=True)
        )
        mock.input_reader = Mock(poll=Mock(return_value=input_state))
        mock.alert = Mock()
        mock.command_window = Mock()
        mock.command_cursor = Mock(selected_key="save", active=True)
        mock.party_cursor = None
        mock.settings_cursor = None
        mock.confirmation_cursor = None
        mock.save_screen = None
        mock.palette_shifter = Mock(base_colors=(0x000000,))
        mock.save_repository = Mock()
        mock.current_save_slot = None
        mock.settings = Settings()
        mock.texts = Mock()
        mock.fonts = Mock()
        mock.faces = object()
        mock.character_face_positions = {"Fiora": Mock()}

        mock.update()

        self.assertIs(
            mock.pending_screen_change,
            GameScreenChange.OPEN_SAVE,
        )
        self.assertFalse(mock.command_cursor.active)
        for _frame in range(DEFAULT_FADE_FRAME_COUNT):
            mock._update_fade()

        save_screen_class.assert_called_once_with(
            summaries=mock.save_repository.summaries.return_value,
            current_slot=None,
            settings=mock.settings,
            texts=mock.texts,
            fonts=mock.fonts,
            faces=mock.faces,
            face_positions=mock.character_face_positions,
            palette_shifter=mock.palette_shifter,
            on_save=mock._save_to_slot,
            on_invalid_action=mock.alert.start,
        )
        self.assertIs(mock.save_screen, save_screen_class.return_value)
        self.assertIsNone(mock.pending_screen_change)

    def test_cancel_from_save_returns_to_selected_menu_command(self) -> None:
        mock = Game.__new__(Game)
        input_state = InputState(cancel=InputButton(triggered=True, held=True))
        mock.input_reader = Mock(poll=Mock(return_value=input_state))
        mock.alert = Mock()
        mock.command_cursor = Mock(active=False)
        mock.palette_shifter = Mock(base_colors=(0x000000,))
        mock.save_screen = Mock()
        mock.save_screen.update.return_value = True

        save_screen = mock.save_screen
        mock.update()

        save_screen.update.assert_called_once_with(input_state)
        self.assertIs(
            mock.pending_screen_change,
            GameScreenChange.CLOSE_SAVE,
        )
        for _frame in range(DEFAULT_FADE_FRAME_COUNT):
            mock._update_fade()

        self.assertIsNone(mock.save_screen)
        self.assertTrue(mock.command_cursor.active)

    @patch("game.pyxel.camera")
    @patch("game.pyxel.cls")
    def test_draw_uses_save_screen_while_save_is_active(
        self,
        clear_screen: Mock,
        camera: Mock,
    ) -> None:
        mock = Game.__new__(Game)
        mock.save_screen = Mock()
        mock.alert = Mock(camera_x=0)

        mock.draw()

        clear_screen.assert_called_once_with(0)
        mock.save_screen.draw.assert_called_once_with()
        self.assertEqual(camera.call_args_list, [call(0, 0), call()])

    @patch("game.create_save_document")
    def test_save_slot_writes_current_field_and_all_known_characters(
        self,
        create_document: Mock,
    ) -> None:
        mock = Game.__new__(Game)
        mock.save_data = Mock()
        mock.party = (Mock(),)
        mock.character_states = {"Fiora": mock.party[0], "Cerion": Mock()}
        mock.inventory_system = Mock()
        mock.current_map = Mock(map_id="worldmap")
        mock.field = Mock(
            position=FieldPosition(17, 39),
            facing=Direction.LEFT,
        )
        summary = Mock(slot=3)
        mock.save_repository = Mock()
        mock.save_repository.save.return_value = summary
        mock.current_save_slot = None
        mock.battle_command_memory = BattleCommandMemory(global_command="auto")
        document = {"format_version": 1}
        create_document.return_value = document

        result = mock._save_to_slot(3)

        create_document.assert_called_once_with(
            save_data=mock.save_data,
            active_party=mock.party,
            character_states=mock.character_states,
            inventory=mock.inventory_system,
            map_id="worldmap",
            position=FieldPosition(17, 39),
            facing=Direction.LEFT,
            battle_command_memory=mock.battle_command_memory,
        )
        mock.save_repository.save.assert_called_once_with(3, document)
        self.assertIs(result, summary)
        self.assertEqual(mock.current_save_slot, 3)

    @patch("game.create_save_document")
    def test_autosave_writes_slot_zero_without_changing_manual_slot(
        self, create_document: Mock
    ) -> None:
        mock = Game.__new__(Game)
        mock.save_data = SaveData()
        mock.party = (Mock(),)
        mock.character_states = {"Fiora": mock.party[0]}
        mock.inventory_system = Mock()
        mock.current_map = Mock(map_id="worldmap")
        mock.field = Mock(position=FieldPosition(7, 8), facing=Direction.UP)
        mock.save_repository = Mock()
        mock.current_save_slot = 3
        create_document.return_value = {"format_version": 2}

        mock._auto_save()

        self.assertEqual(create_document.call_args.kwargs["map_id"], "worldmap")
        self.assertEqual(create_document.call_args.kwargs["position"], FieldPosition(7, 8))
        mock.save_repository.save.assert_called_once_with(
            AUTO_SAVE_SLOT, create_document.return_value
        )
        self.assertEqual(mock.current_save_slot, 3)

        mock.save_repository.save.side_effect = SaveSystemError("disk full")
        mock._auto_save()
        self.assertEqual(mock.current_save_slot, 3)

    def test_arrival_autosave_waits_until_hint_flag_is_recorded(self) -> None:
        mock = Game.__new__(Game)
        mock.fade = Mock(
            is_active=True,
            phase=FadePhase.FADING_IN,
            visible_rate=1.0,
            update=Mock(return_value=FadeEvent.FINISHED),
        )
        mock.palette_shifter = Mock(base_colors=(0,))
        mock.fade_bgm = False
        mock.animate_main_windows_with_fade = False
        mock.auto_save_after_fade = True
        mock.event_resume_after_fade = False
        mock.save_data = SaveData()
        saved_flags = []
        mock._show_pending_hint_after_fade = Mock(
            side_effect=lambda: mock.save_data.event_flags.add(
                "hint.shown.first_dungeon_exit"
            )
        )
        mock._auto_save = Mock(
            side_effect=lambda: saved_flags.append(set(mock.save_data.event_flags))
        )

        mock._update_fade()

        self.assertEqual(saved_flags, [{"hint.shown.first_dungeon_exit"}])
        self.assertFalse(mock.auto_save_after_fade)

    @patch("game.FieldRenderer")
    @patch("game.FieldMovement")
    @patch("game.restore_save_document")
    def test_load_slot_stages_validated_state_and_field_before_fade(
        self,
        restore_document: Mock,
        field_movement_class: Mock,
        field_renderer_class: Mock,
    ) -> None:
        mock = Game.__new__(Game)
        document = {"format_version": 1}
        mock.save_repository = Mock()
        mock.save_repository.load.return_value = document
        mock.character_records = (Mock(),)
        mock.items = {"POTION": Mock()}
        mock.skills = {"Two-Handed": Mock()}
        loaded = Mock(
            map_id="worldmap",
            position=FieldPosition(17, 39),
            facing=Direction.LEFT,
        )
        restore_document.return_value = loaded
        target_map = Mock()
        mock.map_resources = Mock()
        mock.map_resources.map.return_value = target_map
        mock._begin_screen_change = Mock()

        result = mock._load_from_slot(4)

        self.assertTrue(result)
        mock.save_repository.load.assert_called_once_with(4)
        restore_document.assert_called_once_with(
            document,
            character_records=mock.character_records,
            items=mock.items,
            skills=mock.skills,
        )
        field_movement_class.assert_called_once_with(
            target_map,
            start=FieldPosition(17, 39),
            facing=Direction.LEFT,
            allow_blocked_start=True,
        )
        field_renderer_class.assert_called_once_with(
            target_map,
            screen_width=256,
            screen_height=240,
        )
        self.assertIs(mock.pending_loaded_state, loaded)
        self.assertEqual(mock.pending_load_slot, 4)
        mock._begin_screen_change.assert_called_once_with(
            GameScreenChange.START_GAME
        )

    @patch("game.ShopSystem")
    def test_start_game_commits_loaded_state_at_fade_midpoint(
        self,
        shop_system_class: Mock,
    ) -> None:
        mock = Game.__new__(Game)
        loaded = Mock()
        loaded.save_data = SaveData(gold=321)
        loaded.active_party = (Mock(), Mock())
        loaded.character_states = {"Fiora": loaded.active_party[0]}
        loaded.inventory = InventorySystem({})
        loaded.battle_command_memory = BattleCommandMemory(global_command="escape")
        mock.settings = Settings(in_game_hints_enabled=False)
        mock.pending_loaded_state = loaded
        mock.pending_loaded_map = Mock(sites=(), bgm_id="dungeon/ruins")
        mock.pending_loaded_field = Mock()
        mock.pending_loaded_renderer = Mock()
        mock.pending_load_slot = 4
        mock.shops = (Mock(),)
        mock._build_main_windows = Mock()
        mock._refresh_site_name_label = Mock()
        mock._start_field_event = Mock()
        mock.bgm = Mock()
        mock.start_screen = Mock()
        mock.showing_field = False

        mock._apply_start_game()

        self.assertIs(mock.save_data, loaded.save_data)
        self.assertIs(mock.party, loaded.active_party)
        self.assertIs(mock.character_states, loaded.character_states)
        self.assertIs(mock.inventory_system, loaded.inventory)
        self.assertIs(mock.battle_command_memory, loaded.battle_command_memory)
        self.assertEqual(mock.current_save_slot, 4)
        shop_system_class.assert_called_once_with(
            shops=mock.shops,
            inventory=loaded.inventory,
            party=loaded.active_party,
            save_data=loaded.save_data,
        )
        mock._build_main_windows.assert_called_once_with(animate=False)
        self.assertIsNone(mock.start_screen)
        self.assertTrue(mock.showing_field)
        mock.bgm.play.assert_called_once_with("dungeon/ruins")
        mock._start_field_event.assert_not_called()

        mock.pending_loaded_state = loaded
        mock.pending_loaded_map = mock.current_map
        mock.pending_loaded_field = mock.field
        mock.pending_loaded_renderer = mock.field_renderer
        mock.pending_load_slot = AUTO_SAVE_SLOT
        mock._apply_start_game()

        self.assertIsNone(mock.current_save_slot)

    @patch("game.ShopSystem")
    @patch("game.HintOverlay")
    def test_loaded_game_creates_mission_hint_when_enabled(
        self, hint_class: Mock, _shop_class: Mock,
    ) -> None:
        mock = Game.__new__(Game)
        mock.settings = Settings()
        mock.texts = Mock()
        mock.fonts = Mock()
        mock.pending_loaded_state = Mock(
            save_data=SaveData(), active_party=(), character_states={},
            inventory=InventorySystem({}),
        )
        mock.pending_loaded_map = Mock(sites=(), bgm_id="da3-field")
        mock.pending_loaded_field = Mock()
        mock.pending_loaded_renderer = Mock()
        mock.pending_load_slot = 1
        mock.shops = ()
        mock._build_main_windows = Mock()
        mock._refresh_site_name_label = Mock()
        mock._reset_field_actors = Mock()
        mock.bgm = Mock()

        mock._apply_start_game()

        hint_class.assert_called_once_with(
            text_key="hint.load.mission", settings=mock.settings,
            texts=mock.texts, fonts=mock.fonts,
        )
        self.assertIs(mock.hint_overlay, hint_class.return_value)
        self.assertTrue(mock._load_mission_hint_shown_this_launch)

    @patch("game.ShopSystem")
    @patch("game.HintOverlay")
    def test_loaded_game_does_not_repeat_mission_hint_in_same_launch(
        self, hint_class: Mock, _shop_class: Mock,
    ) -> None:
        mock = Game.__new__(Game)
        mock.settings = Settings()
        mock._load_mission_hint_shown_this_launch = True
        mock.pending_loaded_state = Mock(
            save_data=SaveData(), active_party=(), character_states={},
            inventory=InventorySystem({}),
        )
        mock.pending_loaded_map = Mock(sites=(), bgm_id="da3-field")
        mock.pending_loaded_field = Mock()
        mock.pending_loaded_renderer = Mock()
        mock.pending_load_slot = 2
        mock.shops = ()
        mock._build_main_windows = Mock()
        mock._refresh_site_name_label = Mock()
        mock._reset_field_actors = Mock()
        mock.bgm = Mock()

        mock._apply_start_game()

        hint_class.assert_not_called()
        self.assertTrue(mock._load_mission_hint_shown_this_launch)

    def test_hint_consumes_input_and_finishes_without_updating_field(self) -> None:
        mock = Game.__new__(Game)
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState(navigation=Direction.RIGHT)
        mock._update_game_menu = Mock(return_value=False)
        mock._update_field_menu_guide = Mock()
        mock.alert = Mock()
        mock._update_fade = Mock(return_value=False)
        mock.hint_overlay = Mock()
        mock.hint_overlay.update.return_value = False
        mock._update_field = Mock()

        mock.update()

        mock._update_field.assert_not_called()
        mock.hint_overlay.update.return_value = True
        mock.update()
        self.assertIsNone(mock.hint_overlay)
        mock._update_field.assert_not_called()

    @patch("game.HintOverlay")
    def test_progression_hint_is_recorded_once_only_after_it_is_shown(
        self,
        hint_class: Mock,
    ) -> None:
        mock = Game.__new__(Game)
        mock.settings = Settings(in_game_hints_enabled=False)
        mock.save_data = SaveData()
        mock.texts = Mock()
        mock.fonts = Mock()
        mock.hint_overlay = None

        self.assertFalse(mock._show_hint_once(FIRST_BATTLE_HINT_ID))
        self.assertEqual(mock.save_data.event_flags, set())

        mock.settings = mock.settings.with_in_game_hints_enabled(True)
        self.assertTrue(mock._show_hint_once(FIRST_BATTLE_HINT_ID))
        self.assertIn("hint.shown.first_battle", mock.save_data.event_flags)
        hint_class.assert_called_once_with(
            text_key="hint.first_battle",
            settings=mock.settings,
            texts=mock.texts,
            fonts=mock.fonts,
        )

        mock.hint_overlay = None
        self.assertFalse(mock._show_hint_once(FIRST_BATTLE_HINT_ID))
        hint_class.assert_called_once()

    def test_pending_field_hint_opens_after_fade(self) -> None:
        mock = Game.__new__(Game)
        mock.pending_hint_after_fade = FIRST_DUNGEON_EXIT_HINT_ID
        mock._show_hint_once = Mock()

        mock._show_pending_hint_after_fade()

        self.assertIsNone(mock.pending_hint_after_fade)
        mock._show_hint_once.assert_called_once_with(FIRST_DUNGEON_EXIT_HINT_ID)

    def test_result_phase_requests_the_first_result_hint(self) -> None:
        mock = Game.__new__(Game)
        mock.battle_scene = Mock(phase=BattlePhase.RESULT, result=None)
        mock.pending_first_party_turn_hint = False
        mock._show_hint_once = Mock()
        mock._begin_battle_return = Mock()

        self.assertTrue(mock._update_battle_scene(InputState()))

        mock.battle_scene.update.assert_called_once_with(InputState())
        mock._show_hint_once.assert_called_once_with(FIRST_RESULT_HINT_ID)
        mock._begin_battle_return.assert_not_called()

    def test_first_battle_hint_waits_for_an_open_party_command_window(self) -> None:
        mock = Game.__new__(Game)
        mock.battle_scene = Mock(phase=BattlePhase.ENTRANCE, result=None)
        mock.battle_scene.is_party_command_ready = False
        mock.pending_first_party_turn_hint = True
        mock._show_hint_once = Mock()

        self.assertTrue(mock._update_battle_scene(InputState()))
        mock._show_hint_once.assert_not_called()

        mock.battle_scene.is_party_command_ready = True
        self.assertTrue(mock._update_battle_scene(InputState()))
        mock._show_hint_once.assert_called_once_with(FIRST_BATTLE_HINT_ID)
        self.assertFalse(mock.pending_first_party_turn_hint)

    def test_dungeon_exit_queues_hint_for_completed_fade(self) -> None:
        mock = Game.__new__(Game)
        mock.current_map = Mock(profile="dungeon")
        mock.world_map = Mock(profile="world")
        mock.pending_target_map = mock.world_map
        mock.pending_site = Mock()
        mock._apply_pending_map_destination = Mock()
        mock._queue_hint_after_fade = Mock()

        mock._apply_pending_site_change()

        mock._queue_hint_after_fade.assert_called_once_with(
            FIRST_DUNGEON_EXIT_HINT_ID
        )

    def test_defeat_hint_opens_after_return_fade_finishes(self) -> None:
        mock = Game.__new__(Game)
        mock.battle_return_fade = Mock(
            visible_rate=1.0,
            update=Mock(return_value=FadeEvent.FINISHED),
        )
        mock.battle_return_result = BattleResult.DEFEAT
        mock.palette_shifter = Mock(base_colors=(0,))
        mock.bgm = Mock()
        mock._show_hint_once = Mock()

        mock._update_battle_return(InputState())

        self.assertIsNone(mock.battle_return_fade)
        mock._show_hint_once.assert_called_once_with(
            FIRST_DEFEAT_RESTART_HINT_ID
        )

    def test_start_game_starts_prologue_only_for_new_game(self) -> None:
        mock = Game.__new__(Game)
        calls = []
        mock.settings = Settings()
        mock.battle_command_memory = BattleCommandMemory(global_command="auto")
        mock.pending_loaded_state = None
        mock.pending_loaded_map = None
        mock.pending_loaded_field = None
        mock.pending_loaded_renderer = None
        mock.pending_load_slot = None
        mock.start_screen = Mock()
        mock.showing_field = False
        mock.current_map = Mock(bgm_id="da3-field")
        mock._refresh_site_name_label = Mock()
        mock.bgm = Mock()
        mock._start_field_event = Mock()
        mock.bgm.play.side_effect = lambda _bgm_id: calls.append("bgm")
        mock._start_field_event.side_effect = lambda _event_id: calls.append(
            "event"
        )

        mock._apply_start_game()

        self.assertIsNone(mock.start_screen)
        self.assertTrue(mock.showing_field)
        mock.bgm.play.assert_called_once_with("da3-field")
        mock._start_field_event.assert_called_once_with(NEW_GAME_EVENT_ID)
        self.assertEqual(mock.battle_command_memory, BattleCommandMemory())
        self.assertEqual(calls, ["bgm", "event"])

    def test_fade_blocks_screen_input_and_restores_palette(self) -> None:
        mock = Game.__new__(Game)
        mock.alert = Mock()
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState()
        mock.palette_shifter = Mock(base_colors=(0x000000,))
        mock.fade = FadeThroughBlack()
        mock.fade.start()
        mock.pending_screen_change = GameScreenChange.OPEN_ITEM
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

    def test_field_change_restores_bgm_at_fade_midpoint(self) -> None:
        for change in (
            GameScreenChange.CHANGE_MAP,
            GameScreenChange.TELEPORT,
            GameScreenChange.START_GAME,
        ):
            with self.subTest(change=change):
                frame_count = (
                    SITE_MAP_FADE_FRAME_COUNT
                    if change is not GameScreenChange.START_GAME
                    else DEFAULT_FADE_FRAME_COUNT
                )
                mock = Game.__new__(Game)
                mock.fade = FadeThroughBlack(frame_count)
                mock.pending_screen_change = None
                mock.bgm = Mock()
                mock.palette_shifter = Mock(base_colors=(0x000000,))
                mock._apply_pending_screen_change = Mock(
                    side_effect=lambda: mock.bgm.play("destination")
                )

                mock._begin_screen_change(change)
                for _frame in range(frame_count):
                    mock._update_fade()

                self.assertEqual(
                    [call.args[0] for call in mock.bgm.set_fade_rate.call_args_list],
                    [1.0 - frame / frame_count for frame in range(1, frame_count + 1)]
                    + [1.0],
                )
                self.assertEqual(
                    mock.bgm.mock_calls[-2:],
                    [call.play("destination"), call.set_fade_rate(1.0)],
                )
                mock._apply_pending_screen_change.assert_called_once_with()
                self.assertFalse(mock.fade_bgm)

                for _frame in range(frame_count):
                    mock._update_fade()

                self.assertFalse(mock.fade.is_active)
                self.assertEqual(
                    mock.bgm.set_fade_rate.call_count,
                    frame_count + 1,
                )

    def test_menu_change_does_not_fade_bgm(self) -> None:
        mock = Game.__new__(Game)
        mock.fade = FadeThroughBlack()
        mock.pending_screen_change = None
        mock.bgm = Mock()
        mock.command_cursor = Mock()
        mock.palette_shifter = Mock(base_colors=(0x000000,))
        mock._apply_pending_screen_change = Mock()

        mock._begin_screen_change(GameScreenChange.SHOW_MENU)
        mock._update_fade()

        mock.bgm.set_fade_rate.assert_not_called()

    def test_status_return_rebuilds_changed_language_without_window_animation(
        self,
    ) -> None:
        mock = Game.__new__(Game)
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

    @patch("game.pyxel.camera")
    @patch("game.pyxel.cls")
    def test_draw_uses_status_screen_while_status_is_active(
        self,
        clear_screen: Mock,
        camera: Mock,
    ) -> None:
        mock = Game.__new__(Game)
        mock.status_screen = Mock()
        mock.alert = Mock(camera_x=0)

        mock.draw()

        clear_screen.assert_called_once_with(0)
        mock.status_screen.draw.assert_called_once_with()
        self.assertEqual(camera.call_args_list, [call(0, 0), call()])

    @patch("game.SpellMenuOverlay")
    def test_confirming_spell_command_opens_connected_spell_screen(
        self,
        spell_screen_class: Mock,
    ) -> None:
        mock = Game.__new__(Game)
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
        mock._teleport_targets = Mock(return_value=())

        mock.update()

        spell_screen_class.assert_not_called()
        self.assertIs(
            mock.pending_screen_change,
            GameScreenChange.OPEN_SPELL,
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
            palette_shifter=mock.palette_shifter,
            member_index=2,
            on_field_fade=mock._activate_field_fade,
            teleport_targets=(),
            on_field_teleport=mock._start_field_teleport,
            on_invalid_action=mock.alert.start,
        )
        self.assertIs(mock.spell_screen, spell_screen_class.return_value)
        self.assertIsNone(mock.pending_screen_change)
        mock.command_window.update.assert_not_called()

    @patch("game.SpellMenuOverlay")
    def test_first_spell_screen_in_menu_uses_automatic_caster_selection(
        self,
        spell_screen_class: Mock,
    ) -> None:
        mock = Game.__new__(Game)
        mock.alert = Mock()
        mock.command_cursor = Mock(active=True)
        mock.party = (Mock(), Mock())
        mock.spells = {"HEALING1": Mock()}
        mock.settings = Settings()
        mock.texts = Mock()
        mock.fonts = Mock()
        mock.faces = object()
        mock.palette_shifter = Mock()
        mock.selected_member_index = 0
        mock.menu_member_selected = False
        mock._teleport_targets = Mock(return_value=())
        spell_screen_class.return_value.member_index = 1

        mock._start_spell()

        self.assertEqual(
            spell_screen_class.call_args.kwargs["member_index"],
            None,
        )
        self.assertEqual(mock.selected_member_index, 1)
        self.assertTrue(mock.menu_member_selected)

    def test_cancel_from_spell_returns_to_selected_menu_command(self) -> None:
        mock = Game.__new__(Game)
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
        mock._refresh_party_window_texts = Mock()

        spell_screen = mock.spell_screen
        mock.update()

        spell_screen.update.assert_called_once_with(input_state)
        self.assertIs(mock.spell_screen, spell_screen)
        self.assertIs(
            mock.pending_screen_change,
            GameScreenChange.CLOSE_SPELL,
        )
        for _frame in range(DEFAULT_FADE_FRAME_COUNT):
            mock._update_fade()

        self.assertIsNone(mock.spell_screen)
        self.assertTrue(mock.command_cursor.active)
        self.assertEqual(mock.selected_member_index, 2)
        mock._refresh_party_window_texts.assert_called_once_with()

    @patch("game.pyxel.camera")
    @patch("game.pyxel.cls")
    def test_draw_uses_spell_screen_while_spell_is_active(
        self,
        clear_screen: Mock,
        camera: Mock,
    ) -> None:
        mock = Game.__new__(Game)
        mock.spell_screen = Mock()
        mock.alert = Mock(camera_x=0)

        mock.draw()

        clear_screen.assert_called_once_with(0)
        mock.spell_screen.draw.assert_called_once_with()
        self.assertEqual(camera.call_args_list, [call(0, 0), call()])

    def test_field_confirm_has_no_temporary_shop_action(self) -> None:
        mock = Game.__new__(Game)
        mock.alert = Mock()
        mock.input_reader = Mock(
            poll=Mock(
                return_value=InputState(confirm=InputButton(triggered=True))
            )
        )
        mock.fade = FadeThroughBlack()
        mock.shop_screen = None
        mock.showing_field = True
        mock.field = Mock()
        mock._handle_arrived_site = Mock()
        mock._refresh_site_name_label = Mock()

        mock.update()

        mock.field.update.assert_called_once_with(None)
        mock._handle_arrived_site.assert_called_once_with()
        mock._refresh_site_name_label.assert_called_once_with()

    def test_debug_shop_targets_follow_loaded_shop_order(self) -> None:
        mock = Game.__new__(Game)
        mock.shops = (
            Mock(key="FAIRY_HAMLET_ITEMS"),
            Mock(key="SILVALIA_ARMORY"),
        )

        self.assertEqual(
            mock._debug_shop_targets(),
            (
                DebugShopTarget("FAIRY_HAMLET_ITEMS", "FAIRY_HAMLET_ITEMS"),
                DebugShopTarget("SILVALIA_ARMORY", "SILVALIA_ARMORY"),
            ),
        )

    def test_debug_shop_stages_selected_shop_for_fade_transition(self) -> None:
        mock = Game.__new__(Game)
        selected_shop = Mock(key="TEST_SHOP")
        member = Mock()
        member.definition.key = "Fiora"
        mock.debug_screen = Mock(party=(member,))
        mock.party = ()
        mock.character_states = {}
        mock._force_reserve_front = Mock()
        mock.selected_member_index = 5
        mock.fade = FadeThroughBlack()
        mock.pending_screen_change = None
        mock.shops = (selected_shop,)

        result = mock._start_debug_shop("TEST_SHOP")

        self.assertTrue(result)
        self.assertIs(mock.pending_shop, selected_shop)
        self.assertTrue(mock.shop_return_to_debug)
        self.assertIs(mock.pending_screen_change, GameScreenChange.OPEN_SHOP)
        self.assertEqual(mock.party, (member,))
        self.assertIs(mock.character_states["Fiora"], member)
        self.assertEqual(mock.selected_member_index, 0)

    def test_closing_debug_shop_returns_to_debug_shop_list(self) -> None:
        mock = Game.__new__(Game)
        mock.pending_screen_change = GameScreenChange.CLOSE_SHOP
        mock.shop_return_to_debug = True
        mock.debug_screen = Mock()
        mock._finish_shop = Mock()
        mock.showing_field = False

        mock._apply_pending_screen_change()

        mock._finish_shop.assert_called_once_with()
        self.assertIsNotNone(mock.debug_screen)
        self.assertFalse(mock.showing_field)
        self.assertFalse(mock.shop_return_to_debug)
        self.assertIsNone(mock.pending_screen_change)

    @patch("game.WindowCursor")
    def test_selecting_fiora_and_reserve_swaps_their_order(
        self,
        window_cursor: Mock,
    ) -> None:
        mock = Game.__new__(Game)
        mock.party_window = Mock()
        mock.party_cursor = Mock(selected_key=0)
        mock.party = tuple(
            Mock(
                key=key,
                hp=10,
                paralyzed=False,
                is_front_row=True,
                formation_row=FormationRow.FRONT,
            )
            for key in ("Fiora", "b", "c", "d", "e", "reserve")
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

    @patch("game.WindowCursor")
    def test_selecting_same_member_changes_formation_row(
        self,
        _window_cursor: Mock,
    ) -> None:
        mock = Game.__new__(Game)
        mock.party_window = Mock()
        mock.party_cursor = Mock(selected_key=0)
        front = Mock(
            hp=10,
            paralyzed=False,
            is_front_row=True,
            formation_row=FormationRow.FRONT,
        )
        other_front = Mock(
            hp=10,
            paralyzed=False,
            is_front_row=True,
            formation_row=FormationRow.FRONT,
        )
        mock.party = (front, other_front)
        mock.sort_source_index = None
        mock.sort_source_cursor = None
        mock.alert = Mock()

        mock._confirm_sort_member()
        mock._confirm_sort_member()

        self.assertIs(front.formation_row, FormationRow.BACK)
        self.assertIsNone(mock.sort_source_index)

    @patch("game.WindowCursor")
    def test_reserve_is_forced_front_across_two_swaps(
        self,
        _window_cursor: Mock,
    ) -> None:
        mock = Game.__new__(Game)
        mock.party_window = Mock()
        mock.party_cursor = Mock()
        front = Mock(
            key="front",
            hp=10,
            paralyzed=False,
            is_front_row=True,
            formation_row=FormationRow.FRONT,
        )
        back_members = tuple(
            Mock(
                key=f"back-{index}",
                hp=10,
                paralyzed=False,
                is_front_row=False,
                formation_row=FormationRow.BACK,
            )
            for index in range(4)
        )
        reserve = Mock(
            key="reserve",
            hp=10,
            paralyzed=False,
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

    @patch("game.WindowCursor")
    def test_reserve_cannot_be_changed_to_back(
        self,
        _window_cursor: Mock,
    ) -> None:
        mock = Game.__new__(Game)
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

    @patch("game.WindowCursor")
    def test_last_front_member_cannot_move_to_back(
        self,
        _window_cursor: Mock,
    ) -> None:
        mock = Game.__new__(Game)
        mock.party_window = Mock()
        mock.party_cursor = Mock(selected_key=0)
        front = Mock(
            hp=10,
            paralyzed=False,
            is_front_row=True,
            formation_row=FormationRow.FRONT,
        )
        back = Mock(
            hp=10,
            paralyzed=False,
            is_front_row=False,
            formation_row=FormationRow.BACK,
        )
        mock.party = (front, back)
        mock.sort_source_index = None
        mock.sort_source_cursor = None
        mock.alert = Mock()

        mock._confirm_sort_member()
        mock._confirm_sort_member()

        self.assertIs(front.formation_row, FormationRow.FRONT)
        self.assertIsNone(mock.sort_source_index)
        mock.alert.start.assert_called_once_with()

    @patch("game.WindowCursor")
    def test_dead_or_paralyzed_front_does_not_replace_last_recoverable_front(
        self,
        _window_cursor: Mock,
    ) -> None:
        for hp, paralyzed in ((0, False), (10, True)):
            with self.subTest(hp=hp, paralyzed=paralyzed):
                mock = Game.__new__(Game)
                mock.party_window = Mock()
                mock.party_cursor = Mock(selected_key=0)
                recoverable = Mock(
                    hp=10,
                    paralyzed=False,
                    is_front_row=True,
                    formation_row=FormationRow.FRONT,
                )
                unavailable = Mock(
                    hp=hp,
                    paralyzed=paralyzed,
                    is_front_row=True,
                    formation_row=FormationRow.FRONT,
                )
                mock.party = (recoverable, unavailable)
                mock.sort_source_index = None
                mock.sort_source_cursor = None
                mock.alert = Mock()

                mock._confirm_sort_member()
                mock._confirm_sort_member()

                self.assertIs(recoverable.formation_row, FormationRow.FRONT)
                mock.alert.start.assert_called_once_with()

    @patch("game.WindowCursor")
    def test_cannot_swap_last_recoverable_front_with_unavailable_reserve(
        self,
        _window_cursor: Mock,
    ) -> None:
        mock = Game.__new__(Game)
        mock.party_window = Mock()
        mock.party_cursor = Mock(selected_key=0)
        recoverable = Mock(
            key="recoverable",
            hp=10,
            paralyzed=False,
            is_front_row=True,
            formation_row=FormationRow.FRONT,
        )
        rear_members = tuple(
            Mock(
                key=f"rear-{index}",
                hp=10 if index == 0 else 0,
                paralyzed=False,
                is_front_row=False,
                formation_row=FormationRow.BACK,
            )
            for index in range(4)
        )
        reserve = Mock(
            key="reserve",
            hp=10,
            paralyzed=True,
            is_front_row=True,
            formation_row=FormationRow.FRONT,
        )
        mock.party = (recoverable, *rear_members, reserve)
        original_party = mock.party
        mock.sort_source_index = None
        mock.sort_source_cursor = None
        mock.alert = Mock()
        mock._refresh_party_window_texts = Mock()

        mock._confirm_sort_member()
        mock.party_cursor.selected_key = 5
        mock._confirm_sort_member()

        self.assertEqual(mock.party, original_party)
        mock.alert.start.assert_called_once_with()
        mock._refresh_party_window_texts.assert_not_called()

    def test_cancel_steps_back_from_source_then_from_sort_mode(self) -> None:
        mock = Game.__new__(Game)
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

    def test_right_returns_from_sort_mode_before_selecting_source(self) -> None:
        mock = Game.__new__(Game)
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState(
            navigation=Direction.RIGHT,
            held_direction=Direction.RIGHT,
        )
        mock.command_cursor = Mock(active=False)
        mock.command_window = Mock()
        mock.party_window = Mock()
        mock.party_cursor = Mock()
        mock.sort_source_index = None
        mock.sort_source_cursor = None
        mock.alert = Mock()
        mock.settings_cursor = None
        mock.confirmation_cursor = None

        mock.update()

        self.assertIsNone(mock.party_cursor)
        self.assertTrue(mock.command_cursor.active)
        mock.party_window.clear_cursor.assert_called_once_with()
        mock.party_window.update.assert_not_called()

    def test_right_does_not_return_after_selecting_sort_source(self) -> None:
        mock = Game.__new__(Game)
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState(
            navigation=Direction.RIGHT,
            held_direction=Direction.RIGHT,
        )
        mock.command_cursor = Mock(active=False)
        mock.command_window = Mock()
        mock.party_window = Mock()
        mock.party_cursor = Mock(selected_key=2)
        mock.sort_source_index = 2
        mock.sort_source_cursor = Mock()
        mock.selected_member_index = 2
        mock.alert = Mock()
        mock.settings_cursor = None
        mock.confirmation_cursor = None

        mock.update()

        self.assertIsNotNone(mock.party_cursor)
        self.assertEqual(mock.sort_source_index, 2)
        self.assertFalse(mock.command_cursor.active)
        mock.party_window.clear_cursor.assert_not_called()
        mock.party_window.update.assert_called_once_with(Direction.RIGHT)

    @patch("game.pyxel.play")
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

    @patch("game.pyxel.blt")
    def test_selected_member_draws_blinking_formation_arrow(
        self,
        blt: Mock,
    ) -> None:
        mock = Game.__new__(Game)
        mock.sort_source_index = 1
        mock.party_cursor = Mock(selected_key=1)
        mock.party = (
            Mock(is_front_row=True),
            Mock(is_front_row=False),
        )

        with patch(
            "game.pyxel.frame_count",
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

    @patch("game.pyxel.blt")
    def test_front_member_draws_right_arrow_when_another_front_remains(
        self,
        blt: Mock,
    ) -> None:
        mock = Game.__new__(Game)
        mock.sort_source_index = 0
        mock.party_cursor = Mock(selected_key=0)
        mock.party = (
            Mock(hp=10, paralyzed=False, is_front_row=True),
            Mock(hp=10, paralyzed=False, is_front_row=True),
        )

        with patch("game.pyxel.frame_count", 0):
            mock._draw_formation_arrow()

        self.assertEqual(blt.call_args.args[0], PARTY_FACE_X[True] + PARTY_FACE_SIZE)
        self.assertEqual(blt.call_args.args[3], FORMATION_ARROW_RIGHT_X[0])

    @patch("game.pyxel.blt")
    def test_last_front_member_does_not_draw_formation_arrow(
        self,
        blt: Mock,
    ) -> None:
        mock = Game.__new__(Game)
        mock.sort_source_index = 0
        mock.party_cursor = Mock(selected_key=0)
        mock.party = (
            Mock(hp=10, paralyzed=False, is_front_row=True),
            Mock(hp=10, paralyzed=False, is_front_row=False),
        )

        mock._draw_formation_arrow()

        blt.assert_not_called()

    @patch("game.pyxel.blt")
    def test_formation_arrow_is_hidden_when_cursor_moves_from_source(
        self,
        blt: Mock,
    ) -> None:
        mock = Game.__new__(Game)
        mock.sort_source_index = 0
        mock.party_cursor = Mock(selected_key=1)
        mock.party = (
            Mock(is_front_row=True),
            Mock(is_front_row=True),
        )

        mock._draw_formation_arrow()

        blt.assert_not_called()

    def test_confirming_settings_command_opens_settings_window(self) -> None:
        mock = Game.__new__(Game)
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

    def test_debug_settings_row_is_available_in_current_game(self) -> None:
        self.assertIn(("screen_flash", 17), SETTINGS_ROWS)
        self.assertIn(("in_game_hints", 20), SETTINGS_ROWS)
        self.assertIn(("command_memory", 23), SETTINGS_ROWS)
        self.assertIn(("auto_spells", 26), SETTINGS_ROWS)
        self.assertIn(("debug", 29), SETTINGS_ROWS)

    def test_confirming_debug_setting_opens_debug_menu(self) -> None:
        mock = Game.__new__(Game)
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
        mock = Game.__new__(Game)
        mock.settings = Settings()
        mock.settings_repository = Mock()
        mock.settings_cursor = Mock(selected_key="language")
        mock.command_cursor = Mock(active=True)
        mock._build_main_windows = Mock()
        mock._refresh_settings_window = Mock()

        mock._change_setting(-1)

        self.assertIs(mock.settings.language, Language.ENGLISH)
        mock.settings_repository.save.assert_called_once_with(mock.settings)
        mock._build_main_windows.assert_called_once_with(
            selected_command="config",
            animate=False,
        )
        self.assertFalse(mock.command_cursor.active)
        mock._refresh_settings_window.assert_called_once_with(
            selected_key="language"
        )

    @patch("game.pyxel.play")
    def test_se_setting_wraps_and_plays_da2_preview_sound(self, play: Mock) -> None:
        mock = Game.__new__(Game)
        mock.settings = Settings(se_volume=4)
        mock.settings_repository = Mock()
        mock.settings_cursor = Mock(selected_key="se")
        mock._apply_se_volume = Mock()
        mock._refresh_settings_window = Mock()

        mock._change_setting(1)

        self.assertEqual(mock.settings.se_volume, 0)
        mock._apply_se_volume.assert_called_once_with()
        play.assert_called_once_with(ALERT_CHANNEL, SE_PREVIEW_SOUND_ID)
        mock._refresh_settings_window.assert_called_once_with(selected_key="se")

    @patch("game.pyxel.play")
    def test_bgm_setting_wraps_and_immediately_changes_volume(
        self,
        play: Mock,
    ) -> None:
        mock = Game.__new__(Game)
        mock.settings = Settings(bgm_volume=4)
        mock.settings_repository = Mock()
        mock.settings_cursor = Mock(selected_key="bgm")
        mock.bgm = Mock()
        mock._refresh_settings_window = Mock()

        mock._change_setting(1)

        self.assertEqual(mock.settings.bgm_volume, 0)
        mock.bgm.set_volume.assert_called_once_with(0)
        play.assert_not_called()
        mock._refresh_settings_window.assert_called_once_with(selected_key="bgm")

    def test_screen_size_and_display_settings_wrap_in_both_directions(self) -> None:
        mock = Game.__new__(Game)
        mock.settings = Settings(screen_scale=1)
        mock.settings_repository = Mock()
        mock.settings_cursor = Mock(selected_key="screen_size")
        mock._refresh_settings_window = Mock()

        mock._change_setting(-1)

        self.assertEqual(mock.settings.screen_scale, 5)

        mock.settings_cursor.selected_key = "display"
        mock._apply_display_mode = Mock()
        mock._change_setting(1)

        self.assertIs(mock.settings.display_mode, DisplayMode.SMOOTH)
        mock._apply_display_mode.assert_called_once_with()

    def test_in_game_hints_setting_toggles_and_is_persisted(self) -> None:
        mock = Game.__new__(Game)
        mock.settings = Settings()
        mock.localized = localized_menu_texts(
            TextCatalog.from_json(APP_ROOT / "data" / "texts.json"),
            Language.JAPANESE,
        )
        mock.settings_repository = Mock()
        mock.settings_cursor = Mock(selected_key="in_game_hints")
        mock._refresh_settings_window = Mock()

        mock._change_setting(1)
        self.assertFalse(mock.settings.in_game_hints_enabled)
        self.assertEqual(mock._settings_value("in_game_hints"), "オフ")
        mock.settings_repository.save.assert_called_with(mock.settings)
        mock._change_setting(-1)
        self.assertTrue(mock.settings.in_game_hints_enabled)
        self.assertEqual(mock._settings_value("in_game_hints"), "オン")
        mock.settings_repository.save.assert_called_with(mock.settings)

    def test_screen_flash_setting_toggles_and_is_persisted(self) -> None:
        mock = Game.__new__(Game)
        mock.settings = Settings(screen_flash_enabled=True)
        mock.settings_repository = Mock()
        mock.settings_cursor = Mock(selected_key="screen_flash")
        mock._refresh_settings_window = Mock()

        mock._change_setting(1)

        self.assertFalse(mock.settings.screen_flash_enabled)
        mock.settings_repository.save.assert_called_once_with(mock.settings)
        mock._refresh_settings_window.assert_called_once_with(
            selected_key="screen_flash"
        )

    def test_setting_change_is_not_applied_when_persistence_fails(self) -> None:
        from systems import SettingsSystemError

        mock = Game.__new__(Game)
        mock.settings = Settings()
        mock.settings_repository = Mock()
        mock.settings_repository.save.side_effect = SettingsSystemError()
        mock.settings_cursor = Mock(selected_key="language")
        mock.alert = Mock()
        mock._build_main_windows = Mock()
        mock._refresh_settings_window = Mock()

        mock._change_setting(1)

        self.assertIs(mock.settings.language, Language.JAPANESE)
        mock.alert.start.assert_called_once_with()
        mock._build_main_windows.assert_not_called()
        mock._refresh_settings_window.assert_not_called()

    def test_moving_settings_cursor_refreshes_text_without_reopening_window(
        self,
    ) -> None:
        mock = Game.__new__(Game)
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
        mock = Game.__new__(Game)
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

    @patch("game.pyxel.reset")
    def test_return_to_title_restarts_pyxel_when_screen_scale_changed(
        self,
        reset: Mock,
    ) -> None:
        mock = Game.__new__(Game)
        mock.settings = Settings(
            language=Language.ENGLISH,
            screen_scale=5,
        )
        mock.applied_screen_scale = 3
        mock.bgm = Mock()
        mock._return_to_start_without_window_restart = Mock()
        with patch.dict(
            "game.os.environ",
            {"PYXEL_WINDOW_STATE": "old"},
            clear=True,
        ) as environment:
            with patch(
                "game.pyxel.WINDOW_STATE_ENV",
                "PYXEL_WINDOW_STATE",
            ):
                mock._return_to_start_screen()

            self.assertNotIn("PYXEL_WINDOW_STATE", environment)
            self.assertEqual(
                json.loads(environment[GAME_SETTINGS_ENV]),
                mock.settings.to_dict(),
            )
        reset.assert_called_once_with()
        mock.bgm.stop.assert_called_once_with()
        mock._return_to_start_without_window_restart.assert_not_called()

    @patch("game.pyxel.reset")
    def test_return_to_title_preserves_window_when_screen_scale_is_unchanged(
        self,
        reset: Mock,
    ) -> None:
        mock = Game.__new__(Game)
        mock.settings = Settings(
            language=Language.ENGLISH,
            screen_scale=3,
        )
        mock.applied_screen_scale = 3
        mock.bgm = Mock()
        mock._return_to_start_without_window_restart = Mock()
        with patch.dict(
            "game.os.environ",
            {"PYXEL_WINDOW_STATE": "preserve"},
            clear=True,
        ) as environment:
            with patch(
                "game.pyxel.WINDOW_STATE_ENV",
                "PYXEL_WINDOW_STATE",
            ):
                mock._return_to_start_screen()

            self.assertEqual(environment["PYXEL_WINDOW_STATE"], "preserve")
            self.assertEqual(
                json.loads(environment[GAME_SETTINGS_ENV]),
                mock.settings.to_dict(),
            )
        mock.bgm.stop.assert_called_once_with()
        reset.assert_not_called()
        mock._return_to_start_without_window_restart.assert_called_once_with()

    def test_in_memory_title_return_reinitializes_same_game_object(self) -> None:
        mock = Game.__new__(Game)
        mock.settings = Settings(language=Language.ENGLISH, screen_scale=3)
        mock.settings_repository = Mock()
        mock.palette_shifter = Mock()
        mock._load_mission_hint_shown_this_launch = True

        def reinitialize(game: Game, **_kwargs: object) -> None:
            game._load_mission_hint_shown_this_launch = False

        with patch.object(
            Game,
            "__init__",
            autospec=True,
            side_effect=reinitialize,
        ) as initialize:
            Game._return_to_start_without_window_restart(mock)

        initialize.assert_called_once_with(
            mock,
            settings=mock.settings,
            palette_shifter=mock.palette_shifter,
            settings_repository=mock.settings_repository,
        )
        self.assertTrue(mock._load_mission_hint_shown_this_launch)

    def test_return_to_title_closes_all_menu_windows_and_disables_cursors(
        self,
    ) -> None:
        mock = Game.__new__(Game)
        main_window = Window(0, 0, 8, 8)
        settings_window = Window(8, 0, 8, 8)
        confirmation_window = Window(16, 0, 8, 8)
        mock.windows = (main_window,)
        mock.settings_window = settings_window
        mock.confirmation_window = confirmation_window
        mock.settings_cursor = Mock(active=True)
        mock.confirmation_cursor = Mock(active=True)

        mock._begin_return_to_start()

        self.assertTrue(mock._returning_to_start)
        self.assertFalse(mock.settings_cursor.active)
        self.assertFalse(mock.confirmation_cursor.active)
        for window in (main_window, settings_window, confirmation_window):
            self.assertTrue(window.is_animating)

    def test_return_to_title_waits_for_window_close_and_action_release(
        self,
    ) -> None:
        mock = Game.__new__(Game)
        window = Window(0, 0, 8, 8)
        mock.windows = (window,)
        mock.settings_window = None
        mock.confirmation_window = None
        mock.settings_cursor = None
        mock.confirmation_cursor = None
        mock._return_to_start_screen = Mock()
        mock._begin_return_to_start()
        held_confirm = InputState(
            confirm=InputButton(triggered=False, held=True),
        )

        for _frame in range(WINDOW_ANIMATION_FRAME_COUNT):
            mock._update_return_to_start(held_confirm)

        self.assertTrue(window.is_closed)
        mock._return_to_start_screen.assert_not_called()
        self.assertTrue(mock._returning_to_start)

        mock._update_return_to_start(InputState())

        mock._return_to_start_screen.assert_called_once_with()
        self.assertFalse(mock._returning_to_start)

    @patch("game.pyxel.quit")
    def test_confirmed_quit_exits_the_game(self, quit_game: Mock) -> None:
        mock = Game.__new__(Game)
        mock.alert = Mock()
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState(
            confirm=InputButton(triggered=True, held=True)
        )
        mock.confirmation_cursor = Mock(selected_key="yes")
        mock.pending_settings_action = "quit"

        mock.update()

        quit_game.assert_called_once_with()

    def test_confirmed_return_to_title_begins_window_close(self) -> None:
        mock = Game.__new__(Game)
        mock.alert = Mock()
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState(
            confirm=InputButton(triggered=True, held=True)
        )
        mock.confirmation_cursor = Mock(selected_key="yes")
        mock.pending_settings_action = "return_title"
        mock._begin_return_to_start = Mock()

        mock.update()

        mock._begin_return_to_start.assert_called_once_with()

    def test_cancel_closes_settings_and_reactivates_command_cursor(self) -> None:
        mock = Game.__new__(Game)
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
        mock = Game.__new__(Game)
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
