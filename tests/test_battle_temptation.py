from __future__ import annotations

import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from tools._bootstrap import APP_ROOT
from tools.screen_mocks._fixtures import load_mock_items, load_mock_party, load_mock_skills
from auto_battle_simulation import BattleForecast
from member import EquipmentSlot, Gender
from monster import MonsterSpecialAction
from monster_ai import MonsterAction
from resistance import ResistanceType
from resources import load_record_array
from scenes.battle import BattleMonster
from spell_effect import load_spell_effects
from state import Settings
from tests.test_auto_battle import AutoBattleFixtures
from tests.test_battle_monster_spells import spell_scene


class TemptationSceneTest(unittest.TestCase):
    def setUp(self):
        self.record = next(r for r in load_record_array("monsters.json") if r["name_en"] == "Lamia")
        self.actor = BattleMonster.from_record(self.record, is_front_row=False)
        self.scene = spell_scene(self.actor)

    def test_turn_tints_screen_while_animating_only_successful_men(self):
        scene, actor = self.scene, self.actor
        self.assertEqual(actor.special_actions, (
            MonsterSpecialAction.TEMPTATION, MonsterSpecialAction.CONSTRICTION,
        ))
        self.assertEqual(actor.magic, self.record["mag"])
        self.assertEqual(actor.spell_keys, ())
        items = load_mock_items()
        scene.party = load_mock_party(
            items, load_mock_skills(), character_keys=("Fiora", "Cerion", "Alvan"),
        )
        scene.party[2].equipment = scene.party[2].equipment.replaced({
            EquipmentSlot.BODY: items["MASTER LEATHER"],
        })
        scene.party_visuals = tuple(SimpleNamespace(member=member) for member in scene.party)
        scene.hidden_party_indexes = {1}
        scene._party_draw_position = Mock(return_value=None)
        scene._party_sprite_x = Mock(return_value=188)
        scene.spell_effects = load_spell_effects(APP_ROOT / "effects" / "spells.json")
        scene.spell_effect_renderer = Mock()
        scene._show_monster_action_message = Mock()
        scene._complete_current_turn = Mock()
        scene._sync_unselectable_target_palette = Mock()
        scene.timeline = (actor,)
        scene.command_window = Mock()
        scene.monster_attack_target_index = None
        scene.monster_blink_frames_remaining = 0
        scene.progression = Mock()
        actor.state.apply_silence(2)
        with (
            patch("monster_ai.random.choice", return_value=MonsterAction.TEMPTATION) as choose,
            patch("scenes.battle.random.randint", side_effect=(0, 3, 0)) as roll,
            patch("scenes.battle.play_se") as sound,
        ):
            scene._update_monster_action()
            choose.assert_called_once_with([MonsterAction.TEMPTATION, MonsterAction.IDLE])
            self.assertEqual(roll.call_args_list, [call(0, 19), call(2, 3), call(0, 19)])
            scene.progression.record_enemy_action.assert_called_once_with(0)
            scene._show_monster_action_message.assert_called_once_with("battle.monster.temptation")
            self.assertEqual(actor.state.mp, 0)
            self.assertEqual(actor.state.silenced, 1)
            presentation = scene.action_presentation
            self.assertEqual(
                [(result.target_index, result.success) for result in presentation.party_confuse_results],
                [(1, True), (2, False)],
            )
            effect, = presentation.spell_effects
            self.assertEqual(effect.target_index, 1)
            self.assertIs(effect.player.definition, scene.spell_effects["CONFUSION"])
            flash = presentation.screen_flash
            self.assertEqual(flash.color_index, 57)
            sound.assert_called_once_with("spell_confusion")
            self.assertEqual(effect.player.elapsed_frame, 0)
            for _ in range(15):
                scene._update_action_presentation()
                self.assertFalse(presentation.results_applied)
            scene.sync_action_screen_flash(suspended=True)
            scene.spell_effect_renderer.prepare_screen_flash.assert_called_with(None, 15)
            scene.sync_action_screen_flash()
            scene.spell_effect_renderer.prepare_screen_flash.assert_called_with(flash, 15)
            scene._update_action_presentation()
            self.assertTrue(presentation.results_applied)
            for _ in range(16):
                scene._update_action_presentation()
            scene.spell_effect_renderer.prepare_screen_flash.assert_called_with(flash, 32)
            self.assertIsNone(scene.action_presentation)
            self.assertEqual([member.confused for member in scene.party], [0, 3, 0])
            scene._complete_current_turn.assert_called_once_with()

    def test_each_nonresistant_man_uses_his_own_success_roll(self):
        scene, actor = self.scene, self.actor
        scene.party = load_mock_party(
            load_mock_items(), load_mock_skills(), character_keys=("Cerion", "Alvan"),
        )
        scene.party_visuals = tuple(SimpleNamespace(member=member) for member in scene.party)
        self.assertFalse(any(ResistanceType.CONFUSE in member.resistances for member in scene.party))
        scene.settings = Settings(screen_flash_enabled=False)
        scene._show_monster_action_message = Mock()
        for rolls, expected in (
            ((0, 2, 19), (True, False)),
            ((19, 0, 2), (False, True)),
        ):
            with self.subTest(rolls=rolls), patch("scenes.battle.random.randint", side_effect=rolls):
                self.assertTrue(scene._begin_monster_temptation(actor))
                results = scene.action_presentation.party_confuse_results
                self.assertEqual(tuple(result.success for result in results), expected)

    def test_target_selection_and_flash_setting(self):
        scene, actor = self.scene, self.actor
        scene.escaped_party_indexes = {1}
        self.assertIs(scene._select_monster_action(actor), MonsterAction.IDLE)
        self.assertFalse(scene._begin_monster_temptation(actor))
        scene.escaped_party_indexes.clear()
        scene.settings = Settings(screen_flash_enabled=False)
        scene._show_monster_action_message = Mock()
        with patch("scenes.battle.random.randint", return_value=19):
            self.assertTrue(scene._begin_monster_temptation(actor))
        self.assertIsNone(scene.action_presentation.screen_flash)
        self.assertEqual(scene.action_presentation.spell_effects, ())

        scene.settings = Settings()
        scene.spell_effect_renderer = Mock()
        with patch("scenes.battle.random.randint", return_value=19):
            self.assertTrue(scene._begin_monster_temptation(actor))
        presentation = scene.action_presentation
        self.assertEqual(presentation.screen_flash.color_index, 57)
        self.assertEqual(presentation.spell_effects, ())
        for _ in range(16):
            scene._update_action_presentation()
        self.assertTrue(presentation.results_applied)
        self.assertEqual(len(scene.spell_damage_popups), 1)
        self.assertEqual(scene.party[1].confused, 0)


