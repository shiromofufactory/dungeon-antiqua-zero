from __future__ import annotations

import unittest

from tools._bootstrap import APP_ROOT as _APP_ROOT

from member import Member, ProficiencyKind
from systems.spell_progression import (
    apply_menu_spell_proficiency_growth,
    menu_spell_proficiency_gain,
)


PROFICIENCIES = {kind.value: 0 for kind in ProficiencyKind}


def member_record() -> dict[str, object]:
    return {
        "name_en": "Mage",
        "name_ja": "Mage",
        "type": "SUB",
        "race": "HUMAN",
        "gender": "MALE",
        "lv_diff": 0,
        "base_hp": 40,
        "base_mp": 20,
        "base_str": 10,
        "base_agi": 10,
        "base_mag": 20,
        "face_x": 0,
        "face_y": 0,
        **PROFICIENCIES,
        "sp_mystic": 1,
        "sp_sacred": 2,
        "sp_nether": 1,
    }


class MenuSpellProgressionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.member = Member.from_record(member_record())

    def test_gain_uses_mp_aptitude_and_highest_other_spell_level(self) -> None:
        self.member.proficiency(ProficiencyKind.MYSTIC).level = 6
        self.member.proficiency(ProficiencyKind.SACRED).level = 4
        self.member.proficiency(ProficiencyKind.NETHER).level = 3

        amount = menu_spell_proficiency_gain(
            self.member,
            ProficiencyKind.SACRED,
            mp_spent=15,
        )

        self.assertEqual(amount, 3 + 2 + 6 - 4)

    def test_gain_never_reduces_proficiency(self) -> None:
        self.member.proficiency(ProficiencyKind.MYSTIC).level = 8

        self.assertEqual(
            menu_spell_proficiency_gain(
                self.member,
                ProficiencyKind.MYSTIC,
                mp_spent=0,
            ),
            0,
        )

    def test_application_carries_level_and_refreshes_max_mp(self) -> None:
        self.member.proficiency(ProficiencyKind.MYSTIC).level = 4
        sacred = self.member.proficiency(ProficiencyKind.SACRED)
        sacred.level = 1
        sacred.progress = 98
        self.member.max_mp = 1

        growth = apply_menu_spell_proficiency_growth(
            self.member,
            ProficiencyKind.SACRED,
            mp_spent=3,
        )

        self.assertEqual((growth.before_total, growth.after_total), (198, 204))
        self.assertEqual((sacred.level, sacred.progress), (2, 4))
        self.assertGreater(self.member.max_mp, 1)

    def test_rejects_weapon_proficiency_and_invalid_mp(self) -> None:
        with self.assertRaisesRegex(ValueError, "spell school"):
            menu_spell_proficiency_gain(
                self.member,
                ProficiencyKind.SWORD,
                mp_spent=1,
            )
        with self.assertRaisesRegex(TypeError, "integer"):
            menu_spell_proficiency_gain(
                self.member,
                ProficiencyKind.MYSTIC,
                mp_spent=True,
            )


if __name__ == "__main__":
    unittest.main()
