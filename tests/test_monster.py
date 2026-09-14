from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.monster import (
    MonsterDefinition,
    MonsterBattleState,
    MonsterCombatStats,
    MonsterDataError,
    promote_rear_monsters_if_front_empty,
)
from app.resources import load_record_array


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


class MonsterSpellDefinitionTest(unittest.TestCase):
    def test_reads_magic_intelligence_and_structured_spell_keys(self) -> None:
        records = {
            record["name_en"]: record
            for record in load_record_array("monsters.json")
        }

        goblin = MonsterDefinition.from_record(records["Goblin"])
        treant = MonsterDefinition.from_record(records["Treant"])

        self.assertEqual((goblin.magic, goblin.intelligence), (0, 0))
        self.assertEqual(goblin.spell_keys, ("SLOW",))
        self.assertEqual((treant.magic, treant.intelligence), (15, 0))
        self.assertEqual(treant.spell_keys, ("SLEEP",))
        self.assertEqual(treant.treasure_rate, 16)


class MonsterBattleStateTest(unittest.TestCase):
    def test_master_values_initialize_current_and_max_hp_mp(self) -> None:
        state = MonsterBattleState.from_record({"mhp": 12, "mmp": 5})

        self.assertEqual(state.max_hp, 12)
        self.assertEqual(state.hp, 12)
        self.assertEqual(state.max_mp, 5)
        self.assertEqual(state.mp, 5)
        self.assertTrue(state.is_alive)

    def test_spend_mp_rejects_shortage_without_changing_current_mp(self) -> None:
        state = MonsterBattleState(max_hp=10, max_mp=3)

        self.assertTrue(state.spend_mp(2))
        self.assertEqual(state.mp, 1)
        self.assertFalse(state.spend_mp(2))
        self.assertEqual(state.mp, 1)

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

    def test_stun_skips_exactly_one_future_action(self) -> None:
        state = MonsterBattleState(max_hp=10)

        self.assertTrue(state.apply_stun())
        self.assertFalse(state.apply_stun())
        self.assertTrue(state.consume_stun())
        self.assertFalse(state.consume_stun())

    def test_silence_does_not_shorten_and_elapses_by_monster_turn(self) -> None:
        state = MonsterBattleState(max_hp=10)

        self.assertTrue(state.apply_silence(6))
        self.assertFalse(state.apply_silence(4))
        self.assertEqual(state.silenced, 6)
        self.assertTrue(state.elapse_silence_turn())
        self.assertEqual(state.silenced, 5)

        state.defeat()
        self.assertEqual(state.silenced, 0)

    def test_defense_down_applies_once_with_da2_formula(self) -> None:
        state = MonsterBattleState(max_hp=10)

        self.assertEqual(state.modified_defense(20), 20)
        self.assertTrue(state.apply_defense_down())
        self.assertEqual(state.defense_modifier, -1)
        self.assertEqual(state.modified_defense(20), 5)
        self.assertEqual(state.modified_defense(5), 0)
        self.assertFalse(state.apply_defense_down())

    def test_poison_damage_preserves_sleep_and_restore_clears_poison(self) -> None:
        state = MonsterBattleState(max_hp=10, poisoned=True, sleeping=2)

        self.assertEqual(state.take_poison_damage(1), 1)
        self.assertEqual(state.hp, 9)
        self.assertEqual(state.sleeping, 2)
        state.restore()

        self.assertFalse(state.poisoned)
        self.assertFalse(state.stunned)
        self.assertEqual(state.defense_modifier, 0)
        self.assertEqual(state.hp, 10)

    def test_defeat_and_restore_manage_mock_battle_lifecycle(self) -> None:
        state = MonsterBattleState.from_record({"mhp": 7, "mmp": 4})
        state.speed_modifier = -1
        state.spend_mp(3)

        state.defeat()
        self.assertEqual(state.hp, 0)
        state.restore()
        self.assertEqual(state.hp, 7)
        self.assertEqual(state.sleeping, 0)
        self.assertEqual(state.speed_modifier, 0)
        self.assertEqual(state.mp, 4)

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
