from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from tools._bootstrap import APP_ROOT as _APP_ROOT
from input import Direction, InputButton, InputState
from localization import normalize_ascii_display_text
from resources import FontResources
from state import SaveData
from ui.debug_flags import DebugFlagsOverlay, FLAGS_PER_PAGE
from ui.debug_text import DEBUG_TEXT


class DebugFlagsOverlayTest(unittest.TestCase):
    def screen(self, count: int) -> DebugFlagsOverlay:
        # Reverse input to verify stable ID ordering independent of set iteration.
        return DebugFlagsOverlay(
            flag_ids=(f"quest.flag_{index:03}" for index in reversed(range(count))),
            save_data=SaveData(), fonts=FontResources(), alert=Mock(),
        )

    def test_all_hundred_flags_are_reachable_and_editable_across_ten_pages(self) -> None:
        screen = self.screen(100)
        self.assertEqual(screen.page_count, 10)
        visited = []
        for page in range(10):
            self.assertEqual(screen.page, page)
            self.assertIn(
                DEBUG_TEXT.flag_page(page + 1, 10),
                [placement.text for placement in screen.window.texts],
            )
            self.assertEqual(len(screen.cursor.targets), FLAGS_PER_PAGE)
            for _row in range(FLAGS_PER_PAGE):
                visited.append(screen.cursor.selected_key)
                screen.update(InputState(confirm=InputButton(triggered=True)))
                self.assertIn(screen.cursor.selected_key, screen.save_data.event_flags)
                screen.update(InputState(navigation=Direction.DOWN))
            screen.update(InputState(navigation=Direction.RIGHT))
        self.assertEqual(visited, list(screen.flag_ids))
        self.assertEqual(screen.page, 0)
        self.assertEqual(screen.save_data.event_flags, set(screen.flag_ids))
        screen.update(InputState(navigation=Direction.LEFT))
        self.assertEqual(screen.page, 9)

    def test_short_last_page_clamps_selection_and_shoulder_buttons_wrap(self) -> None:
        screen = self.screen(23)
        for _ in range(8):
            screen.update(InputState(navigation=Direction.DOWN))
        self.assertEqual(screen.cursor.selected_key, "quest.flag_008")
        screen.update(InputState(next_page=InputButton(triggered=True)))
        self.assertEqual(screen.cursor.selected_key, "quest.flag_018")
        screen.update(InputState(next_page=InputButton(triggered=True)))
        self.assertEqual(len(screen.cursor.targets), 3)
        self.assertEqual(screen.cursor.selected_key, "quest.flag_022")
        screen.update(InputState(navigation=Direction.DOWN))
        self.assertEqual(screen.cursor.selected_key, "quest.flag_020")
        screen.update(InputState(navigation=Direction.UP))
        self.assertEqual(screen.cursor.selected_key, "quest.flag_022")
        screen.update(InputState(next_page=InputButton(triggered=True)))
        self.assertEqual(screen.cursor.selected_key, "quest.flag_002")
        screen.update(InputState(previous_page=InputButton(triggered=True)))
        self.assertEqual(screen.cursor.selected_key, "quest.flag_022")

    def test_page_boundaries_and_empty_catalog(self) -> None:
        for count, expected_pages in ((0, 1), (1, 1), (10, 1), (11, 2), (101, 11)):
            with self.subTest(count=count):
                screen = self.screen(count)
                self.assertEqual(screen.page_count, expected_pages)
        screen = self.screen(0)
        screen.save_data.event_flags.add("legacy.flag")
        self.assertIsNone(screen.cursor)
        self.assertIn(
            DEBUG_TEXT.no_event_flags,
            [placement.text for placement in screen.window.texts],
        )
        for direction in Direction:
            screen.update(InputState(navigation=direction))
        screen.update(InputState(confirm=InputButton(triggered=True)))
        screen.alert.start.assert_called_once_with()
        self.assertEqual(screen.save_data.event_flags, {"legacy.flag"})
        self.assertEqual(screen.page, 0)
        self.assertTrue(screen.update(InputState(cancel=InputButton(triggered=True))))

    def test_toggle_requires_trigger_and_drawing_does_not_edit_flags(self) -> None:
        screen = self.screen(1)
        screen.update(InputState(confirm=InputButton(held=True)))
        self.assertEqual(screen.save_data.event_flags, set())
        screen.update(InputState(confirm=InputButton(triggered=True)))
        self.assertEqual(screen.save_data.event_flags, {"quest.flag_000"})
        with patch.object(screen.window, "draw") as draw:
            screen.draw()
            draw.assert_called_once_with()
        self.assertEqual(screen.save_data.event_flags, {"quest.flag_000"})
        screen.update(InputState(confirm=InputButton(triggered=True)))
        self.assertEqual(screen.save_data.event_flags, set())

    def test_long_ids_fit_list_and_selected_id_uses_two_detail_lines(self) -> None:
        flag_id = "quest." + "long_flag_name_" * 3
        screen = DebugFlagsOverlay(
            flag_ids=(flag_id,), save_data=SaveData(),
            fonts=FontResources(), alert=Mock(),
        )
        detail = "".join(text.text for text in screen.window.texts if text.y in (39, 42))
        self.assertEqual(detail, normalize_ascii_display_text(flag_id))
        label = next(text for text in screen.window.texts if text.x == 8 and text.y == 7)
        self.assertTrue(label.text.endswith("．．．"))
        self.assertLess(label.x * 4 + label.font.text_width(label.text), 50 * 4)
        self.assertEqual(screen.cursor.selected_key, flag_id)


if __name__ == "__main__":
    unittest.main()
