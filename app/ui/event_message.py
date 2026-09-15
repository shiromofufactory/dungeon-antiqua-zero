"""Blocking field/battle event message overlay."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

import pyxel

if __package__ == "ui":
    from input import InputState
    from localization import Localizer
    from member import FacePosition
    from resources import FontResources, FontRole, TRANSPARENT_INDEX
    from resources.event_messages import EventMessageCatalog
    from state import Language, Settings
else:
    from ..input import InputState
    from ..localization import Localizer
    from ..member import FacePosition
    from ..resources import FontResources, FontRole, TRANSPARENT_INDEX
    from ..resources.event_messages import EventMessageCatalog
    from ..state import Language, Settings

from .localized_text import LocalizedWindowTextFactory
from .window import WindowFactory, WindowText

EVENT_MESSAGE_WINDOW_GRID = (0, 0, 64, 12)
EVENT_MESSAGE_TEXT_X = 4
EVENT_MESSAGE_PORTRAIT_TEXT_X = 12
EVENT_MESSAGE_FIRST_TEXT_Y = 2
EVENT_MESSAGE_CJK_LINE_STEP = 4
EVENT_MESSAGE_CJK_MAX_LINES = 2
EVENT_MESSAGE_ENGLISH_LINE_STEP = 3
EVENT_MESSAGE_ENGLISH_MAX_LINES = 3
EVENT_MESSAGE_FACE_X = 8
EVENT_MESSAGE_FACE_Y = 8
EVENT_MESSAGE_FACE_SIZE = 32
EVENT_MESSAGE_FONT_ROLE = FontRole.LARGE
EVENT_MESSAGE_CHARACTERS_PER_FRAME = 1
EVENT_MESSAGE_FAST_CHARACTERS_PER_FRAME = 2
EVENT_MESSAGE_WAIT_ARROW_BANK = 0
EVENT_MESSAGE_WAIT_ARROW_SOURCE = (88, 16)
EVENT_MESSAGE_WAIT_ARROW_SIZE = 8
EVENT_MESSAGE_WAIT_ARROW_BLINK_FRAMES = 30


def _page_layout_for(language: Language) -> tuple[int, int]:
    """Return page line count and 4px-grid line step for one language."""

    if language is Language.ENGLISH:
        return EVENT_MESSAGE_ENGLISH_MAX_LINES, EVENT_MESSAGE_ENGLISH_LINE_STEP
    return EVENT_MESSAGE_CJK_MAX_LINES, EVENT_MESSAGE_CJK_LINE_STEP


class EventMessageDataError(RuntimeError):
    """Raised when an event message cannot be represented by the overlay."""


class MessageOverlay:
    """Display already-localized lines with the standard blocking message UI."""

    def __init__(
        self,
        *,
        lines: tuple[str, ...],
        settings: Settings,
        fonts: FontResources,
        faces: object | None = None,
        face_position: FacePosition | None = None,
    ) -> None:
        if not lines or not all(isinstance(line, str) for line in lines):
            raise EventMessageDataError("メッセージは1行以上必要です。")
        self.faces = faces
        self.face_position = face_position
        self._max_lines, self._line_step = _page_layout_for(settings.language)
        self._pages = tuple(
            tuple(lines[index : index + self._max_lines])
            for index in range(0, len(lines), self._max_lines)
        )
        self._page_index = 0
        self._visible_character_count = 0
        self._wait_arrow_frame = 0
        self._text_factory = LocalizedWindowTextFactory.from_language(
            fonts,
            settings.language,
            role=EVENT_MESSAGE_FONT_ROLE,
        )
        self._text_x = (
            EVENT_MESSAGE_PORTRAIT_TEXT_X
            if self.face_position is not None
            else EVENT_MESSAGE_TEXT_X
        )
        self._window_factory = WindowFactory(self._text_factory.font)
        self._page_placements = self._create_page_placements()
        self.window = self._create_window()
        self.window.open()

    def _create_page_placements(self) -> tuple[WindowText, ...]:
        return tuple(
            self._text_factory.create(
                line,
                self._text_x,
                EVENT_MESSAGE_FIRST_TEXT_Y + index * self._line_step,
            )
            for index, line in enumerate(self._pages[self._page_index])
        )

    @property
    def _page_character_count(self) -> int:
        return sum(len(placement.text) for placement in self._page_placements)

    @property
    def _page_is_complete(self) -> bool:
        return self._visible_character_count >= self._page_character_count

    @property
    def _wait_arrow_is_visible(self) -> bool:
        return self._wait_arrow_frame // EVENT_MESSAGE_WAIT_ARROW_BLINK_FRAMES % 2 == 0

    def _visible_page_placements(self) -> tuple[WindowText, ...]:
        remaining = self._visible_character_count
        placements: list[WindowText] = []
        for placement in self._page_placements:
            visible_count = min(len(placement.text), remaining)
            font_spans = tuple(
                replace(span, end=min(span.end, visible_count))
                for span in placement.font_spans
                if span.start < visible_count
            )
            placements.append(
                replace(
                    placement,
                    text=placement.text[:visible_count],
                    font_spans=font_spans,
                )
            )
            remaining -= visible_count
        return tuple(placements)

    def _create_window(self):
        return self._window_factory.create(
            *EVENT_MESSAGE_WINDOW_GRID,
            self._visible_page_placements(),
            opened=False,
        )

    def _refresh_visible_text(self) -> None:
        self.window.clear_texts()
        for placement in self._visible_page_placements():
            self.window.add_text(
                placement.text,
                placement.x,
                placement.y,
                color=placement.color,
                font=placement.font,
                shadow_color=placement.shadow_color,
                baseline_offset=placement.baseline_offset,
                font_spans=placement.font_spans,
            )

    def update(self, input_state: InputState) -> bool:
        """Return true when the current message was acknowledged."""

        if not isinstance(input_state, InputState):
            raise TypeError("input_state must be an InputState")
        was_open = self.window.is_open
        self.window.update()
        if not was_open:
            return False
        if not self._page_is_complete:
            characters_per_frame = (
                EVENT_MESSAGE_FAST_CHARACTERS_PER_FRAME
                if input_state.confirm.held
                else EVENT_MESSAGE_CHARACTERS_PER_FRAME
            )
            self._visible_character_count = min(
                self._page_character_count,
                self._visible_character_count + characters_per_frame,
            )
            self._refresh_visible_text()
            return False
        if not input_state.confirm.triggered:
            self._wait_arrow_frame += 1
            return False
        if self._page_index + 1 >= len(self._pages):
            return True
        self._page_index += 1
        self._visible_character_count = 0
        self._wait_arrow_frame = 0
        self._page_placements = self._create_page_placements()
        self._refresh_visible_text()
        return False

    def draw(self) -> None:
        self.window.draw()
        if not self.window.is_open:
            return
        if self.face_position is not None:
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
        if self._page_is_complete and self._wait_arrow_is_visible:
            source_x, source_y = EVENT_MESSAGE_WAIT_ARROW_SOURCE
            pyxel.blt(
                self.window.content_x
                + self.window.content_width
                + 2
                - EVENT_MESSAGE_WAIT_ARROW_SIZE,
                self.window.content_y
                + self.window.content_height
                + 2
                - EVENT_MESSAGE_WAIT_ARROW_SIZE,
                EVENT_MESSAGE_WAIT_ARROW_BANK,
                source_x,
                source_y,
                EVENT_MESSAGE_WAIT_ARROW_SIZE,
                EVENT_MESSAGE_WAIT_ARROW_SIZE,
                TRANSPARENT_INDEX,
            )


class EventMessageOverlay(MessageOverlay):
    def __init__(
        self,
        *,
        message_id: str,
        settings: Settings,
        messages: EventMessageCatalog,
        fonts: FontResources,
        faces: object,
        face_positions: Mapping[str, FacePosition],
    ) -> None:
        self.message_id = message_id
        portrait_character_key = messages.portrait_character_key(message_id)
        self.portrait_character_key = portrait_character_key
        portrait_position = messages.portrait_position(message_id)
        face_position = (
            FacePosition(*portrait_position)
            if portrait_position is not None
            else (
                None
                if portrait_character_key is None
                else face_positions.get(portrait_character_key)
            )
        )
        if portrait_character_key is not None and face_position is None:
            raise EventMessageDataError(
                f"顔グラフィックが見つかりません: {portrait_character_key}"
            )
        lines = messages.lines(message_id, Localizer(settings.language))
        if not lines:
            raise EventMessageDataError(
                f"イベントメッセージが見つかりません: {message_id}"
            )
        super().__init__(
            lines=lines,
            settings=settings,
            fonts=fonts,
            faces=faces,
            face_position=face_position,
        )
__all__ = [
    "EVENT_MESSAGE_CJK_LINE_STEP",
    "EVENT_MESSAGE_CJK_MAX_LINES",
    "EVENT_MESSAGE_CHARACTERS_PER_FRAME",
    "EVENT_MESSAGE_ENGLISH_LINE_STEP",
    "EVENT_MESSAGE_ENGLISH_MAX_LINES",
    "EVENT_MESSAGE_FACE_SIZE",
    "EVENT_MESSAGE_FAST_CHARACTERS_PER_FRAME",
    "EVENT_MESSAGE_FONT_ROLE",
    "EVENT_MESSAGE_WAIT_ARROW_BLINK_FRAMES",
    "EVENT_MESSAGE_WAIT_ARROW_SOURCE",
    "EVENT_MESSAGE_WINDOW_GRID",
    "EventMessageDataError",
    "EventMessageOverlay",
    "MessageOverlay",
]
