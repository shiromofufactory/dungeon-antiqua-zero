from __future__ import annotations

from contextlib import nullcontext
from dataclasses import replace
import unittest
from unittest.mock import Mock, patch

from tools._bootstrap import APP_ROOT
from app.input import Direction, InputButton, InputState
from app.member import FacePosition
from app.rendering import MONOCHROME_PALETTE
from app.resources import FontRole
from app.state import Language, Settings
from app.systems import AUTO_SAVE_SLOT, SAVE_SLOT_COUNT, SaveSlotSummary
from app.text_catalog import TextCatalog
from app.ui.colors import DISABLED_COLOR
from app.ui.start_menu import START_COMMANDS, StartMenuOverlay


def summaries(*occupied_slots: int) -> tuple[SaveSlotSummary, ...]:
    return tuple(
        SaveSlotSummary(
            slot,
            slot in occupied_slots,
            f"2026-09-{slot:02d}T12:34:56+09:00"
            if slot in occupied_slots
            else None,
            ("Fiora", "Cerion") if slot in occupied_slots else (),
        )
        for slot in range(1, SAVE_SLOT_COUNT + 1)
    )


class StartMenuOverlayTest(unittest.TestCase):
    def create_overlay(
        self,
        slot_summaries: tuple[SaveSlotSummary, ...] | None = None,
        *,
        autosave_summary: SaveSlotSummary | None = None,
        on_new_game: Mock | None = None,
        on_load: Mock | None = None,
        on_delete: Mock | None = None,
        on_invalid_action: Mock | None = None,
        palette_shifter: Mock | None = None,
        language: Language = Language.JAPANESE,
    ) -> StartMenuOverlay:
        fonts = Mock()
        japanese_font = Mock()
        japanese_font.text_width.side_effect = lambda text: len(text) * 8
        japanese_large_font = Mock()
        japanese_large_font.text_width.side_effect = lambda text: len(text) * 12
        other_font = Mock()
        other_font.text_width.side_effect = lambda text: len(text) * 6
        fonts.font_for.side_effect = lambda language, role=FontRole.STANDARD: (
            (japanese_large_font if role is FontRole.LARGE else japanese_font)
            if language is Language.JAPANESE else other_font
        )
        fonts.baseline_offset_for.side_effect = lambda language, role=FontRole.STANDARD: (
            3 if language is Language.ENGLISH else 0
        )
        return StartMenuOverlay(
            summaries=summaries() if slot_summaries is None else slot_summaries,
            autosave_summary=autosave_summary,
            settings=Settings(language=language),
            texts=TextCatalog.from_json(APP_ROOT / "data" / "texts.json"),
            fonts=fonts,
            faces=object(),
            face_positions={
                "Fiora": FacePosition(0, 0),
                "Cerion": FacePosition(32, 0),
            },
            palette_shifter=palette_shifter,
            location_text_keys={"fairy_village": "location.fairy_village"},
            on_new_game=Mock() if on_new_game is None else on_new_game,
            on_load=Mock(return_value=True) if on_load is None else on_load,
            on_delete=Mock(return_value=True) if on_delete is None else on_delete,
            on_invalid_action=(
                Mock() if on_invalid_action is None else on_invalid_action
            ),
        )

    def test_empty_start_focuses_new_game_and_disables_inheritance(self) -> None:
        overlay = self.create_overlay()

        self.assertEqual(overlay.focus, "commands")
        self.assertEqual(overlay.command_cursor.selected_key, "new_game")
        inherit_target = next(
            target
            for target in overlay.command_cursor.targets
            if target.key == "inherit_data"
        )
        inherit_text = next(
            text
            for text in overlay.command_window.texts
            if text.text == "データひきつぎ"
        )
        self.assertFalse(inherit_target.selectable)
        self.assertEqual(inherit_text.color, DISABLED_COLOR)
        self.assertEqual(
            [key for key, _text_key, _x, selectable in START_COMMANDS if selectable],
            ["new_game", "delete_data"],
        )

    def test_existing_data_focuses_latest_slot_and_loads_it(self) -> None:
        on_load = Mock(return_value=True)
        overlay = self.create_overlay(summaries(2, 5), on_load=on_load)

        self.assertEqual(overlay.focus, "slots")
        self.assertEqual(overlay.selected_slot, 5)
        overlay.update(InputState(confirm=InputButton(triggered=True, held=True)))

        on_load.assert_called_once_with(5)

    def test_autosave_is_latest_loadable_slot_and_delete_excludes_it(self) -> None:
        on_load = Mock(return_value=True)
        on_delete = Mock(return_value=True)
        autosave = SaveSlotSummary(
            AUTO_SAVE_SLOT, True, "2026-09-25T12:34:56+09:00", ("Fiora",)
        )
        overlay = self.create_overlay(
            summaries(2),
            autosave_summary=autosave,
            on_load=on_load,
            on_delete=on_delete,
        )

        self.assertEqual(overlay.selected_slot, AUTO_SAVE_SLOT)
        self.assertEqual(overlay.base_slot, AUTO_SAVE_SLOT)
        self.assertEqual([slot.slot for slot in overlay.visible_summaries], [0, 1, 2])
        self.assertEqual(overlay.slot_windows[0].texts[0].text, "［オートセーブ］")
        overlay.update(InputState(confirm=InputButton(triggered=True, held=True)))
        on_load.assert_called_once_with(AUTO_SAVE_SLOT)

        overlay.focus = "commands"
        overlay._build_windows()
        overlay.command_cursor.select_key("delete_data")
        overlay.update(InputState(confirm=InputButton(triggered=True, held=True)))
        self.assertEqual(overlay.mode, "delete")
        self.assertEqual(overlay.selected_slot, 1)
        self.assertEqual(overlay.base_slot, 1)
        self.assertEqual([slot.slot for slot in overlay.visible_summaries], [1, 2, 3])
        overlay.update(InputState(navigation=Direction.UP))
        self.assertEqual(overlay.selected_slot, SAVE_SLOT_COUNT)
        on_delete.assert_not_called()

    def test_autosave_alone_does_not_enable_data_deletion(self) -> None:
        autosave = SaveSlotSummary(
            AUTO_SAVE_SLOT, True, "2026-09-25T12:34:56+09:00", ("Fiora",)
        )
        invalid = Mock()
        overlay = self.create_overlay(
            autosave_summary=autosave, on_invalid_action=invalid
        )
        overlay.focus = "commands"
        overlay._build_windows()
        overlay.command_cursor.select_key("delete_data")

        overlay.update(InputState(confirm=InputButton(triggered=True, held=True)))

        self.assertEqual(overlay.mode, "main")
        invalid.assert_called_once_with()

    @patch("app.ui.start_menu.pyxel.blt")
    @patch("app.ui.window.Window.draw")
    def test_load_locations_include_autosave_and_faces_are_lowered(
        self, _draw_window: Mock, blt: Mock,
    ) -> None:
        slots = list(summaries(1))
        slots[0] = replace(slots[0], map_id="fairy_village")
        overlay = self.create_overlay(
            tuple(slots),
            autosave_summary=SaveSlotSummary(
                AUTO_SAVE_SLOT, True, "2026-09-25T12:34:56+09:00", ("Fiora",),
                map_id="worldmap",
            ),
        )

        overlay.draw()

        self.assertEqual(overlay.slot_windows[0].texts[-1].text, "ワールドマップ")
        self.assertEqual(overlay.slot_windows[1].texts[-1].text, "妖精の里")
        self.assertEqual(overlay.slot_windows[0].texts[-1].y, 2)
        self.assertIs(
            overlay.slot_windows[1].texts[-1].font, overlay.location_text_factory.font
        )
        for window in overlay.slot_windows[:2]:
            self.assertEqual(window.texts[1].x, window.texts[0].x)
            self.assertEqual((window.texts[0].x, window.texts[0].y), (4, 2))
            self.assertEqual((window.texts[1].x, window.texts[1].y), (4, 5))
            self.assertIs(window.texts[1].font, overlay.fonts.font_for(Language.ENGLISH))
            self.assertEqual(window.texts[1].baseline_offset, 3)
        self.assertEqual(
            (overlay.slot_cursor.targets[0].x, overlay.slot_cursor.targets[0].y),
            (2, 2),
        )
        self.assertEqual([item.args[1] for item in blt.call_args_list], [56, 128, 128])

    def test_english_slot_label_uses_standard_english_font(self) -> None:
        overlay = self.create_overlay(language=Language.ENGLISH)

        slot_text = overlay.slot_windows[0].texts[0]

        self.assertEqual(slot_text.text, "Ｓａｖｅ　Ｓｌｏｔ　１")
        self.assertIs(slot_text.font, overlay.text_factory.font)
        self.assertIsNot(slot_text.font, overlay.text_factory.wide_font)
        self.assertEqual(slot_text.font_spans, ())

    def test_empty_slot_reports_invalid_action(self) -> None:
        invalid = Mock()
        on_load = Mock(return_value=True)
        overlay = self.create_overlay(
            summaries(2),
            on_load=on_load,
            on_invalid_action=invalid,
        )
        overlay.selected_slot = 1
        overlay.base_slot = 1
        overlay._build_windows()

        overlay.update(InputState(confirm=InputButton(triggered=True, held=True)))

        on_load.assert_not_called()
        invalid.assert_called_once_with()
        self.assertEqual(
            overlay.command_window.texts[0].text,
            "セーブデータが　ありません",
        )

    def test_command_cursor_skips_disabled_inheritance(self) -> None:
        overlay = self.create_overlay()

        overlay.update(InputState(navigation=Direction.RIGHT))
        self.assertEqual(overlay.command_cursor.selected_key, "delete_data")
        overlay.update(InputState(navigation=Direction.RIGHT))
        self.assertEqual(overlay.command_cursor.selected_key, "new_game")

    def test_new_game_command_calls_owner(self) -> None:
        on_new_game = Mock()
        overlay = self.create_overlay(on_new_game=on_new_game)

        overlay.update(InputState(confirm=InputButton(triggered=True, held=True)))

        on_new_game.assert_called_once_with()

    def test_delete_command_requires_confirmation_and_refreshes_slot(self) -> None:
        on_delete = Mock(return_value=True)
        overlay = self.create_overlay(summaries(1), on_delete=on_delete)
        overlay.focus = "commands"
        overlay.selected_command = "delete_data"
        overlay._build_windows()
        overlay.command_cursor.select_key("delete_data")

        overlay.update(InputState(confirm=InputButton(triggered=True, held=True)))
        self.assertEqual(overlay.mode, "delete")
        overlay.update(InputState(confirm=InputButton(triggered=True, held=True)))
        self.assertEqual(overlay.pending_delete_slot, 1)
        on_delete.assert_not_called()

        for _frame in range(8):
            overlay.update(InputState())
        overlay.update(InputState(confirm=InputButton(triggered=True, held=True)))

        on_delete.assert_called_once_with(1)
        self.assertFalse(overlay.summaries[0].occupied)
        self.assertEqual(
            overlay.command_window.texts[0].text,
            "セーブデータを　さくじょしました",
        )

    @patch("app.ui.start_menu.pyxel.blt")
    @patch("app.ui.window.Window.draw")
    def test_dead_load_preview_face_uses_monochrome_palette(
        self,
        _draw_window: Mock,
        _blt: Mock,
    ) -> None:
        slot_summaries = list(summaries(1))
        slot_summaries[0] = replace(
            slot_summaries[0],
            dead_character_keys=("Cerion",),
        )
        palette_shifter = Mock()
        palette_shifter.shifted.return_value = nullcontext()
        overlay = self.create_overlay(
            tuple(slot_summaries),
            palette_shifter=palette_shifter,
        )

        overlay.draw()

        palette_shifter.shifted.assert_called_once_with(MONOCHROME_PALETTE)


if __name__ == "__main__":
    unittest.main()
