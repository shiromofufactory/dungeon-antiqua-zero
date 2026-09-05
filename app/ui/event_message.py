"""Blocking field/battle event message overlay."""

from __future__ import annotations

from collections.abc import Mapping

import pyxel

if __package__ == "ui":
    from input import InputState
    from localization import Localizer
    from member import FacePosition
    from resources import FontResources, TRANSPARENT_INDEX
    from resources.event_messages import EventMessageCatalog
    from state import Settings
else:
    from ..input import InputState
    from ..localization import Localizer
    from ..member import FacePosition
    from ..resources import FontResources, TRANSPARENT_INDEX
    from ..resources.event_messages import EventMessageCatalog
    from ..state import Settings

from .localized_text import LocalizedWindowTextFactory
from .window import WindowFactory


EVENT_MESSAGE_WINDOW_GRID = (0, 44, 64, 16)
EVENT_MESSAGE_TEXT_X = 4
EVENT_MESSAGE_PORTRAIT_TEXT_X = 12
EVENT_MESSAGE_FIRST_TEXT_Y = 3
EVENT_MESSAGE_LINE_HEIGHT = 3
EVENT_MESSAGE_MAX_LINES = 4
EVENT_MESSAGE_FACE_X = 12
EVENT_MESSAGE_FACE_Y = 192
EVENT_MESSAGE_FACE_SIZE = 32


class EventMessageDataError(RuntimeError):
    """Raised when an event message cannot be represented by the overlay."""


class EventMessageOverlay:
    def __init__(
        self,
        *,
        message_id: str,
        portrait_character_key: str | None,
        settings: Settings,
        messages: EventMessageCatalog,
        fonts: FontResources,
        faces: object,
        face_positions: Mapping[str, FacePosition],
    ) -> None:
        self.message_id = message_id
        self.portrait_character_key = portrait_character_key
        self.faces = faces
        self.face_position = (
            None
            if portrait_character_key is None
            else face_positions.get(portrait_character_key)
        )
        if portrait_character_key is not None and self.face_position is None:
            raise EventMessageDataError(
                f"顔グラフィックが見つかりません: {portrait_character_key}"
            )
        localizer = Localizer(settings.language)
        lines = messages.lines(message_id, localizer)
        if not lines:
            raise EventMessageDataError(
                f"イベントメッセージが見つかりません: {message_id}"
            )
        self._pages = tuple(
            tuple(lines[index : index + EVENT_MESSAGE_MAX_LINES])
            for index in range(0, len(lines), EVENT_MESSAGE_MAX_LINES)
        )
        self._page_index = 0
        self._text_factory = LocalizedWindowTextFactory.from_language(
            fonts, settings.language
        )
        self._text_x = (
            EVENT_MESSAGE_PORTRAIT_TEXT_X
            if self.face_position is not None
            else EVENT_MESSAGE_TEXT_X
        )
        self._window_factory = WindowFactory(fonts.font_for(settings.language))
        self.window = self._create_window()

    def _create_window(self):
        placements = tuple(
            self._text_factory.create(
                line,
                self._text_x,
                EVENT_MESSAGE_FIRST_TEXT_Y + index * EVENT_MESSAGE_LINE_HEIGHT,
            )
            for index, line in enumerate(self._pages[self._page_index])
        )
        return self._window_factory.create(
            *EVENT_MESSAGE_WINDOW_GRID,
            placements,
        )

    def update(self, input_state: InputState) -> bool:
        """Return true when the current message was acknowledged."""

        if not isinstance(input_state, InputState):
            raise TypeError("input_state must be an InputState")
        self.window.update()
        if not self.window.is_open or not input_state.confirm.triggered:
            return False
        if self._page_index + 1 >= len(self._pages):
            return True
        self._page_index += 1
        self.window = self._create_window()
        return False

    def draw(self) -> None:
        self.window.draw()
        if self.face_position is None or not self.window.is_open:
            return
        pyxel.blt(
            EVENT_MESSAGE_FACE_X,
            EVENT_MESSAGE_FACE_Y,
            self.faces,
            self.face_position.x,
            self.face_position.y,
            EVENT_MESSAGE_FACE_SIZE,
            EVENT_MESSAGE_FACE_SIZE,
            TRANSPARENT_INDEX,
        )


__all__ = [
    "EVENT_MESSAGE_FACE_SIZE",
    "EVENT_MESSAGE_MAX_LINES",
    "EVENT_MESSAGE_WINDOW_GRID",
    "EventMessageDataError",
    "EventMessageOverlay",
]
