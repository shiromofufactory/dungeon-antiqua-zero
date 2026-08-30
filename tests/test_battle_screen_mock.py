from __future__ import annotations

import unittest
from unittest.mock import Mock, call, patch

from tools.screen_mocks.battle import (
    BattleScreenMock,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
)
from tools.screen_mocks._runtime import FPS
from input import Direction, InputButton, InputState


class BattleScreenMockTest(unittest.TestCase):
    def test_mock_uses_sixty_fps(self) -> None:
        self.assertEqual(FPS, 60)

    def test_draw_uses_explicit_back_to_front_order(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock._draw_background = Mock()
        mock._draw_party = Mock()
        mock._draw_monsters = Mock()
        mock._draw_timeline = Mock()
        mock._draw_windows = Mock()

        manager = Mock()
        manager.attach_mock(mock._draw_background, "background")
        manager.attach_mock(mock._draw_party, "party")
        manager.attach_mock(mock._draw_monsters, "monsters")
        manager.attach_mock(mock._draw_timeline, "timeline")
        manager.attach_mock(mock._draw_windows, "windows")

        mock.draw()

        self.assertEqual(
            manager.mock_calls,
            [
                call.background(),
                call.party(),
                call.monsters(),
                call.timeline(),
                call.windows(),
            ],
        )

    def test_draw_background_is_opaque(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.background = object()

        with patch("tools.screen_mocks.battle.pyxel.blt") as blt:
            mock._draw_background()

        blt.assert_called_once_with(
            0,
            0,
            mock.background,
            0,
            0,
            SCREEN_WIDTH,
            SCREEN_HEIGHT,
        )

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
