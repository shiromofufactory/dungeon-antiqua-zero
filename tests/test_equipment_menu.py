from __future__ import annotations

import unittest
from unittest.mock import Mock, call, patch

from tools._bootstrap import APP_ROOT as _APP_ROOT

from ui.equipment_menu import (
    AUTO_KEY,
    EQUIPPABLE_ICON_ORDER,
    FACE_SIZE,
    FACE_X,
    FACE_Y,
    HEADER_EQUIPMENT_TYPES_Y,
    HEADER_EQUIPMENT_COLUMN_PIXEL_WIDTH,
    HEADER_EQUIPMENT_ICON_GAP,
    HEADER_EQUIPMENT_ICON_PIXEL_Y,
    HEADER_EQUIPMENT_LEVEL_PIXEL_Y,
    HEADER_EQUIPMENT_LEVEL_RIGHT_OFFSET,
    HEADER_FORMATION_Y,
    HEADER_NAME_Y,
    HEADER_TEXT_X,
    ITEM_FIRST_Y,
    ITEM_INFO_WINDOW_GRID,
    ITEM_LIST_WINDOW_GRID,
    ITEM_COUNT_X,
    ITEM_ROW_HEIGHT,
    ITEM_TEXT_X,
    ITEM_VISIBLE_COUNT,
    MAIN_WINDOW_GRID,
    MAIN_TEXT_X,
    REMOVE_KEY,
    STAT_LABEL_X,
    STAT_VALUE_X,
    STAT_Y,
    TOLERANCE_ICON_Y,
    TOLERANCE_LABEL_Y,
    TOLERANCE_PREVIEW_Y,
    EquipmentSelectionPhase,
)
from tests.ui_test_support import EquipmentMenuHarness
from input import Direction, InputButton, InputState
from item import ItemEquipType
from member import BattleStats, EquipmentSlot, HandHit, ProficiencyKind
from state import Language, Settings
from ui import DEFAULT_TEXT_COLOR, DISABLED_COLOR


