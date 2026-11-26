from __future__ import annotations

import unittest
from dataclasses import replace
from unittest.mock import Mock, PropertyMock, patch

from tools._bootstrap import APP_ROOT  # noqa: F401
from battle_breath import resolve_fire_breath
from battle_magic import SpellAffinity
from auto_battle_simulation import BattleForecast
from monster import MonsterSpecialAction
from monster_ai import MonsterAction, monster_action_candidates, select_monster_action
from resistance import ResistanceType
from resources import load_record_array
from scenes.battle import (
    BattleMonster, BattlePhase, BATTLE_BACKGROUND_TINT_FRAME_COUNT, DAMAGE_POPUP_FRAME_COUNT,
    FIRE_BREATH_TINT_COLOR, SPELL_EFFECT_FLASH_PALETTE,
)
from tests.test_auto_battle import AutoBattleFixtures
from tests import test_battle_poison_breath as poison_tests


class FireBreathRuleTest(unittest.TestCase):
    def test_full_attack_hp_bonus_defense_and_independent_fire_resistance(self):
        args = dict(attack=84, hp=480, max_hp=480, target_spell_defense=20,
                    fire_resistant=False, random_factor=0.5)
        for changes, expected in (
            ({}, 30), ({"hp": 240}, 45), ({"hp": 1}, 60),
            ({"random_factor": 0}, 26), ({"random_factor": 1}, 33),
            ({"target_spell_defense": 100}, 0),
            ({"fire_resistant": True, "random_factor": 1}, 8),
        ):
            with self.subTest(changes=changes):
                result = resolve_fire_breath(**(args | changes))
                self.assertEqual(result.damage, expected)
                self.assertFalse(result.poisoned)
                self.assertEqual(result.resisted, changes.get("fire_resistant", False))


class FireBreathSelectionTest(unittest.TestCase):
    def test_fire_gigas_retains_power_hit_and_loads_fire_breath(self):
        record = next(r for r in load_record_array("monsters.json")
                      if r["name_en"] == "Fire Gigas")
        actor = BattleMonster.from_record(record, is_front_row=True)
        self.assertEqual(actor.special_actions, (
            MonsterSpecialAction.POWER_HIT, MonsterSpecialAction.FIRE_BREATH,
        ))

    def test_front_rear_and_both_breaths_are_equal_weight_candidates(self):
        for front in (False, True):
            for can_breathe in (False, True):
                candidates = monster_action_candidates(
                    special_actions=(MonsterSpecialAction.POWER_HIT,
                                     MonsterSpecialAction.FIRE_BREATH,
                                     MonsterSpecialAction.POISON_BREATH),
                    is_front_row=front, can_attack=front, can_charge=True,
                    can_breathe=can_breathe, spell_keys=(), escape_eligible=False,
                )
                self.assertEqual(candidates, (
                    *((MonsterAction.POISON_BREATH, MonsterAction.FIRE_BREATH)
                      if can_breathe else ()),
                    MonsterAction.ATTACK if front else MonsterAction.IDLE,
                ))

    def test_intelligence_seven_avoids_fire_only_when_all_targets_resist(self):
        for intelligence in (0, 1, 6, 7):
            for effective in (False, True):
                with patch("monster_ai.random.choice", side_effect=lambda values: values[0]):
                    action = select_monster_action(
                        special_actions=(MonsterSpecialAction.FIRE_BREATH,),
                        is_front_row=False, can_attack=False, can_charge=True,
                        party_actual_attacks=(), monster_attack=84,
                        can_breathe=True, intelligence=intelligence,
                        fire_breath_effective=effective,
                    )
                self.assertIs(action, MonsterAction.IDLE
                              if intelligence == 7 and not effective
                              else MonsterAction.FIRE_BREATH)

    def test_display_names_distinguish_both_breaths(self):
        texts = {r["text_key"]: r for r in load_record_array("texts.json")}
        self.assertEqual(texts["battle.monster.poison_breath"]["text_ja"], "どくのブレス")
        self.assertEqual(texts["battle.monster.fire_breath"]["text_ja"], "ほのおのブレス")


