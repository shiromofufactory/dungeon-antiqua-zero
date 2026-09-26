from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tools._bootstrap import APP_ROOT

# isort: split
from battle_command_memory import BattleCommandMemory
from battle_commands import BattleCommand, BattleCommandOption
from game import Game
from input import InputButton, InputState
from localization import Localizer
from scenes.battle import (
    BattleCharacter,
    BattleEncounter,
    BattleGlobalCommand,
    BattleItemCandidate,
    BattlePhase,
    BattleScene,
)
from state import SaveData, Settings, SpellMode
from systems.inventory import InventorySystem
from systems.settings import SettingsSystemError
from text_catalog import TextCatalog
from ui.window import WindowFactory

from tests.test_auto_battle import AutoBattleFixtures


class BattlePreferencesTest(AutoBattleFixtures, unittest.TestCase):
    def scene(self, settings=None, memory=None, party=None, encounter=None):
        settings = Settings() if settings is None else settings
        scene = BattleScene.__new__(BattleScene)
        scene.settings = settings
        scene.party = self.party if party is None else party
        scene.encounter = (
            BattleEncounter(("Coyote",)) if encounter is None else encounter
        )
        scene.active_party_index = 0
        scene.command_memory = BattleCommandMemory() if memory is None else memory
        scene.last_command_by_party_index = {}
        scene.last_spell_key_by_party_index = {}
        scene.last_item_selection_by_party_index = {}
        scene.last_cover_target_by_party_index = {}
        scene.last_global_command = None
        scene.command_cursor = Mock()
        scene.texts = TextCatalog.from_json(APP_ROOT / "data" / "texts.json")
        scene.localizer = Localizer(settings.language)
        scene.global_command_window = WindowFactory(object()).create(
            0, 0, 15, 13, opened=True
        )
        scene._open_member_command_menu = Mock()
        scene._begin_escape_confirmation = Mock()
        scene._begin_auto_battle = Mock()
        scene._restore_command_memory()
        scene._refresh_global_command_options()
        return scene

    def test_event_battle_disables_escape_and_skips_remembered_escape(self):
        memory = BattleCommandMemory(global_command="escape")
        scene = self.scene(
            memory=memory,
            encounter=BattleEncounter(("Coyote",), escape_command_enabled=False),
        )

        self.assertFalse(scene.initial_global_command_pending)
        self.assertEqual(
            scene.global_command_cursor.selected_key, BattleGlobalCommand.FIGHT
        )
        self.assertEqual(memory.global_command, "escape")
        targets = scene.global_command_cursor.targets
        self.assertEqual([target.selectable for target in targets], [True, False, True])
        with self.assertRaises(ValueError):
            scene.global_command_cursor.select_key(BattleGlobalCommand.ESCAPE)
        scene.global_command_cursor.select_key(BattleGlobalCommand.AUTO)
        self.assertEqual(
            scene.global_command_cursor.selected_key, BattleGlobalCommand.AUTO
        )

    def test_event_battle_ignores_escape_confirmation(self):
        scene = self.scene(
            encounter=BattleEncounter(("Coyote",), escape_command_enabled=False)
        )
        scene.global_command_cursor = Mock(selected_key=BattleGlobalCommand.ESCAPE)

        scene._update_global_command_selection(
            InputState(confirm=InputButton(triggered=True))
        )

        scene._begin_escape_confirmation.assert_not_called()
        self.assertIsNone(scene.command_memory.global_command)

    def test_each_global_command_is_remembered_only_after_confirmation(self):
        for command in BattleGlobalCommand:
            with self.subTest(command=command):
                scene = self.scene()
                scene.global_command_cursor.select_key(command)
                self.assertIsNone(scene.command_memory.global_command)
                scene._update_global_command_selection(
                    InputState(confirm=InputButton(triggered=True))
                )
                scene._refresh_global_command_options()
                self.assertEqual(scene.global_command_cursor.selected_key, command)
                self.assertEqual(scene.command_memory.global_command, command.value)
                following = self.scene(memory=scene.command_memory)
                self.assertEqual(following.global_command_cursor.selected_key, command)
                following._begin_auto_battle.assert_not_called()

    def prepare_first_turn(self, scene):
        scene.party_visuals = tuple(
            BattleCharacter(member, 0, 0, 0) for member in scene.party
        )
        scene.timeline = (scene.party_visuals[0],)
        scene.phase = BattlePhase.ENTRANCE
        scene.auto_battle_active = False
        scene.defending_party_indexes = set()
        scene.command_window = WindowFactory(object()).create(
            0, 0, 30, 30, opened=False
        )
        scene.global_command_window.close_immediately()
        scene.target_cursor = Mock()
        for name in (
            "_remove_defeated_party_from_timeline",
            "_refresh_party_text_colors",
            "_refresh_monster_name_colors",
            "_refresh_input_guide",
            "_close_spell_windows",
            "_hide_command_guide",
            "_refresh_command_options",
            "_select_initial_member_command",
            "_start_timeline_animation",
        ):
            setattr(scene, name, Mock())
        for name in (
            "_party_is_defeated",
            "_prune_surprise_pending_party",
            "_begin_front_promotion_if_needed",
            "_apply_turn_start_hp_change",
            "_skip_surprised_party_turn",
            "_begin_focused_attack",
        ):
            setattr(scene, name, Mock(return_value=False))

    def test_next_battle_starts_with_remembered_auto_or_escape_window(self):
        for command in (BattleGlobalCommand.AUTO, BattleGlobalCommand.ESCAPE):
            with self.subTest(command=command):
                first = self.scene()
                first.global_command_cursor.select_key(command)
                first._update_global_command_selection(
                    InputState(confirm=InputButton(triggered=True))
                )
                scene = self.scene(memory=first.command_memory)
                self.prepare_first_turn(scene)
                scene._activate_timeline_head()
                self.assertIs(scene.phase, BattlePhase.GLOBAL_COMMAND)
                self.assertIs(scene.global_command_cursor.selected_key, command)
                self.assertTrue(scene.global_command_window.is_animating)
                self.assertFalse(scene.command_window.is_open)
                self.assertFalse(scene.auto_battle_active)
                scene._begin_auto_battle.assert_not_called()
                scene._begin_escape_confirmation.assert_not_called()
                scene._open_member_command_menu = (
                    BattleScene._open_member_command_menu.__get__(scene)
                )
                scene._update_global_command_selection(
                    InputState(cancel=InputButton(triggered=True))
                )
                self.assertIs(scene.phase, BattlePhase.COMMAND)
                scene._activate_timeline_head()
                self.assertIs(scene.phase, BattlePhase.COMMAND)
                self.assertFalse(scene.global_command_window.is_open)

    def test_first_window_stays_individual_without_auto_or_escape_memory(self):
        for remembered, enabled in ((None, True), ("fight", True), ("auto", False)):
            with self.subTest(remembered=remembered, enabled=enabled):
                scene = self.scene(
                    Settings(remember_battle_commands=enabled),
                    BattleCommandMemory(global_command=remembered),
                )
                self.prepare_first_turn(scene)
                scene._activate_timeline_head()
                self.assertIs(scene.phase, BattlePhase.COMMAND)
                self.assertTrue(scene.command_window.is_animating)
                self.assertFalse(scene.global_command_window.is_open)

    def test_initial_global_window_waits_for_a_selectable_party_turn(self):
        scene = self.scene(memory=BattleCommandMemory(global_command="auto"))
        self.prepare_first_turn(scene)
        enemy = Mock()
        enemy.state.consume_stun.return_value = False
        enemy.state.elapse_sleep_turn.return_value = False
        scene._monster_can_attempt_action = Mock(return_value=True)
        scene.monsters = (enemy,)
        scene.timeline = (enemy,)
        scene._activate_timeline_head()
        self.assertIs(scene.phase, BattlePhase.MONSTER_ACTION)
        self.assertTrue(scene.initial_global_command_pending)
        scene.timeline = (scene.party_visuals[0],)
        scene._skip_surprised_party_turn.return_value = True
        scene._activate_timeline_head()
        self.assertTrue(scene.initial_global_command_pending)
        scene._skip_surprised_party_turn.return_value = False
        scene._activate_timeline_head()
        self.assertIs(scene.phase, BattlePhase.GLOBAL_COMMAND)
        self.assertFalse(scene.initial_global_command_pending)

    def test_auto_interruption_remembers_fight_in_every_cancellable_phase(self):
        for phase in (
            BattlePhase.AUTO_THINKING,
            BattlePhase.ACTION_TARGET,
            BattlePhase.TARGET,
            BattlePhase.IDENTIFY_RESULT,
            BattlePhase.ACTION_PRESENTATION,
            BattlePhase.ATTACK_PRESENTATION,
            BattlePhase.MONSTER_ACTION,
        ):
            with self.subTest(phase=phase):
                scene = self.scene(memory=BattleCommandMemory(global_command="auto"))
                scene.phase = phase
                scene.auto_battle_active = True
                scene.auto_battle_planner = object()
                scene.last_command_by_party_index[0] = BattleCommand.SPELL
                scene.last_spell_key_by_party_index[0] = "FIRE1"
                scene._clear_action_target_state = Mock()
                scene._begin_action_return = Mock()
                scene._finish_identify_result = Mock()
                scene.target_cursor = Mock()
                scene._refresh_input_guide = Mock()
                scene._cancel_auto_battle()
                self.assertFalse(scene.auto_battle_active)
                self.assertIsNone(scene.auto_battle_planner)
                self.assertFalse(scene.initial_global_command_pending)
                self.assertIs(scene.last_global_command, BattleGlobalCommand.FIGHT)
                self.assertEqual(scene.command_memory.global_command, "fight")
                self.assertIs(scene.last_command_by_party_index[0], BattleCommand.SPELL)
                self.assertEqual(scene.last_spell_key_by_party_index[0], "FIRE1")
                scene._refresh_global_command_options()
                self.assertIs(
                    scene.global_command_cursor.selected_key, BattleGlobalCommand.FIGHT
                )
                following = self.scene(memory=scene.command_memory)
                self.prepare_first_turn(following)
                following._activate_timeline_head()
                self.assertIs(following.phase, BattlePhase.COMMAND)

    def test_auto_interruption_does_not_store_memory_when_disabled(self):
        scene = self.scene(Settings(remember_battle_commands=False))
        scene.phase = BattlePhase.AUTO_THINKING
        scene.auto_battle_active = True
        scene._refresh_input_guide = Mock()
        scene._cancel_auto_battle()
        self.assertEqual(scene.command_memory, BattleCommandMemory())
        self.assertIsNone(scene.last_global_command)

    def test_global_cancel_does_not_remember_an_unconfirmed_choice(self):
        scene = self.scene(memory=BattleCommandMemory(global_command="auto"))
        scene.global_command_cursor.select_key(BattleGlobalCommand.ESCAPE)
        scene._update_global_command_selection(
            InputState(cancel=InputButton(triggered=True))
        )
        scene._refresh_global_command_options()
        self.assertEqual(
            scene.global_command_cursor.selected_key, BattleGlobalCommand.AUTO
        )

    def test_memory_stays_with_character_across_battles_and_reordering(self):
        first = self.scene()
        first._remember_active_command(BattleCommand.SPELL)
        first.last_spell_key_by_party_index[0] = "FIRE1"
        candidate = BattleItemCandidate(self.items["MIRACLE RING"])
        first._remember_active_item(candidate)
        second = self.scene(
            memory=first.command_memory, party=tuple(reversed(self.party))
        )
        index = len(self.party) - 1
        self.assertEqual(second.last_command_by_party_index[index], BattleCommand.SPELL)
        self.assertEqual(second.last_spell_key_by_party_index[index], "FIRE1")
        self.assertEqual(
            second.last_item_selection_by_party_index[index], ("MIRACLE RING", None)
        )
        self.assertEqual(second.last_cover_target_by_party_index, {})

    def test_off_clears_prior_memory_and_does_not_store_or_restore_choices(self):
        memory = BattleCommandMemory(
            global_command="auto",
            commands={self.party[0].definition.key: BattleCommand.SPELL},
        )
        scene = self.scene(Settings(remember_battle_commands=False), memory)
        self.assertEqual(memory, BattleCommandMemory())
        self.assertEqual(
            scene.global_command_cursor.selected_key, BattleGlobalCommand.FIGHT
        )
        scene.global_command_cursor.select_key(BattleGlobalCommand.AUTO)
        scene._update_global_command_selection(
            InputState(confirm=InputButton(triggered=True))
        )
        scene._remember_active_command(BattleCommand.DEFEND)
        scene._remember_active_item(BattleItemCandidate(self.items["MIRACLE RING"]))
        self.assertEqual(memory, BattleCommandMemory())
        self.assertEqual(scene.last_command_by_party_index, {})
        self.assertEqual(scene.last_item_selection_by_party_index, {})
        scene.last_item_selection_by_party_index[0] = ("MIRACLE RING", None)
        self.assertIsNone(
            scene._remembered_item_index(
                (BattleItemCandidate(self.items["MIRACLE RING"]),)
            )
        )
        scene.last_command_by_party_index[0] = BattleCommand.SPELL
        scene._active_member_command_options = Mock(
            return_value=(BattleCommandOption(BattleCommand.ATTACK),)
        )
        scene._select_initial_member_command()
        scene.command_cursor.select_key.assert_not_called()

    def test_spell_menu_restores_only_confirmed_choices_when_enabled(self):
        first = self.spells["FIRE1"]
        previous = self.spells["SLOW"]
        for enabled in (True, False):
            with self.subTest(enabled=enabled):
                scene = self.scene(Settings(remember_battle_commands=enabled))
                scene.last_spell_key_by_party_index[0] = previous.key
                scene.spell_cursor = Mock(selected_key=previous.key)
                scene._active_member_spell_candidates = Mock(
                    return_value=(first, previous)
                )
                scene._begin_action_motion = Mock()
                scene.command_window = Mock()
                scene.spell_window = WindowFactory(object()).create(0, 0, 30, 45)
                scene._hide_command_guide = Mock()
                scene._refresh_spell_guide = Mock()
                self.assertTrue(scene._begin_spell_selection())
                self.assertEqual(
                    scene.spell_cursor.selected_key,
                    previous.key if enabled else first.key,
                )
                scene.last_spell_key_by_party_index.clear()
                scene.spell_cursor.select_key(previous.key)
                self.assertTrue(scene._begin_spell_selection())
                self.assertEqual(scene.spell_cursor.selected_key, first.key)

    def test_manual_spell_usage_does_not_record_choices_when_disabled(self):
        scene = self.scene(Settings(remember_battle_commands=False))
        spell = self.spells["FIRE1"]
        scene.spell_candidates = (spell,)
        scene.spell_cursor = Mock(selected_key=spell.key)
        scene._begin_action_target_selection = Mock(return_value=True)
        self.assertTrue(scene._use_selected_spell())
        self.assertEqual(scene.last_spell_key_by_party_index, {})
        self.assertEqual(scene.command_memory.spells, {})

    def test_loading_applies_saved_choices_only_when_memory_is_enabled(self):
        for command in ("auto", "escape"):
            for enabled in (True, False):
                with self.subTest(command=command, enabled=enabled):
                    game = Game.__new__(Game)
                    game.settings = Settings(
                        in_game_hints_enabled=False,
                        remember_battle_commands=enabled,
                    )
                    memory = BattleCommandMemory(global_command=command)
                    loaded = SimpleNamespace(
                        save_data=SaveData(),
                        active_party=self.party,
                        character_states={m.definition.key: m for m in self.party},
                        inventory=InventorySystem(self.items),
                        battle_command_memory=memory,
                    )
                    game.pending_loaded_state = loaded
                    game.pending_loaded_map = Mock(sites=(), bgm_id="da3-field")
                    game.pending_loaded_field = Mock()
                    game.pending_loaded_renderer = Mock()
                    game.pending_load_slot = 1
                    game.shops = ()
                    game._reset_field_actors = Mock()
                    game._build_main_windows = Mock()
                    game._refresh_site_name_label = Mock()
                    game.bgm = Mock()
                    with patch("game.ShopSystem"):
                        game._apply_start_game()
                    self.assertIs(game.battle_command_memory, memory)
                    scene = self.scene(game.settings, memory=game.battle_command_memory)
                    self.prepare_first_turn(scene)
                    scene._activate_timeline_head()
                    self.assertIs(
                        scene.phase,
                        BattlePhase.GLOBAL_COMMAND if enabled else BattlePhase.COMMAND,
                    )
                    if enabled:
                        self.assertEqual(
                            scene.global_command_cursor.selected_key.value, command
                        )
                    else:
                        self.assertEqual(
                            game.battle_command_memory, BattleCommandMemory()
                        )

    def game(self, key):
        game = Game.__new__(Game)
        game.settings = Settings()
        game.settings_cursor = Mock(selected_key=key)
        game.settings_repository = Mock()
        game._refresh_settings_window = Mock()
        game.alert = Mock()
        game.battle_command_memory = BattleCommandMemory(global_command="auto")
        return game

    def test_spell_setting_cycles_both_directions_and_is_immediately_saved(self):
        game = self.game("auto_spells")
        for expected in (SpellMode.RECOVERY_ONLY, SpellMode.NEVER, SpellMode.USE):
            game._change_setting(1)
            self.assertIs(game.settings.auto_battle_spell_mode, expected)
            self.assertEqual(
                game.settings_repository.save.call_args.args[0], game.settings
            )
        game._change_setting(-1)
        self.assertIs(game.settings.auto_battle_spell_mode, SpellMode.NEVER)

    def test_memory_setting_clears_only_after_successful_save(self):
        game = self.game("command_memory")
        game.settings_repository.save.side_effect = SettingsSystemError()
        game._change_setting(1)
        self.assertTrue(game.settings.remember_battle_commands)
        self.assertEqual(game.battle_command_memory.global_command, "auto")
        game.alert.start.assert_called_once()
        game.settings_repository.save.side_effect = None
        game._change_setting(1)
        self.assertFalse(game.settings.remember_battle_commands)
        self.assertEqual(game.battle_command_memory, BattleCommandMemory())
        game._change_setting(-1)
        self.assertTrue(game.settings.remember_battle_commands)


if __name__ == "__main__":
    unittest.main()
