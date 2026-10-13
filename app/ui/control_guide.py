"""Explain the active input family before continuing from the title."""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum, auto

if __package__ == "ui":
    from input import InputAction, InputDevice, InputState
    from localization import Localizer
    from resources import FontResources
    from state import Settings
    from text_catalog import TextCatalog, TextCatalogError
else:
    from ..input import InputAction, InputDevice, InputState
    from ..localization import Localizer
    from ..resources import FontResources
    from ..state import Settings
    from ..text_catalog import TextCatalog, TextCatalogError

from .input_icons import input_icon_tag
from .localized_text import LocalizedWindowTextFactory
from .window import WindowFactory, WindowText

CONTROL_GUIDE_WINDOW_GRID = (4, 16, 56, 28)
CONTROL_GUIDE_TEXT_X = 4
CONTROL_GUIDE_TEXT_ROWS = (2, 8, 11, 14, 17)
CONTROL_GUIDE_PROMPT_Y = 23


class ControlGuideResult(Enum):
    CONTINUE = auto()
    RETURN_TITLE = auto()


class ControlGuideOverlay:
    """Own startup help, input release, device changes and dismissal animation."""

    def __init__(
        self,
        *,
        device: InputDevice,
        settings: Settings,
        texts: TextCatalog,
        fonts: FontResources,
        on_confirm: Callable[[InputDevice], bool],
    ) -> None:
        self.device = device
        self.texts = texts
        self.localizer = Localizer(settings.language)
        self.text_factory = LocalizedWindowTextFactory.from_language(fonts, settings.language)
        self.on_confirm = on_confirm
        self._waiting_for_release = True
        self._result: ControlGuideResult | None = None
        self._build_window()

    def _build_window(self) -> None:
        self.window = WindowFactory(self.text_factory.font).create(
            *CONTROL_GUIDE_WINDOW_GRID, self._placements(), opened=False,
        )
        self.window.open()

    def _placements(self) -> tuple[WindowText, ...]:
        key = f"start.controls.{self.device.value}"
        lines = self.texts.lines(key, self.localizer)
        prompt = self.texts.text("start.controls.prompt", self.localizer)
        if len(lines) != len(CONTROL_GUIDE_TEXT_ROWS) or not all(lines) or not prompt:
            raise TextCatalogError(f"操作説明のテキストが不正です: {key}")
        replacements = {
            "%CONFIRM%": input_icon_tag(InputAction.CONFIRM, self.device),
            "%CANCEL%": input_icon_tag(InputAction.CANCEL, self.device),
            "%MENU%": input_icon_tag(InputAction.MENU, self.device),
            "%MENU_ALTERNATE%": "%GAMEPAD_Y%",
        }

        def placement(line: str, y: int) -> WindowText:
            for token, icon in replacements.items():
                line = line.replace(token, icon)
            return self.text_factory.create(line, CONTROL_GUIDE_TEXT_X, y)

        return (
            *(placement(line, y) for line, y in zip(lines, CONTROL_GUIDE_TEXT_ROWS)),
            placement(prompt, CONTROL_GUIDE_PROMPT_Y),
        )

    def update(self, input_state: InputState) -> ControlGuideResult | None:
        was_open = self.window.is_open
        self.window.update()
        if self.window.is_closed:
            return self._result
        if self._result is not None:
            return None
        if input_state.device is not self.device:
            self.device = input_state.device
            self._build_window()
            self._waiting_for_release = True
        if self._waiting_for_release:
            if not (input_state.confirm.held or input_state.cancel.held):
                self._waiting_for_release = False
            return None
        if was_open and input_state.cancel.triggered:
            self._result = ControlGuideResult.RETURN_TITLE
            self.window.close()
        elif was_open and input_state.confirm.triggered and self.on_confirm(self.device):
            self._result = ControlGuideResult.CONTINUE
            return self._result
        return None

    def draw(self) -> None:
        self.window.draw()
