"""Debug menu view used by the connected menu-screen mock."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from input import InputAction, InputDevice, InputState
from localization import Localizer, format_number
from member import (
    FIORA_CHARACTER_KEY,
    MAX_INTERNAL_LEVEL,
    MIN_INTERNAL_LEVEL,
    Member,
)
from resources import FontResources
from state import Language, SaveData, Settings
from systems import DebugPartyEditor, DebugPartyError
from tools.screen_mocks.debug_text import DEBUG_TEXT
from ui import (
    CursorTarget,
    DEFAULT_TEXT_COLOR,
    DISABLED_COLOR,
    LocalizedWindowTextFactory,
    Window,
    WindowCursor,
    WindowFactory,
    WindowText,
    input_icon_tag,
)

DEBUG_WINDOW_GRID = (2, 2, 60, 56)
MAIN_ROWS = (
    ("party_level", 11),
    ("gold", 17),
    ("members", 23),
)
MAIN_CURSOR_X = 4
MAIN_LABEL_X = 6
MAIN_VALUE_X = 34
MEMBER_FIRST_Y = 9
MEMBER_ROW_HEIGHT = 3
MEMBER_ROW_COUNT = 10
MEMBER_TEXT_X = (6, 34)
MEMBER_CURSOR_X = (4, 32)
NUMERIC_WINDOW_GRID = (12, 14, 40, 30)
NUMERIC_DIGIT_X = (6, 10, 14, 18, 22)
NUMERIC_ROW_Y = (11, 15)
NUMERIC_ACTION_X = 29
NUMERIC_DISPLAY_X = 6
NUMERIC_DISPLAY_Y = 6
GUIDE_X = 4
GUIDE_Y = 49
MAX_GOLD = 999999


class DebugMenuPhase(Enum):
    """Current interaction layer owned by the debug menu."""

    MAIN = auto()
    MEMBERS = auto()
    NUMBER = auto()


@dataclass
class NumericEntry:
    """DA2-style bounded numeric input buffer independent of Pyxel."""

    minimum: int
    maximum: int
    max_digits: int
    digits: str = ""

    def __post_init__(self) -> None:
        for name in ("minimum", "maximum", "max_digits"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
        if self.minimum < 0 or self.maximum < self.minimum:
            raise ValueError("numeric entry range is invalid")
        if self.max_digits <= 0 or len(str(self.maximum)) > self.max_digits:
            raise ValueError("max_digits must contain the maximum value")
        if not isinstance(self.digits, str) or (
            self.digits
            and (
                not self.digits.isdigit()
                or len(self.digits) > self.max_digits
            )
        ):
            raise ValueError("digits must contain at most max_digits decimal digits")

    @property
    def value(self) -> int | None:
        if not self.digits:
            return None
        value = int(self.digits)
        return value if self.minimum <= value <= self.maximum else None

    def append(self, digit: str) -> bool:
        if not isinstance(digit, str) or len(digit) != 1 or not digit.isdigit():
            raise ValueError("digit must be one decimal character")
        if len(self.digits) >= self.max_digits:
            return False
        self.digits += digit
        return True

    def delete(self) -> bool:
        if not self.digits:
            return False
        self.digits = self.digits[:-1]
        return True


class DebugMenuScreenMock:
    """Edit level, gold, and party membership inside the menu mock."""

    def __init__(
        self,
        *,
        editor: DebugPartyEditor,
        save_data: SaveData,
        settings: Settings,
        fonts: FontResources,
        alert: object,
    ) -> None:
        if not isinstance(editor, DebugPartyEditor):
            raise TypeError("editor must be a DebugPartyEditor")
        if not isinstance(save_data, SaveData):
            raise TypeError("save_data must be SaveData")
        if not isinstance(settings, Settings):
            raise TypeError("settings must be Settings")
        if not isinstance(fonts, FontResources):
            raise TypeError("fonts must be FontResources")
        if not callable(getattr(alert, "start", None)):
            raise TypeError("alert must provide start()")

        self.editor = editor
        self.save_data = save_data
        self.settings = settings
        self.fonts = fonts
        self.alert = alert
        self.localizer = Localizer(settings.language)
        self.debug_texts = LocalizedWindowTextFactory.from_language(
            fonts,
            Language.JAPANESE,
        )
        self.member_texts = LocalizedWindowTextFactory.from_language(
            fonts,
            settings.language,
        )
        self.windows = WindowFactory(fonts.font_for(Language.JAPANESE))
        self.phase = DebugMenuPhase.MAIN
        self.main_window: Window
        self.main_cursor: WindowCursor
        self.member_window: Window | None = None
        self.member_cursor: WindowCursor | None = None
        self.member_index = 0
        self.numeric_window: Window | None = None
        self.numeric_cursor: WindowCursor | None = None
        self.numeric_entry: NumericEntry | None = None
        self.numeric_target: str | None = None
        self._build_main_window()

    @property
    def party(self) -> tuple[Member, ...]:
        return self.editor.party

    def _member_count_text(self) -> str:
        return DEBUG_TEXT.member_count(self.editor.other_member_count)

    def _guide_text(self) -> WindowText:
        return self.debug_texts.create(
            DEBUG_TEXT.close_guide.replace(
                "%CANCEL%",
                input_icon_tag(InputAction.CANCEL, InputDevice.KEYBOARD),
            ),
            GUIDE_X,
            GUIDE_Y,
        )

    def _build_main_window(self, selected_key: str = "party_level") -> None:
        values = {
            "party_level": format_number(self.editor.baseline_level),
            "gold": format_number(self.save_data.gold),
            "members": self._member_count_text(),
        }
        labels = {
            "party_level": DEBUG_TEXT.party_level,
            "gold": DEBUG_TEXT.gold,
            "members": DEBUG_TEXT.members,
        }
        placements = [
            self.debug_texts.create(DEBUG_TEXT.title, 4, 3)
        ]
        for key, y in MAIN_ROWS:
            placements.extend(
                (
                    self.debug_texts.create(labels[key], MAIN_LABEL_X, y),
                    self.debug_texts.create("：", 31, y),
                    self.debug_texts.create(values[key], MAIN_VALUE_X, y),
                )
            )
        placements.append(self._guide_text())
        self.main_window = self.windows.create(
            *DEBUG_WINDOW_GRID,
            tuple(placements),
            opened=True,
        )
        self.main_cursor = self.main_window.set_cursor(
            tuple(
                CursorTarget(MAIN_CURSOR_X, y, key=key) for key, y in MAIN_ROWS
            )
        )
        self._select_cursor_key(self.main_cursor, selected_key)

    def _build_member_window(self) -> None:
        definitions = self.editor.candidate_definitions
        placements = [
            self.debug_texts.create(DEBUG_TEXT.members, 4, 3),
            self.debug_texts.create(
                self._member_count_text(),
                32,
                3,
            ),
        ]
        targets: list[CursorTarget] = []
        for index, definition in enumerate(definitions):
            column, row = divmod(index, MEMBER_ROW_COUNT)
            y = MEMBER_FIRST_Y + row * MEMBER_ROW_HEIGHT
            selected = definition.key in self.editor.selected_keys
            marker = "●" if selected else "○"
            color = (
                DISABLED_COLOR
                if definition.key == FIORA_CHARACTER_KEY
                else DEFAULT_TEXT_COLOR
            )
            placements.extend(
                (
                    self.debug_texts.create(
                        marker,
                        MEMBER_TEXT_X[column],
                        y,
                        color=color,
                    ),
                    self.member_texts.create(
                        definition.localized_name(self.localizer),
                        MEMBER_TEXT_X[column] + 2,
                        y,
                        color=color,
                    ),
                )
            )
            targets.append(
                CursorTarget(
                    MEMBER_CURSOR_X[column],
                    y,
                    key=definition.key,
                )
            )
        placements.append(self._guide_text())
        self.member_window = self.windows.create(
            *DEBUG_WINDOW_GRID,
            tuple(placements),
            opened=True,
        )
        self.member_cursor = self.member_window.set_cursor(tuple(targets))
        selected_key = definitions[self.member_index].key
        self._select_cursor_key(self.member_cursor, selected_key)

    def _open_members(self) -> None:
        self.phase = DebugMenuPhase.MEMBERS
        self.member_index = 0
        self._build_member_window()

    def _toggle_selected_member(self) -> None:
        key = self.editor.candidate_definitions[self.member_index].key
        try:
            self.editor.toggle_member(key)
        except DebugPartyError:
            self.alert.start()
        self._build_member_window()

    def _open_numeric(self, target: str) -> None:
        if target == "party_level":
            entry = NumericEntry(MIN_INTERNAL_LEVEL, MAX_INTERNAL_LEVEL, 2)
        elif target == "gold":
            entry = NumericEntry(0, MAX_GOLD, 6)
        else:
            raise ValueError(f"unsupported numeric target: {target}")
        self.phase = DebugMenuPhase.NUMBER
        self.numeric_target = target
        self.numeric_entry = entry
        self._build_numeric_window()

    def _build_numeric_window(self) -> None:
        if self.numeric_entry is None or self.numeric_target is None:
            raise RuntimeError("numeric input is not active")
        label = (
            DEBUG_TEXT.party_level
            if self.numeric_target == "party_level"
            else DEBUG_TEXT.gold
        )
        digits = self.numeric_entry.digits
        display = digits + (
            "■" if len(digits) < self.numeric_entry.max_digits else ""
        )
        display += " " * (self.numeric_entry.max_digits - len(display))
        placements = [
            self.debug_texts.create(label, 4, 2),
            self.debug_texts.create(display, NUMERIC_DISPLAY_X, NUMERIC_DISPLAY_Y),
        ]
        targets: list[CursorTarget] = []
        for row, digit_row in enumerate(("01234", "56789")):
            y = NUMERIC_ROW_Y[row]
            for column, digit in enumerate(digit_row):
                x = NUMERIC_DIGIT_X[column]
                placements.append(self.debug_texts.create(digit, x, y))
                targets.append(CursorTarget(x - 2, y, key=digit))
        placements.extend(
            (
                self.debug_texts.create(
                    DEBUG_TEXT.numeric_delete,
                    NUMERIC_ACTION_X,
                    NUMERIC_ROW_Y[0],
                ),
                self.debug_texts.create(
                    DEBUG_TEXT.numeric_confirm,
                    NUMERIC_ACTION_X,
                    NUMERIC_ROW_Y[1],
                ),
            )
        )
        targets.extend(
            (
                CursorTarget(
                    NUMERIC_ACTION_X - 2,
                    NUMERIC_ROW_Y[0],
                    key="delete",
                ),
                CursorTarget(
                    NUMERIC_ACTION_X - 2,
                    NUMERIC_ROW_Y[1],
                    key="confirm",
                ),
            )
        )
        selected_key = (
            self.numeric_cursor.selected_key
            if self.numeric_cursor is not None
            else "0"
        )
        self.numeric_window = self.windows.create(
            *NUMERIC_WINDOW_GRID,
            tuple(placements),
            opened=True,
        )
        self.numeric_cursor = self.numeric_window.set_cursor(tuple(targets))
        self._select_cursor_key(self.numeric_cursor, selected_key)

    def _confirm_numeric(self) -> None:
        if self.numeric_entry is None or self.numeric_target is None:
            return
        value = self.numeric_entry.value
        if value is None:
            self.alert.start()
            return
        target = self.numeric_target
        if target == "party_level":
            self.editor.set_baseline_level(value)
        else:
            self.save_data.gold = value
        self.numeric_entry = None
        self.numeric_target = None
        self.numeric_window = None
        self.numeric_cursor = None
        self.phase = DebugMenuPhase.MAIN
        self._build_main_window(selected_key=target)

    def _update_numeric(self, input_state: InputState) -> None:
        if self.numeric_entry is None or self.numeric_cursor is None:
            return
        if input_state.cancel.triggered:
            if self.numeric_entry.delete():
                self._build_numeric_window()
            else:
                target = self.numeric_target or "party_level"
                self.numeric_entry = None
                self.numeric_target = None
                self.numeric_window = None
                self.numeric_cursor = None
                self.phase = DebugMenuPhase.MAIN
                self._build_main_window(selected_key=target)
            return
        if input_state.confirm.triggered:
            key = self.numeric_cursor.selected_key
            if isinstance(key, str) and len(key) == 1 and key.isdigit():
                if not self.numeric_entry.append(key):
                    self.alert.start()
                self._build_numeric_window()
                if len(self.numeric_entry.digits) == self.numeric_entry.max_digits:
                    self._select_cursor_key(self.numeric_cursor, "confirm")
            elif key == "delete":
                if not self.numeric_entry.delete():
                    self.alert.start()
                self._build_numeric_window()
            elif key == "confirm":
                self._confirm_numeric()
            return
        self.numeric_window.update(input_state.navigation)

    def update(self, input_state: InputState) -> bool:
        """Update the debug view and return True when settings should resume."""

        if not isinstance(input_state, InputState):
            raise TypeError("input_state must be an InputState")
        if self.phase is DebugMenuPhase.NUMBER:
            self._update_numeric(input_state)
            return False
        if self.phase is DebugMenuPhase.MEMBERS:
            if input_state.cancel.triggered:
                self.phase = DebugMenuPhase.MAIN
                self.member_window = None
                self.member_cursor = None
                self._build_main_window(selected_key="members")
            elif input_state.confirm.triggered:
                self._toggle_selected_member()
            elif (
                self.member_window is not None
                and self.member_window.update(input_state.navigation)
                and self.member_cursor is not None
            ):
                selected_key = self.member_cursor.selected_key
                self.member_index = next(
                    index
                    for index, definition in enumerate(
                        self.editor.candidate_definitions
                    )
                    if definition.key == selected_key
                )
            return False

        if input_state.cancel.triggered:
            return True
        if input_state.confirm.triggered:
            key = self.main_cursor.selected_key
            if key == "members":
                self._open_members()
            elif isinstance(key, str):
                self._open_numeric(key)
            return False
        self.main_window.update(input_state.navigation)
        return False

    def draw(self) -> None:
        if self.phase is DebugMenuPhase.NUMBER and self.numeric_window is not None:
            self.numeric_window.draw()
        elif self.phase is DebugMenuPhase.MEMBERS and self.member_window is not None:
            self.member_window.draw()
        else:
            self.main_window.draw()

    @staticmethod
    def _select_cursor_key(cursor: WindowCursor, key: object) -> None:
        cursor.select_key(key)


__all__ = [
    "DebugMenuPhase",
    "DebugMenuScreenMock",
    "MAX_GOLD",
    "NumericEntry",
]
