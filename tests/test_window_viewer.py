from __future__ import annotations

import unittest
from unittest.mock import Mock, call, patch

from tools.window_viewer import SCREEN_HEIGHT, SCREEN_WIDTH, WindowViewer


class WindowViewerTest(unittest.TestCase):
    def test_draw_places_windows_over_full_screen_background(self) -> None:
        viewer = WindowViewer.__new__(WindowViewer)
        viewer.background = object()
        first_window = Mock()
        second_window = Mock()
        viewer.windows = (first_window, second_window)
        draw_order: list[str] = []

        first_window.draw.side_effect = lambda: draw_order.append("first_window")
        second_window.draw.side_effect = lambda: draw_order.append("second_window")

        with patch(
            "tools.window_viewer.pyxel.blt",
            side_effect=lambda *args: draw_order.append("background"),
        ) as blt:
            viewer.draw()

        self.assertEqual(
            blt.call_args,
            call(
                0,
                0,
                viewer.background,
                0,
                0,
                SCREEN_WIDTH,
                SCREEN_HEIGHT,
            ),
        )
        self.assertEqual(
            draw_order,
            ["background", "first_window", "second_window"],
        )


if __name__ == "__main__":
    unittest.main()
