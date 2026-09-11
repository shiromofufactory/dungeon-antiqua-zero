from __future__ import annotations

import unittest

from app.battle_physical import member_physical_attack, resolve_physical_attack


class MemberPhysicalAttackTest(unittest.TestCase):
    def test_uses_weapon_strength_weapon_level_and_internal_level(self) -> None:
        self.assertEqual(
            member_physical_attack(
                weapon_attack=40,
                strength=25,
                weapon_level=8,
                internal_level=50,
            ),
            340,
        )

    def test_uses_already_adjusted_two_handed_weapon_attack(self) -> None:
        self.assertEqual(
            member_physical_attack(
                weapon_attack=60,
                strength=25,
                weapon_level=8,
                internal_level=50,
            ),
            510,
        )


class ResolvePhysicalAttackTest(unittest.TestCase):
    def test_matches_da2_hit_and_damage_calculation(self) -> None:
        result = resolve_physical_attack(
            attack=100,
            hit=90,
            agility=25,
            target_defense=10,
            target_evasion=20,
            hit_roll=40,
        )

        self.assertTrue(result.hit)
        self.assertEqual(result.adjusted_hit, 112.5)
        self.assertEqual(result.hit_value, 50.0)
        self.assertEqual(result.damage, 81)

    def test_negative_hit_value_is_a_miss(self) -> None:
        result = resolve_physical_attack(
            attack=100,
            hit=90,
            agility=25,
            target_defense=10,
            target_evasion=20,
            hit_roll=91,
        )

        self.assertFalse(result.hit)
        self.assertEqual(result.damage, 0)
        self.assertEqual(result.hit_value, -1.0)

    def test_zero_hit_value_still_hits_like_da2(self) -> None:
        result = resolve_physical_attack(
            attack=20,
            hit=100,
            agility=5,
            target_defense=0,
            target_evasion=20,
            hit_roll=60,
        )

        self.assertTrue(result.hit)
        self.assertEqual(result.adjusted_hit, 75.0)
        self.assertEqual(result.hit_value, 0.0)
        self.assertEqual(result.damage, 16)

    def test_hit_value_bonus_is_added_after_evasion_and_random_roll(self) -> None:
        result = resolve_physical_attack(
            attack=100,
            hit=0,
            agility=20,
            target_defense=0,
            target_evasion=100,
            hit_roll=99,
            hit_value_bonus=100,
        )

        self.assertTrue(result.hit)
        self.assertEqual(result.hit_value, 1.0)
        self.assertEqual(result.damage, 81)

    def test_unable_to_evade_matches_da2_split_vulnerability(self) -> None:
        result = resolve_physical_attack(
            attack=100,
            hit=0,
            agility=20,
            target_defense=0,
            target_evasion=100,
            hit_roll=99,
            target_unable_to_evade=True,
        )

        self.assertTrue(result.hit)
        self.assertEqual(result.adjusted_hit, 0.0)
        self.assertEqual(result.hit_value, 1.0)
        self.assertEqual(result.damage, 81)

    def test_power_hit_uses_da2_rate_and_critical_damage(self) -> None:
        result = resolve_physical_attack(
            attack=100,
            hit=100,
            agility=20,
            target_defense=40,
            target_evasion=0,
            hit_roll=0,
            attacker_has_power_hit=True,
            critical_roll=9,
        )

        self.assertTrue(result.hit)
        self.assertTrue(result.critical)
        self.assertEqual(result.critical_rate, 10.0)
        # DA2 doubles attack and skips the flat defense subtraction, while
        # retaining the final defense-rate cut.
        self.assertEqual(result.damage, 144)

    def test_da2_critical_boundary_is_strictly_greater_than_roll(self) -> None:
        result = resolve_physical_attack(
            attack=100,
            hit=100,
            agility=20,
            target_defense=40,
            target_evasion=0,
            hit_roll=0,
            attacker_has_power_hit=True,
            critical_roll=10,
        )

        self.assertFalse(result.critical)
        self.assertEqual(result.critical_rate, 10.0)
        self.assertEqual(result.damage, 44)

    def test_incapacitated_target_adds_accuracy_and_enables_critical(self) -> None:
        result = resolve_physical_attack(
            attack=100,
            hit=100,
            agility=20,
            target_defense=0,
            target_evasion=100,
            hit_roll=99,
            target_incapacitated=True,
            critical_roll=19,
        )

        self.assertEqual(result.adjusted_hit, 200.0)
        self.assertEqual(result.hit_value, 101.0)
        self.assertEqual(result.critical_rate, 20.0)
        self.assertTrue(result.critical)

    def test_all_critical_sources_and_two_handed_rate_stack_like_da2(self) -> None:
        result = resolve_physical_attack(
            attack=100,
            hit=100,
            agility=20,
            target_defense=0,
            target_evasion=0,
            hit_roll=0,
            target_incapacitated=True,
            attacker_has_power_hit=True,
            weapon_has_power_hit=True,
            critical_rate_scale=1.5,
            critical_roll=89,
        )

        self.assertAlmostEqual(result.critical_rate, 90.0)
        self.assertTrue(result.critical)

    def test_attack_without_critical_condition_cannot_critical(self) -> None:
        result = resolve_physical_attack(
            attack=100,
            hit=100,
            agility=20,
            target_defense=0,
            target_evasion=0,
            hit_roll=0,
            critical_roll=0,
        )

        self.assertEqual(result.critical_rate, 0.0)
        self.assertFalse(result.critical)

    def test_defending_avoids_an_attack_below_da2_guard_threshold(self) -> None:
        result = resolve_physical_attack(
            attack=100,
            hit=100,
            agility=20,
            target_defense=0,
            target_evasion=0,
            hit_roll=76,
            target_defending=True,
        )

        self.assertEqual(result.hit_value, 24.0)
        self.assertFalse(result.hit)
        self.assertEqual(result.damage, 0)

    def test_defending_halves_damage_at_da2_guard_threshold(self) -> None:
        result = resolve_physical_attack(
            attack=100,
            hit=100,
            agility=20,
            target_defense=0,
            target_evasion=0,
            hit_roll=75,
            target_defending=True,
        )

        self.assertEqual(result.hit_value, 25.0)
        self.assertTrue(result.hit)
        self.assertEqual(result.damage, 45)


if __name__ == "__main__":
    unittest.main()
