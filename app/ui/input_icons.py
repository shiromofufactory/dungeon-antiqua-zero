"""Choose tagged-text icons for logical input actions."""

from __future__ import annotations

from types import MappingProxyType

if __package__ == "ui":
    from input import InputAction, InputDevice
else:
    from ..input import InputAction, InputDevice


_INPUT_ICON_TAGS = MappingProxyType(
    {
        InputDevice.KEYBOARD: MappingProxyType(
            {
                InputAction.CONFIRM: "%KEY_Z%",
                InputAction.CANCEL: "%KEY_X%",
                InputAction.MENU: "%KEY_S%",
            }
        ),
        InputDevice.GAMEPAD: MappingProxyType(
            {
                InputAction.CONFIRM: "%GAMEPAD_A%",
                InputAction.CANCEL: "%GAMEPAD_B%",
                InputAction.MENU: "%GAMEPAD_X%",
            }
        ),
    }
)


def input_icon_tag(action: InputAction, device: InputDevice) -> str:
    """Return the tagged-text icon for one logical action and device."""

    if not isinstance(action, InputAction):
        raise TypeError("action must be an InputAction")
    if not isinstance(device, InputDevice):
        raise TypeError("device must be an InputDevice")
    return _INPUT_ICON_TAGS[device][action]


__all__ = ["input_icon_tag"]