class EquipmentMenuTest(unittest.TestCase):
    def build_mock(
        self,
        *,
        member_index: int = 0,
        on_invalid_action=None,
    ) -> EquipmentMenuHarness:
        font = object()
        with (
            patch("tests.ui_test_support.ImageResources") as images,
            patch("tests.ui_test_support.FontResources") as fonts,
        ):
            images.return_value.image.return_value = object()
            fonts.return_value.font_for.return_value = font
            fonts.return_value.baseline_offset_for.return_value = 0
            return EquipmentMenuHarness(
                member_index=member_index,
                on_invalid_action=on_invalid_action,
            )

    def test_builds_zero_equipment_layout_from_da2_rows(self) -> None:
        mock = self.build_mock()

        self.assertEqual(
            [
                (window.x, window.y, window.width, window.height)
                for window in mock.windows
            ],
            [MAIN_WINDOW_GRID, ITEM_LIST_WINDOW_GRID, ITEM_INFO_WINDOW_GRID],
        )
        placed = {(text.x, text.y): text for text in mock.main_window.texts}
        self.assertEqual(placed[(HEADER_TEXT_X, HEADER_NAME_Y)].text, "フィオラ")
        self.assertEqual(
            placed[(HEADER_TEXT_X, HEADER_FORMATION_Y)].text,
            "ぜんえい",
        )
        self.assertFalse(
            any(text.y == HEADER_EQUIPMENT_TYPES_Y for text in mock.main_window.texts)
        )
        self.assertEqual(len(EQUIPPABLE_ICON_ORDER), 10)
        self.assertEqual(
            placed[(MAIN_TEXT_X, 14)].text,
            "%RIGHT%：%KNIFE%ダガー",
        )
        self.assertEqual(
            placed[(MAIN_TEXT_X, 20)].text,
            "%BODY%：ローブ",
        )
        self.assertEqual(
            placed[(STAT_LABEL_X, STAT_Y["attack"])].text,
            "こうげき",
        )
        self.assertEqual(
            placed[(STAT_LABEL_X, STAT_Y["hit"])].text,
            "めいちゅう",
        )
        self.assertEqual(set(STAT_VALUE_X.values()), {16})
        self.assertEqual(
            placed[(STAT_VALUE_X["attack"], STAT_Y["attack"])].text,
            "　　８",
        )
        self.assertIn(
            "（",
            placed[(STAT_VALUE_X["hit"], STAT_Y["hit"])].text,
        )
        self.assertEqual(
            placed[(STAT_LABEL_X, STAT_Y["defense"])].text,
            "ぼうぎょ",
        )
        self.assertEqual(
            placed[(STAT_LABEL_X, STAT_Y["evasion"])].text,
            "かいひりつ",
        )
        self.assertEqual(
            placed[(STAT_LABEL_X, STAT_Y["spell_resistance"])].text,
            "じゅつぼうぎょ",
        )

    def test_dual_wield_member_displays_total_attack_in_equipment_menu(self) -> None:
        mock = self.build_mock(member_index=3)
        placed = {(text.x, text.y): text for text in mock.main_window.texts}

        self.assertEqual(mock.member.definition.key, "Elika")
        self.assertEqual(
            (
                mock.member.battle_stats.attack_right,
                mock.member.battle_stats.attack_left,
            ),
            (39, 27),
        )
        self.assertEqual(
            placed[(STAT_VALUE_X["attack"], STAT_Y["attack"])].text,
            "　６６",
        )
        self.assertEqual(
            placed[(STAT_LABEL_X, TOLERANCE_LABEL_Y)].text,
            "たいせい",
        )
        self.assertEqual(
            TOLERANCE_LABEL_Y - STAT_Y["spell_resistance"],
            3,
        )

    @patch("ui.equipment_menu.pyxel.blt")
    def test_equipment_icons_use_two_pixel_gaps(self, blt: Mock) -> None:
        mock = self.build_mock(member_index=4)
        kinds = mock._equippable_proficiency_kinds()

        mock._draw_equipment_icons()

        calls = blt.call_args_list
        self.assertEqual(len(calls), len(kinds))
        self.assertEqual(
            tuple(call_args.args[0] for call_args in calls),
            tuple(
                mock.main_window.pixel_x
                + HEADER_TEXT_X * 4
                + index * HEADER_EQUIPMENT_COLUMN_PIXEL_WIDTH
                for index in range(len(kinds))
            ),
        )
        self.assertTrue(
            all(
                right.args[0] - left.args[0] - 8
                == HEADER_EQUIPMENT_ICON_GAP
                for left, right in zip(calls, calls[1:])
            )
        )
        self.assertTrue(
            all(
                call_args.args[1]
                == mock.main_window.pixel_y + HEADER_EQUIPMENT_ICON_PIXEL_Y
                for call_args in calls
            )
        )

    @patch("ui.equipment_menu.pyxel.text")
    def test_weapon_levels_use_right_aligned_pyxel_text_below_icons(
        self,
        text: Mock,
    ) -> None:
        mock = self.build_mock(member_index=4)
        kinds = mock._equippable_proficiency_kinds()
        self.assertIn(ProficiencyKind.SHIELD, kinds)
        mock._draw_equipment_levels()

        self.assertEqual(
            text.call_args_list,
            [
                call(
                    mock.main_window.pixel_x
                    + HEADER_TEXT_X * 4
                    + index * HEADER_EQUIPMENT_COLUMN_PIXEL_WIDTH
                    + HEADER_EQUIPMENT_LEVEL_RIGHT_OFFSET,
                    mock.main_window.pixel_y + HEADER_EQUIPMENT_LEVEL_PIXEL_Y,
                    "-"
                    if kind is ProficiencyKind.SHIELD
                    else str(mock.member.proficiency(kind).level),
                    DEFAULT_TEXT_COLOR,
                )
                for index, kind in enumerate(kinds)
            ],
        )
        for args, (index, _kind) in zip(
            text.call_args_list,
            enumerate(kinds),
            strict=True,
        ):
            icon_right = (
                mock.main_window.pixel_x
                + HEADER_TEXT_X * 4
                + index * HEADER_EQUIPMENT_COLUMN_PIXEL_WIDTH
                + 8
            )
            self.assertEqual(args.args[0] + 3, icon_right)
            self.assertEqual(len(args.args), 4)

    def test_equipment_stats_use_three_digit_values_and_sum_dual_attack(
        self,
    ) -> None:
        stats = BattleStats(
            attack_right=40,
            attack_left=32,
            hit_right=HandHit(109, 16, 2),
            hit_left=HandHit(108, 14, 2),
            defense=4,
            evasion=5,
            spell_resistance=6,
        )

        self.assertEqual(
            EquipmentMenuHarness._stat_displays(
                stats,
                include_hit_bonus=False,
            ),
            {
                "attack": "　７２",
                "hit": "１０８",
                "defense": "　　４",
                "evasion": "　　５",
                "spell_resistance": "　　６",
            },
        )

    def test_equipment_slot_labels_use_icons_only_in_japanese_and_english(
        self,
    ) -> None:
        mock = self.build_mock()

        for language, expected_right, expected_body, expected_both in (
            (
                Language.JAPANESE,
                "%RIGHT%：%KNIFE%ダガー",
                "%BODY%：ローブ",
                "%RIGHT%：",
            ),
            (
                Language.ENGLISH,
                "%RIGHT%：%KNIFE%ＤＡＧＧＥＲ",
                "%BODY%：ＲＯＢＥ",
                "%RIGHT%：",
            ),
            (
                Language.SIMPLIFIED_CHINESE,
                "右手：%KNIFE%DAGGER",
                "身体：ROBE",
                "双手：",
            ),
        ):
            with self.subTest(language=language):
                mock.settings = Settings(language=language)
                mock._rebuild()
                placed = {
                    (text.x, text.y): text.text
                    for text in mock.main_window.texts
                }
                self.assertEqual(placed[(MAIN_TEXT_X, 14)], expected_right)
                self.assertEqual(placed[(MAIN_TEXT_X, 20)], expected_body)
                self.assertEqual(mock.labels["slot.both"], expected_both)

    def test_empty_weapon_slots_do_not_display_bare_hand_text(self) -> None:
        mock = self.build_mock()
        mock.member.equipment = mock.member.equipment.replaced(
            {
                EquipmentSlot.RIGHT: None,
                EquipmentSlot.LEFT: None,
            }
        )

        for language, expected_right, expected_left in (
            (Language.JAPANESE, "%RIGHT%：", "%LEFT%："),
            (Language.ENGLISH, "%RIGHT%：", "%LEFT%："),
            (Language.SIMPLIFIED_CHINESE, "右手：", "左手："),
        ):
            with self.subTest(language=language):
                mock.settings = Settings(language=language)
                mock._rebuild()
                placed = {
                    (text.x, text.y): text.text
                    for text in mock.main_window.texts
                }
                self.assertEqual(placed[(MAIN_TEXT_X, 14)], expected_right)
                self.assertEqual(placed[(MAIN_TEXT_X, 17)], expected_left)

    def test_only_npc_initial_equipment_is_fixed_and_positive(self) -> None:
        mock = self.build_mock(member_index=2)

        self.assertTrue(mock.member.is_npc)
        right = next(text for text in mock.main_window.texts if text.y == 14)
        body = next(text for text in mock.main_window.texts if text.y == 20)
        self.assertEqual(right.color, DEFAULT_TEXT_COLOR)
        self.assertEqual(body.color, DEFAULT_TEXT_COLOR)
        for placement in (right, body):
            self.assertIn("：%COL_POSITIVE%", placement.text)
            self.assertNotIn("%COL_POSITIVE%：", placement.text)
        self.assertEqual(mock.selected_slot, EquipmentSlot.RIGHT)
        self.assertTrue(mock.candidates)
        self.assertFalse(mock.equippable_candidate_indexes)

        mock.selected_main_key = EquipmentSlot.HEAD
        mock._rebuild()

        self.assertTrue(mock.candidates)
        self.assertNotIn(None, mock.candidates)
        added = next(item for item in mock.candidates if item is not None)
        self.assertTrue(
            mock.inventory_system.equip(
                mock.member,
                EquipmentSlot.HEAD,
                added,
            )
        )
        mock._rebuild()

        head = next(text for text in mock.main_window.texts if text.y == 23)
        self.assertEqual(head.color, DEFAULT_TEXT_COLOR)
        self.assertIn(None, mock.candidates)

    def test_confirming_npc_initial_equipment_stays_put_and_alerts(self) -> None:
        on_invalid_action = Mock()
        mock = self.build_mock(
            member_index=2,
            on_invalid_action=on_invalid_action,
        )

        closed = mock.update(
            InputState(confirm=InputButton(triggered=True, held=True))
        )

        self.assertFalse(closed)
        self.assertEqual(mock.phase, EquipmentSelectionPhase.MAIN)
        self.assertEqual(mock.selected_main_key, EquipmentSlot.RIGHT)
        self.assertEqual(mock.main_cursor.selected_key, EquipmentSlot.RIGHT)
        on_invalid_action.assert_called_once_with()

    def test_item_preview_uses_status_terms_without_mutating_equipment(self) -> None:
        mock = self.build_mock()
        original = mock.member.equipment.item_at(EquipmentSlot.RIGHT)
        mock.phase = EquipmentSelectionPhase.ITEM
        mock.selected_item_index = next(
            index
            for index, item in enumerate(mock.candidates)
            if item is not None and item.key == "IRON KUNAI"
        )

        mock._rebuild()

        attack = next(
            text
            for text in mock.main_window.texts
            if text.x == STAT_VALUE_X["attack"]
            and text.y == STAT_Y["attack"]
        )
        hit = next(
            text
            for text in mock.main_window.texts
            if text.x == STAT_VALUE_X["hit"] and text.y == STAT_Y["hit"]
        )
        self.assertIn("→", attack.text)
        self.assertIn("→", hit.text)
        self.assertNotIn("（", hit.text)
        self.assertIs(
            mock.member.equipment.item_at(EquipmentSlot.RIGHT),
            original,
        )
        self.assertEqual(mock.inventory_system.quantity("IRON KUNAI"), 1)

    def test_weapon_candidates_prepend_weapon_type_icons(self) -> None:
        mock = self.build_mock()
        visible = mock.candidates[:ITEM_VISIBLE_COUNT]
        texts_by_y = {
            text.y: text.text
            for text in mock.item_list_window.texts
            if text.x == ITEM_TEXT_X
        }

        for row, item in enumerate(visible):
            if item is None:
                continue
            with self.subTest(item=item.key):
                self.assertTrue(
                    texts_by_y[ITEM_FIRST_Y + row * ITEM_ROW_HEIGHT].startswith(
                        f"%{item.subtype}%"
                    )
                )

        mock.selected_main_key = EquipmentSlot.HEAD
        mock._rebuild()
        armor_names = (
            text.text
            for text in mock.item_list_window.texts
            if text.x == ITEM_TEXT_X
        )
        self.assertTrue(all(not name.startswith("%") for name in armor_names))

        mock.settings = Settings(language=Language.ENGLISH)
        mock.selected_main_key = EquipmentSlot.RIGHT
        poison_wand = mock.items["WAND of POISON"]
        poison_index = mock.candidates.index(poison_wand)
        mock.scroll_offset = max(0, poison_index - 3)
        mock.selected_item_index = poison_index
        mock._rebuild()
        name = next(
            text
            for text in mock.item_list_window.texts
            if text.x == ITEM_TEXT_X
            and text.y
            == ITEM_FIRST_Y
            + (poison_index - mock.scroll_offset) * ITEM_ROW_HEIGHT
        )
        self.assertEqual(
            name.text,
            f"%WAND%{poison_wand.localized_name(mock.localizer)}",
        )

    def test_ineligible_items_sort_last_but_remain_cursorable(self) -> None:
        on_invalid_action = Mock()
        mock = self.build_mock(on_invalid_action=on_invalid_action)
        equippable = tuple(
            mock._candidate_is_equippable(index)
            for index in range(len(mock.candidates))
        )
        self.assertEqual(equippable, tuple(sorted(equippable, reverse=True)))
        source_order = tuple(
            item
            for item in mock.inventory_system.items
            if mock._is_item_for_slot(item, EquipmentSlot.RIGHT)
        )
        expected_order = tuple(
            item
            for expected_equippable in (True, False)
            for item in source_order
            if mock.inventory_system.can_equip(
                mock.member,
                EquipmentSlot.RIGHT,
                item,
            )
            is expected_equippable
        )
        self.assertEqual(
            tuple(item for item in mock.candidates if item is not None),
            expected_order,
        )

        disabled_item = mock.items["IRON SWORD"]
        disabled_index = mock.candidates.index(disabled_item)
        self.assertFalse(mock._candidate_is_equippable(disabled_index))
        mock.phase = EquipmentSelectionPhase.ITEM
        mock.selected_item_index = disabled_index
        mock.scroll_offset = disabled_index
        mock._rebuild()

        name = next(
            text
            for text in mock.item_list_window.texts
            if text.x == ITEM_TEXT_X and text.y == ITEM_FIRST_Y
        )
        count = next(
            text
            for text in mock.item_list_window.texts
            if text.x == ITEM_COUNT_X and text.y == ITEM_FIRST_Y
        )
        self.assertEqual(name.color, DISABLED_COLOR)
        self.assertEqual(count.color, DISABLED_COLOR)
        self.assertTrue(mock.item_cursor.targets[0].selectable)
        self.assertEqual(mock.item_cursor.selected_key, disabled_item.key)
        self.assertTrue(mock.item_info_window.texts)

        stat_values = tuple(
            text.text
            for text in mock.main_window.texts
            if text.y in STAT_Y.values() and text.x == STAT_VALUE_X["attack"]
        )
        self.assertFalse(any("→" in value for value in stat_values))
        hit = next(
            text.text
            for text in mock.main_window.texts
            if text.x == STAT_VALUE_X["hit"] and text.y == STAT_Y["hit"]
        )
        self.assertIn("（", hit)
        self.assertFalse(
            any(
                text.y == TOLERANCE_PREVIEW_Y
                for text in mock.main_window.texts
            )
        )

        before = mock.member.equipment.item_at(EquipmentSlot.RIGHT)
        mock.update(InputState(confirm=InputButton(triggered=True, held=True)))
        self.assertIs(mock.member.equipment.item_at(EquipmentSlot.RIGHT), before)
        self.assertEqual(mock.phase, EquipmentSelectionPhase.ITEM)
        on_invalid_action.assert_called_once_with()

    def test_left_hides_one_hand_weapons_without_dual_wield(self) -> None:
        mock = self.build_mock()
        self.assertFalse(mock.member.has_skill("Dual-Wield"))
        mock.selected_main_key = EquipmentSlot.LEFT
        mock._rebuild()

        items = tuple(item for item in mock.candidates if item is not None)
        self.assertTrue(items)
        self.assertTrue(
            all(item.equip_type is ItemEquipType.LEFT for item in items)
        )

        mock.update(InputState(confirm=InputButton(triggered=True, held=True)))
        self.assertEqual(mock.phase, EquipmentSelectionPhase.ITEM)
        self.assertEqual(mock.selected_item_index, 0)
        self.assertIsNotNone(mock.item_cursor.selected_target)
        self.assertFalse(mock.equippable_candidate_indexes)
        before = mock.member.equipment.item_at(EquipmentSlot.LEFT)
        mock.update(InputState(confirm=InputButton(triggered=True, held=True)))
        self.assertIs(mock.member.equipment.item_at(EquipmentSlot.LEFT), before)

    def test_left_shows_one_hand_weapons_with_dual_wield(self) -> None:
        mock = self.build_mock()
        dual_wield = next(
            skill
            for member in mock.party
            for skill in member.skills
            if skill.key == "Dual-Wield"
        )
        mock.member.skills.append(dual_wield)
        mock.selected_main_key = EquipmentSlot.LEFT
        mock._rebuild()

        item_types = {
            item.equip_type for item in mock.candidates if item is not None
        }
        self.assertIn(ItemEquipType.LEFT, item_types)
        self.assertIn(ItemEquipType.RIGHT, item_types)
        self.assertNotIn(ItemEquipType.TWO_HANDS, item_types)

    def test_page_movement_keeps_cursor_on_disabled_pages(self) -> None:
        mock = self.build_mock()
        mock.phase = EquipmentSelectionPhase.ITEM
        mock.selected_item_index = 0
        mock.scroll_offset = 0
        mock._rebuild()

        for _page in range(
            (len(mock.candidates) + ITEM_VISIBLE_COUNT - 1)
            // ITEM_VISIBLE_COUNT
        ):
            self.assertIsNotNone(mock.item_cursor.selected_target)
            self.assertEqual(
                mock.item_cursor.selected_key,
                (
                    REMOVE_KEY
                    if mock.selected_candidate is None
                    else mock.selected_candidate.key
                ),
            )
            mock._move_page(1)

    def test_resistance_preview_shows_only_da2_style_changes(self) -> None:
        mock = self.build_mock()
        mock.phase = EquipmentSelectionPhase.ITEM
        mock.selected_item_index = next(
            index
            for index, item in enumerate(mock.candidates)
            if item is not None and item.key == "SILVER KNIFE"
        )
        mock._rebuild()

        current_paralysis = next(
            text
            for text in mock.main_window.texts
            if text.y == TOLERANCE_ICON_Y
            and text.text == "%PARALIZE_DISABLED%"
        )
        preview = [
            text
            for text in mock.main_window.texts
            if text.y == TOLERANCE_PREVIEW_Y
        ]
        self.assertEqual([text.text for text in preview], ["→", "%PARALIZE%"])
        self.assertEqual(preview[1].x, current_paralysis.x)

        removal = self.build_mock()
        silver_knife = removal.items["SILVER KNIFE"]
        self.assertTrue(
            removal.inventory_system.equip(
                removal.member,
                EquipmentSlot.RIGHT,
                silver_knife,
            )
        )
        removal.phase = EquipmentSelectionPhase.ITEM
        removal.selected_item_index = removal.candidates.index(None)
        removal._rebuild()

        current_paralysis = next(
            text
            for text in removal.main_window.texts
            if text.y == TOLERANCE_ICON_Y and text.text == "%PARALIZE%"
        )
        preview = [
            text
            for text in removal.main_window.texts
            if text.y == TOLERANCE_PREVIEW_Y
        ]
        self.assertEqual(
            [text.text for text in preview],
            ["→", "%PARALIZE_DISABLED%"],
        )
        self.assertEqual(preview[1].x, current_paralysis.x)

    def test_confirm_equips_candidate_and_keeps_source_slot_selected(self) -> None:
        mock = self.build_mock()
        mock.phase = EquipmentSelectionPhase.ITEM
        mock.selected_item_index = next(
            index
            for index, item in enumerate(mock.candidates)
            if item is not None and item.key == "SILVER KNIFE"
        )

        closed = mock.update(
            InputState(confirm=InputButton(triggered=True, held=True))
        )

        self.assertFalse(closed)
        self.assertEqual(mock.phase, EquipmentSelectionPhase.MAIN)
        self.assertEqual(mock.selected_main_key, EquipmentSlot.RIGHT)
        self.assertEqual(
            mock.member.equipment.item_at(EquipmentSlot.RIGHT).key,
            "SILVER KNIFE",
        )
        self.assertEqual(mock.inventory_system.quantity("SILVER KNIFE"), 0)
        self.assertEqual(mock.inventory_system.quantity("DAGGER"), 2)

    def test_member_switch_wraps_and_auto_equipment_is_selectable(self) -> None:
        mock = self.build_mock(member_index=5)
        mock.selected_main_key = AUTO_KEY
        mock._rebuild()

        mock.update(InputState(next_page=InputButton(triggered=True, held=True)))

        self.assertEqual(mock.member_index, 0)
        self.assertEqual(mock.selected_main_key, AUTO_KEY)
        mock.update(InputState(previous_page=InputButton(triggered=True, held=True)))
        self.assertEqual(mock.member_index, 5)
        self.assertEqual(mock.member.definition.key, "Dain")

    @patch("ui.equipment_menu.play_se")
    def test_auto_equipment_plays_save_sound_when_executed(self, play_se: Mock) -> None:
        mock = self.build_mock()
        mock.selected_main_key = AUTO_KEY
        mock._rebuild()
        mock.inventory_system.auto_equip = Mock(return_value=False)

        mock.update(InputState(confirm=InputButton(triggered=True, held=True)))

        mock.inventory_system.auto_equip.assert_called_once_with(mock.member)
        play_se.assert_called_once_with("auto_equip_complete")

    def test_reserve_replaces_formation_text(self) -> None:
        mock = self.build_mock(member_index=5)
        placed = {(text.x, text.y): text for text in mock.main_window.texts}

        self.assertEqual(
            placed[(HEADER_TEXT_X, HEADER_FORMATION_Y)].text,
            "（ひかえ）",
        )

    def test_horizontal_navigation_switches_member_in_main_phase(self) -> None:
        mock = self.build_mock()

        mock.update(InputState(navigation=Direction.RIGHT))
        self.assertEqual(mock.member_index, 1)

        mock.update(InputState(navigation=Direction.LEFT))
        self.assertEqual(mock.member_index, 0)

    def test_only_active_equipment_window_shows_horizontal_navigation(self) -> None:
        mock = self.build_mock()
        self.assertTrue(mock.main_window.active)
        self.assertFalse(mock.item_list_window.active)

        mock.update(InputState(confirm=InputButton(triggered=True, held=True)))

        self.assertFalse(mock.main_window.active)
        self.assertTrue(mock.item_list_window.active)

    @patch("ui.equipment_menu.pyxel.text")
    @patch("ui.equipment_menu.pyxel.blt")
    def test_draws_current_member_face(self, blt, _text) -> None:
        mock = self.build_mock(member_index=1)
        for window in mock.windows:
            window.draw = Mock()
        mock.main_cursor.draw = Mock()

        mock.draw()

        face_position = mock.member.face_position
        self.assertIn(
            call(
                FACE_X,
                FACE_Y,
                mock.faces,
                face_position.x,
                face_position.y,
                FACE_SIZE,
                FACE_SIZE,
                1,
            ),
            blt.call_args_list,
        )

    @patch("ui.equipment_menu.pyxel.text")
    @patch("ui.equipment_menu.pyxel.blt")
    def test_item_selection_draws_inactive_source_and_active_item_cursors(
        self,
        _blt,
        _text,
    ) -> None:
        mock = self.build_mock()
        mock.update(InputState(confirm=InputButton(triggered=True, held=True)))
        for window in mock.windows:
            window.draw = Mock()
        mock.main_cursor.draw = Mock()
        mock.item_cursor.draw = Mock()

        mock.draw()

        self.assertFalse(mock.main_cursor.active)
        self.assertEqual(mock.main_cursor.selected_key, EquipmentSlot.RIGHT)
        mock.main_cursor.draw.assert_called_once_with()
        self.assertTrue(mock.item_cursor.active)
        mock.item_cursor.draw.assert_called_once_with()

    def test_cancel_returns_from_item_phase_before_closing(self) -> None:
        mock = self.build_mock()
        mock.update(InputState(confirm=InputButton(triggered=True, held=True)))
        self.assertEqual(mock.phase, EquipmentSelectionPhase.ITEM)

        self.assertFalse(
            mock.update(InputState(cancel=InputButton(triggered=True, held=True)))
        )
        self.assertEqual(mock.phase, EquipmentSelectionPhase.MAIN)
        self.assertTrue(
            mock.update(InputState(cancel=InputButton(triggered=True, held=True)))
        )

    def test_confirming_head_slot_enters_item_selection(self) -> None:
        mock = self.build_mock()
        for _ in range(3):
            mock.update(InputState(navigation=Direction.DOWN))
        self.assertEqual(mock.main_cursor.selected_key, EquipmentSlot.HEAD)

        closed = mock.update(
            InputState(confirm=InputButton(triggered=True, held=True))
        )

        self.assertFalse(closed)
        self.assertEqual(mock.phase, EquipmentSelectionPhase.ITEM)
        self.assertEqual(mock.main_cursor.selected_key, EquipmentSlot.HEAD)
        self.assertFalse(mock.main_cursor.active)
        self.assertTrue(mock.item_cursor.active)


if __name__ == "__main__":
    unittest.main()
