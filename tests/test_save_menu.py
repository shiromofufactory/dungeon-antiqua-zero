from __future__ import annotations

from contextlib import nullcontext
from dataclasses import replace
import unittest
from unittest.mock import Mock, call, patch

from tools._bootstrap import APP_ROOT
from app.input import Direction, InputButton, InputState
from app.member import FacePosition
from app.rendering import MONOCHROME_PALETTE
from app.state import Language, Settings
from app.systems import SaveSlotSummary
from app.text_catalog import TextCatalog
from app.ui.colors import POSITIVE_COLOR
from app.ui.save_menu import (
    SAVE_FACE_COUNT,
    SAVE_FACE_COLUMN_WIDTH,
    SAVE_FACE_FIRST_X,
    SAVE_FACE_ROW_WIDTH,
    SAVE_FACE_SIZE,
    SAVE_MESSAGE_WINDOW_GRID,
    SAVE_SLOT_COUNT,
    SAVE_SLOT_DATE_RIGHT_X,
    SAVE_SLOT_WINDOW_GRID,
    SAVE_VISIBLE_SLOT_COUNT,
    SaveMenuOverlay,
    format_saved_at,
)
from app.ui.window import DEFAULT_TEXT_COLOR


SAVE_TEXTS = TextCatalog.from_records(
    [
        {
            "text_key": "save.select_slot",
            "text_ja": "セーブスロットを せんたくしてください",
            "text_en": "Select a save slot",
            "text_zhcn": "请选择存档槽",
        },
        {
            "text_key": "save.slot",
            "text_ja": "スロット $SLOT$",
            "text_en": "Save Slot $SLOT$",
            "text_zhcn": "存档槽 $SLOT$",
        },
        {
            "text_key": "save.overwrite_confirm",
            "text_ja": "うわがきしますか？",
            "text_en": "Overwrite?",
            "text_zhcn": "要覆盖吗？",
        },
        {
            "text_key": "save.complete",
            "text_ja": "セーブしました",
            "text_en": "Saved",
            "text_zhcn": "已保存",
        },
        {
            "text_key": "save.failed",
            "text_ja": "セーブに しっぱいしました",
            "text_en": "Save failed",
            "text_zhcn": "存档失败",
        },
        {
            "text_key": "settings.yes",
            "text_ja": "はい",
            "text_en": "Yes",
            "text_zhcn": "是",
        },
        {
            "text_key": "settings.no",
            "text_ja": "いいえ",
            "text_en": "No",
            "text_zhcn": "否",
        },
    ]
)

PARTY_CHARACTER_KEYS = (
    "Fiora",
    "Cerion",
    "Alvan",
    "Elika",
    "Ragna",
    "Dain",
)


def summaries(*occupied_slots: int) -> tuple[SaveSlotSummary, ...]:
    return tuple(
        SaveSlotSummary(
            slot,
            slot in occupied_slots,
            f"2026-09-{slot:02d}T12:34:56+09:00" if slot in occupied_slots else None,
            PARTY_CHARACTER_KEYS if slot in occupied_slots else (),
        )
        for slot in range(1, SAVE_SLOT_COUNT + 1)
    )


