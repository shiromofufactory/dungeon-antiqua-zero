from __future__ import annotations

import unittest
from dataclasses import replace
from unittest.mock import Mock, patch

from tools._bootstrap import APP_ROOT
from tools.screen_mocks._fixtures import load_mock_items, load_mock_skills
from battle_physical import counter_attack_succeeds
from battle_timeline import TimelineEntry, TimelineOrder
from item import AdditionalEffect
from localization import Localizer
from monster import MonsterSpecialAction
from monster_ai import MonsterAction, monster_action_candidates
from scenes.battle import (
    BattleAttackPresentation, BattleAttackStrike, BattleCharacter,
    BattlePhase, BattleScene, MONSTER_BLINK_FRAME_COUNT,
)
from state import Language
from text_catalog import TextCatalog
from tests import test_battle_poison_breath as poison_tests
from tests.test_auto_battle import AutoBattleFixtures
from auto_battle_simulation import BattleForecast
from auto_battle_model import AutoAction, AutoCombatant
from battle_commands import BattleCommand
from member import EquipmentSlot, FormationRow


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

    def party_counter_scene(self):
        scene, actor = self.scene()
        scene.party[0].skills.append(load_mock_skills()["Retaliate"])
        scene._timeline_order = TimelineOrder((
            TimelineEntry(actor, actor.agility, 64),
            TimelineEntry(scene.party_visuals[0], 10, 30),
            TimelineEntry(scene.party_visuals[1], 10, 20),
        ))
        scene.timeline = scene._timeline_order.actors
        scene.active_party_index = None
        scene.selected_command = None
        scene.monster_action = MonsterAction.ATTACK
        scene.monster_attack_target_index = 0
        scene.monster_attack_damage = 0
        scene.monster_attack_critical = False
        scene.monster_attack_additional_effects = ()
        scene.monster_attack_animation_frame = 0
        scene.target_cursor = Mock()
        scene.command_cursor = Mock()
        scene.command_window = Mock()
        scene._refresh_monster_name_colors = Mock()
        scene._queue_monster_counter = Mock(wraps=scene._queue_monster_counter)
        scene._show_battle_popup = Mock()
        scene._start_timeline_animation = Mock()
        scene.texts = TextCatalog.from_json(APP_ROOT / "data" / "texts.json")
        scene.localizer = Localizer(Language.JAPANESE)
        scene._clear_action_motion_state()
        return scene, actor

    def test_party_counter_uses_actual_hit_recipient_and_keeps_enemy_turn(self):
        scene, actor = self.party_counter_scene()
        scene.protected_party_index = 1
        scene.covering_party_index = 0
        scene.defending_party_indexes.add(0)
        member = scene.party[0]
        member.poisoned = True
        member.silenced = 3
        before = scene._timeline_order

        with patch("scenes.battle.random.randint", return_value=0), patch("scenes.battle.play_se"):
            scene._finish_monster_attack()
            self.assertIs(scene.phase, BattlePhase.ATTACK_PRESENTATION)
            self.assertTrue(scene.attack_presentation.is_counter)
            self.assertEqual(scene.action_party_index, 0)
            self.assertIsNone(scene.active_party_index)
            self.assertEqual(scene.attack_presentation.target_index, 0)
            self.assertIs(scene._timeline_order, before)
            scene._show_battle_popup.assert_called_once()
            scene._begin_monster_death = Mock()
            actor.state.hp = 1
            for _ in range(100):
                scene._update_action_motion()
                scene._update_attack_presentation()
                if scene.attack_presentation is None:
                    break

        self.assertEqual(actor.state.hp, 0)
        scene._begin_monster_death.assert_called_once_with(0, from_timeline_head=True)
        scene._queue_monster_counter.assert_not_called()
        self.assertIs(scene._timeline_order, before)
        self.assertIsNone(scene.action_party_index)
        self.assertTrue(member.poisoned)
        self.assertEqual(member.silenced, 3)
        self.assertIn(0, scene.defending_party_indexes)
        scene.progression.record_weapon_action.assert_called_once()

    def test_party_counter_uses_da2_reach_and_actionability(self):
        for condition in ("surprised", "sleeping", "paralyzed", "stunned", "confused", "dead", "rear", "long_reach"):
            with self.subTest(condition=condition):
                scene, actor = self.party_counter_scene()
                member = scene.party[0]
                if condition == "surprised":
                    scene.surprise_active = True
                elif condition == "dead":
                    member.defeat()
                elif condition in ("rear", "long_reach"):
                    actor.is_front_row = False
                    member.formation_row = FormationRow.BACK
                    if condition == "long_reach":
                        weapon = member.equipment.weapon_at(EquipmentSlot.RIGHT)
                        member.equipment = member.equipment.replaced({
                            EquipmentSlot.RIGHT: replace(weapon, reach=2),
                        })
                else:
                    setattr(member, condition, True)
                with patch("scenes.battle.random.randint", return_value=0):
                    scene._queue_party_counter(0)
                self.assertEqual(getattr(scene, "pending_party_counter_index", None),
                                 0 if condition == "long_reach" else None)

    def test_second_strike_can_cancel_reserved_party_counter(self):
        scene, actor = self.party_counter_scene()
        actor.special_actions = (MonsterSpecialAction.DOUBLE_ATTACK,)
        scene._begin_standard_monster_attack = Mock()
        with patch("scenes.battle.random.randint", return_value=0):
            scene._finish_monster_attack()
            self.assertEqual(scene.pending_party_counter_index, 0)
            scene._begin_standard_monster_attack.assert_called_once()
            scene.monster_attack_target_index = 0
            scene.monster_attack_damage = 1
            scene.monster_attack_additional_effects = (AdditionalEffect.STUN,)
            scene._finish_monster_attack()
        self.assertTrue(scene.party[0].stunned)
        self.assertIsNone(scene.pending_party_counter_index)
        scene._start_timeline_animation.assert_called_once_with()
        scene._show_battle_popup.assert_not_called()


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

    def test_party_counter_forecast_damages_original_attacker_without_using_own_turn(self):
        member = self.party[0]
        with patch.object(member, "skills", [load_mock_skills()["Retaliate"]]):
            defender = AutoCombatant.from_member(member, 0, front=True, spells=())
        self.assertIn("Retaliate", defender.skills)
        defender = replace(defender, hp=500, max_hp=500, silenced=2, defending=True)
        attacker = self.enemy(
            hp=1, max_hp=1, hit=0,
            special_actions=(MonsterSpecialAction.COUNTER,),
        )
        forecast = BattleForecast(self.snapshot(attacker, defender, active=5), 0)
        forecast.roll = lambda *_args: 0.0
        forecast.enemy_turn(forecast.actors[5])
        self.assertEqual(forecast.actors[5].hp, 0)
        self.assertEqual(forecast.actors[0].hp, 500)
        self.assertTrue(forecast.actors[0].defending)
        self.assertEqual(forecast.actors[0].silenced, 2)
        self.assertEqual(forecast.turns[0], 0)
        self.assertEqual(forecast.order.actors, (0,))


if __name__ == "__main__":
    unittest.main()
