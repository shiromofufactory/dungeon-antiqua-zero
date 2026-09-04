from __future__ import annotations

import unittest
from unittest.mock import Mock

from tools._bootstrap import APP_ROOT
from app.input import Direction, InputButton, InputState
from app.member import FacePosition
from app.state import Language, Settings
from app.systems import SAVE_SLOT_COUNT, SaveSlotSummary
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
        on_new_game: Mock | None = None,
        on_load: Mock | None = None,
        on_delete: Mock | None = None,
        on_invalid_action: Mock | None = None,
    ) -> StartMenuOverlay:
        fonts = Mock()
        japanese_font = Mock()
        japanese_font.text_width.side_effect = lambda text: len(text) * 8
        other_font = Mock()
        other_font.text_width.side_effect = lambda text: len(text) * 6
        fonts.font_for.side_effect = lambda language: (
            japanese_font if language is Language.JAPANESE else other_font
        )
        fonts.baseline_offset_for.return_value = 0
        return StartMenuOverlay(
            summaries=summaries() if slot_summaries is None else slot_summaries,
            settings=Settings(),
            texts=TextCatalog.from_json(APP_ROOT / "data" / "texts.json"),
            fonts=fonts,
            faces=object(),
            face_positions={
                "Fiora": FacePosition(0, 0),
                "Cerion": FacePosition(32, 0),
            },
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


if __name__ == "__main__":
    unittest.main()