class FireBreathSceneTest(unittest.TestCase):
    scene = poison_tests.PoisonBreathSceneTest.scene

    def begin(self, scene, actor):
        actor.state.silenced = 4
        with patch("scenes.battle.random.random", return_value=0.5), \
                patch("scenes.battle.random.randint") as poison_roll, \
                patch("scenes.battle.play_se") as sound:
            self.assertTrue(scene._begin_monster_fire_breath(actor))
        sound.assert_called_once_with("battle_fire_breath")
        poison_roll.assert_not_called()

    def test_simultaneous_damage_timing_red_background_and_restoration(self):
        scene, actor = self.scene()
        hp = tuple(m.hp for m in scene.party)
        self.begin(scene, actor)
        presentation = scene.action_presentation
        self.assertIs(scene.phase, BattlePhase.ACTION_PRESENTATION)
        self.assertEqual(presentation.background_tint_color, FIRE_BREATH_TINT_COLOR)
        self.assertEqual(presentation.party_poison_results, ())
        self.assertEqual(len(presentation.party_damage_results), 2)
        self.assertEqual(actor.state.mp, 0)
        scene._show_monster_action_message.assert_called_once_with("battle.monster.fire_breath")
        scene.palette_shifter.define_mix = Mock(wraps=scene.palette_shifter.define_mix)
        for frame in range(1, DAMAGE_POPUP_FRAME_COUNT + BATTLE_BACKGROUND_TINT_FRAME_COUNT + 1):
            scene._update_action_presentation()
            if frame < DAMAGE_POPUP_FRAME_COUNT:
                self.assertEqual(tuple(m.hp for m in scene.party), hp)
            if frame == 16:
                self.assertAlmostEqual(scene.palette_shifter.define_mix.call_args.kwargs["base_rate"], 0.4)
                self.assertEqual(scene.palette_shifter.define_mix.call_args.kwargs["target_color"], FIRE_BREATH_TINT_COLOR)
        for i, result in enumerate(presentation.party_damage_results):
            self.assertEqual(scene.party[i].hp, max(0, hp[i] - result.damage))
            self.assertFalse(scene.party[i].poisoned)
        self.assertEqual(len(scene.spell_damage_popups), 2)
        self.assertIsNone(scene.action_presentation)
        scene._complete_current_turn.assert_called_once_with()
        self.assertNotIn(SPELL_EFFECT_FLASH_PALETTE, scene.palette_shifter._variants)

    def test_only_fire_resistance_reduces_damage_and_shows_resist_icon(self):
        for attribute in (ResistanceType.FIRE, ResistanceType.POISON):
            scene, actor = self.scene()
            with patch.object(type(scene.party[0]), "resistances", new_callable=PropertyMock,
                              return_value=frozenset((attribute,))):
                self.begin(scene, actor)
            for result in scene.action_presentation.party_damage_results:
                expected = resolve_fire_breath(
                    attack=70, hp=actor.state.hp, max_hp=actor.state.max_hp,
                    target_spell_defense=scene.party[result.target_index].battle_stats.spell_resistance,
                    fire_resistant=attribute is ResistanceType.FIRE, random_factor=0.5,
                )
                self.assertEqual(result.damage, expected.damage)
                self.assertIs(result.affinity, SpellAffinity.RESIST
                              if expected.resisted else SpellAffinity.NORMAL)
            self.assertEqual(len(scene.affinity_popups), 2 if attribute is ResistanceType.FIRE else 0)

    def test_hidden_dead_and_escaped_targets_and_no_target(self):
        for condition in ("hidden", "dead", "escaped"):
            scene, actor = self.scene()
            if condition == "hidden":
                scene.hidden_party_indexes.add(1)
            elif condition == "escaped":
                scene.escaped_party_indexes.add(1)
            else:
                scene.party[1].defeat()
            self.begin(scene, actor)
            self.assertEqual(tuple(r.target_index for r in scene.action_presentation.party_damage_results), (0,))
        scene, actor = self.scene()
        scene.hidden_party_indexes = {0, 1}
        with patch("scenes.battle.play_se") as sound:
            self.assertFalse(scene._begin_monster_fire_breath(actor))
        sound.assert_not_called()

    def test_monster_turn_dispatches_breath_and_records_action(self):
        scene, actor = self.scene()
        scene.timeline = (actor,)
        scene.command_window = Mock()
        scene.monster_blink_frames_remaining = 0
        scene.monster_attack_target_index = None
        scene._select_monster_action = Mock(return_value=MonsterAction.FIRE_BREATH)
        scene.progression = Mock()
        with patch("scenes.battle.play_se"):
            scene._update_monster_action()
        self.assertEqual(scene.action_presentation.background_tint_color, FIRE_BREATH_TINT_COLOR)
        scene.progression.record_enemy_action.assert_called_once_with(0)


class FireBreathForecastTest(AutoBattleFixtures, unittest.TestCase):
    def test_forecast_respects_hidden_fire_resistance_and_hp_bonus(self):
        enemy = self.enemy(front=False, attack=84, hp=60, max_hp=120,
                           special_actions=(MonsterSpecialAction.FIRE_BREATH,))
        ally = replace(self.specs[0], hp=100, max_hp=100, spell_defense=20)
        hidden = replace(self.specs[1], hidden=True)
        resistant = replace(self.specs[2], hp=100, max_hp=100, spell_defense=20,
                            resistances=frozenset((ResistanceType.FIRE,)))
        forecast = BattleForecast(self.snapshot(ally, hidden, resistant, enemy), 0)
        # Sorted candidates: fire_breath (0), idle (1).
        forecast.roll = lambda *args: 0.1
        forecast.enemy_turn(forecast.actors[5])
        expected = resolve_fire_breath(
            attack=84, hp=60, max_hp=120, target_spell_defense=20,
            fire_resistant=False, random_factor=0.1,
        ).damage
        self.assertEqual(forecast.actors[0].hp, 100 - expected)
        self.assertFalse(forecast.actors[0].poisoned)
        self.assertEqual(forecast.actors[1].hp, hidden.hp)
        self.assertEqual(forecast.actors[2].hp, 100 - expected // 4)

    def test_intelligent_forecast_avoids_resisted_breath(self):
        enemy = self.enemy(front=False, intelligence=7,
                           special_actions=(MonsterSpecialAction.FIRE_BREATH,))
        ally = replace(self.specs[0], resistances=frozenset((ResistanceType.FIRE,)))
        forecast = BattleForecast(self.snapshot(ally, enemy), 0)
        forecast.roll = lambda *args: 0.1
        forecast.enemy_turn(forecast.actors[5])
        self.assertEqual(forecast.actors[0].hp, ally.hp)


if __name__ == "__main__":
    unittest.main()
