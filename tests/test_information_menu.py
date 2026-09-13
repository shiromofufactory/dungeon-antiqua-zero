from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from tools._bootstrap import APP_ROOT

from game_data import load_items, load_monsters
from input import Direction, InputButton, InputState
from resistance import ResistanceType
from resources import FontRole
from resources.event_messages import EventMessageCatalog
from state import Language, Settings
from systems import (
    MONSTER_COMBAT_FIELD_KEYS,
    MONSTER_TREASURE_ACQUIRED_FIELD_KEY,
    MONSTER_TREASURE_IDENTIFIED_FIELD_KEY,
)
from text_catalog import TextCatalog
from ui import DEFAULT_TEXT_COLOR
from ui.information_menu import (
    INFORMATION_HEADER_WINDOW_GRID,
    INFORMATION_MAIN_WINDOW_GRID,
    MONSTER_DETAIL_WINDOW_GRID,
    MONSTER_LIST_VISIBLE_COUNT,
    MONSTER_LIST_WINDOW_GRID,
    InformationMenuOverlay,
    InformationPhase,
    monster_affinity_icon_row,
)


def input_state(
    *,
    navigation: Direction | None = None,
    confirm: bool = False,
    cancel: bool = False,
    previous_page: bool = False,
    next_page: bool = False,
) -> InputState:
    return InputState(
        navigation=navigation,
        confirm=InputButton(triggered=confirm, held=confirm),
        cancel=InputButton(triggered=cancel, held=cancel),
        previous_page=InputButton(
            triggered=previous_page,
            held=previous_page,
        ),
        next_page=InputButton(triggered=next_page, held=next_page),
    )


