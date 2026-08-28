from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from tools.screen_mocks.status import TRANSPARENT_INDEX, StatusScreenMock


class StatusScreenMockTest(unittest.TestCase):
    def test_draws_all_windows_before_face(self) -> None:
        mock = StatusScreenMock.__new__(StatusScreenMock)
        mock.faces = object()
        first_window = Mock()
        second_window = Mock()
        mock.windows = (first_window, second_window)
        draw_order: list[str] = []

        first_window.draw.side_effect = lambda: draw_order.append("first_window")
        second_window.draw.side_effect = lambda: draw_order.append("second_window")

        with patch(
            "tools.screen_mocks.status.pyxel.blt",
            side_effect=lambda *args: draw_order.append("face"),
        ) as blt:
            mock.draw()

        self.assertEqual(draw_order, ["first_window", "second_window", "face"])
        blt.assert_called_once_with(
            8,
            8,
            mock.faces,
            0,
            0,
            32,
            32,
            TRANSPARENT_INDEX,
        )


if __name__ == "__main__":
    unittest.main()
