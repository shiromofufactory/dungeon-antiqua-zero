from __future__ import annotations

import unittest

from app.battle_physical import (
    member_physical_attack,
    resolve_physical_additional_effect,
    resolve_physical_attack,
)
from app.item import AdditionalEffect


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

    def test_attack_from_hiding_uses_da2_ambush_advantage(self) -> None:
        result = resolve_physical_attack(
            attack=100,
            hit=80,
            agility=20,
            target_defense=0,
            target_evasion=100,
            hit_roll=99,
            attacker_hidden=True,
            critical_roll=17,
        )

        self.assertTrue(result.hit)
        self.assertEqual(result.adjusted_hit, 180.0)
        self.assertEqual(result.hit_value, 81.0)
        self.assertEqual(result.damage, 225)
        self.assertEqual(result.critical_rate, 18.0)
        self.assertTrue(result.critical)

    def test_hiding_and_incapacitation_share_one_critical_rate_unit(self) -> None:
        result = resolve_physical_attack(
            attack=100,
            hit=100,
            agility=20,
            target_defense=0,
            target_evasion=0,
            hit_roll=0,
            target_incapacitated=True,
            attacker_hidden=True,
            critical_roll=20,
        )

        self.assertEqual(result.critical_rate, 20.0)
        self.assertFalse(result.critical)

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

    def test_effective_weapon_adds_sixty_hit_value_and_guarantees_critical(
        self,
    ) -> None:
        result = resolve_physical_attack(
            attack=100,
            hit=100,
            agility=20,
            target_defense=40,
            target_evasion=0,
            hit_roll=0,
            weapon_effective=True,
        )

        self.assertTrue(result.hit)
        self.assertEqual(result.hit_value, 160.0)
        self.assertEqual(result.critical_rate, 100.0)
        self.assertTrue(result.critical)
        self.assertEqual(result.damage, 173)

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

    def test_defending_miss_keeps_critical_for_additional_effect_check(
        self,
    ) -> None:
        result = resolve_physical_attack(
            attack=100,
            hit=100,
            agility=20,
            target_defense=0,
            target_evasion=0,
            hit_roll=76,
            target_defending=True,
            attacker_has_power_hit=True,
            critical_roll=0,
        )

        self.assertEqual(result.hit_value, 24.0)
        self.assertFalse(result.hit)
        self.assertEqual(result.damage, 0)
        self.assertTrue(result.critical)

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


class ResolvePhysicalAdditionalEffectTest(unittest.TestCase):
    def test_effective_weapon_adds_one_activation_point(self) -> None:
        result = resolve_physical_additional_effect(
            effect=AdditionalEffect.POISON,
            adjusted_hit=100,
            effect_roll=99,
            target_is_member=False,
            weapon_effective=True,
            critical=True,
        )

        self.assertEqual(result.activation_points, 4)
        self.assertTrue(result.success)

    def test_attack_from_hiding_adds_one_activation_point(self) -> None:
        result = resolve_physical_additional_effect(
            effect=AdditionalEffect.POISON,
            adjusted_hit=100,
            effect_roll=99,
            target_is_member=False,
            attacker_hidden=True,
        )

        self.assertEqual(result.activation_points, 3)

    def test_ordinary_status_uses_monster_rate_and_adjusted_hit(self) -> None:
        result = resolve_physical_additional_effect(
            effect=AdditionalEffect.POISON,
            adjusted_hit=115,
            effect_roll=34,
            target_is_member=False,
        )

        self.assertEqual(result.activation_points, 2)
        self.assertEqual(result.success_rate, 34.5)
        self.assertTrue(result.success)

    def test_boss_halves_ordinary_status_rate(self) -> None:
        result = resolve_physical_additional_effect(
            effect=AdditionalEffect.STUN,
            adjusted_hit=115,
            effect_roll=17,
            target_is_member=False,
            target_is_boss=True,
        )

        self.assertEqual(result.activation_points, 1)
        self.assertEqual(result.success_rate, 17.25)
        self.assertTrue(result.success)

    def test_boss_does_not_halve_da2_defense_down_rate(self) -> None:
        result = resolve_physical_additional_effect(
            effect=AdditionalEffect.DEFENSE_DOWN,
            adjusted_hit=115,
            effect_roll=34,
            target_is_member=False,
            target_is_boss=True,
        )

        self.assertEqual(result.activation_points, 1)
        self.assertEqual(result.success_rate, 34.5)
        self.assertTrue(result.success)

    def test_stun_does_not_use_da2_pinshot_guarantee(self) -> None:
        result = resolve_physical_additional_effect(
            effect=AdditionalEffect.STUN,
            adjusted_hit=100,
            effect_roll=30,
            target_is_member=False,
        )

        self.assertEqual(result.success_rate, 30)
        self.assertFalse(result.success)

    def test_monsters_cannot_be_paralyzed(self) -> None:
        result = resolve_physical_additional_effect(
            effect=AdditionalEffect.PARALIZE,
            adjusted_hit=999,
            effect_roll=0,
            target_is_member=False,
            target_is_weak=True,
            critical=True,
        )

        self.assertEqual(result.activation_points, 0)
        self.assertEqual(result.success_rate, 0)
        self.assertFalse(result.success)

    def test_member_target_uses_twelve_percent_status_rate(self) -> None:
        result = resolve_physical_additional_effect(
            effect=AdditionalEffect.PARALIZE,
            adjusted_hit=100,
            effect_roll=11,
            target_is_member=True,
        )

        self.assertEqual(result.success_rate, 12)
        self.assertTrue(result.success)

    def test_resistance_and_defense_keep_da2_critical_point_behavior(self) -> None:
        resistant = resolve_physical_additional_effect(
            effect=AdditionalEffect.SLEEP,
            adjusted_hit=100,
            effect_roll=99,
            target_is_member=True,
            target_is_resistant=True,
            critical=True,
        )
        defending = resolve_physical_additional_effect(
            effect=AdditionalEffect.STUN,
            adjusted_hit=100,
            effect_roll=99,
            target_is_member=True,
            target_defending=True,
            critical=True,
        )

        self.assertEqual(resistant.activation_points, 1)
        self.assertTrue(resistant.success)
        self.assertEqual(defending.activation_points, 1)
        self.assertTrue(defending.success)

    def test_instant_death_uses_lower_rate_and_boss_point_penalty(self) -> None:
        ordinary = resolve_physical_additional_effect(
            effect=AdditionalEffect.DEATH,
            adjusted_hit=130,
            effect_roll=12,
            target_is_member=False,
        )
        boss = resolve_physical_additional_effect(
            effect=AdditionalEffect.DEATH,
            adjusted_hit=130,
            effect_roll=0,
            target_is_member=False,
            target_is_boss=True,
            target_is_weak=True,
            critical=True,
        )

        self.assertEqual(ordinary.success_rate, 13)
        self.assertTrue(ordinary.success)
        self.assertLessEqual(boss.activation_points, 0)
        self.assertFalse(boss.success)

    def test_lethal_and_weapon_death_keep_da2_stacked_point(self) -> None:
        result = resolve_physical_additional_effect(
            effect=AdditionalEffect.DEATH,
            adjusted_hit=100,
            effect_roll=9,
            target_is_member=False,
            target_is_resistant=True,
            stacked_death=True,
        )

        self.assertEqual(result.activation_points, 1)
        self.assertTrue(result.success)


if __name__ == "__main__":
    unittest.main()
