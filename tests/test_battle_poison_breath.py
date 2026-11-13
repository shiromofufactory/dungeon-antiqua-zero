from __future__ import annotations

import unittest
from dataclasses import replace
from unittest.mock import Mock, PropertyMock, patch

from tools._bootstrap import APP_ROOT  # noqa: F401
from battle_breath import resolve_poison_breath
from battle_magic import SpellAffinity
from monster import MonsterSpecialAction
from monster_ai import MonsterAction, monster_action_candidates, select_monster_action
from rendering.palette import PaletteShifter
from resistance import ResistanceType
from resources import load_record_array
from scenes.battle import (
    BattleMonster, BattlePhase, DAMAGE_POPUP_FRAME_COUNT,
    MONSTER_DAMAGE_SPRITE_SOURCE_X, POISON_BREATH_TINT_FRAME_COUNT,
    POISON_BREATH_TINT_COLOR,
    SPELL_EFFECT_FLASH_PALETTE,
)
from tests.test_battle_monster_spells import spell_scene, spellcaster
from tests.test_auto_battle import AutoBattleFixtures
from auto_battle_simulation import BattleForecast


class PoisonBreathRuleTest(unittest.TestCase):
    def resolve(self, **changes):
        args = dict(
            attack=70, hp=1300, max_hp=1300, target_spell_defense=20,
            poison_resistant=False, random_factor=0.5, poison_roll=1,
        )
        return resolve_poison_breath(**(args | changes))

    def test_da2_damage_increases_with_missing_hp_and_uses_spell_defense(self):
        self.assertEqual(self.resolve().damage, 20)
        self.assertEqual(self.resolve(hp=650).damage, 30)
        self.assertEqual(self.resolve(hp=1).damage, 40)
        self.assertEqual(self.resolve(random_factor=0).damage, 17)
        self.assertEqual(self.resolve(random_factor=1).damage, 22)
        self.assertEqual(self.resolve(target_spell_defense=100).damage, 0)

    def test_resistance_uses_integer_quarter_and_always_blocks_poison(self):
        result = self.resolve(poison_resistant=True, random_factor=1)
        self.assertEqual(result.damage, 5)  # floor(22 / 4), not ceil or spell's /3
        self.assertTrue(result.resisted)
        self.assertFalse(result.poisoned)

    def test_poison_has_exact_two_in_ten_chance_even_with_zero_damage(self):
        for roll in range(10):
            result = self.resolve(attack=0, poison_roll=roll)
            self.assertEqual(result.damage, 0)
            self.assertEqual(result.poisoned, roll < 2)


class PoisonBreathSelectionTest(unittest.TestCase):
    def test_gas_dragon_loads_poison_breath_from_registered_data(self):
        record = next(r for r in load_record_array("monsters.json")
                      if r["name_en"] == "Gas Dragon")
        actor = BattleMonster.from_record(record, is_front_row=True)
        self.assertIn(MonsterSpecialAction.POISON_BREATH, actor.special_actions)

    def test_front_and_rear_candidates_have_equal_weight_and_require_targets(self):
        for front in (False, True):
            for target in (False, True):
                candidates = monster_action_candidates(
                    special_actions=(MonsterSpecialAction.POISON_BREATH,),
                    is_front_row=front, can_attack=front, can_charge=target,
                    can_breathe=target, spell_keys=(), escape_eligible=False,
                )
                self.assertEqual(candidates, (
                    *((MonsterAction.POISON_BREATH,) if target else ()),
                    MonsterAction.ATTACK if front else MonsterAction.IDLE,
                ))

    def test_selector_does_not_use_mp_or_intelligence_to_filter_breath(self):
        with patch("monster_ai.random.choice", return_value=MonsterAction.POISON_BREATH) as choice:
            self.assertIs(select_monster_action(
                special_actions=(MonsterSpecialAction.POISON_BREATH,),
                is_front_row=False, can_attack=False, can_charge=True,
                can_breathe=True, party_actual_attacks=(), monster_attack=70,
                intelligence=7,
            ), MonsterAction.POISON_BREATH)
        self.assertEqual(choice.call_args.args[0], [MonsterAction.POISON_BREATH, MonsterAction.IDLE])


