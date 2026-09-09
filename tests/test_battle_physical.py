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


if __name__ == "__main__":
    unittest.main()
