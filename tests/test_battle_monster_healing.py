from __future__ import annotations

import unittest
from unittest.mock import Mock

from tools._bootstrap import APP_ROOT  # noqa: F401 - add app to sys.path
from auto_battle_model import AutoBattleObservations
from monster import MonsterBattleState, MonsterCombatStats
from resistance import ResistanceType
from scenes.battle import BattleMonster, BattleScene


class MonsterTurnHealingTest(unittest.TestCase):
    def make_scene(self, *, healing=1, hp=10, poisoned=False, weak=False):
        monster = BattleMonster(
            key="healer", names={}, image_id="0", width=64, height=64,
            icon_x=0, icon_y=0, is_front_row=True, agility=10,
            state=MonsterBattleState(max_hp=120, hp=hp, poisoned=poisoned, sleeping=2),
            combat_stats=MonsterCombatStats(0, 0, 0, 0, healing=healing),
            weaknesses=frozenset((ResistanceType.POISON,)) if weak else frozenset(),
        )
        scene = BattleScene.__new__(BattleScene)
        scene.monsters = (monster,)
        scene.spell_damage_popups = []
        scene.healing_popups = []
        scene.auto_battle_observations = AutoBattleObservations()
        scene._monster_base_position = Mock(return_value=(10, 20))
        scene._monster_draw_x = Mock(return_value=10)
        scene._begin_monster_death = Mock()
        return scene, monster

    def test_recovers_before_action_without_waking_and_shows_recovery(self):
        scene, monster = self.make_scene()
        self.assertFalse(scene._apply_turn_start_hp_change(monster))
        self.assertEqual(monster.state.hp, 18)
        self.assertEqual(monster.state.sleeping, 2)
        popup = scene.healing_popups[0]
        self.assertEqual((popup.x, popup.y, popup.amount), (42, 76, 8))
        self.assertEqual(scene.spell_damage_popups, [])
        self.assertEqual(scene.auto_battle_observations.enemy_net_damage[0], -8)

    def test_cap_limits_observed_recovery_but_not_displayed_number(self):
        scene, monster = self.make_scene(hp=119)
        scene._apply_turn_start_hp_change(monster)
        self.assertEqual(monster.state.hp, 120)
        self.assertEqual(scene.healing_popups[0].amount, 8)
        self.assertEqual(scene.auto_battle_observations.enemy_net_damage[0], -1)

    def test_poison_and_recovery_cancel_without_popups(self):
        scene, monster = self.make_scene(poisoned=True)
        scene._apply_turn_start_hp_change(monster)
        self.assertEqual(monster.state.hp, 10)
        self.assertEqual(scene.healing_popups, [])
        self.assertEqual(scene.spell_damage_popups, [])
        self.assertEqual(scene.auto_battle_observations.enemy_net_damage, {})

    def test_poison_weakness_still_deals_net_damage_without_waking(self):
        scene, monster = self.make_scene(hp=40, poisoned=True, weak=True)
        scene._apply_turn_start_hp_change(monster)
        self.assertEqual(monster.state.hp, 33)
        self.assertEqual(monster.state.sleeping, 2)
        self.assertEqual(scene.spell_damage_popups[0].damage, 7)
        self.assertEqual(scene.auto_battle_observations.enemy_net_damage[0], 7)

    def test_negative_healing_and_poison_start_death_and_timeline_removal(self):
        scene, monster = self.make_scene(healing=-1, poisoned=True)
        self.assertTrue(scene._apply_turn_start_hp_change(monster))
        self.assertEqual(monster.state.hp, 0)
        self.assertEqual(scene.spell_damage_popups[0].damage, 16)
        scene._begin_monster_death.assert_called_once_with(0, from_timeline_head=True)

    def test_dead_monster_does_not_recover(self):
        scene, monster = self.make_scene(hp=0)
        self.assertFalse(scene._apply_turn_start_hp_change(monster))
        self.assertEqual(monster.state.hp, 0)
        self.assertEqual(scene.healing_popups, [])

    def test_timeline_heals_once_before_sleep_or_stun_skips_the_turn(self):
        for stunned in (False, True):
            with self.subTest(stunned=stunned):
                scene, monster = self.make_scene()
                monster.state.stunned = stunned
                scene.timeline = (monster,)
                scene._remove_defeated_party_from_timeline = Mock()
                scene._party_is_defeated = Mock(return_value=False)
                scene._prune_surprise_pending_party = Mock(return_value=False)
                scene._begin_front_promotion_if_needed = Mock(return_value=False)
                scene.command_cursor = Mock()
                scene.command_window = Mock()
                scene._start_timeline_animation = Mock()

                scene._activate_timeline_head()

                self.assertEqual(monster.state.hp, 18)
                self.assertEqual(len(scene.healing_popups), 1)
                self.assertFalse(monster.state.stunned)
                self.assertEqual(monster.state.sleeping, 2 if stunned else 1)
                scene._start_timeline_animation.assert_called_once_with()

    def test_record_healing_reaches_battle_combat_stats(self):
        from resources import load_record_array

        record = {**load_record_array("monsters.json")[0], "healing": 2}
        monster = BattleMonster.from_record(record, is_front_row=True)
        self.assertEqual(monster.combat_stats.healing, 2)
