from __future__ import annotations

import unittest
from unittest.mock import Mock, call, patch

from tools.screen_mocks.battle import (
    FPS,
    BattleScreenMock,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
)
from input import Direction, InputButton, InputState


class BattleScreenMockTest(unittest.TestCase):
    def test_mock_uses_sixty_fps(self) -> None:
        self.assertEqual(FPS, 60)

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

    def test_update_passes_logical_navigation_to_open_command_window(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState(
            navigation=Direction.RIGHT,
            held_direction=Direction.RIGHT,
        )
        mock.command_window = Mock()
        mock.command_window.is_closed = False
        mock.command_window.is_open = True
        mock.command_cursor = Mock()
        mock.selected_command = None

        mock.update()

        mock.command_window.update.assert_called_once_with(Direction.RIGHT)

    def test_first_confirm_opens_closed_command_window(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState(
            confirm=InputButton(triggered=True, held=True)
        )
        mock.command_cursor = Mock()
        mock.command_cursor.selected_key = "attack"
        mock.command_window = Mock()
        mock.command_window.is_closed = True
        mock.command_window.is_open = False
        mock.selected_command = None

        mock.update()

        mock.command_window.open.assert_called_once_with()
        mock.command_window.close.assert_not_called()
        mock.command_window.update.assert_called_once_with(None)
        self.assertIsNone(mock.selected_command)

    def test_second_confirm_obtains_key_and_closes_open_command_window(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState(
            confirm=InputButton(triggered=True, held=True)
        )
        mock.command_cursor = Mock()
        mock.command_cursor.selected_key = "attack"
        mock.command_window = Mock()
        mock.command_window.is_closed = False
        mock.command_window.is_open = True
        mock.selected_command = None

        mock.update()

        self.assertEqual(mock.selected_command, "attack")
        mock.command_window.close.assert_called_once_with()
        mock.command_window.open.assert_not_called()
        mock.command_window.update.assert_called_once_with(None)

    def test_cancel_input_quits_before_updating_cursor(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState(
            cancel=InputButton(triggered=True, held=True)
        )
        mock.command_cursor = Mock()
        mock.command_window = Mock()

        with patch("tools.screen_mocks.battle.pyxel.quit") as quit_game:
            mock.update()

        quit_game.assert_called_once_with()
        mock.command_window.update.assert_not_called()


if __name__ == "__main__":
    unittest.main()
