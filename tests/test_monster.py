from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.monster import (
    MonsterBattleState,
    MonsterDataError,
    promote_rear_monsters_if_front_empty,
)


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

    def test_defeat_and_restore_manage_mock_battle_lifecycle(self) -> None:
        state = MonsterBattleState.from_record({"mhp": 7})

        state.defeat()
        self.assertEqual(state.hp, 0)
        state.restore()
        self.assertEqual(state.hp, 7)

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
