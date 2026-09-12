from __future__ import annotations

import unittest
from unittest.mock import Mock

from tools.screen_mocks._fixtures import (
    load_mock_character_records,
    load_mock_items,
    load_mock_party,
    load_mock_skills,
)
from ui.debug_menu import (
    DebugMenuPhase,
    DebugMenuOverlay,
    DebugShopTarget,
    DebugTeleportTarget,
    MAX_GOLD,
    NumericEntry,
)
from ui.debug_text import DEBUG_TEXT, DebugText
from input import Direction, InputButton, InputState
from resources import FontResources, FontRole
from state import Language, SaveData, Settings
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


class DebugMenuOverlayTest(unittest.TestCase):
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
        self.screen = DebugMenuOverlay(
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

    def test_main_items_use_the_standard_twelve_pixel_row_spacing(self) -> None:
        target_y = [target.y for target in self.screen.main_cursor.targets]

        self.assertEqual(len(target_y), 6)
        self.assertTrue(
            all(
                next_y - current_y == 3
                for current_y, next_y in zip(target_y, target_y[1:])
            )
        )

    def test_edits_each_members_hp_mp_poison_and_paralysis(self) -> None:
        self.screen.main_cursor.select_key("member_status")
        self.screen.update(self.confirm())

        self.assertIs(
            self.screen.phase,
            DebugMenuPhase.MEMBER_STATUS_LIST,
        )
        self.assertEqual(
            len(self.screen.member_status_list_cursor.targets),
            len(self.screen.party),
        )
        self.screen.update(
            InputState(
                navigation=Direction.DOWN,
                held_direction=Direction.DOWN,
            )
        )
        self.screen.update(self.confirm())
        self.assertIs(self.screen.phase, DebugMenuPhase.MEMBER_STATUS)
        self.assertEqual(self.screen.member_status_key, "Cerion")

        member = self.editor.member("Cerion")
        self.screen.member_status_cursor.select_key("hp")
        self.screen.update(self.confirm())
        self.screen.numeric_cursor.select_key("0")
        self.screen.update(self.confirm())
        self.screen.numeric_cursor.select_key("confirm")
        self.screen.update(self.confirm())
        self.assertEqual(member.hp, 0)
        self.assertIs(self.screen.phase, DebugMenuPhase.MEMBER_STATUS)

        self.screen.member_status_cursor.select_key("mp")
        self.screen.update(self.confirm())
        for digit in str(member.max_mp):
            self.screen.numeric_cursor.select_key(digit)
            self.screen.update(self.confirm())
        self.screen.update(self.confirm())
        self.assertEqual(member.mp, member.max_mp)

        self.screen.member_status_cursor.select_key("poisoned")
        self.screen.update(self.confirm())
        self.screen.member_status_cursor.select_key("paralyzed")
        self.screen.update(self.confirm())
        self.assertTrue(member.poisoned)
        self.assertTrue(member.paralyzed)

        self.screen.member_status_cursor.select_key("poisoned")
        self.screen.update(self.confirm())
        self.screen.member_status_cursor.select_key("paralyzed")
        self.screen.update(self.confirm())
        self.assertFalse(member.poisoned)
        self.assertFalse(member.paralyzed)

    def test_member_status_cancel_returns_through_each_parent_screen(self) -> None:
        self.screen.main_cursor.select_key("member_status")
        self.screen.update(self.confirm())
        self.screen.update(self.confirm())
        self.screen.update(self.confirm())
        self.assertIs(self.screen.phase, DebugMenuPhase.NUMBER)

        self.screen.update(self.cancel())
        self.assertIs(self.screen.phase, DebugMenuPhase.MEMBER_STATUS)
        self.assertEqual(self.screen.member_status_cursor.selected_key, "hp")

        self.screen.update(self.cancel())
        self.assertIs(
            self.screen.phase,
            DebugMenuPhase.MEMBER_STATUS_LIST,
        )
        self.screen.update(self.cancel())
        self.assertIs(self.screen.phase, DebugMenuPhase.MAIN)
        self.assertEqual(
            self.screen.main_cursor.selected_key,
            "member_status",
        )

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

    def test_teleport_list_requests_the_selected_visited_site(self) -> None:
        on_teleport = Mock(return_value=True)
        screen = DebugMenuOverlay(
            editor=self.editor,
            save_data=self.save_data,
            settings=Settings(),
            fonts=FontResources(),
            alert=self.alert,
            teleport_targets=(
                DebugTeleportTarget("fairy_village", "妖精の里"),
                DebugTeleportTarget("sample_cave", "サンプルの洞窟"),
            ),
            on_teleport=on_teleport,
        )
        screen.main_cursor.select_key("teleport")

        screen.update(self.confirm())
        self.assertIs(screen.phase, DebugMenuPhase.TELEPORT)
        self.assertEqual(screen.teleport_cursor.selected_key, "fairy_village")
        self.assertIs(
            screen.teleport_texts.font,
            screen.fonts.font_for(Language.JAPANESE, role=FontRole.LARGE),
        )

        screen.update(
            InputState(
                navigation=Direction.DOWN,
                held_direction=Direction.DOWN,
            )
        )
        self.assertEqual(screen.teleport_cursor.selected_key, "sample_cave")
        screen.update(self.confirm())

        on_teleport.assert_called_once_with("sample_cave")
        self.alert.start.assert_not_called()

    def test_empty_teleport_list_alerts_and_can_return_to_main(self) -> None:
        self.screen.main_cursor.select_key("teleport")
        self.screen.update(self.confirm())

        self.assertIs(self.screen.phase, DebugMenuPhase.TELEPORT)
        self.assertIsNone(self.screen.teleport_cursor)
        self.screen.update(self.confirm())
        self.alert.start.assert_called_once_with()

        self.screen.update(self.cancel())
        self.assertIs(self.screen.phase, DebugMenuPhase.MAIN)
        self.assertEqual(self.screen.main_cursor.selected_key, "teleport")

    def test_teleport_list_scrolls_beyond_the_visible_rows(self) -> None:
        targets = tuple(
            DebugTeleportTarget(f"site_{index}", f"拠点{index}")
            for index in range(15)
        )
        screen = DebugMenuOverlay(
            editor=self.editor,
            save_data=self.save_data,
            settings=Settings(),
            fonts=FontResources(),
            alert=self.alert,
            teleport_targets=targets,
            on_teleport=Mock(return_value=True),
        )
        screen.main_cursor.select_key("teleport")
        screen.update(self.confirm())

        for _index in range(13):
            screen.update(
                InputState(
                    navigation=Direction.DOWN,
                    held_direction=Direction.DOWN,
                )
            )

        self.assertEqual(screen.teleport_index, 13)
        self.assertEqual(screen.teleport_scroll_offset, 1)
        self.assertEqual(screen.teleport_cursor.selected_key, "site_13")
        self.assertEqual(len(screen.teleport_cursor.targets), 13)

    def test_shop_list_opens_the_selected_production_shop(self) -> None:
        on_shop = Mock(return_value=True)
        screen = DebugMenuOverlay(
            editor=self.editor,
            save_data=self.save_data,
            settings=Settings(),
            fonts=FontResources(),
            alert=self.alert,
            shop_targets=(
                DebugShopTarget("FAIRY_HAMLET_ITEMS", "FAIRY_HAMLET_ITEMS"),
                DebugShopTarget("SILVALIA_ARMORY", "SILVALIA_ARMORY"),
            ),
            on_shop=on_shop,
        )
        screen.main_cursor.select_key("shop")

        screen.update(self.confirm())

        self.assertIs(screen.phase, DebugMenuPhase.SHOP)
        self.assertEqual(screen.shop_cursor.selected_key, "FAIRY_HAMLET_ITEMS")
        screen.update(
            InputState(
                navigation=Direction.DOWN,
                held_direction=Direction.DOWN,
            )
        )
        screen.update(self.confirm())

        on_shop.assert_called_once_with("SILVALIA_ARMORY")
        self.alert.start.assert_not_called()

    def test_empty_shop_list_alerts_and_can_return_to_main(self) -> None:
        self.screen.main_cursor.select_key("shop")
        self.screen.update(self.confirm())

        self.assertIs(self.screen.phase, DebugMenuPhase.SHOP)
        self.assertIsNone(self.screen.shop_cursor)
        self.screen.update(self.confirm())
        self.alert.start.assert_called_once_with()

        self.screen.update(self.cancel())
        self.assertIs(self.screen.phase, DebugMenuPhase.MAIN)
        self.assertEqual(self.screen.main_cursor.selected_key, "shop")

    def test_debug_text_is_japanese_only_and_formats_member_count(self) -> None:
        self.assertIsInstance(DEBUG_TEXT, DebugText)
        self.assertEqual(DEBUG_TEXT.title, "デバッグメニュー")
        self.assertEqual(DEBUG_TEXT.member_count(0), "フィオラ＋０にん")
        self.assertEqual(DEBUG_TEXT.party_member_count(6), "６にん")
        self.assertEqual(DEBUG_TEXT.member_status, "メンバー状態")
        self.assertEqual(DEBUG_TEXT.teleport_count(2), "２かしょ")
        self.assertEqual(DEBUG_TEXT.shop, "ショップ")
        self.assertEqual(DEBUG_TEXT.shop_count(13), "１３けん")


if __name__ == "__main__":
    unittest.main()