class PoisonBreathSceneTest(unittest.TestCase):
    def scene(self):
        actor = spellcaster(magic=0, spell_key="SLEEP", max_mp=0)
        actor.combat_stats = replace(actor.combat_stats, attack=70)
        scene = spell_scene(actor)
        scene.affinity_popups = []
        scene.palette_shifter = PaletteShifter(colors=list(range(32)), remap=Mock())
        scene._show_monster_action_message = Mock()
        scene._complete_current_turn = Mock()
        scene._member_focus_is_interrupted = Mock(return_value=True)
        scene.focused_target_by_party_index = {0: 0}
        return scene, actor

    def begin(self, scene, actor, *, roll=0):
        with (
            patch("scenes.battle.random.random", return_value=0.5),
            patch("scenes.battle.random.randint", return_value=roll),
            patch("scenes.battle.play_se") as sound,
        ):
            self.assertTrue(scene._begin_monster_poison_breath(actor))
        sound.assert_called_once_with("battle_poison_breath")

    def test_damage_poison_timing_tint_and_turn_completion(self):
        scene, actor = self.scene()
        scene.party[0].sleeping = 2
        hp = tuple(member.hp for member in scene.party)
        self.begin(scene, actor)
        self.assertIs(scene.phase, BattlePhase.ACTION_PRESENTATION)
        presentation = scene.action_presentation
        self.assertEqual(len(presentation.party_damage_results), 2)
        self.assertEqual(len(scene.spell_damage_popups), 2)
        self.assertEqual(actor.state.mp, 0)
        self.assertEqual(scene._party_sprite_source_x(0), MONSTER_DAMAGE_SPRITE_SOURCE_X)
        scene._show_monster_action_message.assert_called_once_with("battle.monster.poison_breath")
        for _ in range(DAMAGE_POPUP_FRAME_COUNT - 1):
            scene._update_action_presentation()
        self.assertEqual(tuple(member.hp for member in scene.party), hp)
        self.assertFalse(scene.party[0].poisoned)
        scene._update_action_presentation()
        for i, result in enumerate(presentation.party_damage_results):
            self.assertEqual(scene.party[i].hp, max(0, hp[i] - result.damage))
            self.assertTrue(scene.party[i].poisoned)
        self.assertEqual(scene.party[0].sleeping, 0)
        self.assertNotIn(0, scene.focused_target_by_party_index)
        self.assertEqual(len(scene.spell_damage_popups), 2)
        scene._complete_current_turn.assert_not_called()
        for _ in range(POISON_BREATH_TINT_FRAME_COUNT):
            scene._update_action_presentation()
        scene._complete_current_turn.assert_called_once_with()
        self.assertIsNone(scene.action_presentation)
        self.assertNotIn(SPELL_EFFECT_FLASH_PALETTE, scene.palette_shifter._variants)

    def test_hidden_dead_and_escaped_members_are_excluded(self):
        for excluded in ("hidden", "dead", "escaped"):
            with self.subTest(excluded=excluded):
                scene, actor = self.scene()
                if excluded == "hidden":
                    scene.hidden_party_indexes.add(1)
                elif excluded == "escaped":
                    scene.escaped_party_indexes.add(1)
                else:
                    scene.party[1].defeat()
                self.begin(scene, actor)
                self.assertEqual(tuple(r.target_index for r in scene.action_presentation.party_damage_results), (0,))
        scene, actor = self.scene()
        scene.hidden_party_indexes = {0, 1}
        with patch("scenes.battle.play_se") as sound:
            self.assertFalse(scene._begin_monster_poison_breath(actor))
        sound.assert_not_called()

    def test_scene_displays_resistance_and_does_not_poison(self):
        scene, actor = self.scene()
        with patch.object(type(scene.party[0]), "resistances", new_callable=PropertyMock,
                          return_value=frozenset((ResistanceType.POISON,))):
            self.begin(scene, actor)
        self.assertEqual(len(scene.affinity_popups), 2)
        self.assertTrue(all(r.affinity is SpellAffinity.RESIST for r in scene.action_presentation.party_damage_results))
        scene._apply_action_results(scene.action_presentation)
        self.assertTrue(all(not member.poisoned for member in scene.party))

    def test_lethal_results_do_not_poison(self):
        scene, actor = self.scene()
        scene.party[0].hp = scene.party[1].hp = 1
        self.begin(scene, actor)
        scene._apply_action_results(scene.action_presentation)
        self.assertTrue(all(member.hp == 0 and not member.poisoned for member in scene.party))

    def test_background_draw_does_not_advance_or_tint_other_layers(self):
        scene, actor = self.scene()
        self.begin(scene, actor)
        presentation = scene.action_presentation
        scene.palette_shifter.define_mix = Mock(wraps=scene.palette_shifter.define_mix)
        for frame, expected in ((0, 1.0), (16, 0.4), (35, 0.4), (51, 1.0)):
            presentation.elapsed_frame = frame
            scene._sync_poison_breath_background(presentation)
            self.assertAlmostEqual(scene.palette_shifter.define_mix.call_args.kwargs["base_rate"], expected)
            self.assertEqual(scene.palette_shifter.define_mix.call_args.kwargs["target_color"], POISON_BREATH_TINT_COLOR)
        scene._draw_background_image = Mock()
        scene._draw_background()
        scene._draw_background()
        self.assertEqual(presentation.elapsed_frame, 51)
        self.assertEqual(scene._draw_background_image.call_count, 2)
        self.assertEqual(scene.palette_shifter.define_mix.call_count, 4)


class PoisonBreathForecastTest(AutoBattleFixtures, unittest.TestCase):
    def test_forecast_uses_same_damage_and_poison_with_visible_living_targets(self):
        enemy = self.enemy(
            front=False, attack=70, hp=60, max_hp=120,
            special_actions=(MonsterSpecialAction.POISON_BREATH,),
        )
        ally = replace(self.specs[0], hp=100, max_hp=100, spell_defense=20)
        hidden = replace(self.specs[1], hidden=True)
        resistant = replace(self.specs[2], hp=100, max_hp=100, spell_defense=20,
                            resistances=frozenset((ResistanceType.POISON,)))
        forecast = BattleForecast(self.snapshot(ally, hidden, resistant, enemy), 0)
        # Sorted action candidates: idle (0), poison_breath (1).
        forecast.roll = lambda actor, target, purpose: 0.75 if purpose == 0 else 0.1
        forecast.enemy_turn(forecast.actors[5])
        expected = resolve_poison_breath(
            attack=70, hp=60, max_hp=120, target_spell_defense=20,
            poison_resistant=False, random_factor=0.1, poison_roll=1,
        )
        self.assertEqual(forecast.actors[0].hp, 100 - expected.damage)
        self.assertTrue(forecast.actors[0].poisoned)
        self.assertEqual(forecast.actors[1].hp, hidden.hp)
        self.assertEqual(forecast.actors[2].hp, 100 - expected.damage // 4)
        self.assertFalse(forecast.actors[2].poisoned)


if __name__ == "__main__":
    unittest.main()
