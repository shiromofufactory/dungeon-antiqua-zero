from __future__ import annotations

import unittest
from dataclasses import replace
from unittest.mock import Mock, patch

from tools._bootstrap import APP_ROOT  # noqa: F401
from battle_physical import counter_attack_succeeds
from battle_timeline import TimelineEntry, TimelineOrder
from monster import MonsterSpecialAction
from monster_ai import MonsterAction, monster_action_candidates
from scenes.battle import (
    BattleAttackPresentation, BattleAttackStrike, BattleCharacter,
    BattleScene, MONSTER_BLINK_FRAME_COUNT,
)
from tests import test_battle_poison_breath as poison_tests
from tests.test_auto_battle import AutoBattleFixtures
from auto_battle_simulation import BattleForecast
from auto_battle_model import AutoAction
from battle_commands import BattleCommand
from member import FormationRow


class CounterRuleTest(unittest.TestCase):
    def test_da2_speed_ratio_and_twenty_step_boundary(self):
        for attacker, defender, successes in ((10, 10, 5), (20, 10, 3), (1, 30, 9)):
            for roll in range(20):
                self.assertEqual(counter_attack_succeeds(
                    attacker_agility=attacker, defender_agility=defender,
                    attacker_front=True, defender_front=True,
                    defender_actionable=True, roll=roll,
                ), roll < successes)

    def test_short_reach_requires_both_front_and_actionable(self):
        for front_a, front_d, able in ((False, True, True), (True, False, True), (True, True, False)):
            self.assertFalse(counter_attack_succeeds(
                attacker_agility=10, defender_agility=10,
                attacker_front=front_a, defender_front=front_d,
                defender_actionable=able, roll=0,
            ))

    def test_counter_is_passive(self):
        self.assertEqual(monster_action_candidates(
            special_actions=(MonsterSpecialAction.COUNTER,), is_front_row=True,
            can_attack=True, can_charge=True, spell_keys=(), escape_eligible=False,
        ), (MonsterAction.ATTACK,))


