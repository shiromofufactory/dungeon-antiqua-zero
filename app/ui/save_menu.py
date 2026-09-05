"""DA2-style save-slot overlay with a deliberately small slot preview."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from datetime import datetime

import pyxel

if __package__ == "ui":
    from input import Direction, InputState
    from localization import Localizer, ascii_to_fullwidth, format_number
    from member import BATTLE_PARTY_MEMBER_COUNT, FacePosition
    from resources import FontResources, TRANSPARENT_INDEX
    from state import Language, Settings
    from systems import SAVE_SLOT_COUNT, SaveSlotSummary
    from text_catalog import TextCatalog
else:
    from ..input import Direction, InputState
    from ..localization import Localizer, ascii_to_fullwidth, format_number
    from ..member import BATTLE_PARTY_MEMBER_COUNT, FacePosition
    from ..resources import FontResources, TRANSPARENT_INDEX
    from ..state import Language, Settings
    from ..systems import SAVE_SLOT_COUNT, SaveSlotSummary
    from ..text_catalog import TextCatalog

from .localized_text import LocalizedWindowTextFactory
from .colors import POSITIVE_COLOR
from .shop_party import (
    SHOP_PARTY_COLUMN_WIDTH,
    SHOP_PARTY_FACE_SIZE,
)
from .text_layout import right_aligned_grid_x
from .window import (
    DEFAULT_TEXT_COLOR,
    CursorTarget,
    WindowCursor,
    WindowFactory,
)

SAVE_VISIBLE_SLOT_COUNT = 3
SAVE_MESSAGE_WINDOW_GRID = (0, 0, 64, 6)
SAVE_SLOT_WINDOW_GRID = (0, 6, 64, 18)
SAVE_SLOT_WINDOW_HEIGHT = SAVE_SLOT_WINDOW_GRID[3]
SAVE_SLOT_TEXT_Y = 2
SAVE_SLOT_TEXT_X = 6
SAVE_SLOT_DATE_RIGHT_X = 60
SAVE_SLOT_CURSOR_X = 4
SAVE_FACE_COUNT = BATTLE_PARTY_MEMBER_COUNT
SAVE_FACE_COLUMN_WIDTH = SHOP_PARTY_COLUMN_WIDTH
SAVE_FACE_Y_OFFSET = 7
SAVE_FACE_SIZE = SHOP_PARTY_FACE_SIZE
SAVE_FACE_ROW_WIDTH = SAVE_FACE_SIZE + (SAVE_FACE_COUNT - 1) * SAVE_FACE_COLUMN_WIDTH
SAVE_FACE_FIRST_X = (SAVE_SLOT_WINDOW_GRID[2] * 4 - SAVE_FACE_ROW_WIDTH) // 2
SAVE_CONFIRM_WINDOW_GRID = (48, 6, 16, 10)
SAVE_CONFIRM_TEXT_X = 5
SAVE_CONFIRM_CURSOR_X = 3
SAVE_CONFIRM_YES_Y = 2
SAVE_CONFIRM_NO_Y = 5

SAVE_TEXT_KEYS = (
    "save.select_slot",
    "save.slot",
    "save.overwrite_confirm",
    "save.complete",
    "save.failed",
    "settings.yes",
    "settings.no",
)


class SaveMenuDataError(RuntimeError):
    """Raised when the save menu cannot resolve required preview data."""


def format_saved_at(value: str | None) -> str:
    """Return the compact DA2 timestamp used by a slot preview."""

    if value is None:
        return ""
    if not isinstance(value, str):
        raise TypeError("saved timestamp must be a string or None")
    try:
        timestamp = datetime.fromisoformat(value)
    except ValueError:
        return ""
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        return ""
    return timestamp.strftime("%Y/%m/%d %H:%M")


class SaveMenuOverlay:
    """Select and write manual save slots without restoring game state."""

    def __init__(
        self,
        *,
        summaries: Sequence[SaveSlotSummary],
        current_slot: int | None,
        settings: Settings,
        texts: TextCatalog,
        fonts: FontResources,
        faces: object,
        face_positions: Mapping[str, FacePosition],
        on_save: Callable[[int], SaveSlotSummary | None],
        on_invalid_action: Callable[[], None] | None = None,
    ) -> None:
        if not isinstance(summaries, Sequence) or len(summaries) != SAVE_SLOT_COUNT:
            raise ValueError(f"summaries must contain {SAVE_SLOT_COUNT} save slots")
        if not all(
            isinstance(summary, SaveSlotSummary) and summary.slot == index
            for index, summary in enumerate(summaries, start=1)
        ):
            raise ValueError("summaries must be ordered from slot 1")
        if current_slot is not None and not 1 <= current_slot <= SAVE_SLOT_COUNT:
            raise ValueError("current_slot is outside the manual save range")
        if not isinstance(settings, Settings):
            raise TypeError("settings must be Settings")
        if not isinstance(texts, TextCatalog):
            raise TypeError("texts must be TextCatalog")
        if not isinstance(face_positions, Mapping) or not all(
            isinstance(key, str) and isinstance(position, FacePosition)
            for key, position in face_positions.items()
        ):
            raise TypeError("face_positions must map character keys to FacePosition")
        if not callable(on_save):
            raise TypeError("on_save must be callable")
        if on_invalid_action is not None and not callable(on_invalid_action):
            raise TypeError("on_invalid_action must be callable")

        self.summaries = tuple(summaries)
        self.current_slot = current_slot
        self.settings = settings
        self.texts = texts
        self.fonts = fonts
        self.faces = faces
        self.face_positions = dict(face_positions)
        self.on_save = on_save
        self.on_invalid_action = on_invalid_action
        self.pending_overwrite_slot: int | None = None
        self.confirmation_window = None
        self.confirmation_cursor: WindowCursor | None = None

        self.localizer = Localizer(settings.language)
        self.localized = self._localized_texts()
        self.text_factory = LocalizedWindowTextFactory.from_language(
            fonts,
            settings.language,
        )
        self.date_text_factory = LocalizedWindowTextFactory.from_language(
            fonts,
            Language.JAPANESE,
        )
        self.window_factory = WindowFactory(fonts.font_for(Language.JAPANESE))
        self.selected_slot = self._initial_slot()
        self.base_slot = min(
            max(1, self.selected_slot - SAVE_VISIBLE_SLOT_COUNT + 1),
            SAVE_SLOT_COUNT - SAVE_VISIBLE_SLOT_COUNT + 1,
        )
        self._build_windows(message_key="save.select_slot")

    @property
    def visible_summaries(self) -> tuple[SaveSlotSummary, ...]:
        start = self.base_slot - 1
        return self.summaries[start : start + SAVE_VISIBLE_SLOT_COUNT]

    def _localized_texts(self) -> dict[str, str]:
        localized = {
            key: self.texts.text(key, self.localizer) for key in SAVE_TEXT_KEYS
        }
        missing = tuple(key for key, value in localized.items() if not value)
        if missing:
            raise SaveMenuDataError(f"セーブ画面用テキストが見つかりません: {missing}")
        return localized

    def _initial_slot(self) -> int:
        if self.current_slot is not None:
            return self.current_slot
        return self._latest_saved_slot() or 1

    def _latest_saved_slot(self) -> int | None:
        dated = []
        for summary in self.summaries:
            if not format_saved_at(summary.saved_at):
                continue
            dated.append((datetime.fromisoformat(summary.saved_at or ""), summary.slot))
        if not dated:
            return None
        return max(dated, key=lambda value: value[0])[1]

    def _slot_label(self, slot: int) -> str:
        slot_number = (
            str(slot)
            if self.settings.language is Language.ENGLISH
            else format_number(slot)
        )
        return self.texts.formatted_text(
            "save.slot",
            self.localizer,
            {"SLOT": slot_number},
        )

    def _build_windows(self, *, message_key: str) -> None:
        self.message_window = self.window_factory.create(
            *SAVE_MESSAGE_WINDOW_GRID,
            (self.text_factory.create(self.localized[message_key], 4, 2),),
        )
        slot_windows = []
        selected_cursor = None
        latest_slot = self._latest_saved_slot()
        for row, summary in enumerate(self.visible_summaries):
            slot_texts = [
                self.text_factory.create(
                    self._slot_label(summary.slot),
                    SAVE_SLOT_TEXT_X,
                    SAVE_SLOT_TEXT_Y,
                )
            ]
            saved_at = format_saved_at(summary.saved_at)
            if saved_at:
                date_text = self.date_text_factory.create(
                    ascii_to_fullwidth(saved_at),
                    0,
                    SAVE_SLOT_TEXT_Y,
                    color=(
                        POSITIVE_COLOR
                        if summary.slot == latest_slot
                        else DEFAULT_TEXT_COLOR
                    ),
                )
                slot_texts.append(
                    replace(
                        date_text,
                        x=right_aligned_grid_x(
                            date_text.text,
                            reference_text="",
                            reference_x=SAVE_SLOT_DATE_RIGHT_X,
                            font=date_text.font,
                        ),
                    )
                )
            x, first_y, width, height = SAVE_SLOT_WINDOW_GRID
            slot_window = self.window_factory.create(
                x,
                first_y + row * SAVE_SLOT_WINDOW_HEIGHT,
                width,
                height,
                tuple(slot_texts),
            )
            if summary.slot == self.selected_slot:
                selected_cursor = slot_window.set_cursor(
                    (
                        CursorTarget(
                            SAVE_SLOT_CURSOR_X,
                            SAVE_SLOT_TEXT_Y,
                            key=summary.slot,
                        ),
                    )
                )
            slot_windows.append(slot_window)
        if selected_cursor is None:
            raise RuntimeError("the selected save slot must be visible")
        self.slot_windows = tuple(slot_windows)
        self.slot_cursor = selected_cursor

    def _set_message(self, message_key: str) -> None:
        self.message_window.clear_texts()
        placement = self.text_factory.create(self.localized[message_key], 4, 2)
        self.message_window.add_text(
            placement.text,
            placement.x,
            placement.y,
            color=placement.color,
            font=placement.font,
            shadow_color=placement.shadow_color,
            baseline_offset=placement.baseline_offset,
            font_spans=placement.font_spans,
        )

    def _move_selection(self, distance: int) -> None:
        self.selected_slot = ((self.selected_slot - 1 + distance) % SAVE_SLOT_COUNT) + 1
        max_base_slot = SAVE_SLOT_COUNT - SAVE_VISIBLE_SLOT_COUNT + 1
        if self.selected_slot < self.base_slot:
            self.base_slot = (
                max_base_slot
                if self.selected_slot == SAVE_SLOT_COUNT
                else self.selected_slot
            )
        elif self.selected_slot >= self.base_slot + SAVE_VISIBLE_SLOT_COUNT:
            self.base_slot = 1 if self.selected_slot == 1 else self.selected_slot - 2
        self._build_windows(message_key=self._current_message_key)

    @property
    def _current_message_key(self) -> str:
        texts = self.message_window.texts
        current = texts[0].text if texts else ""
        for key in ("save.select_slot", "save.complete", "save.failed"):
            if current == self.localized[key]:
                return key
        return "save.select_slot"

    def _start_overwrite_confirmation(self) -> None:
        self.pending_overwrite_slot = self.selected_slot
        self.slot_cursor.active = False
        self._set_message("save.overwrite_confirm")
        self.confirmation_window = self.window_factory.create(
            *SAVE_CONFIRM_WINDOW_GRID,
            (
                self.text_factory.create(
                    self.localized["settings.yes"],
                    SAVE_CONFIRM_TEXT_X,
                    SAVE_CONFIRM_YES_Y,
                ),
                self.text_factory.create(
                    self.localized["settings.no"],
                    SAVE_CONFIRM_TEXT_X,
                    SAVE_CONFIRM_NO_Y,
                ),
            ),
            opened=False,
        )
        self.confirmation_cursor = self.confirmation_window.set_cursor(
            (
                CursorTarget(
                    SAVE_CONFIRM_CURSOR_X,
                    SAVE_CONFIRM_YES_Y,
                    key="yes",
                ),
                CursorTarget(
                    SAVE_CONFIRM_CURSOR_X,
                    SAVE_CONFIRM_NO_Y,
                    key="no",
                ),
            )
        )
        self.confirmation_window.open()

    def _cancel_overwrite_confirmation(self) -> None:
        self.pending_overwrite_slot = None
        self.confirmation_window = None
        self.confirmation_cursor = None
        self.slot_cursor.active = True
        self._set_message("save.select_slot")

    def _save_selected_slot(self) -> None:
        summary = self.on_save(self.selected_slot)
        if summary is None:
            self._set_message("save.failed")
            if self.on_invalid_action is not None:
                self.on_invalid_action()
            return
        if (
            not isinstance(summary, SaveSlotSummary)
            or summary.slot != self.selected_slot
        ):
            raise TypeError("on_save must return the selected SaveSlotSummary or None")
        replaced = list(self.summaries)
        replaced[self.selected_slot - 1] = summary
        self.summaries = tuple(replaced)
        self.current_slot = self.selected_slot
        self._build_windows(message_key="save.complete")

    def update(self, input_state: InputState) -> bool:
        """Update save selection and return whether the overlay should close."""

        if not isinstance(input_state, InputState):
            raise TypeError("input_state must be an InputState")
        if (
            self.confirmation_window is not None
            and self.confirmation_window.is_animating
        ):
            self.confirmation_window.update()
            return False
        if self.confirmation_cursor is not None:
            if input_state.cancel.triggered:
                self._cancel_overwrite_confirmation()
                return False
            if input_state.confirm.triggered:
                if self.confirmation_cursor.selected_key == "yes":
                    self._cancel_overwrite_confirmation()
                    self._save_selected_slot()
                else:
                    self._cancel_overwrite_confirmation()
                return False
            self.confirmation_window.update(input_state.navigation)
            return False

        if input_state.cancel.triggered:
            return True
        if input_state.confirm.triggered:
            summary = self.summaries[self.selected_slot - 1]
            if summary.occupied and self.selected_slot != self.current_slot:
                self._start_overwrite_confirmation()
            else:
                self._save_selected_slot()
            return False
        if input_state.navigation in (Direction.UP, Direction.DOWN):
            distance = -1 if input_state.navigation is Direction.UP else 1
            self._move_selection(distance)
            return False
        for slot_window in self.slot_windows:
            slot_window.update()
        return False

    def draw(self) -> None:
        self.message_window.draw()
        for slot_window in self.slot_windows:
            slot_window.draw()
        for slot_window, summary in zip(
            self.slot_windows,
            self.visible_summaries,
            strict=True,
        ):
            if not slot_window.is_open:
                continue
            for member_index, character_key in enumerate(
                summary.party_character_keys[:SAVE_FACE_COUNT]
            ):
                face = self.face_positions.get(character_key)
                if face is None:
                    continue
                pyxel.blt(
                    SAVE_FACE_FIRST_X + member_index * SAVE_FACE_COLUMN_WIDTH,
                    slot_window.pixel_y + SAVE_FACE_Y_OFFSET * 4,
                    self.faces,
                    face.x,
                    face.y,
                    SAVE_FACE_SIZE,
                    SAVE_FACE_SIZE,
                    TRANSPARENT_INDEX,
                )
        if self.confirmation_window is not None:
            self.confirmation_window.draw()


__all__ = [
    "SAVE_CONFIRM_WINDOW_GRID",
    "SAVE_FACE_COLUMN_WIDTH",
    "SAVE_FACE_COUNT",
    "SAVE_FACE_FIRST_X",
    "SAVE_FACE_ROW_WIDTH",
    "SAVE_FACE_SIZE",
    "SAVE_MESSAGE_WINDOW_GRID",
    "SAVE_SLOT_COUNT",
    "SAVE_SLOT_DATE_RIGHT_X",
    "SAVE_SLOT_WINDOW_GRID",
    "SAVE_VISIBLE_SLOT_COUNT",
    "SaveMenuDataError",
    "SaveMenuOverlay",
    "format_saved_at",
]
