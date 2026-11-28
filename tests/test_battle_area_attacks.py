from __future__ import annotations

import unittest
from dataclasses import replace
from unittest.mock import Mock, patch

from tests.test_auto_battle import AutoBattleFixtures
from tests.test_battle_monster_spells import spellcaster
from tests import test_battle_poison_breath as poison_tests

from auto_battle_simulation import BattleForecast
from monster import MonsterBattleState, MonsterSpecialAction
from monster_ai import MonsterAction, MonsterSpellAction


AREA_SPECIALS = (
    MonsterSpecialAction.POISON_BREATH,
    MonsterSpecialAction.FIRE_BREATH,
    MonsterSpecialAction.EARTHQUAKE,
)


class MonsterAreaAttackSceneTest(unittest.TestCase):
    def scene(self, *, max_mp=12):
        scene, attacker = poison_tests.PoisonBreathSceneTest().scene()
        attacker.spell_keys = ("FIRE2",)
        attacker.state = MonsterBattleState(max_hp=20, max_mp=max_mp)
        other = spellcaster(magic=0, spell_key="FIRE2")
        other.spell_keys = ("FIRE2", "FIRE1", "SLEEP")
        other.special_actions = AREA_SPECIALS
        other.intelligence = 2
        scene.monsters = (attacker, other)
        scene.command_window = Mock()
        scene.command_cursor = Mock()
        scene.defending_party_indexes = set()
        return scene, attacker, other

    def test_successful_area_cast_filters_other_candidates_until_casters_next_turn(self):
        scene, attacker, other = self.scene()
        # A spell defined as all-target still counts against just one visible member.
        scene.hidden_party_indexes.add(1)
        other.is_front_row = True
        self.assertTrue(scene._begin_monster_spell(attacker, scene.spells["FIRE2"]))
        self.assertEqual(scene._monster_area_attack_cooldown.attacker, 0)
        with patch("monster_ai.random.choice", side_effect=lambda actions: actions[0]) as choose:
            scene._select_monster_action(other)
        self.assertEqual(tuple(choose.call_args.args[0]), (
            MonsterSpellAction("FIRE1"), MonsterSpellAction("SLEEP"), MonsterAction.ATTACK,
        ))

        scene._remove_defeated_party_from_timeline = Mock()
        scene._party_is_defeated = Mock(return_value=False)
        scene._prune_surprise_pending_party = Mock(return_value=False)
        scene._begin_front_promotion_if_needed = Mock(return_value=False)
        scene._apply_turn_start_hp_change = Mock(return_value=False)
        scene._start_timeline_animation = Mock()
        for index, actor in ((0, other), (None, attacker)):
            actor.state.stunned = True
            scene.timeline = (actor,)
            scene._activate_timeline_head()
            self.assertEqual(scene._monster_area_attack_cooldown.attacker, index)
        self.assertEqual(scene._start_timeline_animation.call_count, 2)
        self.assertIn("FIRE2", scene._targetable_monster_spell_keys(other))

    def test_unlaunched_spell_does_not_start_cooldown(self):
        for silenced in (False, True):
            with self.subTest(silenced=silenced):
                scene, attacker, _ = self.scene(max_mp=12 if silenced else 0)
                if silenced:
                    attacker.state.silenced = 2
                self.assertTrue(scene._begin_monster_spell(attacker, scene.spells["FIRE2"]))
                self.assertIsNone(scene._monster_area_attack_cooldown.attacker)
                message = (
                    scene._show_monster_spell_sealed_message
                    if silenced else scene._show_monster_spell_mp_lack_message
                )
                message.assert_called_once()

    def test_both_breaths_and_earthquake_start_cooldown_and_death_clears_it(self):
        for method in ("_begin_monster_poison_breath", "_begin_monster_fire_breath",
                       "_begin_monster_earthquake"):
            with self.subTest(method=method):
                scene, attacker, other = self.scene()
                with patch("scenes.battle.play_se"):
                    self.assertTrue(getattr(scene, method)(attacker))
                self.assertNotIn("FIRE2", scene._targetable_monster_spell_keys(other))
                scene.target_cursor = Mock()
                scene._start_monster_death_effect = Mock()
                self.assertTrue(scene._begin_monster_death(0))
                self.assertIn("FIRE2", scene._targetable_monster_spell_keys(other))

    def test_rotation_uses_an_area_attack_without_replacing_cooldown(self):
        scene, attacker, other = self.scene()
        other.intelligence = 3
        other.state.action_rotation_index = 0
        with patch("scenes.battle.play_se"):
            self.assertTrue(scene._begin_monster_fire_breath(attacker))
            self.assertIs(scene._select_monster_action(other), MonsterAction.POISON_BREATH)
            self.assertTrue(scene._begin_monster_poison_breath(other))
        self.assertEqual(other.state.action_rotation_index, 1)
        self.assertEqual(scene._monster_area_attack_cooldown.attacker, 0)


class MonsterAreaAttackForecastTest(AutoBattleFixtures, unittest.TestCase):
    def test_area_spell_blocks_next_monster_but_releases_on_sleeping_casters_turn(self):
        caster = self.enemy(
            front=False, intelligence=2, agility=30,
            spells=(self.spells["FIRE2"],), mp=20, max_mp=20,
        )
        breather = self.enemy(
            number=6, front=False, intelligence=2, special_actions=AREA_SPECIALS,
        )
        anchor = self.enemy(number=7, front=True, agility=1)
        snapshot = self.snapshot(
            caster, breather, anchor, self.specs[0], active=5,
            gauges=((5, 64), (6, 60), (7, 0), (0, 0)),
        )
        forecast = BattleForecast(snapshot, 0)
        forecast.step({})
        self.assertEqual(forecast.monster_area_attack_cooldown.attacker, 5)
        self.assertEqual(forecast.actors[5].mp, 20 - self.spells["FIRE2"].mp)
        after_spell = forecast.actors[0].hp
        self.assertEqual(forecast.order.entries[0].actor, 6)
        forecast.step({})
        self.assertEqual(forecast.actors[0].hp, after_spell)
        self.assertEqual(forecast.monster_area_attack_cooldown.attacker, 5)
        self.assertEqual(forecast.order.entries[0].actor, 5)
        forecast.actors[5].sleeping = 1
        forecast.step({})
        self.assertIsNone(forecast.monster_area_attack_cooldown.attacker)

    def test_seeded_cooldown_is_ignored_by_rotation_and_cleared_on_attacker_death(self):
        rotation = self.enemy(
            number=6, front=False, intelligence=3, action_rotation_index=0,
            special_actions=(MonsterSpecialAction.FIRE_BREATH,),
        )
        owner = self.enemy()
        snapshot = replace(
            self.snapshot(rotation, owner, self.specs[0], active=6),
            monster_area_attack_attacker=5,
        )
        forecast = BattleForecast(snapshot, 0)
        hp = forecast.actors[0].hp
        forecast.step({})
        self.assertLess(forecast.actors[0].hp, hp)
        self.assertEqual(forecast.monster_area_attack_cooldown.attacker, 5)
        forecast.actors[5].damage(owner.hp)
        forecast.normalize()
        self.assertIsNone(forecast.monster_area_attack_cooldown.attacker)
        forecast = BattleForecast(replace(snapshot, monster_area_attack_attacker=None), 0)
        forecast.step({})
        self.assertIsNone(forecast.monster_area_attack_cooldown.attacker)
