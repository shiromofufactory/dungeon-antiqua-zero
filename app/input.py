"""Convert Pyxel device input into one immutable logical input snapshot."""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
from enum import Enum
from typing import Any

import pyxel

DEFAULT_REPEAT_DELAY = 20
DEFAULT_REPEAT_INTERVAL = 4
DEFAULT_ANALOG_DEADZONE = 12288

_GAMEPAD1_BUTTONS = frozenset(
    getattr(pyxel, name)
    for name in dir(pyxel)
    if name.startswith("GAMEPAD1_BUTTON_")
)


class Direction(Enum):
    """One cardinal direction used for navigation and held movement."""

    UP = (0, -1)
    DOWN = (0, 1)
    LEFT = (-1, 0)
    RIGHT = (1, 0)

    @property
    def dx(self) -> int:
        return self.value[0]

    @property
    def dy(self) -> int:
        return self.value[1]


class InputDevice(Enum):
    """Physical input family most recently used by the player."""

    KEYBOARD = "keyboard"
    GAMEPAD = "gamepad"


class InputAction(Enum):
    """Logical action that may be represented by an input icon."""

    CONFIRM = "confirm"
    CANCEL = "cancel"
    MENU = "menu"


DIRECTION_PRIORITY = (
    Direction.UP,
    Direction.DOWN,
    Direction.LEFT,
    Direction.RIGHT,
)


@dataclass(frozen=True)
class InputButton:
    """Logical button state for the current frame."""

    triggered: bool = False
    held: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.triggered, bool) or not isinstance(self.held, bool):
            raise TypeError("input button states must be booleans")


@dataclass(frozen=True)
class InputState:
    """Immutable logical input produced once per frame."""

    navigation: Direction | None = None
    held_direction: Direction | None = None
    confirm: InputButton = InputButton()
    cancel: InputButton = InputButton()
    menu: InputButton = InputButton()
    previous_page: InputButton = InputButton()
    next_page: InputButton = InputButton()
    device: InputDevice = InputDevice.KEYBOARD

    def __post_init__(self) -> None:
        if self.navigation is not None and not isinstance(
            self.navigation, Direction
        ):
            raise TypeError("navigation must be a Direction or None")
        if self.held_direction is not None and not isinstance(
            self.held_direction, Direction
        ):
            raise TypeError("held_direction must be a Direction or None")
        for name in (
            "confirm",
            "cancel",
            "menu",
            "previous_page",
            "next_page",
        ):
            if not isinstance(getattr(self, name), InputButton):
                raise TypeError(f"{name} must be an InputButton")
        if not isinstance(self.device, InputDevice):
            raise TypeError("device must be an InputDevice")


@dataclass(frozen=True)
class InputBindings:
    """Physical Pyxel buttons assigned to each logical action."""

    up: tuple[int, ...] = ()
    down: tuple[int, ...] = ()
    left: tuple[int, ...] = ()
    right: tuple[int, ...] = ()
    confirm: tuple[int, ...] = ()
    cancel: tuple[int, ...] = ()
    menu: tuple[int, ...] = ()
    previous_page: tuple[int, ...] = ()
    next_page: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        for binding in fields(self):
            buttons = getattr(self, binding.name)
            if not isinstance(buttons, tuple) or not all(
                isinstance(button, int) for button in buttons
            ):
                raise TypeError(f"{binding.name} bindings must be a tuple of integers")

    @classmethod
    def default(cls) -> InputBindings:
        """Return the initial keyboard and gamepad bindings for ZERO."""

        return cls(
            up=(pyxel.KEY_UP, pyxel.GAMEPAD1_BUTTON_DPAD_UP),
            down=(pyxel.KEY_DOWN, pyxel.GAMEPAD1_BUTTON_DPAD_DOWN),
            left=(pyxel.KEY_LEFT, pyxel.GAMEPAD1_BUTTON_DPAD_LEFT),
            right=(pyxel.KEY_RIGHT, pyxel.GAMEPAD1_BUTTON_DPAD_RIGHT),
            confirm=(pyxel.KEY_Z, pyxel.KEY_RETURN, pyxel.GAMEPAD1_BUTTON_A),
            cancel=(
                pyxel.KEY_X,
                pyxel.KEY_BACKSPACE,
                pyxel.KEY_ESCAPE,
                pyxel.GAMEPAD1_BUTTON_B,
            ),
            menu=(pyxel.KEY_S, pyxel.KEY_TAB, pyxel.GAMEPAD1_BUTTON_X),
            previous_page=(
                pyxel.KEY_LSHIFT,
                pyxel.GAMEPAD1_BUTTON_LEFTSHOULDER,
            ),
            next_page=(
                pyxel.KEY_RSHIFT,
                pyxel.GAMEPAD1_BUTTON_RIGHTSHOULDER,
            ),
        )

    def with_cancel(self, *buttons: int) -> InputBindings:
        """Return bindings with extra physical buttons assigned to cancel."""

        if not all(isinstance(button, int) for button in buttons):
            raise TypeError("cancel bindings must be integers")
        return replace(self, cancel=tuple(dict.fromkeys((*self.cancel, *buttons))))


