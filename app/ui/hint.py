"""Animated, blocking gameplay hints with message-size typography."""

from __future__ import annotations

if __package__ == "ui":
    from input import InputState
    from localization import Localizer
    from resources import FontResources, FontRole
    from state import Language, Settings
    from text_catalog import TextCatalog
else:
    from ..input import InputState
    from ..localization import Localizer
    from ..resources import FontResources, FontRole
    from ..state import Language, Settings
    from ..text_catalog import TextCatalog

from .localized_text import LocalizedWindowTextFactory
from .window import WindowFactory

HINT_WINDOW_GRID = (0, 20, 64, 20)
HINT_TOP_WINDOW_GRID = (0, 0, 64, 20)
HINT_BOTTOM_WINDOW_GRID = (0, 40, 64, 20)
TOP_HINT_TEXT_KEYS = frozenset((
    "hint.load.mission",
    "hint.first_battle",
    "hint.first_dungeon_exit",
    "hint.first_defeat_restart",
))
HINT_TEXT_X = 4
HINT_HEADING_Y = 2
HINT_CJK_ROW_HEIGHT = 4
HINT_ENGLISH_ROW_HEIGHT = 3


class HintOverlay:
    """Own hint input and opening/closing animation without changing gameplay."""

    def __init__(
        self,
        *,
        text_key: str,
        settings: Settings,
        texts: TextCatalog,
        fonts: FontResources,
    ) -> None:
        localizer = Localizer(settings.language)
        self.text_factory = LocalizedWindowTextFactory.from_language(
            fonts, settings.language, role=FontRole.LARGE,
        )
        row_height = (
            HINT_ENGLISH_ROW_HEIGHT
            if settings.language is Language.ENGLISH
            else HINT_CJK_ROW_HEIGHT
        )
        placements = (
            self.text_factory.create(
                texts.text("hint.heading", localizer),
                HINT_TEXT_X, HINT_HEADING_Y,
            ),
            *(
                self.text_factory.create(
                    line, HINT_TEXT_X, HINT_HEADING_Y + (index + 1) * row_height,
                )
                for index, line in enumerate(texts.lines(text_key, localizer))
            ),
        )
        if text_key in TOP_HINT_TEXT_KEYS:
            window_grid = HINT_TOP_WINDOW_GRID
        elif text_key == "hint.first_result":
            window_grid = HINT_BOTTOM_WINDOW_GRID
        else:
            window_grid = HINT_WINDOW_GRID
        self.window = WindowFactory(self.text_factory.font).create(
            *window_grid, placements, opened=False,
        )
        self._waiting_for_release = True
        self.window.open()

    def update(self, input_state: InputState) -> bool:
        """Consume dismissal input and report completion only after closing."""

        was_open = self.window.is_open
        self.window.update()
        if self.window.is_closed:
            return True
        if self._waiting_for_release:
            if not (input_state.confirm.held or input_state.cancel.held):
                self._waiting_for_release = False
            return False
        if was_open and (input_state.confirm.triggered or input_state.cancel.triggered):
            self.window.close()
        return False

    def draw(self) -> None:
        self.window.draw()
