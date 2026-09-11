from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.monster import (
    MonsterBattleState,
    MonsterCombatStats,
    MonsterDataError,
    promote_rear_monsters_if_front_empty,
)


class MonsterCombatStatsTest(unittest.TestCase):
    def test_required_values_are_loaded_without_deriving_evasion(self) -> None:
        stats = MonsterCombatStats.from_record(
            {
                "attack": 18,
                "hit": 95,
                "defense": 7,
                "evasion": 12,
                "resistance": 23,
                "agi": 99,
            }
        )

        self.assertEqual(stats.attack, 18)
        self.assertEqual(stats.hit, 95)
        self.assertEqual(stats.defense, 7)
        self.assertEqual(stats.evasion, 12)
        self.assertEqual(stats.spell_resistance, 23)

    def test_values_must_be_non_negative_integers(self) -> None:
        valid = {
            "attack": 1,
            "hit": 100,
            "defense": 0,
            "evasion": 0,
            "resistance": 0,
        }
        for field_name in valid:
            for value in (None, True, -1, 1.5, "1"):
                with self.subTest(field=field_name, value=value):
                    record = {**valid, field_name: value}
                    with self.assertRaises(MonsterDataError):
                        MonsterCombatStats.from_record(record)


class MonsterBattleStateTest(unittest.TestCase):
    def test_mhp_initializes_current_and_max_hp(self) -> None:
        state = MonsterBattleState.from_record({"mhp": 12})

        self.assertEqual(state.max_hp, 12)
        self.assertEqual(state.hp, 12)
        self.assertTrue(state.is_alive)

    def test_damage_clamps_at_zero_and_zero_hp_is_dead(self) -> None:
        state = MonsterBattleState.from_record({"mhp": 2})

        self.assertEqual(state.take_damage(1), 1)
        self.assertEqual(state.hp, 1)
        self.assertEqual(state.take_damage(99), 1)
        self.assertEqual(state.hp, 0)
        self.assertFalse(state.is_alive)

    def test_sleep_does_not_shorten_and_positive_damage_wakes_the_monster(self) -> None:
        state = MonsterBattleState(max_hp=10)

        state.apply_sleep(3)
        state.apply_sleep(2)
        self.assertEqual(state.sleeping, 3)
        self.assertTrue(state.elapse_sleep_turn())
        self.assertEqual(state.sleeping, 2)
        state.take_damage(1)

        self.assertEqual(state.sleeping, 0)
        self.assertFalse(state.elapse_sleep_turn())

    def test_defeat_and_restore_manage_mock_battle_lifecycle(self) -> None:
        state = MonsterBattleState.from_record({"mhp": 7})
        state.speed_modifier = -1

        state.defeat()
        self.assertEqual(state.hp, 0)
        state.restore()
        self.assertEqual(state.hp, 7)
        self.assertEqual(state.sleeping, 0)
        self.assertEqual(state.speed_modifier, 0)

    def test_slow_cancels_haste_then_applies_once(self) -> None:
        state = MonsterBattleState(max_hp=10, speed_modifier=2)

        self.assertTrue(state.apply_slow())
        self.assertEqual(state.speed_modifier, 0)
        self.assertTrue(state.apply_slow())
        self.assertEqual(state.speed_modifier, -1)
        self.assertFalse(state.apply_slow())

    def test_mhp_must_be_a_positive_integer(self) -> None:
        for value in (None, True, 0, -1, 1.5, "2"):
            with self.subTest(value=value):
                with self.assertRaises(MonsterDataError):
                    MonsterBattleState.from_record({"mhp": value})

    def test_living_rear_monsters_advance_when_no_living_front_remains(self) -> None:
        dead_front = SimpleNamespace(is_alive=False, is_front_row=True)
        living_rear = SimpleNamespace(is_alive=True, is_front_row=False)
        dead_rear = SimpleNamespace(is_alive=False, is_front_row=False)

        self.assertTrue(
            promote_rear_monsters_if_front_empty(
                (dead_front, living_rear, dead_rear),
            )
        )
        self.assertTrue(living_rear.is_front_row)
        self.assertFalse(dead_rear.is_front_row)

    def test_rear_monsters_stay_back_while_a_front_monster_lives(self) -> None:
        living_front = SimpleNamespace(is_alive=True, is_front_row=True)
        living_rear = SimpleNamespace(is_alive=True, is_front_row=False)

        self.assertFalse(
            promote_rear_monsters_if_front_empty((living_front, living_rear))
        )
        self.assertFalse(living_rear.is_front_row)


if __name__ == "__main__":
    unittest.main()
