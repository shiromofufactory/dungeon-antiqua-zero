from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import pyxel

from tools._bootstrap import APP_ROOT
from tools.screen_mocks._runner import run_screen_mock
from tools.screen_mocks._runtime import (
    FPS,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    create_mock_input_reader,
    initialize_screen_mock,
)


class ScreenMockRuntimeTest(unittest.TestCase):
    def test_initializes_pyxel_and_common_assets(self) -> None:
        with (
            patch("tools.screen_mocks._runtime.pyxel.init") as init,
            patch("tools.screen_mocks._runtime.pyxel.load") as load,
            patch("tools.screen_mocks._runtime.pyxel.load_pal") as load_pal,
        ):
            initialize_screen_mock("Example Mock")

        init.assert_called_once_with(
            SCREEN_WIDTH,
            SCREEN_HEIGHT,
            title="Example Mock",
            fps=FPS,
        )
        load.assert_called_once_with(str(APP_ROOT / "assets.pyxres"))
        load_pal.assert_called_once_with(str(APP_ROOT / "assets.pyxpal"))

    def test_common_input_reader_adds_q_to_cancel(self) -> None:
        reader = create_mock_input_reader()

        self.assertIn(pyxel.KEY_Q, reader.bindings.cancel)
        self.assertIn(pyxel.KEY_ESCAPE, reader.bindings.cancel)

    def test_runner_returns_zero_after_success(self) -> None:
        factory = Mock()

        result = run_screen_mock(factory, expected_errors=(RuntimeError,))

        self.assertEqual(result, 0)
        factory.assert_called_once_with()

    def test_runner_reports_expected_error(self) -> None:
        factory = Mock(side_effect=RuntimeError("broken"))

        with patch("builtins.print") as print_error:
            result = run_screen_mock(
                factory,
                expected_errors=(RuntimeError,),
            )

        self.assertEqual(result, 1)
        print_error.assert_called_once()

    def test_runner_maps_keyboard_interrupt_to_130(self) -> None:
        factory = Mock(side_effect=KeyboardInterrupt)

        result = run_screen_mock(factory, expected_errors=())

        self.assertEqual(result, 130)


if __name__ == "__main__":
    unittest.main()
