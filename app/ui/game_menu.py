"""DA2-style interruption menu, independent of the suspended screen."""

from __future__ import annotations

from dataclasses import replace
from enum import Enum

if __package__ == "ui":
    from input import Direction, InputState
    from localization import Localizer
    from resources import FontResources
    from state import Settings
    from text_catalog import TextCatalog
else:
    from ..input import Direction, InputState
    from ..localization import Localizer
    from ..resources import FontResources
    from ..state import Settings
    from ..text_catalog import TextCatalog

from .colors import NEGATIVE_COLOR
from .localized_text import LocalizedWindowTextFactory
from .tagged_text import tagged_text_width
from .window import CursorTarget, DEFAULT_TEXT_COLOR, TEXT_GRID_X, WindowFactory

GAME_MENU_WINDOW_GRID = (0, 22, 64, 16)


class GameMenuAction(Enum):
    RESUME = "resume"
    RETURN_TITLE = "return_title"
    QUIT = "quit"


GAME_MENU_COMMANDS = (
    (GameMenuAction.RESUME, "game_menu.resume"),
    (GameMenuAction.RETURN_TITLE, "settings.return_title"),
    (GameMenuAction.QUIT, "settings.quit"),
)


class GameMenuOverlay:
    """Own only the interruption window, cursor, and opening release latch."""

    def __init__(
        self,
        *,
        settings: Settings,
        texts: TextCatalog,
        fonts: FontResources,
    ) -> None:
        localizer = Localizer(settings.language)
        factory = LocalizedWindowTextFactory.from_language(fonts, settings.language)
        placements = []
        for index, (_action, text_key) in enumerate(GAME_MENU_COMMANDS):
            placement = factory.create(
                texts.text(text_key, localizer),
                0,
                2 + index * 4,
                color=(DEFAULT_TEXT_COLOR if index == 0 else NEGATIVE_COLOR),
            )
            placements.append(placement)
        width = max(
            tagged_text_width(
                placement.text,
                placement.font,
                font_spans=placement.font_spans,
            )
            for placement in placements
        )
        left = (GAME_MENU_WINDOW_GRID[2] * TEXT_GRID_X - width) // 2
        grid_x, pixel_offset_x = divmod(left, TEXT_GRID_X)
        placements = [
            replace(placement, x=grid_x, pixel_offset_x=pixel_offset_x)
            for placement in placements
        ]
        self.window = WindowFactory(factory.font).create(
            *GAME_MENU_WINDOW_GRID,
            tuple(placements),
            transparent=True,
            opened=True,
        )
        self.cursor = self.window.set_cursor(
            tuple(
                CursorTarget(placements[index].x - 3, placements[index].y, key=action)
                for index, (action, _text_key) in enumerate(GAME_MENU_COMMANDS)
            )
        )
        self._waiting_for_release = True

    def update(self, input_state: InputState) -> GameMenuAction | None:
        if self._waiting_for_release:
            self._waiting_for_release = any(
                button.held
                for button in (
                    input_state.confirm,
                    input_state.cancel,
                    input_state.interruption,
                )
            )
            return None
        if input_state.interruption.triggered or input_state.cancel.triggered:
            return GameMenuAction.RESUME
        if input_state.confirm.triggered:
            return self.cursor.selected_key
        if input_state.navigation in (Direction.UP, Direction.DOWN):
            index = self.cursor.selected_index
            if index is not None:
                next_index = (index + input_state.navigation.dy) % len(
                    GAME_MENU_COMMANDS
                )
                self.cursor.select_key(GAME_MENU_COMMANDS[next_index][0])
        self.window.update()
        return None

    def draw(self) -> None:
        self.window.draw()
