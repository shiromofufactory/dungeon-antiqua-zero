"""DA2-style opening load screen shown before the playable field."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime

import pyxel

if __package__ == "ui":
    from input import Direction, InputState
    from localization import Localizer, ascii_to_fullwidth, format_number
    from member import FacePosition
    from rendering import MONOCHROME_PALETTE, PaletteShifter
    from resources import FontResources, FontRole, TRANSPARENT_INDEX
    from state import Language, Settings
    from systems import AUTO_SAVE_SLOT, SAVE_SLOT_COUNT, SaveSlotSummary
    from text_catalog import TextCatalog
else:
    from ..input import Direction, InputState
    from ..localization import Localizer, ascii_to_fullwidth, format_number
    from ..member import FacePosition
    from ..rendering import MONOCHROME_PALETTE, PaletteShifter
    from ..resources import FontResources, FontRole, TRANSPARENT_INDEX
    from ..state import Language, Settings
    from ..systems import AUTO_SAVE_SLOT, SAVE_SLOT_COUNT, SaveSlotSummary
    from ..text_catalog import TextCatalog

from .colors import DISABLED_COLOR, POSITIVE_COLOR
from .localized_text import LocalizedWindowTextFactory
from .save_menu import (
    SAVE_CONFIRM_CURSOR_X,
    SAVE_CONFIRM_NO_Y,
    SAVE_CONFIRM_TEXT_X,
    SAVE_CONFIRM_WINDOW_GRID,
    SAVE_CONFIRM_YES_Y,
    SAVE_FACE_COLUMN_WIDTH,
    SAVE_FACE_COUNT,
    SAVE_FACE_FIRST_X,
    SAVE_FACE_SIZE,
    SAVE_FACE_Y_OFFSET,
    SAVE_SLOT_CURSOR_X,
    SAVE_SLOT_DATE_Y,
    SAVE_SLOT_TEXT_X,
    SAVE_SLOT_TEXT_Y,
    SAVE_SLOT_WINDOW_GRID,
    SAVE_SLOT_WINDOW_HEIGHT,
    SAVE_VISIBLE_SLOT_COUNT,
    format_saved_at,
    save_location_text,
)
from .window import (
    DEFAULT_TEXT_COLOR,
    CursorTarget,
    Window,
    WindowCursor,
    WindowFactory,
)

START_COMMANDS = (
    ("new_game", "start.new_game", 6, True),
    ("delete_data", "start.delete_data", 24, True),
    ("inherit_data", "start.inherit_data", 44, False),
)
START_COMMAND_WINDOW_GRID = (0, 0, 64, 6)
START_COMMAND_CURSOR_X_OFFSET = -2
START_COMMAND_TEXT_Y = 2
START_TEXT_KEYS = (
    *(text_key for _key, text_key, _x, _selectable in START_COMMANDS),
    "start.delete_select",
    "start.delete_confirm",
    "start.delete_complete",
    "start.delete_failed",
    "start.load_failed",
    "start.no_save_data",
    "save.slot",
    "save.auto_slot",
    "settings.yes",
    "settings.no",
)


class StartMenuDataError(RuntimeError):
    """Raised when the opening load screen lacks required shared text."""


class StartMenuOverlay:
    """Select New Game, load a slot, or delete a slot before play begins."""

    def __init__(
        self,
        *,
        summaries: Sequence[SaveSlotSummary],
        autosave_summary: SaveSlotSummary | None = None,
        settings: Settings,
        texts: TextCatalog,
        fonts: FontResources,
        faces: object,
        face_positions: Mapping[str, FacePosition],
        location_text_keys: Mapping[str, str] | None = None,
        palette_shifter: PaletteShifter | None = None,
        on_new_game: Callable[[], None],
        on_load: Callable[[int], bool],
        on_delete: Callable[[int], bool],
        on_invalid_action: Callable[[], None] | None = None,
    ) -> None:
        if not isinstance(summaries, Sequence) or len(summaries) != SAVE_SLOT_COUNT:
            raise ValueError(f"summaries must contain {SAVE_SLOT_COUNT} save slots")
        if not all(
            isinstance(summary, SaveSlotSummary) and summary.slot == index
            for index, summary in enumerate(summaries, start=1)
        ):
            raise ValueError("summaries must be ordered from slot 1")
        if autosave_summary is not None and (
            not isinstance(autosave_summary, SaveSlotSummary)
            or autosave_summary.slot != AUTO_SAVE_SLOT
        ):
            raise ValueError("autosave_summary must describe slot 0")
        if not isinstance(settings, Settings):
            raise TypeError("settings must be Settings")
        if not isinstance(texts, TextCatalog):
            raise TypeError("texts must be TextCatalog")
        if not isinstance(face_positions, Mapping) or not all(
            isinstance(key, str) and isinstance(position, FacePosition)
            for key, position in face_positions.items()
        ):
            raise TypeError("face_positions must map character keys to FacePosition")
        for callback_name, callback in (
            ("on_new_game", on_new_game),
            ("on_load", on_load),
            ("on_delete", on_delete),
        ):
            if not callable(callback):
                raise TypeError(f"{callback_name} must be callable")
        if on_invalid_action is not None and not callable(on_invalid_action):
            raise TypeError("on_invalid_action must be callable")

        self.summaries = tuple(summaries)
        self.autosave_summary = autosave_summary or SaveSlotSummary(
            AUTO_SAVE_SLOT, occupied=False
        )
        self.settings = settings
        self.texts = texts
        self.fonts = fonts
        self.faces = faces
        self.face_positions = dict(face_positions)
        self.location_text_keys = dict(location_text_keys or {})
        self.palette_shifter = palette_shifter
        self.on_new_game = on_new_game
        self.on_load = on_load
        self.on_delete = on_delete
        self.on_invalid_action = on_invalid_action

        self.localizer = Localizer(settings.language)
        self.localized = self._localized_texts()
        self.text_factory = LocalizedWindowTextFactory.from_language(
            fonts,
            settings.language,
        )
        self.location_text_factory = LocalizedWindowTextFactory.from_language(
            fonts,
            settings.language,
            role=FontRole.LARGE,
        )
        self.date_text_factory = LocalizedWindowTextFactory(
            font=fonts.font_for(Language.ENGLISH),
            baseline_offset=fonts.baseline_offset_for(Language.ENGLISH),
        )
        self.window_factory = WindowFactory(fonts.font_for(Language.JAPANESE))
        latest_slot = self._latest_saved_slot()
        self.selected_slot = 1 if latest_slot is None else latest_slot
        self.base_slot = min(
            max(
                0 if self.selected_slot == AUTO_SAVE_SLOT else 1,
                self.selected_slot - SAVE_VISIBLE_SLOT_COUNT + 1,
            ),
            SAVE_SLOT_COUNT - SAVE_VISIBLE_SLOT_COUNT + 1,
        )
        self.mode = "main"
        self.focus = "slots" if any(
            summary.occupied for summary in (self.autosave_summary, *summaries)
        ) else "commands"
        self.selected_command = "new_game"
        self.pending_delete_slot: int | None = None
        self.confirmation_window = None
        self.confirmation_cursor: WindowCursor | None = None
        self._build_windows()

    @property
    def visible_summaries(self) -> tuple[SaveSlotSummary, ...]:
        return (self.autosave_summary, *self.summaries)[
            self.base_slot : self.base_slot + SAVE_VISIBLE_SLOT_COUNT
        ]

    def _summary_for_slot(self, slot: int) -> SaveSlotSummary:
        return self.autosave_summary if slot == AUTO_SAVE_SLOT else self.summaries[slot - 1]

    def _localized_texts(self) -> dict[str, str]:
        localized = {
            key: self.texts.text(key, self.localizer) for key in START_TEXT_KEYS
        }
        missing = tuple(key for key, value in localized.items() if not value)
        if missing:
            raise StartMenuDataError(
                f"スタート画面用テキストが見つかりません: {missing}"
            )
        return localized

    def _latest_saved_slot(self) -> int | None:
        dated: list[tuple[datetime, int]] = []
        for summary in (self.autosave_summary, *self.summaries):
            if not format_saved_at(summary.saved_at):
                continue
            dated.append((datetime.fromisoformat(summary.saved_at or ""), summary.slot))
        if not dated:
            return None
        return max(dated, key=lambda value: value[0])[1]

    def _slot_label(self, slot: int) -> str:
        if slot == AUTO_SAVE_SLOT:
            return self.localized["save.auto_slot"]
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

    def _build_windows(self, *, message_key: str | None = None) -> None:
        if message_key is None:
            command_texts = tuple(
                self.text_factory.create(
                    self.localized[text_key],
                    x,
                    START_COMMAND_TEXT_Y,
                    color=DEFAULT_TEXT_COLOR if selectable else DISABLED_COLOR,
                )
                for _key, text_key, x, selectable in START_COMMANDS
            )
        else:
            command_texts = (
                self.text_factory.create(
                    self.localized[message_key],
                    4,
                    START_COMMAND_TEXT_Y,
                ),
            )
        self.command_window = self.window_factory.create(
            *START_COMMAND_WINDOW_GRID,
            command_texts,
        )
        self.command_cursor: WindowCursor | None = None
        if message_key is None and self.focus == "commands":
            self.command_cursor = self.command_window.set_cursor(
                tuple(
                    CursorTarget(
                        x + START_COMMAND_CURSOR_X_OFFSET,
                        START_COMMAND_TEXT_Y,
                        key=key,
                        selectable=selectable,
                    )
                    for key, _text_key, x, selectable in START_COMMANDS
                )
            )
            self.command_cursor.select_key(self.selected_command)

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
                    SAVE_SLOT_TEXT_X,
                    SAVE_SLOT_DATE_Y,
                    color=(
                        POSITIVE_COLOR
                        if summary.slot == latest_slot
                        else DEFAULT_TEXT_COLOR
                    ),
                )
                slot_texts.append(date_text)
            location_text = save_location_text(
                summary,
                location_text_keys=self.location_text_keys,
                texts=self.texts,
                localizer=self.localizer,
                text_factory=self.location_text_factory,
                slot_label=slot_texts[0],
            )
            if location_text is not None:
                slot_texts.append(location_text)
            x, first_y, width, height = SAVE_SLOT_WINDOW_GRID
            slot_window = self.window_factory.create(
                x,
                first_y + row * SAVE_SLOT_WINDOW_HEIGHT,
                width,
                height,
                tuple(slot_texts),
            )
            if summary.slot == self.selected_slot and self.focus == "slots":
                selected_cursor = slot_window.set_cursor(
                    (
                        CursorTarget(
                            SAVE_SLOT_CURSOR_X,
                            SAVE_SLOT_TEXT_Y,
                            key=summary.slot,
                        ),
                    ),
                )
            slot_windows.append(slot_window)
        if self.focus == "slots" and selected_cursor is None:
            raise RuntimeError("the selected save slot must be visible")
        self.slot_windows = tuple(slot_windows)
        self.slot_cursor = selected_cursor

    def _move_slot(self, distance: int) -> None:
        next_slot = self.selected_slot + distance
        if self.mode == "main" and (next_slot < AUTO_SAVE_SLOT or next_slot > SAVE_SLOT_COUNT):
            self.focus = "commands"
            self._build_windows()
            return
        self.selected_slot = (
            ((next_slot - 1) % SAVE_SLOT_COUNT) + 1
            if self.mode == "delete" else next_slot
        )
        max_base_slot = SAVE_SLOT_COUNT - SAVE_VISIBLE_SLOT_COUNT + 1
        if self.selected_slot < self.base_slot:
            self.base_slot = (
                max_base_slot if self.selected_slot == SAVE_SLOT_COUNT else self.selected_slot
            )
        elif self.selected_slot >= self.base_slot + SAVE_VISIBLE_SLOT_COUNT:
            self.base_slot = self.selected_slot - SAVE_VISIBLE_SLOT_COUNT + 1
        message_key = "start.delete_select" if self.mode == "delete" else None
        self._build_windows(message_key=message_key)

    def _enter_delete_mode(self) -> None:
        if not any(summary.occupied for summary in self.summaries):
            self._invalid_action()
            return
        self.mode = "delete"
        if self.selected_slot == AUTO_SAVE_SLOT:
            self.selected_slot = 1
            self.base_slot = 1
        self.focus = "slots"
        self._build_windows(message_key="start.delete_select")

    def _leave_delete_mode(self) -> None:
        self.mode = "main"
        self.focus = "commands"
        self.selected_command = "delete_data"
        self._build_windows()

    def _start_delete_confirmation(self) -> None:
        self.pending_delete_slot = self.selected_slot
        if self.slot_cursor is None:
            raise RuntimeError("delete mode has no selected slot cursor")
        self.slot_cursor.active = False
        self._build_windows(message_key="start.delete_confirm")
        if self.slot_cursor is None:
            raise RuntimeError("delete confirmation has no selected slot cursor")
        self.slot_cursor.active = False
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
                CursorTarget(SAVE_CONFIRM_CURSOR_X, SAVE_CONFIRM_YES_Y, key="yes"),
                CursorTarget(SAVE_CONFIRM_CURSOR_X, SAVE_CONFIRM_NO_Y, key="no"),
            )
        )
        self.confirmation_window.open()

    def _cancel_delete_confirmation(self) -> None:
        self.pending_delete_slot = None
        self.confirmation_window = None
        self.confirmation_cursor = None
        self._build_windows(message_key="start.delete_select")

    def _delete_selected_slot(self) -> None:
        slot = self.pending_delete_slot
        if slot is None:
            raise RuntimeError("delete confirmation has no selected slot")
        succeeded = self.on_delete(slot)
        self.pending_delete_slot = None
        self.confirmation_window = None
        self.confirmation_cursor = None
        if succeeded:
            replaced = list(self.summaries)
            replaced[slot - 1] = SaveSlotSummary(slot, occupied=False)
            self.summaries = tuple(replaced)
            self._build_windows(message_key="start.delete_complete")
        else:
            self._build_windows(message_key="start.delete_failed")
            self._invalid_action()

    def _invalid_action(self) -> None:
        if self.on_invalid_action is not None:
            self.on_invalid_action()

    def update(self, input_state: InputState) -> None:
        """Update the opening selector; Game owns the eventual screen change."""

        if not isinstance(input_state, InputState):
            raise TypeError("input_state must be an InputState")
        if self.confirmation_window is not None and self.confirmation_window.is_animating:
            self.confirmation_window.update()
            return
        if self.confirmation_cursor is not None:
            if input_state.cancel.triggered:
                self._cancel_delete_confirmation()
                return
            if input_state.confirm.triggered:
                if self.confirmation_cursor.selected_key == "yes":
                    self._delete_selected_slot()
                else:
                    self._cancel_delete_confirmation()
                return
            self.confirmation_window.update(input_state.navigation)
            return

        if self.mode == "delete":
            if input_state.cancel.triggered:
                self._leave_delete_mode()
                return
            if input_state.confirm.triggered:
                if self.summaries[self.selected_slot - 1].occupied:
                    self._start_delete_confirmation()
                else:
                    self._build_windows(message_key="start.no_save_data")
                    self._invalid_action()
                return
            if input_state.navigation in (Direction.UP, Direction.DOWN):
                self._move_slot(-1 if input_state.navigation is Direction.UP else 1)
            return

        if self.focus == "commands":
            if self.command_cursor is None:
                raise RuntimeError("command focus has no command cursor")
            if input_state.confirm.triggered:
                command = self.command_cursor.selected_key
                self.selected_command = str(command)
                if command == "new_game":
                    self.on_new_game()
                elif command == "delete_data":
                    self._enter_delete_mode()
                return
            if input_state.navigation in (Direction.LEFT, Direction.RIGHT):
                self.command_window.update(input_state.navigation)
                self.selected_command = str(self.command_cursor.selected_key)
            elif input_state.navigation in (Direction.UP, Direction.DOWN):
                self.focus = "slots"
                self._build_windows()
            else:
                self.command_window.update()
            return

        if input_state.confirm.triggered:
            summary = self._summary_for_slot(self.selected_slot)
            if summary.occupied and self.on_load(self.selected_slot):
                return
            self._build_windows(
                message_key=(
                    "start.load_failed" if summary.occupied else "start.no_save_data"
                )
            )
            self._invalid_action()
            return
        if input_state.navigation in (Direction.UP, Direction.DOWN):
            self._move_slot(-1 if input_state.navigation is Direction.UP else 1)
            return
        for slot_window in self.slot_windows:
            slot_window.update()

    def draw(self) -> None:
        self.command_window.draw()
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
                if (
                    character_key in summary.dead_character_keys
                    and self.palette_shifter is not None
                ):
                    with self.palette_shifter.shifted(MONOCHROME_PALETTE):
                        self._draw_face(slot_window, member_index, face)
                else:
                    self._draw_face(slot_window, member_index, face)
        if self.confirmation_window is not None:
            self.confirmation_window.draw()

    def _draw_face(
        self,
        slot_window: Window,
        member_index: int,
        face: FacePosition,
    ) -> None:
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


__all__ = [
    "START_COMMANDS",
    "START_COMMAND_WINDOW_GRID",
    "StartMenuDataError",
    "StartMenuOverlay",
]
