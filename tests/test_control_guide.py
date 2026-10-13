from __future__ import annotations

import unittest
from unittest.mock import Mock

from tools._bootstrap import APP_ROOT
from input import Direction, InputButton, InputDevice, InputState
from resources import FontResources
from state import Language, Settings
from text_catalog import TextCatalog
from ui.control_guide import ControlGuideOverlay, ControlGuideResult
from ui.tagged_text import tagged_text_width
from ui.window import WINDOW_ANIMATION_FRAME_COUNT


class ControlGuideTest(unittest.TestCase):
    def overlay(
        self, device: InputDevice = InputDevice.KEYBOARD,
        language: Language = Language.JAPANESE,
    ) -> ControlGuideOverlay:
        return ControlGuideOverlay(
            device=device, settings=Settings(language=language),
            texts=TextCatalog.from_json(APP_ROOT / "data" / "texts.json"),
            fonts=FontResources(), on_confirm=Mock(return_value=True),
        )

    def open(self, overlay: ControlGuideOverlay) -> None:
        for _frame in range(WINDOW_ANIMATION_FRAME_COUNT + 1):
            self.assertIsNone(overlay.update(InputState(device=overlay.device)))
        self.assertTrue(overlay.window.is_open)

    def test_all_languages_and_devices_show_four_actions_with_matching_icons_and_fit(self) -> None:
        for language in Language:
            for device in InputDevice:
                with self.subTest(language=language, device=device):
                    overlay = self.overlay(device, language)
                    self.assertEqual(len(overlay.window.texts), 6)
                    prefix = "KEY" if device is InputDevice.KEYBOARD else "GAMEPAD"
                    icons = ("Z", "X", "S") if device is InputDevice.KEYBOARD else ("A", "B", "X")
                    for row, icon in zip(overlay.window.texts[2:5], icons):
                        self.assertIn(f"%{prefix}_{icon}%", row.text)
                    for line in overlay.window.texts:
                        self.assertLessEqual(
                            line.x * 4 + tagged_text_width(line.text, line.font, font_spans=line.font_spans),
                            overlay.window.pixel_width - 4,
                        )
                        self.assertLessEqual(
                            line.y * 4 + line.baseline_offset + FontResources().line_height_for(language),
                            overlay.window.pixel_height - 4,
                        )

    def test_held_title_confirm_cannot_acknowledge_until_released_and_pressed_again(self) -> None:
        overlay = self.overlay()
        held = InputState(confirm=InputButton(held=True))
        for _frame in range(WINDOW_ANIMATION_FRAME_COUNT + 5):
            self.assertIsNone(overlay.update(held))
        overlay.on_confirm.assert_not_called()
        self.assertIsNone(overlay.update(InputState()))
        self.assertIs(
            overlay.update(InputState(confirm=InputButton(triggered=True, held=True))),
            ControlGuideResult.CONTINUE,
        )
        overlay.on_confirm.assert_called_once_with(InputDevice.KEYBOARD)
        # Remain visible for Game's outgoing fade and ignore repeated synthetic presses.
        self.assertTrue(overlay.window.is_open)
        self.assertIsNone(overlay.update(held))

    def test_cancel_animates_back_without_acknowledging(self) -> None:
        overlay = self.overlay()
        self.open(overlay)
        pressed = InputState(cancel=InputButton(triggered=True, held=True))
        self.assertIsNone(overlay.update(pressed))
        for _frame in range(WINDOW_ANIMATION_FRAME_COUNT - 1):
            self.assertIsNone(overlay.update(pressed))
        self.assertIs(overlay.update(pressed), ControlGuideResult.RETURN_TITLE)
        overlay.on_confirm.assert_not_called()

    def test_switching_device_updates_labels_and_requires_fresh_confirmation(self) -> None:
        overlay = self.overlay()
        self.open(overlay)
        pad_confirm = InputState(device=InputDevice.GAMEPAD, confirm=InputButton(triggered=True, held=True))
        self.assertIsNone(overlay.update(pad_confirm))
        self.assertIs(overlay.device, InputDevice.GAMEPAD)
        self.assertIn("%GAMEPAD_A%", overlay.window.texts[2].text)
        self.assertNotIn("%KEY_Z%", overlay.window.texts[2].text)
        for _frame in range(WINDOW_ANIMATION_FRAME_COUNT + 2):
            self.assertIsNone(overlay.update(InputState(device=InputDevice.GAMEPAD, confirm=InputButton(held=True))))
        overlay.on_confirm.assert_not_called()
        self.assertIsNone(overlay.update(InputState(device=InputDevice.GAMEPAD)))
        self.assertIs(overlay.update(pad_confirm), ControlGuideResult.CONTINUE)
        overlay.on_confirm.assert_called_once_with(InputDevice.GAMEPAD)

    def test_direction_and_menu_do_not_dismiss_and_failed_acknowledgement_keeps_open(self) -> None:
        overlay = self.overlay()
        self.open(overlay)
        for state in (
            InputState(navigation=Direction.UP, held_direction=Direction.UP),
            InputState(menu=InputButton(triggered=True, held=True)),
        ):
            self.assertIsNone(overlay.update(state))
        overlay.on_confirm.assert_not_called()
        overlay.on_confirm.return_value = False
        self.assertIsNone(overlay.update(InputState(confirm=InputButton(triggered=True, held=True))))
        self.assertTrue(overlay.window.is_open)


if __name__ == "__main__":
    unittest.main()
