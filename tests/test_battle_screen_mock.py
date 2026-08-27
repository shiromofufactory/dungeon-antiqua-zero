from __future__ import annotations

import unittest
from unittest.mock import Mock, call, patch

from tools.screen_mocks.battle import BattleScreenMock, SCREEN_HEIGHT, SCREEN_WIDTH


class BattleScreenMockTest(unittest.TestCase):
    def test_draw_starts_with_background_and_draws_all_windows(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.background = object()
        mock.characters = object()
        mock.monsters = [object() for _ in range(4)]
        first_window = Mock()
        second_window = Mock()
        mock.windows = (first_window, second_window)
        draw_order: list[str] = []

        first_window.draw.side_effect = lambda: draw_order.append("first_window")
        second_window.draw.side_effect = lambda: draw_order.append("second_window")

        with patch(
            "tools.screen_mocks.battle.pyxel.blt",
            side_effect=lambda *args: draw_order.append("blt"),
        ) as blt:
            with patch("tools.screen_mocks.battle.pyxel.rect"):
                mock.draw()

        self.assertEqual(
            blt.call_args_list[0],
            call(
                0,
                0,
                mock.background,
                0,
                0,
                SCREEN_WIDTH,
                SCREEN_HEIGHT,
            ),
        )
        first_index = draw_order.index("first_window")
        second_index = draw_order.index("second_window")
        self.assertEqual(draw_order[0], "blt")
        self.assertLess(first_index, second_index)


if __name__ == "__main__":
    unittest.main()