class CounterSceneTest(unittest.TestCase):
    def scene(self):
        scene, actor = poison_tests.PoisonBreathSceneTest().scene()
        actor.special_actions = (MonsterSpecialAction.COUNTER,)
        actor.is_front_row = True
        scene.party[0].formation_row = FormationRow.FRONT
        scene.active_party_index = 0
        scene.party_visuals = tuple(BattleCharacter(m, 0, 0, i) for i, m in enumerate(scene.party))
        scene._timeline_order = TimelineOrder((
            TimelineEntry(scene.party_visuals[0], 10, 64),
            TimelineEntry(actor, actor.agility, 30),
            TimelineEntry(scene.party_visuals[1], 10, 20),
        ))
        scene.timeline = scene._timeline_order.actors
        scene.pending_monster_counters = []
        scene.monster_attack_target_index = None
        scene._reveal_hidden_party_if_all_unavailable = Mock()
        scene.defending_party_indexes = set()
        scene.progression = Mock()
        return scene, actor

    def test_right_hand_only_including_miss_and_not_same_side(self):
        for hit in (False, True):
            scene, actor = self.scene()
            scene.action_party_index = 0
            scene._action_forward_jump_in_progress = Mock(return_value=False)
            scene._record_equipped_weapon_action = Mock()
            scene._begin_action_return = Mock()
            scene.attack_presentation = BattleAttackPresentation(0, (
                BattleAttackStrike(1 if hit else 0, (), None, 0, 1, is_hit=hit),
                BattleAttackStrike(1, (), None, 0, 2),
            ))
            with patch("scenes.battle.random.randint", return_value=0), patch("scenes.battle.play_se"):
                scene._update_attack_presentation()
                scene._update_attack_presentation()
            self.assertEqual(scene.pending_monster_counters, [(0, 0)])
        scene, _ = self.scene()
        scene.action_party_index = 0
        scene._action_forward_jump_in_progress = Mock(return_value=False)
        scene._record_equipped_weapon_action = Mock()
        scene._begin_action_return = Mock()
        scene.attack_presentation = BattleAttackPresentation(
            1, (BattleAttackStrike(1, (), None, 0, 1),), target_side="ally",
        )
        with patch("scenes.battle.play_se"):
            scene._update_attack_presentation()
        self.assertEqual(scene.pending_monster_counters, [])

    def test_death_sleep_confusion_stun_or_rear_row_prevents_counter(self):
        for condition in ("dead", "sleeping", "confused", "stunned", "rear"):
            scene, actor = self.scene()
            if condition == "dead":
                actor.state.defeat()
            elif condition == "rear":
                scene.party[0].formation_row = FormationRow.BACK
            else:
                setattr(actor.state, condition, 1)
            with patch("scenes.battle.random.randint", return_value=0):
                scene._queue_monster_counter(0)
            self.assertEqual(scene.pending_monster_counters, [])

    def test_new_status_or_left_hand_kill_cancels_queued_reaction(self):
        for condition in ("sleeping", "confused", "stunned", "dead"):
            scene, actor = self.scene()
            scene.pending_monster_counters = [(0, 0)]
            if condition == "dead":
                actor.state.defeat()
            else:
                setattr(actor.state, condition, 1)
            self.assertFalse(scene._begin_pending_monster_counter())

    def test_counter_blinks_then_attacks_original_attacker_without_turn_cost(self):
        scene, actor = self.scene()
        scene.pending_monster_counters = [(0, 0)]
        before = scene._timeline_order
        actor.state.poisoned = True
        actor.state.silenced = 3
        hp = actor.state.hp
        scene._begin_standard_monster_attack = Mock()
        self.assertTrue(scene._begin_pending_monster_counter())
        for _ in range(MONSTER_BLINK_FRAME_COUNT - 1):
            scene._update_monster_counter()
        scene._begin_standard_monster_attack.assert_not_called()
        scene._update_monster_counter()
        scene._begin_standard_monster_attack.assert_called_once_with(actor, target_indexes=(0,))
        scene._show_monster_action_message.assert_called_once_with("battle.monster.counter")
        scene.progression.record_enemy_action.assert_called_once_with(0)
        self.assertIs(scene._timeline_order, before)
        self.assertEqual(actor.state.hp, hp)
        self.assertEqual(actor.state.silenced, 3)

    def test_lethal_counter_removes_original_actor_without_spending_next_turn(self):
        scene, actor = self.scene()
        scene.party[0].hp = 1
        scene.monster_counter_actor_index = 0
        scene.monster_counter_target_index = 0
        scene.monster_attack_target_index = 0
        scene.monster_attack_damage = 999
        scene.monster_attack_damage_applied = False
        scene.monster_attack_additional_effects = ()
        scene._begin_defeat_message = Mock()
        scene._finish_monster_attack()
        self.assertEqual(scene.party[0].hp, 0)
        self.assertTrue(scene.counter_defeated_turn_actor)
        scene._begin_defeat_message.assert_not_called()
        scene._complete_current_turn.assert_called_once_with()
        scene.party_target_cursor = None
        scene.target_cursor = Mock()
        scene.command_cursor = Mock()
        scene.command_window = Mock()
        scene.command_guide_window = Mock()
        scene._close_spell_windows = Mock()
        scene._refresh_party_text_colors = Mock()
        scene._start_timeline_animation = Mock()
        enemy_gauge = scene._timeline_order.entries[1].gauge
        BattleScene._complete_current_turn(scene)
        scene._start_timeline_animation.assert_not_called()
        self.assertNotIn(scene.party_visuals[0], scene.timeline_advance.after.actors)
        self.assertIn(actor, scene.timeline_advance.after.actors)
        self.assertEqual(scene._timeline_order.entries[1].gauge, enemy_gauge)

    def test_counter_can_wake_from_sleep_but_stun_from_attack_cancels_it(self):
        scene, actor = self.scene()
        actor.state.sleeping = 2
        actor.state.take_damage(1)
        with patch("scenes.battle.random.randint", return_value=0):
            scene._queue_monster_counter(0)
        self.assertEqual(scene.pending_monster_counters, [(0, 0)])
        actor.state.apply_stun()
        self.assertFalse(scene._begin_pending_monster_counter())


class CounterForecastTest(AutoBattleFixtures, unittest.TestCase):
    def test_counter_uses_same_rules_and_does_not_spend_defender_gauge(self):
        ally = replace(self.specs[0], hp=100, max_hp=100)
        enemy = self.enemy(attack=10, hp=1000, max_hp=1000,
                           special_actions=(MonsterSpecialAction.COUNTER,))
        forecast = BattleForecast(self.snapshot(ally, enemy), 0)
        forecast.roll = lambda *args: 0.0
        before = forecast.order
        forecast.physical(forecast.actors[0], AutoAction(BattleCommand.ATTACK, (5,)))
        self.assertLess(forecast.actors[0].hp, 100)
        self.assertIs(forecast.order, before)
        self.assertEqual(forecast.turns[5], 0)

    def test_rear_defender_promoted_by_previous_iai_target_can_counter(self):
        ally = replace(self.specs[0], hp=100, max_hp=100)
        front = self.enemy(hp=1, max_hp=1)
        rear = self.enemy(number=6, front=False, attack=10, hp=1000, max_hp=1000,
                          special_actions=(MonsterSpecialAction.COUNTER,))
        forecast = BattleForecast(self.snapshot(ally, front, rear), 0)
        forecast.roll = lambda *args: 0.0
        forecast.physical(forecast.actors[0], AutoAction(BattleCommand.ATTACK, (5, 6)))
        self.assertFalse(forecast.actors[5].is_alive)
        self.assertTrue(forecast.actors[6].front)
        self.assertLess(forecast.actors[0].hp, 100)


if __name__ == "__main__":
    unittest.main()
