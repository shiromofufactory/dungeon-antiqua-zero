from __future__ import annotations

import unittest
from unittest.mock import Mock, call, patch

from app.input import Direction, InputButton, InputState
from app.resources import TRANSPARENT_INDEX
from tools.screen_mocks._party_status import (
    PARTY_COLUMN_WIDTH,
    PARTY_FACE_SIZE,
    PARTY_FACE_X,
    PARTY_FACE_Y,
    PARTY_HP_Y,
    PARTY_MAX_HP_Y,
    PARTY_TEXT_X,
    PARTY_WINDOW_GRID,
)
from tools.screen_mocks.item import (
    CATEGORY_CURSOR_X,
    CATEGORY_TEXT_X,
    CATEGORY_TEXT_Y,
    CATEGORY_WINDOW_GRID,
    ITEM_COUNT_X,
    ITEM_CURSOR_X,
    ITEM_FIRST_Y,
    ITEM_INFO_WINDOW_GRID,
    ITEM_INFO_X,
    ITEM_INFO_Y,
    ITEM_INFO_ROW_HEIGHT,
    ITEM_LIST_WINDOW_GRID,
    ITEM_ROW_HEIGHT,
    ITEM_TEXT_X,
    ITEM_VISIBLE_COUNT,
    ItemCategory,
    ItemScreenMock,
    ItemSelectionPhase,
)
from state import Language, Settings


