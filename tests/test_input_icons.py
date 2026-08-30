from __future__ import annotations

import unittest

from app.input import InputAction, InputDevice
from app.ui.input_icons import input_icon_tag


class InputIconsTest(unittest.TestCase):
    def test_returns_device_specific_tags_for_each_action(self) -> None:
        self.assertEqual(
            input_icon_tag(InputAction.CONFIRM, InputDevice.KEYBOARD),
            "%KEY_Z%",
        )
        self.assertEqual(
            input_icon_tag(InputAction.CANCEL, InputDevice.KEYBOARD),
            "%KEY_X%",
        )
        self.assertEqual(
            input_icon_tag(InputAction.MENU, InputDevice.KEYBOARD),
            "%KEY_S%",
        )
        self.assertEqual(
            input_icon_tag(InputAction.CONFIRM, InputDevice.GAMEPAD),
            "%GAMEPAD_A%",
        )
        self.assertEqual(
            input_icon_tag(InputAction.CANCEL, InputDevice.GAMEPAD),
            "%GAMEPAD_B%",
        )
        self.assertEqual(
            input_icon_tag(InputAction.MENU, InputDevice.GAMEPAD),
            "%GAMEPAD_X%",
        )

    def test_rejects_non_enum_arguments(self) -> None:
        with self.assertRaises(TypeError):
            input_icon_tag("cancel", InputDevice.KEYBOARD)  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            input_icon_tag(InputAction.CANCEL, "keyboard")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
