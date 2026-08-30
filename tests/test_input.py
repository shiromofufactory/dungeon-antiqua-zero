from __future__ import annotations

import unittest

import pyxel

from app.input import (
    Direction,
    InputDevice,
    InputBindings,
    InputState,
    PyxelInputReader,
)


class FakePyxelInput:
    def __init__(self) -> None:
        self.held: set[int] = set()
        self.axes: dict[int, int] = {}

    def btn(self, button: int) -> bool:
        return button in self.held

    def btnv(self, axis: int) -> int:
        return self.axes.get(axis, 0)


def test_bindings() -> InputBindings:
    return InputBindings(
        up=(1,),
        down=(2,),
        left=(3,),
        right=(4,),
        confirm=(5,),
        cancel=(6,),
        menu=(7,),
        previous_page=(8,),
        next_page=(9,),
    )


class PyxelInputReaderTest(unittest.TestCase):
    def test_navigation_triggers_immediately_and_repeats_after_delay(self) -> None:
        backend = FakePyxelInput()
        reader = PyxelInputReader(
            test_bindings(),
            repeat_delay=3,
            repeat_interval=2,
            backend=backend,
        )
        backend.held.add(1)

        states = [reader.poll() for _ in range(6)]

        self.assertEqual(
            [state.navigation for state in states],
            [
                Direction.UP,
                None,
                None,
                Direction.UP,
                None,
                Direction.UP,
            ],
        )
        self.assertTrue(
            all(state.held_direction is Direction.UP for state in states)
        )

    def test_new_direction_takes_priority_then_falls_back_to_held_direction(
        self,
    ) -> None:
        backend = FakePyxelInput()
        reader = PyxelInputReader(test_bindings(), backend=backend)
        backend.held.add(1)
        self.assertIs(reader.poll().navigation, Direction.UP)

        backend.held.add(4)
        state = reader.poll()
        self.assertIs(state.navigation, Direction.RIGHT)
        self.assertIs(state.held_direction, Direction.RIGHT)

        backend.held.remove(4)
        state = reader.poll()
        self.assertIs(state.navigation, Direction.UP)
        self.assertIs(state.held_direction, Direction.UP)

    def test_action_buttons_trigger_only_on_initial_press(self) -> None:
        backend = FakePyxelInput()
        reader = PyxelInputReader(test_bindings(), backend=backend)
        backend.held.add(5)

        first = reader.poll().confirm
        second = reader.poll().confirm
        backend.held.remove(5)
        released = reader.poll().confirm
        backend.held.add(5)
        pressed_again = reader.poll().confirm

        self.assertTrue(first.triggered)
        self.assertTrue(first.held)
        self.assertFalse(second.triggered)
        self.assertTrue(second.held)
        self.assertFalse(released.triggered)
        self.assertFalse(released.held)
        self.assertTrue(pressed_again.triggered)

    def test_page_buttons_are_separate_from_direction_navigation(self) -> None:
        backend = FakePyxelInput()
        reader = PyxelInputReader(test_bindings(), backend=backend)
        backend.held.update((8, 9))

        first = reader.poll()
        second = reader.poll()

        self.assertIsNone(first.navigation)
        self.assertTrue(first.previous_page.triggered)
        self.assertTrue(first.next_page.triggered)
        self.assertFalse(second.previous_page.triggered)
        self.assertFalse(second.next_page.triggered)

    def test_default_page_buttons_match_da2_lr_controls(self) -> None:
        bindings = InputBindings.default()

        self.assertEqual(
            bindings.previous_page,
            (
                pyxel.KEY_LSHIFT,
                pyxel.GAMEPAD1_BUTTON_LEFTSHOULDER,
            ),
        )
        self.assertEqual(
            bindings.next_page,
            (
                pyxel.KEY_RSHIFT,
                pyxel.GAMEPAD1_BUTTON_RIGHTSHOULDER,
            ),
        )

    def test_analog_axis_uses_deadzone_and_logical_repeat(self) -> None:
        backend = FakePyxelInput()
        reader = PyxelInputReader(
            InputBindings(),
            analog_deadzone=12288,
            backend=backend,
        )
        backend.axes[pyxel.GAMEPAD1_AXIS_LEFTX] = -12288
        self.assertIsNone(reader.poll().held_direction)

        backend.axes[pyxel.GAMEPAD1_AXIS_LEFTX] = -12289
        state = reader.poll()
        self.assertIs(state.navigation, Direction.LEFT)
        self.assertIs(state.held_direction, Direction.LEFT)
        self.assertIs(state.device, InputDevice.GAMEPAD)

    def test_active_device_switches_between_gamepad_and_keyboard(self) -> None:
        backend = FakePyxelInput()
        reader = PyxelInputReader(InputBindings.default(), backend=backend)

        self.assertIs(reader.poll().device, InputDevice.KEYBOARD)

        backend.held.add(pyxel.GAMEPAD1_BUTTON_A)
        self.assertIs(reader.poll().device, InputDevice.GAMEPAD)
        backend.held.clear()
        self.assertIs(reader.poll().device, InputDevice.GAMEPAD)

        backend.held.add(pyxel.KEY_X)
        state = reader.poll()
        self.assertIs(state.device, InputDevice.KEYBOARD)
        self.assertIs(reader.active_device, InputDevice.KEYBOARD)

    def test_input_state_rejects_an_unknown_device(self) -> None:
        with self.assertRaises(TypeError):
            InputState(device="keyboard")  # type: ignore[arg-type]

    def test_extra_cancel_binding_is_added_without_duplicates(self) -> None:
        bindings = test_bindings().with_cancel(8, 6, 9)

        self.assertEqual(bindings.cancel, (6, 8, 9))
        self.assertEqual(test_bindings().cancel, (6,))

    def test_invalid_repeat_settings_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            PyxelInputReader(test_bindings(), repeat_delay=-1)
        with self.assertRaises(ValueError):
            PyxelInputReader(test_bindings(), repeat_interval=0)


if __name__ == "__main__":
    unittest.main()
