from __future__ import annotations

import unittest
from dataclasses import replace
from unittest.mock import Mock, patch

from tools._bootstrap import APP_ROOT
from auto_battle_simulation import BattleForecast
from battle_physical import CONSTRICTION_HIT_ROLL_COUNT, resolve_physical_attack
from item import AdditionalEffect
from member import FormationRow
from monster import MonsterSpecialAction
from monster_ai import MonsterAction, monster_action_candidates
from resistance import ResistanceType
from resources import load_record_array
from scenes.battle import BattleMonster
from tests.test_auto_battle import AutoBattleFixtures
from tests.test_battle_monster_spells import spell_scene


class BattleConstrictionTest(unittest.TestCase):
    def test_normal_hit_count_and_damage_distribution_are_preserved_at_sixty_percent(self):
        for conditions in (
            {"target_evasion": 25},
            {"target_evasion": 25, "target_defending": True},
            {"target_evasion": 25, "target_incapacitated": True, "critical_roll": 0},
        ):
            with self.subTest(conditions=conditions):
                args = dict(attack=30, hit=80, target_defense=10, **conditions)
                normal = [resolve_physical_attack(**args, hit_roll=roll) for roll in range(100)]
                constriction = [
                    resolve_physical_attack(**args, hit_roll=roll, constricting=True)
                    for roll in range(CONSTRICTION_HIT_ROLL_COUNT)
                ]
                self.assertEqual(
                    [result for result in constriction if result.hit],
                    [result for result in normal if result.hit for _ in range(3)],
                )

    def test_constriction_is_a_separate_candidate_with_normal_attack_reach(self):
        constriction = MonsterSpecialAction.CONSTRICTION
        ranged = MonsterSpecialAction.RANGED_ATTACK
        for specials, front, can_attack, expected in (
            ((constriction,), True, True, (MonsterAction.CONSTRICTION, MonsterAction.ATTACK)),
            ((constriction,), True, False, ()),
            ((constriction,), False, False, (MonsterAction.IDLE,)),
            ((constriction, ranged), False, True, (MonsterAction.CONSTRICTION, MonsterAction.ATTACK)),
        ):
            with self.subTest(specials=specials, front=front, can_attack=can_attack):
                self.assertEqual(monster_action_candidates(
                    special_actions=specials, is_front_row=front, can_attack=can_attack,
                    can_charge=False, spell_keys=(), escape_eligible=False,
                ), expected)

    def test_scene_reads_the_key_and_applies_damage_and_stun_on_impact(self):
        record = next(r for r in load_record_array("monsters.json") if r["name_en"] == "Giant Spider")
        for hit_roll, lethal in ((0, False), (499, False), (0, True)):
            with self.subTest(hit_roll=hit_roll, lethal=lethal):
                actor = BattleMonster.from_record(
                    record | {"special": "巻連", "extra": "毒吸", "attack": 8, "hit": 100, "int": 3},
                    is_front_row=True,
                )
                actor.state.action_rotation_index = 0
                scene = spell_scene(actor)
                target, other = scene.party
                target.formation_row = FormationRow.FRONT
                other.formation_row = FormationRow.BACK
                if lethal:
                    target.hp = 1
                hp = target.hp
                scene.timeline = (actor,)
                scene.command_window = Mock()
                scene.monster_blink_frames_remaining = 0
                scene.monster_attack_target_index = None
                scene.defending_party_indexes = set()
                scene._show_monster_action_message = Mock()
                scene._continue_after_formation = Mock()
                scene._remove_defeated_party_from_timeline = Mock()
                scene._prune_surprise_pending_party = Mock(return_value=False)
                scene._begin_front_promotion_if_needed = Mock(return_value=False)
                with patch("scenes.battle.random.randint", return_value=hit_roll) as roll, \
                        patch("scenes.battle.play_se"):
                    scene._update_monster_action()
                    self.assertIs(scene.monster_action, MonsterAction.CONSTRICTION)
                    self.assertEqual(actor.state.action_rotation_index, 1)
                    scene._show_monster_action_message.assert_called_once_with("battle.monster.constriction")
                    self.assertEqual(target.hp, hp)
                    self.assertFalse(target.stunned)
                    damage = scene.monster_attack_damage
                    for _ in range(scene._monster_attack_animation_frame_count()):
                        scene._update_monster_action()
                    roll.assert_called_once_with(0, 499)
                self.assertEqual(damage > 0, hit_roll == 0)
                self.assertEqual(target.hp, max(0, hp - damage))
                self.assertEqual(target.stunned, hit_roll == 0 and not lethal)
                self.assertFalse(target.poisoned)
                scene._continue_after_formation.assert_called_once()


class ConstrictionForecastTest(AutoBattleFixtures, unittest.TestCase):
    def test_forecast_applies_stun_resistance_and_miss_in_the_rotation(self):
        enemy = self.enemy(
            front=True, intelligence=3, action_rotation_index=0,
            special_actions=(MonsterSpecialAction.CONSTRICTION, MonsterSpecialAction.DOUBLE_ATTACK),
            additional_effects=(AdditionalEffect.POISON,),
        )
        for hit, resistances in (
            (True, frozenset()),
            (True, frozenset((ResistanceType.STUN,))),
            (False, frozenset()),
        ):
            with self.subTest(hit=hit, resistances=resistances):
                ally = replace(self.specs[0], hp=100, max_hp=100, defense=0, evasion=0, resistances=resistances)
                forecast = BattleForecast(self.snapshot(ally, enemy), 0)
                forecast.roll = lambda actor, target, purpose: 0.998 if purpose == 2 and not hit else 0.0
                forecast.enemy_turn(forecast.actors[5])
                self.assertEqual(forecast.actors[5].action_rotation_index, 1)
                target = forecast.actors[0]
                self.assertEqual(target.hp, 76 if hit else 100)
                self.assertEqual(target.stunned, hit and not resistances)
                self.assertFalse(target.poisoned)
