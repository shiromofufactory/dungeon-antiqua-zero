from __future__ import annotations

import unittest

from app.battle_magic import (
    battle_healing_amount,
    DA2_DEFAULT_ITEM_SPELL_ABILITY,
    SpellAffinity,
    member_spell_ability,
    member_spell_modifier,
    poison_tick_damage,
    resolve_healing,
    resolve_spell_damage,
    resolve_status_spell,
    spell_cast_delay,
)
from app.resistance import ResistanceType


class MemberSpellAbilityTest(unittest.TestCase):
    def test_uses_da2_level_adjustment_with_zeros_magic_stat(self) -> None:
        self.assertEqual(
            member_spell_ability(magic=20, internal_level=49),
            40,
        )


class MemberSpellModifierTest(unittest.TestCase):
    def test_combines_magic_spell_level_and_internal_level(self) -> None:
        self.assertEqual(
            member_spell_modifier(
                magic=32,
                spell_level=8,
                internal_level=50,
            ),
            34,
        )


class SpellCastDelayTest(unittest.TestCase):
    def test_school_level_and_equipment_reduce_delay(self) -> None:
        for level, normal, reduced in ((0, 17, 9), (1, 16, 8), (9, 8, 0)):
            with self.subTest(level=level):
                self.assertEqual(spell_cast_delay(spell_level=level), normal)
                self.assertEqual(
                    spell_cast_delay(spell_level=level, reduced_wait=True),
                    reduced,
                )


class ResolveSpellDamageTest(unittest.TestCase):
    def test_uses_zero_damage_formula_at_each_random_bound(self) -> None:
        common = {
            "intensity": 15,
            "spell_modifier": 10,
            "target_spell_defense": 20,
            "attribute": ResistanceType.FIRE,
            "target_weaknesses": frozenset(),
            "target_resistances": frozenset(),
        }

        self.assertEqual(resolve_spell_damage(**common, random_factor=0).damage, 24)
        self.assertEqual(resolve_spell_damage(**common, random_factor=1).damage, 30)

    def test_da2_affinities_multiply_weakness_and_quarter_resistance(self) -> None:
        common = {
            "intensity": 15,
            "spell_modifier": 10,
            "target_spell_defense": 20,
            "attribute": ResistanceType.FIRE,
            "random_factor": 0,
        }
        weak = resolve_spell_damage(
            **common,
            target_weaknesses=frozenset((ResistanceType.FIRE,)),
            target_resistances=frozenset(),
        )
        resist = resolve_spell_damage(
            **common,
            target_weaknesses=frozenset(),
            target_resistances=frozenset((ResistanceType.FIRE,)),
        )

        self.assertEqual((weak.damage, weak.affinity), (96, SpellAffinity.WEAK))
        self.assertEqual(
            (resist.damage, resist.affinity),
            (6, SpellAffinity.RESIST),
        )

    def test_resistance_takes_priority_when_both_affinities_are_registered(self) -> None:
        result = resolve_spell_damage(
            intensity=15,
            spell_modifier=10,
            target_spell_defense=20,
            attribute=ResistanceType.FIRE,
            target_weaknesses=frozenset((ResistanceType.FIRE,)),
            target_resistances=frozenset((ResistanceType.FIRE,)),
            random_factor=0,
        )

        self.assertEqual((result.damage, result.affinity), (6, SpellAffinity.RESIST))

    def test_death_magic_treats_shadow_as_da2_double_weakness(self) -> None:
        result = resolve_spell_damage(
            intensity=15,
            spell_modifier=10,
            target_spell_defense=20,
            attribute=ResistanceType.DEATH,
            target_weaknesses=frozenset(),
            target_resistances=frozenset(),
            target_is_shadow=True,
            random_factor=0,
        )

        self.assertEqual((result.damage, result.affinity), (48, SpellAffinity.WEAK))


class ResolveStatusSpellTest(unittest.TestCase):
    def test_uses_da2_twenty_step_roll_with_the_zero_spell_modifier(self) -> None:
        common = {
            "spell_modifier": 20,
            "rate": 6,
            "target_spell_defense": 12,
            "attribute": ResistanceType.SLEEP,
            "target_weaknesses": frozenset(),
            "target_resistances": frozenset(),
        }

        success = resolve_status_spell(**common, success_roll=9)
        failure = resolve_status_spell(**common, success_roll=10)

        self.assertEqual(success.success_rate, 10)
        self.assertTrue(success.success)
        self.assertFalse(failure.success)

    def test_weakness_adds_ten_to_da2_success_rate(self) -> None:
        result = resolve_status_spell(
            spell_modifier=4,
            rate=1,
            target_spell_defense=20,
            attribute=ResistanceType.SLEEP,
            target_weaknesses=frozenset((ResistanceType.SLEEP,)),
            target_resistances=frozenset(),
            success_roll=10,
        )

        self.assertEqual(result.success_rate, 11)
        self.assertTrue(result.success)
        self.assertIs(result.affinity, SpellAffinity.WEAK)

    def test_resistance_always_fails_and_takes_priority_over_weakness(self) -> None:
        result = resolve_status_spell(
            spell_modifier=100,
            rate=100,
            target_spell_defense=0,
            attribute=ResistanceType.SLEEP,
            target_weaknesses=frozenset((ResistanceType.SLEEP,)),
            target_resistances=frozenset((ResistanceType.SLEEP,)),
            success_roll=0,
        )

        self.assertFalse(result.success)
        self.assertEqual(result.success_rate, 0)
        self.assertIs(result.affinity, SpellAffinity.RESIST)


class PoisonTickDamageTest(unittest.TestCase):
    def test_rounds_up_one_sixteenth_and_doubles_for_poison_weakness(self) -> None:
        self.assertEqual(poison_tick_damage(max_hp=1), 1)
        self.assertEqual(poison_tick_damage(max_hp=17), 2)
        self.assertEqual(poison_tick_damage(max_hp=17, weak_to_poison=True), 3)


class BattleHealingAmountTest(unittest.TestCase):
    def test_rounds_up_one_sixteenth_for_each_recovery_level(self) -> None:
        self.assertEqual(battle_healing_amount(max_hp=1, healing=1), 1)
        self.assertEqual(battle_healing_amount(max_hp=17, healing=1), 2)
        self.assertEqual(battle_healing_amount(max_hp=17, healing=2), 3)

    def test_preserves_negative_healing_as_damage(self) -> None:
        self.assertEqual(battle_healing_amount(max_hp=17, healing=-1), -2)


class ResolveHealingTest(unittest.TestCase):
    def test_matches_da2_heal_formula_at_each_random_bound(self) -> None:
        self.assertEqual(
            resolve_healing(
                intensity=20,
                ability=40,
                current_hp=10,
                max_hp=200,
                random_factor=0.0,
            ).amount,
            65,
        )
        self.assertEqual(
            resolve_healing(
                intensity=20,
                ability=40,
                current_hp=10,
                max_hp=200,
                random_factor=0.5,
            ).amount,
            81,
        )
        self.assertEqual(
            resolve_healing(
                intensity=20,
                ability=40,
                current_hp=10,
                max_hp=200,
                random_factor=1.0,
            ).amount,
            97,
        )

    def test_zero_intensity_fully_heals_and_cures_like_da2_healing3(self) -> None:
        result = resolve_healing(
            intensity=0,
            ability=DA2_DEFAULT_ITEM_SPELL_ABILITY,
            current_hp=23,
            max_hp=100,
            random_factor=0.5,
        )

        self.assertEqual(result.amount, 77)
        self.assertTrue(result.cures_ailments)


if __name__ == "__main__":
    unittest.main()