class SaveMenuOverlayTest(unittest.TestCase):
    def create_overlay(
        self,
        slot_summaries: tuple[SaveSlotSummary, ...] | None = None,
        *,
        current_slot: int | None = None,
        on_save: Mock | None = None,
        palette_shifter: Mock | None = None,
        language: Language = Language.JAPANESE,
    ) -> SaveMenuOverlay:
        fonts = Mock()
        japanese_font = Mock()
        japanese_font.text_width.side_effect = lambda text: len(text) * 8
        other_font = Mock()
        other_font.text_width.side_effect = lambda text: len(text) * 6
        fonts.font_for.side_effect = lambda selected_language: (
            japanese_font
            if selected_language is Language.JAPANESE
            else other_font
        )
        fonts.baseline_offset_for.return_value = 0
        return SaveMenuOverlay(
            summaries=summaries() if slot_summaries is None else slot_summaries,
            current_slot=current_slot,
            settings=Settings(language=language),
            texts=SAVE_TEXTS,
            fonts=fonts,
            faces=object(),
            face_positions={
                "Fiora": FacePosition(0, 0),
                "Cerion": FacePosition(32, 0),
                "Alvan": FacePosition(64, 0),
                "Elika": FacePosition(96, 0),
                "Ragna": FacePosition(128, 0),
                "Dain": FacePosition(160, 0),
            },
            palette_shifter=palette_shifter,
            on_save=Mock() if on_save is None else on_save,
        )

    def test_formats_only_minute_precision_timestamp(self) -> None:
        self.assertEqual(
            format_saved_at("2026-09-04T12:34:56+09:00"),
            "2026/09/04 12:34",
        )
        self.assertEqual(format_saved_at(None), "")
        self.assertEqual(format_saved_at("broken"), "")

    def test_shows_three_slots_and_selects_latest_save(self) -> None:
        overlay = self.create_overlay(summaries(2, 5))

        self.assertEqual(overlay.selected_slot, 5)
        self.assertEqual(overlay.base_slot, 3)
        self.assertEqual(
            [summary.slot for summary in overlay.visible_summaries],
            [3, 4, 5],
        )
        self.assertEqual(len(overlay.visible_summaries), SAVE_VISIBLE_SLOT_COUNT)
        texts = [
            placement.text
            for slot_window in overlay.slot_windows
            for placement in slot_window.texts
        ]
        self.assertIn("スロット　５", texts)
        self.assertIn("２０２６／０９／０５　１２：３４", texts)
        self.assertNotIn("Level", "".join(texts))

    def test_message_window_fills_the_screen_width(self) -> None:
        overlay = self.create_overlay()

        self.assertEqual(SAVE_MESSAGE_WINDOW_GRID, (0, 0, 64, 6))
        self.assertEqual(
            (
                overlay.message_window.x,
                overlay.message_window.y,
                overlay.message_window.width,
                overlay.message_window.height,
            ),
            SAVE_MESSAGE_WINDOW_GRID,
        )

    def test_english_slot_label_uses_standard_english_font(self) -> None:
        overlay = self.create_overlay(language=Language.ENGLISH)

        slot_text = overlay.slot_windows[0].texts[0]

        self.assertEqual(slot_text.text, "Ｓａｖｅ　Ｓｌｏｔ　１")
        self.assertIs(slot_text.font, overlay.text_factory.font)
        self.assertIsNot(slot_text.font, overlay.text_factory.wide_font)
        self.assertEqual(slot_text.font_spans, ())

    def test_dates_are_right_aligned_and_only_latest_is_positive(self) -> None:
        overlay = self.create_overlay(
            summaries(1, 2),
            current_slot=1,
            language=Language.ENGLISH,
        )

        date_texts = []
        for slot_window in overlay.slot_windows[:2]:
            date_text = next(
                text for text in slot_window.texts if text.text.startswith("２０２６")
            )
            date_texts.append(date_text)
            self.assertIs(date_text.font, overlay.date_text_factory.font)
            self.assertIsNot(date_text.font, overlay.text_factory.font)
            self.assertEqual(date_text.font_spans, ())
            self.assertEqual(
                date_text.x * 4 + date_text.font.text_width(date_text.text),
                SAVE_SLOT_DATE_RIGHT_X * 4,
            )
        self.assertEqual(
            [date_text.color for date_text in date_texts],
            [DEFAULT_TEXT_COLOR, POSITIVE_COLOR],
        )

    def test_each_visible_slot_has_its_own_window(self) -> None:
        overlay = self.create_overlay(current_slot=2)

        self.assertEqual(len(overlay.slot_windows), SAVE_VISIBLE_SLOT_COUNT)
        x, first_y, width, height = SAVE_SLOT_WINDOW_GRID
        self.assertEqual(
            [
                (window.x, window.y, window.width, window.height)
                for window in overlay.slot_windows
            ],
            [
                (x, first_y + row * height, width, height)
                for row in range(SAVE_VISIBLE_SLOT_COUNT)
            ],
        )
        self.assertIsNone(overlay.slot_windows[0].cursor)
        self.assertIs(overlay.slot_windows[1].cursor, overlay.slot_cursor)
        self.assertIsNone(overlay.slot_windows[2].cursor)

    def test_vertical_selection_scrolls_and_wraps(self) -> None:
        overlay = self.create_overlay(current_slot=SAVE_SLOT_COUNT)

        overlay.update(InputState(navigation=Direction.DOWN))

        self.assertEqual(overlay.selected_slot, 1)
        self.assertEqual(overlay.base_slot, 1)
        self.assertEqual(
            [summary.slot for summary in overlay.visible_summaries],
            [1, 2, 3],
        )

    @patch("app.ui.save_menu.play_se")
    def test_empty_slot_saves_immediately_and_refreshes_preview(
        self, play_se: Mock
    ) -> None:
        on_save = Mock(
            return_value=SaveSlotSummary(
                1,
                True,
                "2026-09-04T12:34:56+09:00",
                PARTY_CHARACTER_KEYS,
            )
        )
        overlay = self.create_overlay(on_save=on_save)

        should_close = overlay.update(
            InputState(confirm=InputButton(triggered=True, held=True))
        )

        self.assertFalse(should_close)
        on_save.assert_called_once_with(1)
        self.assertEqual(overlay.current_slot, 1)
        self.assertEqual(
            overlay.summaries[0].party_character_keys,
            PARTY_CHARACTER_KEYS,
        )
        self.assertEqual(overlay.message_window.texts[0].text, "セーブしました")
        play_se.assert_called_once_with("save_complete")

    @patch("app.ui.save_menu.play_se")
    def test_occupied_other_slot_requires_overwrite_confirmation(
        self, play_se: Mock
    ) -> None:
        on_save = Mock(
            return_value=SaveSlotSummary(
                1,
                True,
                "2026-09-04T12:34:56+09:00",
                PARTY_CHARACTER_KEYS,
            )
        )
        overlay = self.create_overlay(summaries(1), on_save=on_save)

        overlay.update(InputState(confirm=InputButton(triggered=True, held=True)))

        self.assertEqual(overlay.pending_overwrite_slot, 1)
        self.assertIsNotNone(overlay.confirmation_cursor)
        self.assertTrue(overlay.confirmation_window.is_open)
        self.assertFalse(overlay.confirmation_window.is_animating)
        on_save.assert_not_called()
        play_se.assert_not_called()

        overlay.update(InputState(confirm=InputButton(triggered=True, held=True)))

        on_save.assert_called_once_with(1)
        self.assertIsNone(overlay.confirmation_cursor)
        self.assertEqual(overlay.current_slot, 1)
        play_se.assert_called_once_with("save_complete")

    @patch("app.ui.save_menu.play_se")
    def test_failed_save_does_not_play_complete_sound(self, play_se: Mock) -> None:
        overlay = self.create_overlay(on_save=Mock(return_value=None))

        overlay.update(InputState(confirm=InputButton(triggered=True, held=True)))

        self.assertEqual(overlay.message_window.texts[0].text, "セーブに　しっぱいしました")
        play_se.assert_not_called()

    @patch("app.ui.save_menu.pyxel.blt")
    @patch("app.ui.window.Window.draw")
    def test_draws_only_five_battle_party_faces_in_shop_panel_order(
        self,
        _draw_window: Mock,
        blt: Mock,
    ) -> None:
        overlay = self.create_overlay(summaries(1, 3))
        overlay.selected_slot = 1
        overlay.base_slot = 1
        overlay._build_windows(message_key="save.select_slot")

        overlay.draw()

        self.assertEqual(blt.call_count, SAVE_FACE_COUNT * 2)
        self.assertEqual(
            SAVE_FACE_FIRST_X,
            (256 - SAVE_FACE_ROW_WIDTH) // 2,
        )
        self.assertEqual(
            SAVE_FACE_FIRST_X,
            256
            - (
                SAVE_FACE_FIRST_X
                + SAVE_FACE_COLUMN_WIDTH * (SAVE_FACE_COUNT - 1)
                + SAVE_FACE_SIZE
            ),
        )
        self.assertEqual(
            [call.args[0] for call in blt.call_args_list],
            [
                SAVE_FACE_FIRST_X + SAVE_FACE_COLUMN_WIDTH * index
                for index in range(SAVE_FACE_COUNT)
            ]
            * 2,
        )
        self.assertEqual(
            [call.args[1] for call in blt.call_args_list],
            [52] * SAVE_FACE_COUNT + [196] * SAVE_FACE_COUNT,
        )
        self.assertTrue(
            all(
                call.args[5:7] == (SAVE_FACE_SIZE, SAVE_FACE_SIZE)
                for call in blt.call_args_list
            )
        )

    @patch("app.ui.save_menu.pyxel.blt")
    @patch("app.ui.window.Window.draw")
    def test_multiple_dead_faces_reuse_the_monochrome_palette(
        self,
        _draw_window: Mock,
        _blt: Mock,
    ) -> None:
        slot_summaries = list(summaries(1))
        slot_summaries[0] = replace(
            slot_summaries[0],
            dead_character_keys=("Fiora", "Alvan"),
        )
        palette_shifter = Mock()
        palette_shifter.shifted.side_effect = lambda _name: nullcontext()
        overlay = self.create_overlay(
            tuple(slot_summaries),
            palette_shifter=palette_shifter,
        )

        overlay.draw()

        self.assertEqual(
            palette_shifter.shifted.call_args_list,
            [call(MONOCHROME_PALETTE), call(MONOCHROME_PALETTE)],
        )


if __name__ == "__main__":
    unittest.main()
