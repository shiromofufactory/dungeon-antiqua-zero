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
from systems import DebugPartyEditor, DebugPartyError


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

        dain = next(
            member
            for member in self.editor.party
            if member.definition.key == "Dain"
        )
        self.assertEqual(dain.internal_level, 60)
        self.assertEqual(dain.hp, dain.max_hp)
        self.assertEqual(dain.mp, dain.max_mp)

    def test_allows_fiora_only_and_rejects_a_sixth_total_member(self) -> None:
        with self.assertRaisesRegex(DebugPartyError, "Fiora"):
            self.editor.toggle_member("Fiora")

        self.editor.toggle_member("Cerion")
        self.editor.toggle_member("Alvan")
        self.editor.toggle_member("Ragna")
        self.editor.toggle_member("Elika")
        self.assertEqual(self.editor.other_member_count, 0)
        self.assertEqual(
            [member.definition.key for member in self.editor.party],
            ["Fiora"],
        )

        self.editor.toggle_member("Cerion")
        self.editor.toggle_member("Alvan")
        self.editor.toggle_member("Ragna")
        self.editor.toggle_member("Dain")
        with self.assertRaisesRegex(DebugPartyError, "1 to 5 total"):
            self.editor.toggle_member("Cress")


if __name__ == "__main__":
    unittest.main()
