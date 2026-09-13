from __future__ import annotations

import unittest

from tools._bootstrap import APP_ROOT
from tools.screen_mocks._fixtures import (
    load_mock_items,
    load_mock_party,
    load_mock_skills,
)
from member import FormationRow, ProficiencyKind
from resources import load_record_array
from systems import (
    DebugPartyEditor,
    DebugPartyError,
    MAX_MEMBER_SKILL_COUNT,
)


class DebugPartyEditorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.items = load_mock_items()
        self.skills = load_mock_skills()
        self.party = load_mock_party(self.items, self.skills)
        self.editor = DebugPartyEditor(
            load_record_array("characters.json", APP_ROOT / "data"),
            items=self.items,
            skills=self.skills,
            party=self.party,
        )

    def test_exposes_all_twenty_character_candidates(self) -> None:
        self.assertEqual(len(self.editor.candidate_definitions), 20)
        self.assertEqual(
            self.editor.candidate_definitions[0].key,
            "Fiora",
        )
        self.assertEqual(self.editor.baseline_level, 1)

    def test_recreates_party_from_fiora_baseline_and_level_differences(self) -> None:
        self.editor.set_baseline_level(90)

        members = {member.definition.key: member for member in self.editor.party}
        self.assertEqual(members["Fiora"].internal_level, 90)
        self.assertEqual(members["Cerion"].internal_level, 92)
        self.assertEqual(members["Alvan"].internal_level, 99)
        self.assertEqual(
            (members["Cerion"].hp, members["Cerion"].max_hp),
            (members["Cerion"].max_hp, members["Cerion"].max_hp),
        )
        self.assertEqual(
            (members["Cerion"].mp, members["Cerion"].max_mp),
            (members["Cerion"].max_mp, members["Cerion"].max_mp),
        )
        self.assertEqual(
            (
                members["Cerion"].proficiency(ProficiencyKind.SPEAR).level,
                members["Cerion"].proficiency(ProficiencyKind.SPEAR).progress,
            ),
            (8, 96),
        )
        self.assertIs(members["Cerion"].formation_row, FormationRow.BACK)

    def test_adds_member_at_level_derived_from_current_baseline(self) -> None:
        self.editor.set_baseline_level(50)
        self.editor.toggle_member("Cerion")
        self.editor.toggle_member("Dain")
        self.editor.toggle_member("Dain")

        dain = next(
            member
            for member in self.editor.party
            if member.definition.key == "Dain"
        )
        self.assertEqual(dain.internal_level, 60)
        self.assertEqual(dain.hp, dain.max_hp)
        self.assertEqual(dain.mp, dain.max_mp)

    def test_allows_fiora_only_and_rejects_a_seventh_total_member(self) -> None:
        with self.assertRaisesRegex(DebugPartyError, "Fiora"):
            self.editor.toggle_member("Fiora")

        self.editor.toggle_member("Cerion")
        self.editor.toggle_member("Alvan")
        self.editor.toggle_member("Ragna")
        self.editor.toggle_member("Elika")
        self.editor.toggle_member("Dain")
        self.assertEqual(self.editor.other_member_count, 0)
        self.assertEqual(
            [member.definition.key for member in self.editor.party],
            ["Fiora"],
        )

        self.editor.toggle_member("Cerion")
        self.editor.toggle_member("Alvan")
        self.editor.toggle_member("Ragna")
        self.editor.toggle_member("Dain")
        self.editor.toggle_member("Elika")
        with self.assertRaisesRegex(DebugPartyError, "1 to 6 total"):
            self.editor.toggle_member("Cress")

    def test_edits_current_hp_and_mp_within_each_members_maximum(self) -> None:
        member = self.editor.member("Fiora")

        self.editor.set_member_hp("Fiora", 0)
        self.editor.set_member_mp("Fiora", member.max_mp - 1)

        self.assertEqual(member.hp, 0)
        self.assertEqual(member.mp, member.max_mp - 1)
        with self.assertRaisesRegex(DebugPartyError, "HP"):
            self.editor.set_member_hp("Fiora", member.max_hp + 1)
        with self.assertRaisesRegex(DebugPartyError, "MP"):
            self.editor.set_member_mp("Fiora", -1)

    def test_freely_sets_and_clears_poison_and_paralysis(self) -> None:
        member = self.editor.member("Fiora")
        self.editor.set_member_hp("Fiora", 0)

        self.editor.set_member_poisoned("Fiora", True)
        self.editor.set_member_paralyzed("Fiora", True)

        self.assertTrue(member.poisoned)
        self.assertTrue(member.paralyzed)
        self.editor.set_member_poisoned("Fiora", False)
        self.editor.set_member_paralyzed("Fiora", False)
        self.assertFalse(member.poisoned)
        self.assertFalse(member.paralyzed)

    def test_rejects_status_edits_for_a_member_outside_the_party(self) -> None:
        with self.assertRaisesRegex(DebugPartyError, "not in the debug party"):
            self.editor.set_member_hp("Cress", 0)

    def test_adds_and_removes_catalog_skills_up_to_two_without_duplicates(
        self,
    ) -> None:
        fiora = self.editor.member("Fiora")
        self.assertEqual(len(self.editor.candidate_skills), 19)
        self.assertEqual(fiora.skills, [])

        self.editor.toggle_member_skill("Fiora", "Aim")
        self.editor.toggle_member_skill("Fiora", "Hide")

        self.assertEqual([skill.key for skill in fiora.skills], ["Aim", "Hide"])
        self.assertEqual(len(fiora.skills), MAX_MEMBER_SKILL_COUNT)
        with self.assertRaisesRegex(DebugPartyError, "at most 2"):
            self.editor.toggle_member_skill("Fiora", "Identify")
        self.editor.toggle_member_skill("Fiora", "Aim")
        self.assertEqual([skill.key for skill in fiora.skills], ["Hide"])

    def test_rejects_an_unknown_debug_skill(self) -> None:
        with self.assertRaisesRegex(DebugPartyError, "unknown skill key"):
            self.editor.toggle_member_skill("Fiora", "Missing")


if __name__ == "__main__":
    unittest.main()
