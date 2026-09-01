from __future__ import annotations

import unittest
from unittest.mock import Mock

from tools.screen_mocks._fixtures import (
    load_mock_character_records,
    load_mock_items,
    load_mock_party,
    load_mock_skills,
)
from tools.screen_mocks.debug_menu import (
    DebugMenuPhase,
    DebugMenuScreenMock,
    MAX_GOLD,
    NumericEntry,
)
from tools.screen_mocks.debug_text import DEBUG_TEXT, DebugText
from input import Direction, InputButton, InputState
from resources import FontResources
from state import SaveData, Settings
from systems import DebugPartyEditor


class NumericEntryTest(unittest.TestCase):
    def test_accepts_leading_zeroes_and_converts_to_integer(self) -> None:
        entry = NumericEntry(0, MAX_GOLD, 6)

        for digit in "000123":
            self.assertTrue(entry.append(digit))

        self.assertEqual(entry.digits, "000123")
        self.assertEqual(entry.value, 123)
        self.assertFalse(entry.append("4"))

    def test_rejects_empty_and_out_of_range_values(self) -> None:
        entry = NumericEntry(1, 99, 2)

        self.assertIsNone(entry.value)
        entry.append("0")
        entry.append("0")
        self.assertIsNone(entry.value)
        self.assertTrue(entry.delete())
        self.assertTrue(entry.delete())
        self.assertFalse(entry.delete())


class DebugMenuScreenMockTest(unittest.TestCase):
    def setUp(self) -> None:
        items = load_mock_items()
        skills = load_mock_skills()
        party = load_mock_party(items, skills)
        self.editor = DebugPartyEditor(
            load_mock_character_records(),
            items=items,
            skills=skills,
            party=party,
        )
        self.save_data = SaveData()
        self.alert = Mock()
        self.screen = DebugMenuScreenMock(
            editor=self.editor,
            save_data=self.save_data,
            settings=Settings(),
            fonts=FontResources(),
            alert=self.alert,
        )
        self.assertEqual(self.screen._member_count_text(), "フィオラ＋５にん")

    @staticmethod
    def confirm() -> InputState:
        return InputState(confirm=InputButton(triggered=True, held=True))

    @staticmethod
    def cancel() -> InputState:
        return InputState(cancel=InputButton(triggered=True, held=True))

    def test_enters_level_on_da2_style_keypad_and_rebuilds_party(self) -> None:
        self.screen.update(self.confirm())
        self.assertIs(self.screen.phase, DebugMenuPhase.NUMBER)

        self.screen.numeric_cursor.select_key("9")
        self.screen.update(self.confirm())
        self.screen.numeric_cursor.select_key("9")
        self.screen.update(self.confirm())
        self.assertEqual(self.screen.numeric_entry.digits, "99")
        self.assertEqual(self.screen.numeric_cursor.selected_key, "confirm")

        self.screen.update(self.confirm())

        self.assertIs(self.screen.phase, DebugMenuPhase.MAIN)
        self.assertEqual(self.editor.baseline_level, 99)
        self.assertTrue(
            all(member.hp == member.max_hp for member in self.screen.party)
        )
        self.assertTrue(
            all(member.mp == member.max_mp for member in self.screen.party)
        )

    def test_invalid_level_keeps_numeric_input_open_and_alerts(self) -> None:
        self.screen._open_numeric("party_level")
        self.screen.numeric_cursor.select_key("0")
        self.screen.update(self.confirm())
        self.screen.numeric_cursor.select_key("0")
        self.screen.update(self.confirm())
        self.screen.update(self.confirm())

        self.assertIs(self.screen.phase, DebugMenuPhase.NUMBER)
        self.assertEqual(self.editor.baseline_level, 1)
        self.alert.start.assert_called_once_with()

    def test_cancel_deletes_a_digit_then_returns_to_main_when_empty(self) -> None:
        self.screen._open_numeric("gold")
        self.screen.numeric_cursor.select_key("5")
        self.screen.update(self.confirm())

        self.screen.update(self.cancel())
        self.assertEqual(self.screen.numeric_entry.digits, "")
        self.screen.update(self.cancel())

        self.assertIs(self.screen.phase, DebugMenuPhase.MAIN)
        self.assertEqual(self.save_data.gold, 0)

    def test_gold_accepts_six_digits(self) -> None:
        self.screen._open_numeric("gold")
        for digit in "654321":
            self.screen.numeric_cursor.select_key(digit)
            self.screen.update(self.confirm())
        self.screen.update(self.confirm())

        self.assertEqual(self.save_data.gold, 654321)
        self.assertIs(self.screen.phase, DebugMenuPhase.MAIN)

    def test_member_list_contains_all_characters_in_two_columns(self) -> None:
        self.screen._open_members()
        self.assertEqual(len(self.editor.candidate_definitions), 20)
        self.assertEqual(len(self.screen.member_cursor.targets), 20)
        self.assertEqual(self.screen.member_cursor.selected_key, "Fiora")
        self.assertEqual(
            (
                self.screen.member_cursor.targets[0].x,
                self.screen.member_cursor.targets[0].y,
            ),
            (4, 9),
        )
        self.assertEqual(
            (
                self.screen.member_cursor.targets[10].x,
                self.screen.member_cursor.targets[10].y,
            ),
            (32, 9),
        )

        self.screen.update(
            InputState(
                navigation=Direction.RIGHT,
                held_direction=Direction.RIGHT,
            )
        )

        self.assertEqual(
            self.screen.member_cursor.selected_key,
            self.editor.candidate_definitions[10].key,
        )

    def test_fiora_and_seventh_total_member_are_rejected(self) -> None:
        self.screen._open_members()
        self.screen.update(self.confirm())
        self.alert.start.assert_called_once_with()

        cress_index = next(
            index
            for index, definition in enumerate(self.editor.candidate_definitions)
            if definition.key == "Cress"
        )
        self.screen.member_index = cress_index
        self.screen._toggle_selected_member()
        self.assertEqual(self.editor.other_member_count, 5)
        self.assertEqual(self.alert.start.call_count, 2)

    def test_can_remove_every_member_except_fiora(self) -> None:
        self.screen._open_members()

        for key in ("Cerion", "Alvan", "Ragna", "Elika", "Dain"):
            self.screen.member_index = next(
                index
                for index, definition in enumerate(
                    self.editor.candidate_definitions
                )
                if definition.key == key
            )
            self.screen._toggle_selected_member()

        self.assertEqual(self.editor.other_member_count, 0)
        self.assertEqual(
            [member.definition.key for member in self.editor.party],
            ["Fiora"],
        )
        self.alert.start.assert_not_called()

    def test_debug_text_is_japanese_only_and_formats_member_count(self) -> None:
        self.assertIsInstance(DEBUG_TEXT, DebugText)
        self.assertEqual(DEBUG_TEXT.title, "デバッグメニュー")
        self.assertEqual(DEBUG_TEXT.member_count(0), "フィオラ＋０にん")


if __name__ == "__main__":
    unittest.main()