class InformationMenuOverlayTest(unittest.TestCase):
    def create_overlay(
        self,
        records: dict[str, set[str]] | None = None,
        *,
        invalid_action: Mock | None = None,
        logs: list[dict[str, object]] | None = None,
        event_messages: EventMessageCatalog | None = None,
        language: Language = Language.JAPANESE,
    ) -> InformationMenuOverlay:
        fonts = Mock()
        font_map = {
            (font_language, role): Mock()
            for font_language in Language
            for role in FontRole
        }
        for font in font_map.values():
            font.text_width.side_effect = lambda text: len(text) * 8
        fonts.font_for.side_effect = (
            lambda font_language, *, role=FontRole.STANDARD: font_map[
                (font_language, role)
            ]
        )
        fonts.baseline_offset_for.return_value = 0
        images = Mock()
        images.image.return_value = object()
        return InformationMenuOverlay(
            monsters=load_monsters(),
            monster_records={} if records is None else records,
            items=load_items(),
            logs=[] if logs is None else logs,
            settings=Settings(language=language),
            texts=TextCatalog.from_json(APP_ROOT / "data" / "texts.json"),
            event_messages=(
                EventMessageCatalog.from_records(())
                if event_messages is None
                else event_messages
            ),
            fonts=fonts,
            images=images,
            on_invalid_action=invalid_action,
        )

    @staticmethod
    def open_monster_book(overlay: InformationMenuOverlay) -> None:
        overlay.update(input_state(navigation=Direction.DOWN))
        overlay.update(input_state(confirm=True))

    def test_starts_at_conversation_log_then_lists_monster_book(self) -> None:
        overlay = self.create_overlay()

        self.assertIs(overlay.phase, InformationPhase.MENU)
        self.assertEqual(overlay.header_cursor.selected_key, "conversation_log")
        self.assertEqual(
            (
                overlay.header_window.x,
                overlay.header_window.y,
                overlay.header_window.width,
                overlay.header_window.height,
            ),
            INFORMATION_HEADER_WINDOW_GRID,
        )
        self.assertEqual(
            (
                overlay.main_window.x,
                overlay.main_window.y,
                overlay.main_window.width,
                overlay.main_window.height,
            ),
            INFORMATION_MAIN_WINDOW_GRID,
        )
        self.assertEqual(
            [text.text for text in overlay.header_window.texts],
            ["かいわログ", "モンスターずかん"],
        )

    def test_empty_conversation_log_alerts_and_stays_in_submenu(self) -> None:
        invalid_action = Mock()
        overlay = self.create_overlay(invalid_action=invalid_action)

        self.assertFalse(overlay.update(input_state(confirm=True)))

        invalid_action.assert_called_once_with()
        self.assertIs(overlay.phase, InformationPhase.MENU)
        self.assertTrue(overlay.header_cursor.active)

    def test_conversation_log_resolves_current_language_and_saved_arguments(
        self,
    ) -> None:
        messages = EventMessageCatalog.from_records(
            (
                {
                    "message_id": "sample.log",
                    "text_ja": ["王様から$COUNT$個もらった"],
                    "text_en": ["Received $COUNT$ items"],
                    "text_zhcn": ["收到$COUNT$件物品"],
                },
            )
        )
        overlay = self.create_overlay(
            logs=[{"message_id": "sample.log", "arguments": {"COUNT": 3}}],
            event_messages=messages,
        )

        displayed = overlay.main_window.texts

        self.assertIsNone(overlay.conversation_cursor)
        self.assertEqual(
            [text.text for text in displayed],
            ["１／１", "王様から３個もらった", ""],
        )
        self.assertIs(displayed[0].font, overlay.log_number_text_factory.font)
        self.assertTrue(
            all(
                text.font is overlay.log_text_factory.font
                for text in displayed[1:]
            )
        )
        self.assertIsNot(displayed[0].font, displayed[1].font)
        self.assertEqual([text.y for text in displayed], [2, 6, 10])
        overlay.fonts.font_for.assert_any_call(
            Language.JAPANESE,
            role=FontRole.LARGE,
        )

    def test_log_counter_uses_fullwidth_8x12_font_in_every_language(self) -> None:
        messages = EventMessageCatalog.from_records(
            (
                {
                    "message_id": "sample.log",
                    "text_ja": ["日本語"],
                    "text_en": ["English"],
                    "text_zhcn": ["简体中文"],
                },
            )
        )

        for language in Language:
            with self.subTest(language=language):
                overlay = self.create_overlay(
                    logs=[
                        {"message_id": "sample.log", "arguments": {}},
                        {"message_id": "sample.log", "arguments": {}},
                        {"message_id": "sample.log", "arguments": {}},
                    ],
                    event_messages=messages,
                    language=language,
                )

                counter = overlay.main_window.texts[0]
                self.assertEqual(counter.text, "１／３")
                self.assertIs(
                    counter.font,
                    overlay.log_number_text_factory.font,
                )
                self.assertIsNot(counter.font, overlay.log_text_factory.font)
                overlay.fonts.font_for.assert_any_call(Language.JAPANESE)

    def test_conversation_log_selection_scrolls_and_cancel_returns_to_header(
        self,
    ) -> None:
        messages = EventMessageCatalog.from_records(
            tuple(
                {
                    "message_id": f"sample.log{index}",
                    "text_ja": [f"会話{index}"],
                    "text_en": [],
                    "text_zhcn": [],
                }
                for index in range(6)
            )
        )
        logs = [
            {"message_id": f"sample.log{index}", "arguments": {}}
            for index in range(6)
        ]
        overlay = self.create_overlay(logs=logs, event_messages=messages)

        overlay.update(input_state(confirm=True))
        overlay.update(input_state(navigation=Direction.UP))
        self.assertEqual(overlay.selected_log_index, 5)
        overlay.update(input_state(navigation=Direction.DOWN))
        for _ in range(4):
            overlay.update(input_state(navigation=Direction.DOWN))

        self.assertIs(overlay.phase, InformationPhase.CONVERSATION_LOG)
        self.assertEqual(overlay.selected_log_index, 4)
        self.assertGreater(overlay.conversation_scroll_row, 0)
        self.assertTrue(overlay.main_window.vertical_navigation)
        self.assertFalse(overlay.update(input_state(cancel=True)))
        self.assertIs(overlay.phase, InformationPhase.MENU)
        self.assertTrue(overlay.header_cursor.active)
        self.assertIsNone(overlay.conversation_cursor)
        self.assertEqual(overlay.header_cursor.selected_key, "conversation_log")

    def test_scroll_keeps_the_selected_log_body_visible(self) -> None:
        messages = EventMessageCatalog.from_records(
            tuple(
                {
                    "message_id": f"sample.log{index}",
                    "text_ja": [f"会話{index}の一行目", f"会話{index}の二行目"],
                    "text_en": [],
                    "text_zhcn": [],
                }
                for index in range(4)
            )
        )
        overlay = self.create_overlay(
            logs=[
                {"message_id": f"sample.log{index}", "arguments": {}}
                for index in range(4)
            ],
            event_messages=messages,
        )
        overlay.update(input_state(confirm=True))

        for _ in range(3):
            overlay.update(input_state(navigation=Direction.DOWN))

        visible_texts = [text.text for text in overlay.main_window.texts]
        self.assertEqual(overlay.selected_log_index, 3)
        self.assertEqual(overlay.conversation_scroll_row, 5)
        self.assertIn("４／４", visible_texts)
        self.assertIn("会話３の一行目", visible_texts)
        self.assertIn("会話３の二行目", visible_texts)
        self.assertLessEqual(max(text.y for text in overlay.main_window.texts), 38)

    def test_category_navigation_swaps_log_body_for_empty_bestiary_body(self) -> None:
        messages = EventMessageCatalog.from_records(
            (
                {
                    "message_id": "sample.log",
                    "text_ja": ["記録"],
                    "text_en": [],
                    "text_zhcn": [],
                },
            )
        )
        overlay = self.create_overlay(
            logs=[{"message_id": "sample.log", "arguments": {}}],
            event_messages=messages,
        )

        self.assertTrue(overlay.main_window.texts)
        overlay.update(input_state(navigation=Direction.DOWN))

        self.assertEqual(overlay.header_cursor.selected_key, "monster_book")
        self.assertEqual(overlay.main_window.texts, ())

    def test_empty_book_alerts_and_stays_in_information_submenu(self) -> None:
        invalid_action = Mock()
        overlay = self.create_overlay(invalid_action=invalid_action)

        overlay.update(input_state(navigation=Direction.DOWN))
        self.assertFalse(overlay.update(input_state(confirm=True)))

        invalid_action.assert_called_once_with()
        self.assertIs(overlay.phase, InformationPhase.MENU)
        self.assertIsNone(overlay.monster_list_window)

    def test_registered_monsters_are_listed_in_master_order(self) -> None:
        monsters = load_monsters()
        overlay = self.create_overlay(
            {
                monsters[4].key: set(),
                monsters[0].key: set(),
                "removed_monster": set(),
            }
        )

        self.assertEqual(
            [(number, monster.key) for number, monster in overlay.registered_monsters],
            [(1, monsters[0].key), (5, monsters[4].key)],
        )
        self.open_monster_book(overlay)

        self.assertIs(overlay.phase, InformationPhase.MONSTER_BOOK)
        self.assertFalse(overlay.header_cursor.active)
        self.assertEqual(
            (
                overlay.monster_list_window.x,
                overlay.monster_list_window.y,
                overlay.monster_list_window.width,
                overlay.monster_list_window.height,
            ),
            MONSTER_LIST_WINDOW_GRID,
        )
        self.assertEqual(
            (
                overlay.monster_detail_window.x,
                overlay.monster_detail_window.y,
                overlay.monster_detail_window.width,
                overlay.monster_detail_window.height,
            ),
            MONSTER_DETAIL_WINDOW_GRID,
        )
        self.assertEqual(
            [text.text for text in overlay.monster_list_window.texts],
            [
                monsters[0].localized_name(overlay.localizer),
                monsters[4].localized_name(overlay.localizer),
            ],
        )

    def test_incomplete_record_hides_stats_and_identification_details(self) -> None:
        monster = load_monsters()[0]
        overlay = self.create_overlay({monster.key: {"profile", "FIRE"}})
        self.open_monster_book(overlay)

        detail = [text.text for text in overlay.monster_detail_window.texts]

        self.assertEqual(detail[0], "Ｎｏ：　１")
        self.assertEqual(detail[1], monster.localized_name(overlay.localizer))
        self.assertTrue(detail[3].startswith("ＬＶ"))
        self.assertTrue(detail[3].endswith("１"))
        self.assertIn("？？？？", detail[4])
        self.assertIn("？？？？", detail[5])
        self.assertIn("しきべつ　されていません", detail)
        self.assertFalse(any("おたから" in text for text in detail))

    def test_complete_record_shows_level_stats_affinities_and_unknown_treasure(
        self,
    ) -> None:
        monster = load_monsters()[0]
        overlay = self.create_overlay(
            {monster.key: set(MONSTER_COMBAT_FIELD_KEYS)}
        )
        self.open_monster_book(overlay)

        detail = [text.text for text in overlay.monster_detail_window.texts]

        self.assertTrue(
            any(text.startswith("ＨＰ") and text.endswith("２５") for text in detail)
        )
        self.assertTrue(
            any(text.startswith("ＭＰ") and text.endswith("０") for text in detail)
        )
        self.assertTrue(
            any(text.startswith("ＬＶ") and text.endswith("１") for text in detail)
        )
        level_index = next(i for i, text in enumerate(detail) if text.startswith("ＬＶ"))
        hp_index = next(i for i, text in enumerate(detail) if text.startswith("ＨＰ"))
        mp_index = next(i for i, text in enumerate(detail) if text.startswith("ＭＰ"))
        self.assertLess(level_index, hp_index)
        self.assertLess(hp_index, mp_index)
        self.assertEqual(
            len(detail[level_index]),
            len(detail[hp_index]),
        )
        self.assertEqual(len(detail[level_index]), len(detail[mp_index]))
        self.assertIn("おたから：？？？？", detail)
        self.assertIn(monster_affinity_icon_row(monster.resistances), detail)
        self.assertIn(monster_affinity_icon_row(monster.weaknesses), detail)
        self.assertNotIn("止", "".join(detail))
        white_labels = {
            "おたから：？？？？",
            "たいせい：",
            "じゃくてん：",
        }
        self.assertTrue(
            all(
                text.color == DEFAULT_TEXT_COLOR
                for text in overlay.monster_detail_window.texts
                if text.text in white_labels
            )
        )

    def test_identify_reveals_the_monster_treasure_name(self) -> None:
        monster = load_monsters()[0]
        fields = set(MONSTER_COMBAT_FIELD_KEYS)
        fields.add(MONSTER_TREASURE_IDENTIFIED_FIELD_KEY)
        overlay = self.create_overlay({monster.key: fields})
        self.open_monster_book(overlay)

        detail = [text.text for text in overlay.monster_detail_window.texts]
        expected_item = overlay.items[monster.treasure_item_key].localized_name(
            overlay.localizer
        )

        self.assertIn(f"おたから：{expected_item}", detail)

    def test_treasure_name_requires_the_per_monster_acquired_flag(self) -> None:
        monster = load_monsters()[0]
        fields = set(MONSTER_COMBAT_FIELD_KEYS)
        fields.add(MONSTER_TREASURE_ACQUIRED_FIELD_KEY)
        overlay = self.create_overlay({monster.key: fields})
        self.open_monster_book(overlay)

        detail = [text.text for text in overlay.monster_detail_window.texts]

        self.assertIn("おたから：ちりょうやく", detail)

    def test_boss_hp_is_shown_after_complete_identification(self) -> None:
        number, monster = next(
            (number, monster)
            for number, monster in enumerate(load_monsters(), start=1)
            if monster.is_boss
        )
        overlay = self.create_overlay(
            {monster.key: set(MONSTER_COMBAT_FIELD_KEYS)}
        )
        self.open_monster_book(overlay)

        detail = [text.text for text in overlay.monster_detail_window.texts]

        self.assertTrue(detail[0].startswith("Ｎｏ："))
        fullwidth_number = str(number).translate(
            str.maketrans("0123456789", "０１２３４５６７８９")
        )
        self.assertTrue(detail[0].endswith(fullwidth_number))
        hp_line = next(text for text in detail if text.startswith("ＨＰ"))
        fullwidth_hp = str(monster.max_hp).translate(
            str.maketrans("0123456789", "０１２３４５６７８９")
        )
        self.assertNotIn("？？？？", hp_line)
        self.assertTrue(hp_line.endswith(fullwidth_hp))
        self.assertTrue(
            any("ＭＰ" in text and "？？？？" not in text for text in detail)
        )

    def test_up_down_and_page_inputs_move_through_all_registered_entries(self) -> None:
        monsters = load_monsters()
        overlay = self.create_overlay({monster.key: set() for monster in monsters})
        self.open_monster_book(overlay)

        overlay.update(input_state(navigation=Direction.UP))
        self.assertEqual(overlay.selected_monster_index, len(monsters) - 1)
        overlay.update(input_state(navigation=Direction.DOWN))
        self.assertEqual(overlay.selected_monster_index, 0)
        overlay.update(input_state(next_page=True))
        self.assertEqual(
            overlay.selected_monster_index,
            MONSTER_LIST_VISIBLE_COUNT,
        )
        overlay.update(input_state(previous_page=True))
        self.assertEqual(overlay.selected_monster_index, 0)

    def test_cancel_returns_to_submenu_before_closing_information(self) -> None:
        monster = load_monsters()[0]
        overlay = self.create_overlay({monster.key: set()})
        self.open_monster_book(overlay)

        self.assertFalse(overlay.update(input_state(cancel=True)))
        self.assertIs(overlay.phase, InformationPhase.MENU)
        self.assertTrue(overlay.header_cursor.active)
        self.assertTrue(overlay.update(input_state(cancel=True)))

    @patch("ui.information_menu.Window.draw")
    @patch("ui.information_menu.pyxel.blt")
    def test_draw_places_selected_monster_in_detail_window(
        self,
        blt: Mock,
        _draw_window: Mock,
    ) -> None:
        monster = load_monsters()[0]
        overlay = self.create_overlay({monster.key: set()})
        self.open_monster_book(overlay)

        overlay.draw()

        image = overlay.images.image.return_value
        blt.assert_called_once_with(
            overlay.monster_detail_window.content_x + 58 - monster.width // 2,
            overlay.monster_detail_window.content_y + 180 - monster.height // 2,
            image,
            0,
            0,
            monster.width,
            monster.height,
            1,
        )
        overlay.images.image.assert_called_once_with(monster.image_resource_id)


class MonsterAffinityIconRowTest(unittest.TestCase):
    def test_uses_enabled_and_disabled_da2_icon_variants(self) -> None:
        row = monster_affinity_icon_row(
            frozenset(
                (
                    ResistanceType.FIRE,
                    ResistanceType.POISON,
                    ResistanceType.STUN,
                )
            )
        )

        self.assertIn("%FIRE%", row)
        self.assertIn("%POISON%", row)
        self.assertIn("%FREEZE_DISABLED%", row)
        self.assertIn("%DEATH_DISABLED%", row)
        self.assertNotIn("STUN", row)
        self.assertNotIn("止", row)


if __name__ == "__main__":
    unittest.main()
