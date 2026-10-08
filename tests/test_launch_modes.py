from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from tools._bootstrap import APP_ROOT as _APP_ROOT
from field import FieldPosition
from game import Game, GameScreenChange, INITIAL_PARTY_KEYS, MENU_COMMANDS, NEW_GAME_EVENT_ID, NEW_GAME_MAP_ID
from game_data import create_party
from input import Direction, InputButton, InputState
from member import FIORA_CHARACTER_KEY, required_experience_for_level
from resources.events import EventCatalog
from state import Language, LaunchMode, Settings
from ui import DEFAULT_TEXT_COLOR, DISABLED_COLOR, POSITIVE_COLOR
from systems import (
    BattleProgression, EnemyProgressionData, EventContext, MessageEffect, ResetGameEffect,
    create_save_document, restore_save_document,
)


class LaunchModeGameTest(unittest.TestCase):
    def setUp(self) -> None:
        for name in (
            "FontResources", "ImageResources", "MapResources", "FieldMovement",
            "FieldRenderer", "WindowFactory", "create_game_input_reader",
            "BgmPlayer", "StartMenuOverlay", "SaveRepository",
            "Game._reset_field_actors", "Game._refresh_site_name_label",
        ):
            patcher = patch(f"game.{name}")
            mocked = patcher.start()
            self.addCleanup(patcher.stop)
            if name == "FontResources":
                mocked.return_value.baseline_offset_for.return_value = 0
                mocked.return_value.font_for.return_value.text_width.side_effect = lambda text: len(text) * 6
                mocked.return_value.line_height_for.return_value = 8
            elif name == "MapResources":
                mocked.return_value.map.return_value = Mock(sites=())
            elif name == "WindowFactory":
                mocked.return_value.create.return_value.set_cursor.return_value.selected_key = "language"

    def game(self, mode: LaunchMode) -> Game:
        return Game(settings=Settings(), palette_shifter=Mock(base_colors=(0x000000,)), launch_mode=mode)

    def test_title_waits_for_confirm_without_reading_slots_or_counting_play_time(self) -> None:
        for mode in LaunchMode:
            with self.subTest(mode=mode):
                game = self.game(mode)
                game.input_reader.poll.return_value = InputState()
                game.update()
                game.update()
                self.assertIsNotNone(game.title_scene)
                self.assertIsNone(game.start_screen)
                self.assertIsNone(game.pending_screen_change)
                self.assertEqual(game.save_data.play_time_frames, 0)
                game.save_repository.summaries.assert_not_called()
                game.save_repository.summary.assert_not_called()

    def test_title_confirm_routes_exhibition_directly_to_new_game(self) -> None:
        for mode in LaunchMode:
            with self.subTest(mode=mode), patch("game.StartMenuOverlay") as start_menu:
                game = self.game(mode)
                game.save_repository.summaries.reset_mock()
                game._start_field_event = Mock(return_value=True)
                game._update_field = Mock()
                game.input_reader.poll.return_value = InputState(confirm=InputButton(triggered=True, held=True))
                game.update()
                expected = GameScreenChange.START_GAME if mode is LaunchMode.EXHIBITION else GameScreenChange.SHOW_START_MENU
                self.assertIs(game.pending_screen_change, expected)
                game.input_reader.poll.return_value = InputState(confirm=InputButton(held=True))
                for _frame in range(2 * game.fade.frame_count + 1):
                    game.update()
                self.assertIsNone(game.title_scene)
                self.assertIsNone(game.pending_screen_change)
                if mode is LaunchMode.EXHIBITION:
                    start_menu.assert_not_called()
                    game.save_repository.summaries.assert_not_called()
                    self.assertIsNone(game.start_screen)
                    self.assertTrue(game.showing_field)
                    self.assertEqual(game.party[0].internal_level, 3)
                    game._start_field_event.assert_called_once_with(NEW_GAME_EVENT_ID)
                else:
                    start_menu.assert_called_once()
                    game.save_repository.summaries.assert_called_once_with()
                    self.assertIs(game.start_screen, start_menu.return_value)
                    self.assertFalse(game.showing_field)
                    game._start_field_event.assert_not_called()

    def test_only_exhibition_starts_at_party_level_three(self) -> None:
        for mode in LaunchMode:
            with self.subTest(mode=mode):
                game = self.game(mode)
                level = 3 if mode is LaunchMode.EXHIBITION else 1
                experience = 26 if mode is LaunchMode.EXHIBITION else 0
                self.assertEqual(game.save_data.experience, experience)
                for member in game.party:
                    expected = level if member.definition.key == FIORA_CHARACTER_KEY else member.definition.joining_internal_level(level)
                    self.assertEqual(member.internal_level, expected)
                    self.assertEqual(member.refresh_internal_level(experience), expected)
                    self.assertEqual(member.experience_offset, required_experience_for_level(expected) - experience)
                    self.assertEqual(member.hp, member.calculated_max_hp())
                    self.assertEqual(member.mp, member.calculated_max_mp())
                fiora = game.character_states[FIORA_CHARACTER_KEY]
                for proficiency in fiora.proficiencies.values():
                    self.assertEqual(proficiency.level, 1 if proficiency.aptitude else 0)
                    self.assertEqual(proficiency.progress, 0)

    def test_exhibition_level_survives_save_load_and_next_level(self) -> None:
        game = self.game(LaunchMode.EXHIBITION)
        document = create_save_document(
            save_data=game.save_data, active_party=game.party,
            character_states=game.character_states, inventory=game.inventory_system,
            map_id=NEW_GAME_MAP_ID, position=FieldPosition(39, 43), facing=Direction.UP,
        )
        self.assertNotIn("launch_mode", document)
        restored = restore_save_document(
            document, character_records=game.character_records,
            items=game.items, skills=game.skills,
        )
        fiora = restored.character_states[FIORA_CHARACTER_KEY]
        self.assertEqual(restored.save_data.experience, 26)
        self.assertEqual(fiora.experience_offset, 0)
        self.assertEqual(fiora.internal_level, 3)
        self.assertEqual(fiora.refresh_internal_level(required_experience_for_level(4) - 1), 3)
        self.assertEqual(fiora.refresh_internal_level(
            required_experience_for_level(4)
        ), 4)

    def test_loading_preserves_saved_levels_and_current_launch_mode(self) -> None:
        for mode in LaunchMode:
            with self.subTest(mode=mode):
                game = self.game(mode)
                saved_party = create_party(
                    game.items, game.skills, character_keys=INITIAL_PARTY_KEYS,
                    internal_level=7,
                )
                document = create_save_document(
                    save_data=game.save_data, active_party=saved_party,
                    character_states={member.definition.key: member for member in saved_party},
                    inventory=game.inventory_system, map_id=NEW_GAME_MAP_ID,
                    position=FieldPosition(39, 43), facing=Direction.UP,
                )
                game.pending_loaded_state = restore_save_document(
                    document, character_records=game.character_records,
                    items=game.items, skills=game.skills,
                )
                game.pending_loaded_map = game.current_map
                game.pending_loaded_field = game.field
                game.pending_loaded_renderer = game.field_renderer
                game.pending_load_slot = 1
                game._apply_start_game()
                self.assertIs(game.launch_mode, mode)
                self.assertEqual([member.internal_level for member in game.party], [7, 7])

    def test_exhibition_battle_rewards_add_to_initial_shared_experience(self) -> None:
        game = self.game(LaunchMode.EXHIBITION)
        for expected_experience, expected_level in ((41, 3), (56, 4)):
            progression = BattleProgression((EnemyProgressionData(5, 4, 4, 0),))
            growth = progression.settle(game.save_data, game.party)
            self.assertEqual(growth.experience_gained, 15)
            self.assertEqual(game.save_data.experience, expected_experience)
            self.assertEqual(game.party[0].internal_level, expected_level)
            self.assertEqual(game.party[0].experience_offset, 0)

    def test_mode_growth_limits_reach_battle_and_both_field_spell_paths(self) -> None:
        expected = {
            LaunchMode.NORMAL: (None, 999999),
            LaunchMode.EXHIBITION: (2, 500),
            LaunchMode.DEMO: (4, 5000),
            LaunchMode.BETA: (None, 999999),
        }
        for mode, (proficiency_limit, experience_limit) in expected.items():
            with self.subTest(mode=mode), \
                patch("game.BattleScene.create") as battle, \
                patch("game.SpellMenuOverlay") as spell, \
                patch("game.AutoRecoveryOverlay") as recovery:
                game = self.game(mode)
                game._build_battle_scene(Mock())
                game._start_spell()
                game._start_auto_recovery()
                for target in (battle, spell, recovery):
                    self.assertEqual(
                        target.call_args.kwargs["proficiency_level_limit"], proficiency_limit
                    )
                self.assertEqual(battle.call_args.kwargs["experience_limit"], experience_limit)

    def test_experience_value_uses_positive_color_at_each_mode_limit(self) -> None:
        for mode, limit in (
            (LaunchMode.NORMAL, 999999), (LaunchMode.EXHIBITION, 500),
            (LaunchMode.DEMO, 5000), (LaunchMode.BETA, 999999),
        ):
            with self.subTest(mode=mode):
                game = self.game(mode)
                for experience, expected_color in (
                    (limit - 1, DEFAULT_TEXT_COLOR),
                    (limit, POSITIVE_COLOR),
                    (limit + 1, POSITIVE_COLOR),
                    (0, DEFAULT_TEXT_COLOR),
                ):
                    with self.subTest(experience=experience):
                        game.save_data.experience = experience
                        game._refresh_info_window_texts()
                        placements = game._main_info_window_texts()
                        self.assertEqual(placements[3].color, expected_color)
                        self.assertEqual(placements[2].color, DEFAULT_TEXT_COLOR)
                        self.assertEqual(placements[1].color, DEFAULT_TEXT_COLOR)
                        self.assertEqual(
                            game.info_window.add_text.call_args_list[-5].kwargs["color"],
                            expected_color,
                        )

    def test_capped_experience_and_growth_survive_save_restore(self) -> None:
        for mode, limit, expected_level in (
            (LaunchMode.EXHIBITION, 500, 10), (LaunchMode.DEMO, 5000, 19),
        ):
            with self.subTest(mode=mode):
                game = self.game(mode)
                game.save_data.experience = limit - 5
                growth = BattleProgression((EnemyProgressionData(5, 4, 4, 0),)).settle(
                    game.save_data, game.party,
                    proficiency_level_limit=mode.proficiency_level_limit,
                    experience_limit=mode.experience_limit,
                )
                self.assertEqual(growth.experience_gained, 5)
                self.assertEqual(game.party[0].internal_level, expected_level)
                document = create_save_document(
                    save_data=game.save_data, active_party=game.party,
                    character_states=game.character_states, inventory=game.inventory_system,
                    map_id=NEW_GAME_MAP_ID, position=FieldPosition(39, 43), facing=Direction.UP,
                )
                restored = restore_save_document(
                    document, character_records=game.character_records,
                    items=game.items, skills=game.skills,
                )
                self.assertEqual(restored.save_data.experience, limit)
                self.assertEqual(restored.character_states[FIORA_CHARACTER_KEY].internal_level, expected_level)
                growth = BattleProgression((EnemyProgressionData(5, 4, 4, 0),)).settle(
                    restored.save_data, tuple(restored.character_states.values()),
                    proficiency_level_limit=mode.proficiency_level_limit,
                    experience_limit=mode.experience_limit,
                )
                self.assertEqual(growth.experience_gained, 0)

    def test_return_to_start_keeps_launch_mode_and_resets_initial_party(self) -> None:
        for mode in LaunchMode:
            with self.subTest(mode=mode):
                game = self.game(mode)
                game.party[0].internal_level = 40
                game._return_to_start_without_window_restart()
                self.assertIs(game.launch_mode, mode)
                self.assertEqual(game.party[0].internal_level, 3 if mode is LaunchMode.EXHIBITION else 1)
                self.assertEqual(game.save_data.experience, 26 if mode is LaunchMode.EXHIBITION else 0)
                self.assertIsNotNone(game.title_scene)
                self.assertIsNone(game.start_screen)

    def test_message_then_reset_returns_to_title_after_release_in_both_event_contexts(self) -> None:
        catalog = EventCatalog.from_document({
            "format_version": 1, "source_sha256": "0" * 64,
            "flags": ["sample.after_reset"],
            "events": {"sample.end": {"commands": [
                {"command": "message", "message_id": "sample.finished"},
                {"command": "reset_game"},
                {"command": "set_flag", "flag_id": "sample.after_reset"},
            ]}},
        })
        for mode in LaunchMode:
            for context in EventContext:
                with self.subTest(mode=mode, context=context), patch("game.EventMessageOverlay") as message:
                    game = self.game(mode)
                    game.title_scene = None
                    game.showing_field = True
                    game.save_data.gold = 123
                    game.event_catalog = catalog
                    battle = Mock() if context is EventContext.BATTLE else None
                    game.battle_scene = battle
                    if context is EventContext.BATTLE:
                        game._start_battle_event("sample.end")
                    else:
                        self.assertTrue(game._start_field_event("sample.end"))
                    message.return_value.update.return_value = False
                    game._update_event(InputState())
                    self.assertFalse(game._returning_to_start)
                    self.assertIsInstance(game.event_effect, MessageEffect)
                    message.return_value.update.return_value = True
                    held = InputState(confirm=InputButton(triggered=True, held=True))
                    game._update_event(held)
                    self.assertIsInstance(game.event_effect, ResetGameEffect)
                    self.assertTrue(game._returning_to_start)
                    game.input_reader.poll.return_value = held
                    with patch.object(game, "_update_event", wraps=game._update_event) as update_event:
                        for _frame in range(3):
                            game.update()
                        update_event.assert_not_called()
                    self.assertIsNone(game.title_scene)
                    self.assertNotIn("sample.after_reset", game.save_data.event_flags)
                    if battle is not None:
                        battle.update.assert_not_called()
                    game.input_reader.poll.return_value = InputState()
                    game.update()
                    self.assertIs(game.launch_mode, mode)
                    self.assertIsNotNone(game.title_scene)
                    self.assertIsNone(game.start_screen)
                    self.assertIsNone(game.event_runner)
                    self.assertIsNone(game.event_effect)
                    self.assertIsNone(game.battle_scene)
                    self.assertEqual(game.save_data.gold, 0)
                    self.assertEqual(game.save_data.event_flags, set())
                    self.assertEqual(game.save_data.experience, 26 if mode is LaunchMode.EXHIBITION else 0)
                    game.save_repository.save.assert_not_called()
                    if battle is not None:
                        battle.release_palette_variants.assert_called_once_with()

    def test_debug_label_cursor_and_entry_are_hidden_outside_normal_mode(self) -> None:
        for mode in LaunchMode:
            with self.subTest(mode=mode):
                game = self.game(mode)
                game._build_settings_window()
                keys = [target.key for target in game.settings_window.set_cursor.call_args.args[0]]
                texts = [placement.text for placement in game._settings_window_texts("language")]
                self.assertEqual("debug" in keys, mode is LaunchMode.NORMAL)
                self.assertEqual("デバッグメニュー" in texts, mode is LaunchMode.NORMAL)
                with patch("game.DebugMenuOverlay") as overlay:
                    game._start_debug_menu()
                self.assertEqual(overlay.called, mode is LaunchMode.NORMAL)
                self.assertEqual(game.debug_screen is not None, mode is LaunchMode.NORMAL)

    def test_only_exhibition_save_command_is_disabled_in_all_languages(self) -> None:
        for mode in LaunchMode:
            game = self.game(mode)
            for language in Language:
                with self.subTest(mode=mode, language=language), patch("game.WindowFactory") as factory:
                    game.settings = Settings(language=language)
                    game._build_main_windows(animate=False)
                    texts = factory.return_value.create.call_args_list[1].args[4]
                    for (command, _text_key), text in zip(MENU_COMMANDS, texts, strict=True):
                        expected = DISABLED_COLOR if command == "save" and mode is LaunchMode.EXHIBITION else DEFAULT_TEXT_COLOR
                        self.assertEqual(text.color, expected)
                    targets = game.command_window.set_cursor.call_args.args[0]
                    self.assertIn("save", [target.key for target in targets])

    def test_confirming_save_alerts_only_in_exhibition_and_keeps_menu_active(self) -> None:
        for mode in LaunchMode:
            with self.subTest(mode=mode), patch("game.SaveMenuOverlay") as save_screen:
                game = self.game(mode)
                game.title_scene = None
                game.save_repository.reset_mock()
                game.alert = Mock()
                game.command_cursor = Mock(selected_key="save", active=True)
                game.input_reader.poll.return_value = InputState(confirm=InputButton(triggered=True, held=True))
                save_screen.return_value.update.return_value = False
                game.update()
                if mode is LaunchMode.EXHIBITION:
                    game.alert.start.assert_called_once_with()
                    self.assertTrue(game.command_cursor.active)
                    self.assertEqual(game.command_cursor.selected_key, "save")
                    self.assertIsNone(game.pending_screen_change)
                    self.assertFalse(game.fade.is_active)
                else:
                    self.assertIs(game.pending_screen_change, GameScreenChange.OPEN_SAVE)
                game.input_reader.poll.return_value = InputState(confirm=InputButton(held=True))
                for _frame in range(2 * game.fade.frame_count):
                    game.update()
                if mode is LaunchMode.EXHIBITION:
                    save_screen.assert_not_called()
                    game.save_repository.summaries.assert_not_called()
                    game.save_repository.save.assert_not_called()
                    game.alert.start.assert_called_once_with()
                    self.assertIsNone(game.save_screen)
                else:
                    save_screen.assert_called_once()
                    game.save_repository.summaries.assert_called_once_with()
                    game.alert.start.assert_not_called()
                    self.assertIs(game.save_screen, save_screen.return_value)

    def test_game_injects_mode_into_field_and_battle_event_runners(self) -> None:
        for mode in LaunchMode:
            for context in EventContext:
                with self.subTest(mode=mode, context=context):
                    game = self.game(mode)
                    game.event_catalog = EventCatalog.from_document({
                        "format_version": 1, "source_sha256": "0" * 64, "flags": [],
                        "events": {"sample.run": {"commands": [{
                            "command": "branch",
                            "condition": {"type": "launch_mode", "mode": mode.value},
                            "then": [{"command": "message", "message_id": "sample.matches"}],
                            "else": [{"command": "message", "message_id": "sample.other"}],
                        }]}},
                    })
                    game._continue_event = Mock()
                    if context is EventContext.FIELD:
                        self.assertTrue(game._start_field_event("sample.run"))
                    else:
                        game._start_battle_event("sample.run")
                    self.assertIs(game.event_runner.context, context)
                    self.assertEqual(game.event_runner.advance(), MessageEffect("sample.matches"))


if __name__ == "__main__":
    unittest.main()
