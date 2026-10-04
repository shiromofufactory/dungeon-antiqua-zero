from __future__ import annotations

import unittest
from itertools import pairwise
from unittest.mock import Mock

from input import Direction, InputButton, InputState
from resources import FontResources, FontRole
from state import Language, SaveData, Settings
from systems import DebugPartyEditor, InventorySystem
from ui.debug_menu import (
    MAX_GOLD,
    DebugItemPane,
    DebugMenuOverlay,
    DebugMenuPhase,
    DebugShopTarget,
    DebugTeleportTarget,
    NumericEntry,
)
from ui.debug_text import DEBUG_TEXT, DebugText

from tools.screen_mocks._fixtures import (
    load_mock_character_records,
    load_mock_items,
    load_mock_party,
    load_mock_skills,
)


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
        self.inventory = InventorySystem(items)
        self.save_data = SaveData()
        self.alert = Mock()
        self.screen = DebugMenuOverlay(
            editor=self.editor,
            inventory_system=self.inventory,
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
        self.screen.main_cursor.select_key("party_level")
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

        self.assertEqual(len(target_y), 8)
        self.assertEqual(self.screen.main_cursor.targets[0].key, "encounter")
        self.assertEqual(self.screen.main_cursor.selected_key, "encounter")
        self.assertTrue(
            all(
                next_y - current_y == 3
                for current_y, next_y in pairwise(target_y)
            )
        )

    def test_encounter_options_wrap_and_persist_after_cancel_and_reopen(self) -> None:
        self.screen.main_cursor.select_key("encounter")
        self.screen.update(self.confirm())
        menu = self.screen.encounter_menu
        self.assertEqual(menu.cursor.targets[0].key, "start")
        self.assertEqual(menu.cursor.selected_key, "start")
        menu.cursor.select_key("monster_level")
        self.assertEqual(menu.state.settings.monster_level, 1)
        menu.update(InputState(navigation=Direction.LEFT))
        self.assertEqual(menu.state.settings.monster_level, "dynamic")
        menu.update(InputState(navigation=Direction.RIGHT))
        self.assertEqual(menu.state.settings.monster_level, 1)
        for _ in range(8):
            menu.update(self.confirm())
        self.assertEqual(menu.state.settings.monster_level, 9)
        for key, expected in (
            ("danger", "high"), ("polarity", "yin"),
            ("allow_demons", True), ("allow_humans", True),
            ("allow_giants", True), ("allow_large_animals", False),
        ):
            menu.cursor.select_key(key)
            menu.update(self.confirm())
            self.assertEqual(getattr(menu.state.settings, key), expected)
        retained = menu.state.settings
        self.screen.update(self.cancel())
        self.assertIs(self.screen.phase, DebugMenuPhase.MAIN)
        self.assertEqual(self.screen.main_cursor.selected_key, "encounter")
        self.screen.update(self.confirm())
        self.assertEqual(self.screen.encounter_menu.state.settings, retained)
        # A new debug overlay uses the same Game-owned session state.
        other = DebugMenuOverlay(
            editor=self.editor, inventory_system=self.inventory,
            save_data=self.save_data, settings=Settings(),
            fonts=FontResources(), alert=self.alert,
            encounter_state=self.screen.encounter_state,
        )
        self.assertIs(other.encounter_state.settings, retained)

    def test_encounter_start_passes_settings_and_alerts_on_empty_pool(self) -> None:
        callback = Mock(return_value=False)
        self.screen.on_encounter = callback
        self.screen.main_cursor.select_key("encounter")
        self.screen.update(self.confirm())
        self.screen.encounter_menu.cursor.select_key("start")
        self.screen.update(self.confirm())
        callback.assert_called_once_with(self.screen.encounter_state.settings)
        self.alert.start.assert_called_once_with()
        self.assertIs(self.screen.phase, DebugMenuPhase.ENCOUNTER)

    def test_item_warehouse_acquires_one_without_consuming_its_catalog(self) -> None:
        item = self.inventory.catalog_items[0]
        self.screen.main_cursor.select_key("items")

        self.screen.update(self.confirm())

        self.assertIs(self.screen.phase, DebugMenuPhase.ITEMS)
        self.assertIs(self.screen.item_pane, DebugItemPane.WAREHOUSE)
        self.assertEqual(self.screen.item_cursor.selected_key, item.key)
        self.assertEqual(
            len(self.screen.item_cursor.targets),
            min(13, self.inventory.catalog_count),
        )
        texts = self.screen.item_window.texts
        self.assertIn("もちもの", [placement.text for placement in texts])
        self.assertIn("そうこ", [placement.text for placement in texts])
        self.assertFalse(
            any("∞" in placement.text for placement in texts)
        )
        self.assertFalse(
            any("１こ入手" in placement.text for placement in texts)
        )
        self.assertFalse(any("／" in placement.text for placement in texts))
        self.assertIn(
            (DEBUG_TEXT.item_switch_guide, 52),
            [(placement.text, placement.y) for placement in texts],
        )
        self.assertTrue(
            any(
                placement.text.endswith("：もどる") and placement.y == 52
                for placement in texts
            )
        )

        self.screen.update(self.confirm())

        self.assertEqual(self.inventory.quantity(item), 1)
        self.assertEqual(self.inventory.catalog_items[0], item)
        self.assertIn(item, self.inventory.items)
        self.assertEqual(self.screen.item_cursor.selected_key, item.key)
        self.assertIn(
            ("１", 28, 7),
            [
                (placement.text, placement.x, placement.y)
                for placement in self.screen.item_window.texts
            ],
        )
        self.alert.start.assert_not_called()

    def test_item_inventory_column_is_read_only_and_can_return_to_main(self) -> None:
        item = self.inventory.catalog_items[0]
        self.inventory.add(item)
        self.screen.main_cursor.select_key("items")
        self.screen.update(self.confirm())

        self.screen.update(
            InputState(
                navigation=Direction.LEFT,
                held_direction=Direction.LEFT,
            )
        )

        self.assertIs(self.screen.item_pane, DebugItemPane.INVENTORY)
        self.assertEqual(self.screen.item_cursor.selected_key, item.key)
        self.screen.update(self.confirm())
        self.assertEqual(self.inventory.quantity(item), 1)
        self.alert.start.assert_called_once_with()

        self.screen.update(self.cancel())
        self.assertIs(self.screen.phase, DebugMenuPhase.MAIN)
        self.assertEqual(self.screen.main_cursor.selected_key, "items")

    def test_item_warehouse_scrolls_and_rejects_the_shared_stack_limit(self) -> None:
        first_item = self.inventory.catalog_items[0]
        for _index in range(self.inventory.stack_limit(first_item)):
            self.assertTrue(self.inventory.add(first_item))
        self.screen.main_cursor.select_key("items")
        self.screen.update(self.confirm())

        self.screen.update(self.confirm())

        self.assertEqual(
            self.inventory.quantity(first_item),
            self.inventory.stack_limit(first_item),
        )
        self.alert.start.assert_called_once_with()

        for _index in range(13):
            self.screen.update(
                InputState(
                    navigation=Direction.DOWN,
                    held_direction=Direction.DOWN,
                )
            )

        self.assertEqual(self.screen.warehouse_item_index, 13)
        self.assertEqual(self.screen.warehouse_item_scroll_offset, 1)
        self.assertEqual(
            self.screen.item_cursor.selected_key,
            self.inventory.catalog_items[13].key,
        )

    def test_item_warehouse_counts_equipped_copies_toward_the_limit(self) -> None:
        equipped_item = self.editor.party[0].equipment.equipped_items()[0]
        remaining = self.inventory.remaining_capacity(
            equipped_item,
            self.editor.party,
        )
        self.assertTrue(
            self.inventory.add(
                equipped_item,
                remaining,
                members=self.editor.party,
            )
        )
        catalog_index = self.inventory.catalog_items.index(equipped_item)
        self.screen._open_items()
        self.screen.warehouse_item_index = catalog_index
        self.screen.warehouse_item_scroll_offset = max(0, catalog_index - 12)
        self.screen._build_item_window()

        self.screen.update(self.confirm())

        self.assertEqual(
            self.inventory.total_quantity(equipped_item, self.editor.party),
            self.inventory.stack_limit(equipped_item),
        )
        self.alert.start.assert_called_once_with()

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

    def test_adds_and_removes_up_to_two_skills_for_selected_member(self) -> None:
        self.screen.main_cursor.select_key("member_status")
        self.screen.update(self.confirm())
        self.screen.update(self.confirm())
        self.screen.member_status_cursor.select_key("skills")
        self.screen.update(self.confirm())

        self.assertIs(self.screen.phase, DebugMenuPhase.MEMBER_SKILLS)
        self.assertEqual(len(self.screen.member_skill_cursor.targets), 19)
        self.assertEqual(
            self.screen.member_skill_cursor.selected_key,
            "Aim",
        )
        self.assertEqual(
            (
                self.screen.member_skill_cursor.targets[10].x,
                self.screen.member_skill_cursor.targets[10].y,
            ),
            (32, 9),
        )

        member = self.editor.member("Fiora")
        self.screen.update(self.confirm())
        self.assertEqual([skill.key for skill in member.skills], ["Aim"])
        self.screen.update(
            InputState(
                navigation=Direction.DOWN,
                held_direction=Direction.DOWN,
            )
        )
        self.screen.update(self.confirm())
        self.assertEqual(
            [skill.key for skill in member.skills],
            ["Aim", "Hide"],
        )

        self.screen.update(
            InputState(
                navigation=Direction.DOWN,
                held_direction=Direction.DOWN,
            )
        )
        self.screen.update(self.confirm())
        self.assertEqual(
            [skill.key for skill in member.skills],
            ["Aim", "Hide"],
        )
        self.alert.start.assert_called_once_with()

        self.screen.member_skill_cursor.select_key("Hide")
        self.screen.update(self.confirm())
        self.assertEqual([skill.key for skill in member.skills], ["Aim"])

        self.screen.update(self.cancel())
        self.assertIs(self.screen.phase, DebugMenuPhase.MEMBER_STATUS)
        self.assertEqual(
            self.screen.member_status_cursor.selected_key,
            "skills",
        )
        self.assertIn(
            "１／２",
            [placement.text for placement in self.screen.member_status_window.texts],
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
            inventory_system=self.inventory,
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
            inventory_system=self.inventory,
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
            inventory_system=self.inventory,
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
        self.assertEqual(DEBUG_TEXT.skill_count(2), "２／２")
        self.assertEqual(DEBUG_TEXT.items, "アイテム")
        self.assertEqual(DEBUG_TEXT.item_count(2), "２しゅ")
        self.assertEqual(DEBUG_TEXT.item_inventory, "もちもの")
        self.assertEqual(DEBUG_TEXT.item_warehouse, "そうこ")
        self.assertEqual(DEBUG_TEXT.teleport_count(2), "２かしょ")
        self.assertEqual(DEBUG_TEXT.shop, "ショップ")
        self.assertEqual(DEBUG_TEXT.shop_count(13), "１３けん")


if __name__ == "__main__":
    unittest.main()
