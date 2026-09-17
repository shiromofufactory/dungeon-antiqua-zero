"""Idle-only menu input hint for the field, without DA2's pause hint."""

from __future__ import annotations

from dataclasses import replace

if __package__ == "ui":
    from input import InputAction, InputState
    from localization import Localizer
    from resources import FontResources
    from state import Language
    from text_catalog import TextCatalog
else:
    from ..input import InputAction, InputState
    from ..localization import Localizer
    from ..resources import FontResources
    from ..state import Language
    from ..text_catalog import TextCatalog

from .input_icons import input_icon_tag
from .localized_text import LocalizedWindowTextFactory
from .tagged_text import tagged_text_width
from .window import TEXT_GRID_X, WindowFactory

FIELD_MENU_GUIDE_IDLE_FRAMES = 60
FIELD_MENU_GUIDE_WINDOW_GRID = (0, 0, 64, 4)
FIELD_MENU_GUIDE_RIGHT_MARGIN = 8
FIELD_MENU_GUIDE_TEXT_KEY = "field.menu_guide"


class FieldMenuGuide:
    """Own the idle timer and non-interactive, transparent hint window."""

    def __init__(self, *, texts: TextCatalog, fonts: FontResources) -> None:
        self.texts = texts
        self.fonts = fonts
        self.idle_frames = 0
        self.window = None
        self._label_key = None

    def reset(self) -> None:
        self.idle_frames = 0
        self.window = None
        self._label_key = None

    def update(self, input_state: InputState, *, idle: bool, language: Language) -> None:
        active_input = (
            input_state.held_direction is not None
            or input_state.navigation is not None
            or any(
                button.held or button.triggered
                for button in (
                    input_state.confirm, input_state.cancel, input_state.menu,
                    input_state.interruption, input_state.previous_page, input_state.next_page,
                )
            )
        )
        if not idle or active_input:
            self.reset()
            return
        self.idle_frames = min(self.idle_frames + 1, FIELD_MENU_GUIDE_IDLE_FRAMES)
        if self.idle_frames < FIELD_MENU_GUIDE_IDLE_FRAMES:
            return
        label_key = (language, input_state.device)
        if self._label_key == label_key:
            return
        factory = LocalizedWindowTextFactory.from_language(self.fonts, language)
        label = self.texts.text(FIELD_MENU_GUIDE_TEXT_KEY, Localizer(language)).replace(
            "%MENU%", input_icon_tag(InputAction.MENU, input_state.device),
        )
        placement = factory.create(label, 0, 1)
        width = tagged_text_width(
            placement.text, placement.font, font_spans=placement.font_spans,
        )
        left = FIELD_MENU_GUIDE_WINDOW_GRID[2] * TEXT_GRID_X - FIELD_MENU_GUIDE_RIGHT_MARGIN - width
        grid_x, pixel_offset_x = divmod(left, TEXT_GRID_X)
        self.window = WindowFactory(factory.font).create(
            *FIELD_MENU_GUIDE_WINDOW_GRID,
            (replace(placement, x=grid_x, pixel_offset_x=pixel_offset_x),),
            transparent=True,
            opened=True,
        )
        self._label_key = label_key

    def draw(self) -> None:
        if self.window is not None:
            self.window.draw()