class PyxelInputReader:
    """Read configured Pyxel inputs and own navigation repeat state."""

    def __init__(
        self,
        bindings: InputBindings | None = None,
        *,
        repeat_delay: int = DEFAULT_REPEAT_DELAY,
        repeat_interval: int = DEFAULT_REPEAT_INTERVAL,
        analog_deadzone: int = DEFAULT_ANALOG_DEADZONE,
        backend: Any = pyxel,
    ) -> None:
        if bindings is None:
            bindings = InputBindings.default()
        if not isinstance(bindings, InputBindings):
            raise TypeError("bindings must be InputBindings")
        if not isinstance(repeat_delay, int) or repeat_delay < 0:
            raise ValueError("repeat_delay must be a non-negative integer")
        if not isinstance(repeat_interval, int) or repeat_interval <= 0:
            raise ValueError("repeat_interval must be a positive integer")
        if (
            not isinstance(analog_deadzone, int)
            or analog_deadzone < 0
            or analog_deadzone > 32767
        ):
            raise ValueError("analog_deadzone must be between 0 and 32767")

        self.bindings = bindings
        self.repeat_delay = repeat_delay
        self.repeat_interval = repeat_interval
        self.analog_deadzone = analog_deadzone
        self._backend = backend
        self._previous_directions = {
            direction: False for direction in DIRECTION_PRIORITY
        }
        self._active_direction: Direction | None = None
        self._direction_hold_frames = 0
        self._previous_buttons = {
            "confirm": False,
            "cancel": False,
            "menu": False,
            "previous_page": False,
            "next_page": False,
        }
        self._active_device = InputDevice.KEYBOARD
        self._bound_buttons = tuple(
            dict.fromkeys(
                button
                for binding in fields(self.bindings)
                for button in getattr(self.bindings, binding.name)
            )
        )

    def poll(self) -> InputState:
        """Read devices once and return this frame's logical input."""

        held_directions = self._read_held_directions()
        navigation, held_direction = self._resolve_direction(held_directions)
        confirm = self._read_action_button("confirm")
        cancel = self._read_action_button("cancel")
        menu = self._read_action_button("menu")
        previous_page = self._read_action_button("previous_page")
        next_page = self._read_action_button("next_page")
        device = self._detect_input_device()
        self._previous_directions = held_directions

        return InputState(
            navigation=navigation,
            held_direction=held_direction,
            confirm=confirm,
            cancel=cancel,
            menu=menu,
            previous_page=previous_page,
            next_page=next_page,
            device=device,
        )

    @property
    def active_device(self) -> InputDevice:
        """Return the device family selected by the latest unambiguous input."""

        return self._active_device

    def _read_held_directions(self) -> dict[Direction, bool]:
        axis_x = self._backend.btnv(pyxel.GAMEPAD1_AXIS_LEFTX)
        axis_y = self._backend.btnv(pyxel.GAMEPAD1_AXIS_LEFTY)
        return {
            Direction.UP: self._buttons_held(self.bindings.up)
            or axis_y < -self.analog_deadzone,
            Direction.DOWN: self._buttons_held(self.bindings.down)
            or axis_y > self.analog_deadzone,
            Direction.LEFT: self._buttons_held(self.bindings.left)
            or axis_x < -self.analog_deadzone,
            Direction.RIGHT: self._buttons_held(self.bindings.right)
            or axis_x > self.analog_deadzone,
        }

    def _resolve_direction(
        self,
        held_directions: dict[Direction, bool],
    ) -> tuple[Direction | None, Direction | None]:
        newly_pressed = [
            direction
            for direction in DIRECTION_PRIORITY
            if held_directions[direction]
            and not self._previous_directions[direction]
        ]
        if newly_pressed:
            next_direction = newly_pressed[0]
        elif (
            self._active_direction is not None
            and held_directions[self._active_direction]
        ):
            next_direction = self._active_direction
        else:
            next_direction = next(
                (
                    direction
                    for direction in DIRECTION_PRIORITY
                    if held_directions[direction]
                ),
                None,
            )

        if next_direction is None:
            self._active_direction = None
            self._direction_hold_frames = 0
            return None, None

        if next_direction != self._active_direction:
            self._active_direction = next_direction
            self._direction_hold_frames = 0
            return next_direction, next_direction

        self._direction_hold_frames += 1
        should_repeat = (
            self._direction_hold_frames >= self.repeat_delay
            and (self._direction_hold_frames - self.repeat_delay)
            % self.repeat_interval
            == 0
        )
        return (next_direction if should_repeat else None), next_direction

    def _read_action_button(self, name: str) -> InputButton:
        held = self._buttons_held(getattr(self.bindings, name))
        triggered = held and not self._previous_buttons[name]
        self._previous_buttons[name] = held
        return InputButton(triggered=triggered, held=held)

    def _buttons_held(self, buttons: tuple[int, ...]) -> bool:
        return any(self._backend.btn(button) for button in buttons)

    def _detect_input_device(self) -> InputDevice:
        keyboard_held = False
        gamepad_held = (
            abs(self._backend.btnv(pyxel.GAMEPAD1_AXIS_LEFTX))
            > self.analog_deadzone
            or abs(self._backend.btnv(pyxel.GAMEPAD1_AXIS_LEFTY))
            > self.analog_deadzone
        )
        for button in self._bound_buttons:
            if not self._backend.btn(button):
                continue
            if button in _GAMEPAD1_BUTTONS:
                gamepad_held = True
            else:
                keyboard_held = True

        if keyboard_held and not gamepad_held:
            self._active_device = InputDevice.KEYBOARD
        elif gamepad_held and not keyboard_held:
            self._active_device = InputDevice.GAMEPAD
        return self._active_device


__all__ = [
    "DEFAULT_ANALOG_DEADZONE",
    "DEFAULT_REPEAT_DELAY",
    "DEFAULT_REPEAT_INTERVAL",
    "Direction",
    "InputAction",
    "InputBindings",
    "InputButton",
    "InputDevice",
    "InputState",
    "PyxelInputReader",
]