class ItemScreenMockTest(unittest.TestCase):
    def test_builds_da2_layout_with_every_defined_item_owned_once(self) -> None:
        mock = ItemScreenMock()

        self.assertEqual(
            tuple(
                (window.x, window.y, window.width, window.height)
                for window in mock.windows
            ),
            (
                CATEGORY_WINDOW_GRID,
                ITEM_LIST_WINDOW_GRID,
                ITEM_INFO_WINDOW_GRID,
                PARTY_WINDOW_GRID,
            ),
        )
        self.assertEqual(CATEGORY_WINDOW_GRID, (6, 0, 52, 5))
        self.assertEqual(ITEM_LIST_WINDOW_GRID, (0, 5, 33, 39))
        self.assertEqual(ITEM_INFO_WINDOW_GRID, (33, 5, 31, 39))
        self.assertEqual(CATEGORY_TEXT_X, (4, 14, 24, 36))
        self.assertEqual(len(mock.items), 121)
        self.assertEqual(len(mock.inventory), len(mock.items))
        self.assertEqual(set(mock.item_counts.values()), {1})
        self.assertEqual(mock.important_items, ())
        self.assertIs(mock.phase, ItemSelectionPhase.CATEGORY)
        self.assertEqual(mock.category, ItemCategory.USE)
        self.assertTrue(mock.category_cursor.active)
        self.assertFalse(mock.item_cursor.active)
        self.assertEqual(
            [(text.text, text.x, text.y) for text in mock.category_window.texts],
            [
                ("つかう", CATEGORY_TEXT_X[0], CATEGORY_TEXT_Y),
                ("すてる", CATEGORY_TEXT_X[1], CATEGORY_TEXT_Y),
                ("いちらん", CATEGORY_TEXT_X[2], CATEGORY_TEXT_Y),
                ("だいじなもの", CATEGORY_TEXT_X[3], CATEGORY_TEXT_Y),
            ],
        )
        self.assertEqual(
            CATEGORY_CURSOR_X,
            tuple(x - 2 for x in CATEGORY_TEXT_X),
        )
        self.assertEqual(ITEM_CURSOR_X, ITEM_TEXT_X - 2)
        self.assertEqual(
            [
                (target.key, target.x, target.y)
                for target in mock.category_cursor.targets
            ],
            [
                (category, CATEGORY_CURSOR_X[index], CATEGORY_TEXT_Y)
                for index, category in enumerate(ItemCategory)
            ],
        )

        first_page = [
            (text.text, text.x, text.y) for text in mock.item_list_window.texts
        ]
        self.assertEqual(first_page[0], ("きずぐすり", ITEM_TEXT_X, ITEM_FIRST_Y))
        self.assertEqual(first_page[1], ("１", ITEM_COUNT_X, ITEM_FIRST_Y))
        self.assertEqual(len(mock.item_cursor.targets), ITEM_VISIBLE_COUNT)
        self.assertEqual(
            mock.item_cursor.targets[-1].y,
            ITEM_FIRST_Y + (ITEM_VISIBLE_COUNT - 1) * ITEM_ROW_HEIGHT,
        )
        self.assertTrue(mock.item_list_window.horizontal_navigation)
        self.assertTrue(mock.item_list_window.vertical_navigation)
        self.assertEqual(
            [text.text for text in mock.item_info_window.texts],
            ["きずぐすり", "どうぐ"],
        )
        self.assertEqual(
            [
                (text.x, text.y)
                for text in mock.item_info_window.texts
            ],
            [
                (ITEM_INFO_X, ITEM_INFO_Y),
                (ITEM_INFO_X, ITEM_INFO_Y + ITEM_INFO_ROW_HEIGHT),
            ],
        )
        self.assertEqual(
            mock.item_info_window.pixel_x + ITEM_INFO_X * 4,
            140,
        )

    @staticmethod
    def select_item(mock: ItemScreenMock, key: str) -> None:
        mock.phase = ItemSelectionPhase.ITEM
        mock.category_cursor.active = False
        mock.selected_item_index = next(
            index for index, item in enumerate(mock.inventory) if item.key == key
        )
        mock.scroll_offset = mock.selected_item_index
        mock._build_item_windows()

    def test_displays_type_requirement_stats_and_ability_modifiers(self) -> None:
        mock = ItemScreenMock()

        self.select_item(mock, "ELIKA")

        self.assertEqual(
            [text.text for text in mock.item_info_window.texts],
            [
                "エリカ",
                "かたてぶき　／　%SWORD%けん",
                "ラグナのみ",
                "こうげき：５６",
                "めいちゅう：１３０",
                "すばやさ　＋２",
            ],
        )
        self.assertEqual(
            [text.y for text in mock.item_info_window.texts],
            [
                ITEM_INFO_Y,
                ITEM_INFO_Y + ITEM_INFO_ROW_HEIGHT,
                ITEM_INFO_Y + ITEM_INFO_ROW_HEIGHT * 2,
                ITEM_INFO_Y + ITEM_INFO_ROW_HEIGHT * 4,
                ITEM_INFO_Y + ITEM_INFO_ROW_HEIGHT * 5,
                ITEM_INFO_Y + ITEM_INFO_ROW_HEIGHT * 6,
            ],
        )

        self.select_item(mock, "EXCALIBUR")
        self.assertIn(
            "ぶきレベル　９",
            [text.text for text in mock.item_info_window.texts],
        )

        self.select_item(mock, "DWARVEN VEST")
        self.assertEqual(
            mock.item_info_window.texts[1].text,
            "%BODY%からだ　／　だれでも",
        )
        self.assertEqual(mock.item_info_window.texts[2].text, "ようせいをのぞく")

        self.select_item(mock, "EAN SI MANTLE")
        self.assertIn(
            "じゅつぼうぎょ：１０",
            [text.text for text in mock.item_info_window.texts],
        )

    def test_omits_zero_stats_and_keeps_negative_sign(self) -> None:
        mock = ItemScreenMock()

        self.select_item(mock, "IRON ARMOR")

        self.assertEqual(
            [text.text for text in mock.item_info_window.texts],
            [
                "てつのよろい",
                "%BODY%からだ　／　おもいぼうぐ",
                "ぼうぎょ：１２",
                "かいひりつ：－５",
            ],
        )

    def test_displays_two_handed_type_and_each_reach_wording(self) -> None:
        mock = ItemScreenMock()

        self.select_item(mock, "FIRE SPEAR")
        fire_spear_lines = [text.text for text in mock.item_info_window.texts]
        self.assertEqual(
            fire_spear_lines[1],
            "りょうてぶき　／　%SPEAR%やり",
        )
        self.assertEqual(fire_spear_lines[-1], "こうれつから　こうげきかのう")

        self.select_item(mock, "SHURIKENS")
        self.assertEqual(
            mock.item_info_window.texts[-1].text,
            "えんきょりこうげき　かのう",
        )

    def test_displays_equipment_slot_icons_before_head_body_and_arm(self) -> None:
        mock = ItemScreenMock()

        expected = {
            "IRON HELM": "%HEAD%あたま　／　おもいぼうぐ",
            "IRON ARMOR": "%BODY%からだ　／　おもいぼうぐ",
            "DEATH RING": "%ARM%うで　／　だれでも",
        }
        for item_key, type_line in expected.items():
            with self.subTest(item_key=item_key):
                self.select_item(mock, item_key)
                self.assertEqual(mock.item_info_window.texts[1].text, type_line)

    def test_uses_da2_field_healing_wording_for_either_sign(self) -> None:
        mock = ItemScreenMock()

        self.select_item(mock, "DAYBRINGER")
        self.assertIn(
            "ＨＰ　じどうかいふく",
            [text.text for text in mock.item_info_window.texts],
        )

        self.select_item(mock, "DEATH RING")
        self.assertIn(
            "ＨＰ　じょじょにげんしょう",
            [text.text for text in mock.item_info_window.texts],
        )

    def test_reuses_spell_party_panel_layout_and_faces(self) -> None:
        mock = ItemScreenMock()
        placements = {(text.x, text.y): text.text for text in mock.party_window.texts}

        self.assertEqual(placements[(PARTY_TEXT_X, PARTY_HP_Y)], "ＨＰ　４４")
        self.assertEqual(
            placements[(PARTY_TEXT_X + 2, PARTY_MAX_HP_Y)],
            "／　４４",
        )
        mock.windows = tuple(Mock() for _ in mock.windows)
        mock.category_cursor = Mock()
        with patch("tools.screen_mocks._party_status.pyxel.blt") as blt:
            mock.draw()

        self.assertEqual(
            blt.call_args_list,
            [
                call(
                    PARTY_FACE_X + index * PARTY_COLUMN_WIDTH * 4,
                    PARTY_FACE_Y,
                    mock.faces,
                    member.face_position.x,
                    member.face_position.y,
                    PARTY_FACE_SIZE,
                    PARTY_FACE_SIZE,
                    TRANSPARENT_INDEX,
                )
                for index, member in enumerate(mock.party)
            ],
        )

    def test_category_spacing_fits_japanese_and_english_inside_the_frame(self) -> None:
        japanese = ItemScreenMock()
        english = ItemScreenMock(
            settings=Settings(language=Language.ENGLISH),
        )

        japanese_starts = [
            japanese.category_window.pixel_x + text.x * 4
            for text in japanese.category_window.texts
        ]
        english_starts = [
            english.category_window.pixel_x + text.x * 4
            for text in english.category_window.texts
        ]
        self.assertEqual(japanese_starts, english_starts)
        self.assertEqual(
            japanese_starts[1] - (japanese_starts[0] + len("つかう") * 8),
            16,
        )
        self.assertEqual(
            english_starts[1] - (english_starts[0] + len("Use") * 6),
            22,
        )
        important = english.category_window.texts[-1]
        important_end = (
            english.category_window.pixel_x
            + important.x * 4
            + len("Important") * 6
        )
        right_frame_start = (
            english.category_window.pixel_x
            + english.category_window.pixel_width
            - 8
        )
        self.assertLessEqual(important_end, right_frame_start)

    def test_item_selection_scrolls_one_row_at_the_bottom_edge(self) -> None:
        mock = ItemScreenMock()

        mock.update(InputState(confirm=InputButton(True, True)))
        self.assertIs(mock.phase, ItemSelectionPhase.ITEM)
        self.assertFalse(mock.category_cursor.active)
        self.assertTrue(mock.item_cursor.active)

        for _ in range(ITEM_VISIBLE_COUNT - 1):
            mock.update(InputState(navigation=Direction.DOWN))
        self.assertIs(mock.selected_item, mock.inventory[ITEM_VISIBLE_COUNT - 1])
        self.assertEqual(mock.scroll_offset, 0)

        mock.update(InputState(navigation=Direction.DOWN))
        self.assertIs(mock.selected_item, mock.inventory[ITEM_VISIBLE_COUNT])
        self.assertEqual(mock.scroll_offset, 1)
        self.assertEqual(mock.item_cursor.selected_key, mock.selected_item.key)
        visible_names = [
            text.text
            for text in mock.item_list_window.texts
            if text.x == ITEM_TEXT_X
        ]
        self.assertEqual(visible_names[0], "ちりょうやく")
        self.assertEqual(
            visible_names[-1],
            str(mock.inventory[ITEM_VISIBLE_COUNT].localized_name(mock.localizer)),
        )
        self.assertEqual(
            mock.item_info_window.texts[0].text,
            mock.selected_item.localized_name(mock.localizer),
        )

        mock.update(InputState(navigation=Direction.DOWN))
        self.assertEqual(mock.scroll_offset, 2)
        self.assertEqual(
            next(text.text for text in mock.item_list_window.texts if text.x == ITEM_TEXT_X),
            "まほうのくすり",
        )

    def test_item_scroll_indicators_reflect_vertical_input(self) -> None:
        mock = ItemScreenMock()
        mock.update(InputState(confirm=InputButton(True, True)))

        mock.update(InputState(navigation=Direction.DOWN))
        self.assertEqual(mock.item_list_window.vertical_navigation_pressed, 1)

        mock.update(InputState())
        self.assertEqual(mock.item_list_window.vertical_navigation_pressed, 0)

        mock.update(InputState(navigation=Direction.UP))
        self.assertEqual(mock.item_list_window.vertical_navigation_pressed, -1)

    def test_page_input_moves_the_scrolling_viewport_by_ten_rows(self) -> None:
        mock = ItemScreenMock()
        mock.update(InputState(confirm=InputButton(True, True)))
        mock.update(InputState(navigation=Direction.DOWN))

        mock.update(InputState(next_page=InputButton(True, True)))
        self.assertEqual(mock.selected_item_index, ITEM_VISIBLE_COUNT + 1)
        self.assertEqual(mock.scroll_offset, ITEM_VISIBLE_COUNT)
        self.assertEqual(mock.page_index, 1)
        self.assertEqual(mock.item_cursor.selected_key, mock.selected_item.key)
        self.assertGreaterEqual(len(mock.item_info_window.texts), 2)

    def test_longest_japanese_item_name_is_not_truncated_in_the_list(self) -> None:
        mock = ItemScreenMock()
        mock.phase = ItemSelectionPhase.ITEM
        mock.category_cursor.active = False
        mock.selected_item_index = next(
            index
            for index, item in enumerate(mock.inventory)
            if item.key == "FROSTY CHAIN"
        )
        mock.scroll_offset = mock.selected_item_index
        mock._build_item_windows()

        name = next(
            text
            for text in mock.item_list_window.texts
            if text.x == ITEM_TEXT_X
        )
        self.assertEqual(name.text, "こおりのくさりかたびら")
        self.assertLess(
            ITEM_TEXT_X + len(name.text) * 2,
            ITEM_COUNT_X,
        )

    def test_important_items_stay_empty_and_cannot_enter_item_selection(self) -> None:
        mock = ItemScreenMock()
        for _ in range(3):
            mock.update(InputState(navigation=Direction.RIGHT))

        self.assertEqual(mock.category, ItemCategory.IMPORTANT)
        self.assertEqual(mock.category_items, ())
        self.assertEqual(mock.item_list_window.texts, ())
        self.assertEqual(mock.item_info_window.texts, ())
        self.assertFalse(mock.item_list_window.horizontal_navigation)
        self.assertFalse(mock.item_list_window.vertical_navigation)

        mock.update(InputState(confirm=InputButton(True, True)))
        self.assertIs(mock.phase, ItemSelectionPhase.CATEGORY)
        self.assertTrue(mock.category_cursor.active)

    def test_cancel_returns_to_category_then_to_main_menu(self) -> None:
        mock = ItemScreenMock()

        mock.update(InputState(confirm=InputButton(True, True)))
        self.assertFalse(mock.update(InputState(cancel=InputButton(True, True))))
        self.assertIs(mock.phase, ItemSelectionPhase.CATEGORY)
        self.assertTrue(mock.update(InputState(cancel=InputButton(True, True))))


if __name__ == "__main__":
    unittest.main()