class TemptationForecastTest(AutoBattleFixtures, unittest.TestCase):
    def test_predicts_distinct_rolls_for_two_eligible_targets(self):
        first, second = (
            replace(spec, spell_defense=11, resistances=frozenset())
            for spec in self.specs[1:]
        )
        enemy = self.enemy(
            front=False, magic=12, special_actions=(MonsterSpecialAction.TEMPTATION,),
        )
        for successful_target in (first.number, second.number):
            with self.subTest(successful_target=successful_target):
                forecast = BattleForecast(self.snapshot(first, second, enemy, active=first.number), 0)
                values = {
                    (0, 0): 0.99,
                    (first.number, 10): 0.3 if successful_target == first.number else 0.35,
                    (second.number, 10): 0.3 if successful_target == second.number else 0.35,
                }
                forecast.roll = lambda actor, target, purpose: values.get((target, purpose), 0.0)
                forecast.enemy_turn(forecast.actors[5])
                self.assertEqual(
                    [actor.spec.number for actor in forecast.allies() if actor.confused],
                    [successful_target],
                )

    def test_forecast_uses_gender_resistance_magic_and_integer_roll(self):
        self.assertEqual(self.specs[0].gender, Gender.FEMALE)
        self.assertEqual(self.specs[1].gender, Gender.MALE)
        woman = replace(self.specs[0], spell_defense=0, resistances=frozenset())
        man = replace(self.specs[1], hidden=True, spell_defense=11, resistances=frozenset())
        resistant_man = replace(self.specs[2], resistances=frozenset({ResistanceType.CONFUSE}))
        enemy = self.enemy(
            front=False, magic=12, silenced=2, special_actions=(MonsterSpecialAction.TEMPTATION,),
        )
        for roll, expected_turns in ((6, 2), (7, 0)):
            with self.subTest(roll=roll):
                forecast = BattleForecast(self.snapshot(woman, man, resistant_man, enemy), 0)
                rolls = {0: 0.99, 10: roll / 20}
                forecast.roll = lambda actor, target, purpose: rolls.get(purpose, 0.0)
                forecast.enemy_turn(forecast.actors[5])
                self.assertEqual(
                    [forecast.actors[index].confused for index in range(3)],
                    [0, expected_turns, 0],
                )
