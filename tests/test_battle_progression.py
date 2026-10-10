from __future__ import annotations

import unittest
from unittest.mock import patch

from tools._bootstrap import APP_ROOT
from tools.screen_mocks._fixtures import load_mock_items

from member import (
    Member,
    ProficiencyKind,
    internal_level_for_experience,
    required_experience_for_level,
)
from state import SaveData
from systems import (
    BattleProgression,
    EnemyProgressionData,
    InventorySystem,
    MonsterRecordSystem,
)


PROFICIENCIES = {kind.value: 0 for kind in ProficiencyKind}


def member_record(key: str, *, level_difference: int = 0) -> dict[str, object]:
    return {
        "name_en": key,
        "name_ja": key,
        "type": "SUB",
        "race": "HUMAN",
        "gender": "MALE",
        "lv_diff": level_difference,
        "base_hp": 40,
        "base_mp": 20,
        "base_str": 20,
        "base_agi": 20,
        "base_mag": 20,
        "face_x": 0,
        "face_y": 0,
        **PROFICIENCIES,
        "eq_sword": 1,
        "sp_mystic": 1,
    }


class ExperienceCurveTest(unittest.TestCase):
    def test_uses_da2_cumulative_thresholds(self) -> None:
        self.assertEqual(required_experience_for_level(17), 2954)
        self.assertEqual(required_experience_for_level(18), 3786)
        self.assertEqual(internal_level_for_experience(3785), 17)
        self.assertEqual(internal_level_for_experience(3786), 18)

    def test_joining_offset_anchors_level_18_at_shared_experience_10(self) -> None:
        member = Member.from_record_at_internal_level(member_record("Alvan"), 18)

        member.set_joining_experience_offset(10)

        self.assertEqual(member.experience_offset, 3776)
        self.assertEqual(member.refresh_internal_level(10), 18)


class BattleProgressionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.items = load_mock_items()
        cls.sword = next(item for item in cls.items.values() if item.subtype == "SWORD")
        cls.other_item = next(
            item for item in cls.items.values() if item.key != cls.sword.key
        )

    def test_enemy_reward_uses_actual_action_count_and_final_floor(self) -> None:
        enemy = EnemyProgressionData(4, 1, 4, 25)
        progression = BattleProgression((enemy,))

        progression.record_enemy_action(0)
        progression.record_enemy_action(0)

        self.assertEqual(enemy.experience(0), 36)
        self.assertEqual(progression.rewards(), (43, 25))

    def test_reinforcement_keeps_earlier_enemy_reward_identity(self) -> None:
        first = EnemyProgressionData(4, 0, 1, 25)
        reinforcement = EnemyProgressionData(2, 0, 1, 10)
        progression = BattleProgression((first,))
        progression.record_enemy_defeat(0)

        self.assertEqual(progression.register_enemy(reinforcement), 1)
        progression.record_enemy_action(1)
        progression.record_enemy_defeat(1)

        self.assertEqual(
            progression.rewards(),
            (first.experience(0) + reinforcement.experience(1), 35),
        )

    def test_escaped_enemy_gives_neither_experience_nor_gold(self) -> None:
        progression = BattleProgression(
            (
                EnemyProgressionData(4, 1, 4, 25),
                EnemyProgressionData(2, 0, 1, 10),
            )
        )
        progression.record_enemy_action(0)
        progression.record_enemy_escape(0)

        self.assertEqual(progression.rewards(), (48, 10))

    def test_only_last_defeated_enemy_can_drop_its_treasure(self) -> None:
        save_data = SaveData()
        inventory = InventorySystem(self.items)
        records = MonsterRecordSystem(save_data)
        member = Member.from_record(member_record("Fighter"))
        progression = BattleProgression(
            (
                EnemyProgressionData(
                    1,
                    1,
                    1,
                    0,
                    "First Enemy",
                    self.sword.key,
                    16,
                ),
                EnemyProgressionData(
                    1,
                    1,
                    1,
                    0,
                    "Last Enemy",
                    self.other_item.key,
                    16,
                ),
            )
        )
        progression.record_enemy_defeat(0)
        progression.record_enemy_defeat(1)

        with patch("systems.battle_progression.random.randrange", return_value=15):
            growth = progression.settle(
                save_data,
                (member,),
                inventory_system=inventory,
                monster_record_system=records,
            )

        self.assertEqual(growth.treasure_drop.monster_key, "Last Enemy")
        self.assertEqual(growth.treasure_drop.item_key, self.other_item.key)
        self.assertEqual(inventory.quantity(self.sword), 0)
        self.assertEqual(inventory.quantity(self.other_item), 1)
        self.assertFalse(records.treasure_was_acquired("First Enemy"))
        self.assertTrue(records.treasure_was_acquired("Last Enemy"))

    def test_simultaneous_defeats_choose_smallest_index_for_treasure(self) -> None:
        save_data = SaveData()
        inventory = InventorySystem(self.items)
        records = MonsterRecordSystem(save_data)
        member = Member.from_record(member_record("Fighter"))
        progression = BattleProgression(
            (
                EnemyProgressionData(
                    1,
                    1,
                    1,
                    0,
                    "Smallest Index Enemy",
                    self.sword.key,
                    16,
                ),
                EnemyProgressionData(
                    1,
                    1,
                    1,
                    0,
                    "Larger Index Enemy",
                    self.other_item.key,
                    16,
                ),
            )
        )

        progression.record_simultaneous_enemy_defeats((1, 0))

        with patch("systems.battle_progression.random.randrange", return_value=15):
            growth = progression.settle(
                save_data,
                (member,),
                inventory_system=inventory,
                monster_record_system=records,
            )

        self.assertEqual(growth.treasure_drop.monster_key, "Smallest Index Enemy")
        self.assertEqual(growth.treasure_drop.item_key, self.sword.key)
        self.assertEqual(inventory.quantity(self.sword), 1)
        self.assertEqual(inventory.quantity(self.other_item), 0)

    def test_treasure_rate_is_a_sixteenth_roll(self) -> None:
        member = Member.from_record(member_record("Fighter"))

        for roll, expected_quantity in ((0, 1), (1, 0)):
            with self.subTest(roll=roll):
                save_data = SaveData()
                inventory = InventorySystem(self.items)
                records = MonsterRecordSystem(save_data)
                progression = BattleProgression(
                    (
                        EnemyProgressionData(
                            1,
                            1,
                            1,
                            0,
                            "Enemy",
                            self.sword.key,
                            1,
                        ),
                    )
                )
                progression.record_enemy_defeat(0)

                with patch(
                    "systems.battle_progression.random.randrange",
                    return_value=roll,
                ):
                    growth = progression.settle(
                        save_data,
                        (member,),
                        inventory_system=inventory,
                        monster_record_system=records,
                    )

                self.assertEqual(inventory.quantity(self.sword), expected_quantity)
                self.assertEqual(
                    growth.treasure_drop is not None,
                    bool(expected_quantity),
                )

    def test_full_inventory_discards_drop_without_recording_it(self) -> None:
        save_data = SaveData()
        inventory = InventorySystem(
            self.items,
            {
                self.sword.key: InventorySystem.stack_limit(self.sword),
            },
        )
        records = MonsterRecordSystem(save_data)
        member = Member.from_record(member_record("Fighter"))
        progression = BattleProgression(
            (
                EnemyProgressionData(
                    1,
                    1,
                    1,
                    0,
                    "Enemy",
                    self.sword.key,
                    16,
                ),
            )
        )
        progression.record_enemy_defeat(0)

        with patch("systems.battle_progression.random.randrange", return_value=0):
            growth = progression.settle(
                save_data,
                (member,),
                inventory_system=inventory,
                monster_record_system=records,
            )

        self.assertIsNone(growth.treasure_drop)
        self.assertEqual(
            inventory.quantity(self.sword),
            InventorySystem.stack_limit(self.sword),
        )
        self.assertFalse(records.treasure_was_acquired("Enemy"))

    def test_repeated_battles_accumulate_experience_in_the_live_save(self) -> None:
        save_data = SaveData(experience=30)
        member = Member.from_record(member_record("Fighter"))

        for _battle in range(3):
            progression = BattleProgression(
                (EnemyProgressionData(5, 4, 4, 0),)
            )
            growth = progression.settle(save_data, (member,))
            self.assertEqual(growth.experience_gained, 15)

        self.assertEqual(save_data.experience, 75)

    def test_weapon_settlement_carries_progress_into_the_next_level(self) -> None:
        member = Member.from_record(member_record("Fighter"))
        member.proficiency(ProficiencyKind.SWORD).progress = 95
        progression = BattleProgression((EnemyProgressionData(4, 0, 1, 0),))

        progression.record_weapon_action(member, (self.sword,), (4,))
        progression.record_weapon_action(member, (self.sword,), (4,))
        progression.record_weapon_action(
            member,
            (self.sword,),
            (4,),
            defeated_enemy_keys=("Coyote",),
            critical=True,
        )
        progression.settle(SaveData(), (member,))

        proficiency = member.proficiency(ProficiencyKind.SWORD)
        self.assertEqual((proficiency.level, proficiency.progress), (2, 1))

    def test_victory_and_escape_cap_weapon_and_spell_growth_but_preserve_npcs(self) -> None:
        for limit in (2, 4):
            for escape in (False, True):
                with self.subTest(limit=limit, escape=escape):
                    member = Member.from_record(member_record("Fighter"))
                    npc = Member.from_record_at_internal_level(member_record("NPC"), 60)
                    kinds = (ProficiencyKind.SWORD, ProficiencyKind.MYSTIC)
                    npc_before = tuple(
                        (npc.proficiency(kind).level, npc.proficiency(kind).progress)
                        for kind in kinds
                    )
                    progression = BattleProgression((EnemyProgressionData(99, 0, 1, 0),))
                    for kind in kinds:
                        member.proficiency(kind).level = limit
                        member.proficiency(kind).progress = 98
                    for actor in (member, npc):
                        progression.record_weapon_action(actor, (self.sword,), (99,))
                        progression.record_spell_use(
                            actor, ProficiencyKind.MYSTIC, (99,), mp_spent=9
                        )
                    settle = progression.settle_escape if escape else progression.settle
                    settle(SaveData(), (member, npc), proficiency_level_limit=limit)
                    for index, kind in enumerate(kinds):
                        proficiency = member.proficiency(kind)
                        self.assertEqual((proficiency.level, proficiency.progress), (limit, 99))
                        proficiency = npc.proficiency(kind)
                        self.assertGreater(npc_before[index][0], limit)
                        self.assertEqual((proficiency.level, proficiency.progress), npc_before[index])

    def test_experience_ceiling_awards_only_remaining_points_and_keeps_gold(self) -> None:
        for limit, expected_level in ((500, 10), (5000, 19), (999999, 99)):
            with self.subTest(limit=limit):
                member = Member.from_record(member_record("Fighter"))
                save_data = SaveData(experience=limit - 5)
                for expected_award in (5, 0):
                    progression = BattleProgression((EnemyProgressionData(5, 4, 4, 25),))
                    growth = progression.settle(
                        save_data, (member,), experience_limit=limit
                    )
                    self.assertEqual(growth.experience_gained, expected_award)
                    self.assertEqual(growth.gold_gained, 25)
                    self.assertEqual(save_data.experience, limit)
                    self.assertEqual(member.internal_level, expected_level)
                self.assertEqual(save_data.gold, 50)

    def test_default_experience_ceiling_stops_at_six_digits(self) -> None:
        member = Member.from_record(member_record("Fighter"))
        save_data = SaveData(experience=999998)
        for expected_award in (1, 0):
            growth = BattleProgression((EnemyProgressionData(5, 4, 4, 0),)).settle(
                save_data, (member,)
            )
            self.assertEqual(save_data.experience, 999999)
            self.assertEqual(growth.experience_gained, expected_award)

    def test_experience_already_over_ceiling_is_preserved_without_reward(self) -> None:
        member = Member.from_record(member_record("Fighter"))
        save_data = SaveData(experience=6085)
        growth = BattleProgression((EnemyProgressionData(5, 4, 4, 0),)).settle(
            save_data, (member,), experience_limit=5000
        )
        self.assertEqual(save_data.experience, 6085)
        self.assertEqual(growth.experience_gained, 0)
        self.assertEqual(member.internal_level, 20)

    def test_weapon_combines_highest_target_level_defeat_species_and_critical(self) -> None:
        member = Member.from_record(member_record("Fighter"))
        progression = BattleProgression(
            tuple(EnemyProgressionData(level, 0, 1, 0) for level in (7, 1, 1))
        )

        progression.record_weapon_action(member, (self.sword,), (7,))
        progression.record_weapon_action(
            member,
            (self.sword,),
            (1,),
            defeated_enemy_keys=("Coyote",),
            critical=True,
        )
        progression.record_weapon_action(
            member,
            (self.sword,),
            (1,),
            defeated_enemy_keys=("Cobra",),
        )
        progression.record_weapon_action(
            member,
            (self.sword,),
            (1,),
            defeated_enemy_keys=("Coyote", "Cobra"),
            critical=True,
        )
        progression.settle(SaveData(), (member,))

        # Highest LV 7 + two species + any critical 1 + aptitude 1 - weapon LV 1.
        proficiency = member.proficiency(ProficiencyKind.SWORD)
        self.assertEqual((proficiency.level, proficiency.progress), (1, 10))

    def test_coyotes_and_cobras_award_four_for_two_defeated_species(self) -> None:
        for simultaneous in (False, True):
            with self.subTest(simultaneous=simultaneous):
                record = {**member_record("Fighter"), "eq_sword": 2}
                member = Member.from_record(record)
                member.proficiency(ProficiencyKind.SWORD).level = 2
                member.proficiency(ProficiencyKind.SWORD).progress = 0
                progression = BattleProgression(
                    tuple(EnemyProgressionData(level, 0, 5, 0) for level in (1, 1, 1, 2, 2))
                )
                if simultaneous:
                    progression.record_weapon_action(
                        member,
                        (self.sword,),
                        (1, 1, 1, 2, 2),
                        defeated_enemy_keys=("Coyote", "Coyote", "Coyote", "Cobra", "Cobra"),
                    )
                else:
                    for key, level in (("Coyote", 1),) * 3 + (("Cobra", 2),) * 2:
                        progression.record_weapon_action(
                            member, (self.sword,), (level,), defeated_enemy_keys=(key,)
                        )
                progression.settle(SaveData(), (member,))

                proficiency = member.proficiency(ProficiencyKind.SWORD)
                self.assertEqual((proficiency.level, proficiency.progress), (2, 4))

    def test_attacking_only_a_coyote_without_defeating_it_awards_one(self) -> None:
        record = {**member_record("Fighter"), "eq_sword": 2}
        member = Member.from_record(record)
        member.proficiency(ProficiencyKind.SWORD).level = 2
        member.proficiency(ProficiencyKind.SWORD).progress = 0
        progression = BattleProgression(
            (EnemyProgressionData(1, 0, 3, 0), EnemyProgressionData(2, 0, 2, 0))
        )

        progression.record_weapon_action(member, (self.sword,), (1,))
        progression.record_weapon_action(member, (self.sword,), (1,))
        progression.settle_escape(SaveData(), (member,))

        proficiency = member.proficiency(ProficiencyKind.SWORD)
        self.assertEqual((proficiency.level, proficiency.progress), (2, 1))

    def test_weapon_facts_are_separate_by_member_and_weapon_kind(self) -> None:
        member = Member.from_record({**member_record("Fighter"), "eq_axe": 1})
        other = Member.from_record(member_record("Other Fighter"))
        axe = next(item for item in self.items.values() if item.subtype == "AXE")
        progression = BattleProgression((EnemyProgressionData(4, 0, 1, 0),))

        progression.record_weapon_action(
            member, (self.sword, self.sword), (3,), defeated_enemy_keys=("Coyote",)
        )
        progression.record_weapon_action(
            member, (axe,), (2,), defeated_enemy_keys=("Cobra",), critical=True
        )
        progression.record_weapon_action(other, (self.sword,), (4,))
        progression.settle(SaveData(), (member, other))

        self.assertEqual(member.proficiency(ProficiencyKind.SWORD).progress, 4)
        self.assertEqual(member.proficiency(ProficiencyKind.AXE).progress, 4)
        self.assertEqual(other.proficiency(ProficiencyKind.SWORD).progress, 4)

    def test_weapon_formula_uses_settlement_level_and_never_awards_negative_progress(self) -> None:
        for final_level, expected in ((1, 2), (8, 0)):
            with self.subTest(final_level=final_level):
                member = Member.from_record(member_record("Fighter"))
                proficiency = member.proficiency(ProficiencyKind.SWORD)
                proficiency.level = 5
                progression = BattleProgression((EnemyProgressionData(2, 0, 1, 0),))
                progression.record_weapon_action(member, (self.sword,), (2,))
                proficiency.level = final_level
                progression.settle(SaveData(), (member,))
                self.assertEqual((proficiency.level, proficiency.progress), (final_level, expected))

    def test_weapon_rejects_invalid_defeated_species_keys(self) -> None:
        member = Member.from_record(member_record("Fighter"))
        progression = BattleProgression((EnemyProgressionData(4, 0, 1, 0),))

        for keys in (("",), (1,), (None,)):
            with self.subTest(keys=keys), self.assertRaises(ValueError):
                progression.record_weapon_action(
                    member, (self.sword,), (4,), defeated_enemy_keys=keys
                )
        with self.assertRaises(TypeError):
            progression.record_weapon_action(
                member, (self.sword,), (4,), defeated_enemy_keys="Coyote"
            )

    def test_spell_uses_highest_enemy_level_and_cumulative_paid_mp(self) -> None:
        member = Member.from_record(member_record("Mage"))
        member.proficiency(ProficiencyKind.MYSTIC).progress = 95
        progression = BattleProgression((EnemyProgressionData(1, 0, 1, 0),))

        progression.record_spell_use(
            member, ProficiencyKind.MYSTIC, (3,), mp_spent=4
        )
        progression.record_spell_use(
            member, ProficiencyKind.MYSTIC, (4,), mp_spent=5
        )
        progression.settle(SaveData(), (member,))

        proficiency = member.proficiency(ProficiencyKind.MYSTIC)
        self.assertEqual((proficiency.level, proficiency.progress), (2, 2))

    def test_escape_settles_proficiencies_and_mp_without_rewards_or_hp(self) -> None:
        save_data = SaveData(experience=30, gold=40)
        member = Member.from_record(member_record("Escaping Mage"))
        member.max_hp = 1
        member.hp = 1
        member.max_mp = 1
        member.mp = 1
        member.proficiency(ProficiencyKind.SWORD).progress = 95
        member.proficiency(ProficiencyKind.MYSTIC).progress = 95
        progression = BattleProgression(
            (EnemyProgressionData(10, 0, 1, 500),)
        )
        progression.record_weapon_action(member, (self.sword,), (10,))
        progression.record_spell_use(
            member,
            ProficiencyKind.MYSTIC,
            (10,),
            mp_spent=9,
        )

        growth = progression.settle_escape(save_data, (member,))

        self.assertEqual((save_data.experience, save_data.gold), (30, 40))
        self.assertEqual((growth.experience_gained, growth.gold_gained), (0, 0))
        self.assertEqual(member.max_hp, 1)
        self.assertGreater(member.max_mp, 1)
        self.assertGreater(
            member.proficiency(ProficiencyKind.SWORD).level * 100
            + member.proficiency(ProficiencyKind.SWORD).progress,
            195,
        )
        self.assertGreater(
            member.proficiency(ProficiencyKind.MYSTIC).level * 100
            + member.proficiency(ProficiencyKind.MYSTIC).progress,
            195,
        )
        self.assertTrue(growth.has_result_growth)

    def test_result_growth_distinguishes_progress_from_level_up(self) -> None:
        member = Member.from_record(member_record("Fighter"))
        progression = BattleProgression((EnemyProgressionData(1, 1, 1, 0),))
        progression.record_weapon_action(member, (self.sword,), (1,))

        growth = progression.settle(SaveData(), (member,))

        self.assertTrue(growth.has_result_growth)
        self.assertFalse(growth.has_level_up_growth)

    def test_no_growth_can_skip_the_result_screen(self) -> None:
        member = Member.from_record(member_record("Fighter"))
        progression = BattleProgression((EnemyProgressionData(1, 1, 1, 0),))

        growth = progression.settle(SaveData(), (member,))

        self.assertFalse(growth.has_result_growth)
        self.assertFalse(growth.has_level_up_growth)

    def test_victory_limits_hp_growth_to_one_internal_level_step(self) -> None:
        member = Member.from_record(member_record("Fighter"))
        member.experience_offset = required_experience_for_level(5)
        progression = BattleProgression((EnemyProgressionData(1, 1, 1, 0),))

        progression.settle(SaveData(), (member,))

        self.assertEqual(member.internal_level, 5)
        self.assertEqual(member.max_hp, 48)
        self.assertEqual(member.calculated_max_hp(), 72)

    def test_victory_uses_spell_step_when_maximum_spell_level_increases(
        self,
    ) -> None:
        member = Member.from_record(member_record("Mage"))
        member.experience_offset = required_experience_for_level(5)
        member.proficiency(ProficiencyKind.MYSTIC).progress = 95
        progression = BattleProgression((EnemyProgressionData(10, 10, 1, 0),))
        progression.record_spell_use(
            member, ProficiencyKind.MYSTIC, (10,), mp_spent=1
        )

        progression.settle(SaveData(), (member,))

        self.assertEqual(member.internal_level, 5)
        self.assertEqual(member.proficiency(ProficiencyKind.MYSTIC).level, 2)
        self.assertEqual(member.max_mp, 11)
        self.assertEqual(member.calculated_max_mp(), 14)

    def test_mp_recipient_alone_is_excluded_from_hp_growth(self) -> None:
        first = Member.from_record(member_record("First"))
        second = Member.from_record(member_record("Second"))
        first.max_hp = second.max_hp = 1
        first.hp = second.hp = 1
        first.max_mp = second.max_mp = 0
        first.mp = second.mp = 0
        progression = BattleProgression((EnemyProgressionData(10, 0, 1, 0),))
        progression.record_spell_use(
            first, ProficiencyKind.MYSTIC, (10,), mp_spent=1
        )
        progression.record_spell_use(
            second, ProficiencyKind.MYSTIC, (10,), mp_spent=1
        )

        progression.settle(SaveData(), (first, second))

        self.assertEqual(first.max_hp, 1)
        self.assertGreater(second.max_hp, 1)
        self.assertGreater(first.max_mp, 0)
        self.assertEqual(second.max_mp, 0)

    def test_dead_member_gets_shared_internal_level_but_no_visible_growth(self) -> None:
        member = Member.from_record(member_record("Dead"))
        member.hp = 0
        old_hp = member.max_hp
        old_proficiency = member.proficiency(ProficiencyKind.MYSTIC).progress
        progression = BattleProgression((EnemyProgressionData(10, 0, 1, 0),))
        progression.record_spell_use(
            member, ProficiencyKind.MYSTIC, (10,), mp_spent=9
        )

        progression.settle(SaveData(), (member,))

        self.assertGreater(member.internal_level, 1)
        self.assertEqual(member.max_hp, old_hp)
        self.assertEqual(
            member.proficiency(ProficiencyKind.MYSTIC).progress,
            old_proficiency,
        )


if __name__ == "__main__":
    unittest.main()
