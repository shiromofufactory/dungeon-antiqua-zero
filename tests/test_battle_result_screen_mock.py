from __future__ import annotations

import unittest

from tools.screen_mocks._fixtures import (
    load_mock_character_records,
    load_mock_items,
    load_mock_skills,
)
from tools.screen_mocks.battle_result import (
    RESULT_PARTY_CHARACTER_KEYS,
    build_result_party,
    member_battle_sprite_region,
    member_result_texts,
    result_window_grid,
    spell_proficiency_display,
    weapon_proficiency_display,
)


class BattleResultScreenMockTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.party = build_result_party(
            load_mock_character_records(),
            load_mock_items(),
            load_mock_skills(),
        )

    def test_places_six_windows_in_two_columns_and_three_rows(self) -> None:
        self.assertEqual(
            [result_window_grid(index) for index in range(6)],
            [
                (0, 0, 32, 20),
                (32, 0, 32, 20),
                (0, 20, 32, 20),
                (32, 20, 32, 20),
                (0, 40, 32, 20),
                (32, 40, 32, 20),
            ],
        )

    def test_uses_fiora_level_50_and_character_joining_level_offsets(self) -> None:
        self.assertEqual(
            tuple(member.definition.key for member in self.party),
            RESULT_PARTY_CHARACTER_KEYS,
        )
        self.assertEqual(
            tuple(member.internal_level for member in self.party),
            (50, 52, 67, 57, 60, 60),
        )

    def test_places_hp_mp_weapon_and_spell_rows_at_requested_y_values(self) -> None:
        fiora_texts = member_result_texts(self.party[0])
        self.assertEqual(
            [(text.y, text.text) for text in fiora_texts],
            [
                (2, "フィオラ"),
                (5, "ＨＰ　４７５／４７５"),
                (8, "ＭＰ　　９０／　９０"),
                (13, "%KNIFE%４－４３"),
                (16, "%MYSTIC%４－４３　%NETHER%４－４３"),
            ],
        )
        self.assertTrue(all(text.x == 8 for text in fiora_texts))

    def test_uses_first_battle_pose_and_leaves_dain_artwork_blank(self) -> None:
        self.assertEqual(
            [member_battle_sprite_region(member) for member in self.party],
            [
                (0, 0, 16, 32),
                (0, 32, 16, 32),
                (0, 64, 16, 32),
                (0, 96, 16, 32),
                (0, 128, 16, 32),
                None,
            ],
        )

    def test_shows_left_weapon_before_right_weapon(self) -> None:
        elika = self.party[3]
        self.assertEqual(
            weapon_proficiency_display(elika),
            "%KNIFE%４－９２　%KATANA%６－１６",
        )

    def test_omits_spell_row_when_member_has_no_spell_family(self) -> None:
        ragna = self.party[4]
        self.assertIsNone(spell_proficiency_display(ragna))
        self.assertEqual(
            [text.y for text in member_result_texts(ragna)],
            [2, 5, 8, 13],
        )


if __name__ == "__main__":
    unittest.main()
