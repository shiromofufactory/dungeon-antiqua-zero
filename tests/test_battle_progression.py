from __future__ import annotations

import unittest

from tools._bootstrap import APP_ROOT
from tools.screen_mocks._fixtures import load_mock_items

from member import (
    Member,
    ProficiencyKind,
    internal_level_for_experience,
    required_experience_for_level,
)
from state import SaveData
from systems import BattleProgression, EnemyProgressionData


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

    def test_enemy_reward_uses_actual_action_count_and_final_floor(self) -> None:
        enemy = EnemyProgressionData(4, 1, 4, 25)
        progression = BattleProgression((enemy,))

        progression.record_enemy_action(0)
        progression.record_enemy_action(0)

        self.assertEqual(enemy.experience(0), 36)
        self.assertEqual(progression.rewards(), (43, 25))

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

    def test_hp_recipient_alone_is_excluded_from_mp_growth(self) -> None:
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

        self.assertGreater(first.max_hp, 1)
        self.assertEqual(second.max_hp, 1)
        self.assertEqual(first.max_mp, 0)
        self.assertGreater(second.max_mp, 0)

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
