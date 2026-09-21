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

    def test_weapon_uses_maximum_action_award_and_stacks_bonuses(self) -> None:
        member = Member.from_record(member_record("Fighter"))
        member.proficiency(ProficiencyKind.SWORD).progress = 95
        progression = BattleProgression((EnemyProgressionData(4, 0, 1, 0),))

        progression.record_weapon_action(member, (self.sword,), (4,))
        progression.record_weapon_action(member, (self.sword,), (4,))
        progression.record_weapon_action(
            member,
            (self.sword,),
            (4,),
            defeated_enemy=True,
            critical=True,
        )
        progression.settle(SaveData(), (member,))

        proficiency = member.proficiency(ProficiencyKind.SWORD)
        self.assertEqual((proficiency.level, proficiency.progress), (2, 1))

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
