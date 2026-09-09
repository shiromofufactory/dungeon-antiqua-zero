from __future__ import annotations

import unittest

from app.battle_magic import (
    DA2_DEFAULT_ITEM_SPELL_ABILITY,
    member_spell_ability,
    resolve_healing,
)


class MemberSpellAbilityTest(unittest.TestCase):
    def test_uses_da2_level_adjustment_with_zeros_magic_stat(self) -> None:
        self.assertEqual(
            member_spell_ability(magic=20, internal_level=49),
            40,
        )


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
