"""Development-only debug menu overlay used by the game."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import Enum, auto

from input import Direction, InputAction, InputDevice, InputState
from localization import Localizer, format_number
from member import (
    FIORA_CHARACTER_KEY,
    MAX_INTERNAL_LEVEL,
    MIN_INTERNAL_LEVEL,
    Member,
)
from resources import FontResources, FontRole
from state import Language, SaveData, Settings
from systems import DebugPartyEditor, DebugPartyError
from ui.debug_text import DEBUG_TEXT
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
    ("teleport", 29),
    ("shop", 35),
)
MAIN_CURSOR_X = 4
MAIN_LABEL_X = 6
MAIN_VALUE_X = 34
MEMBER_FIRST_Y = 9
MEMBER_ROW_HEIGHT = 3
MEMBER_ROW_COUNT = 10
MEMBER_TEXT_X = (6, 34)
MEMBER_CURSOR_X = (4, 32)
TELEPORT_FIRST_Y = 9
TELEPORT_ROW_HEIGHT = 4
TELEPORT_VISIBLE_COUNT = 10
TELEPORT_TEXT_X = 6
TELEPORT_CURSOR_X = 4
SHOP_FIRST_Y = 7
SHOP_ROW_HEIGHT = 3
SHOP_VISIBLE_COUNT = 13
SHOP_TEXT_X = 6
SHOP_CURSOR_X = 4
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
    TELEPORT = auto()
    SHOP = auto()
    NUMBER = auto()


@dataclass(frozen=True)
class DebugTeleportTarget:
    """One stable teleport target and its already-localized display name."""

    site_id: str
    name: str

    def __post_init__(self) -> None:
        if not isinstance(self.site_id, str) or not self.site_id:
            raise ValueError("debug teleport site ID must be a non-empty string")
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("debug teleport name must be a non-empty string")


@dataclass(frozen=True)
class DebugShopTarget:
    """One shop selectable from the development-only debug menu."""

    shop_key: str
    name: str

    def __post_init__(self) -> None:
        if not isinstance(self.shop_key, str) or not self.shop_key:
            raise ValueError("debug shop key must be a non-empty string")
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("debug shop name must be a non-empty string")


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


class DebugMenuOverlay:
    """Edit party state and request debug travel inside the current game."""

    def __init__(
        self,
        *,
        editor: DebugPartyEditor,
        save_data: SaveData,
        settings: Settings,
        fonts: FontResources,
        alert: object,
        teleport_targets: Iterable[DebugTeleportTarget] = (),
        on_teleport: Callable[[str], bool] | None = None,
        shop_targets: Iterable[DebugShopTarget] = (),
        on_shop: Callable[[str], bool] | None = None,
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
        registered_teleports = tuple(teleport_targets)
        if not all(
            isinstance(target, DebugTeleportTarget)
            for target in registered_teleports
        ):
            raise TypeError(
                "teleport_targets must contain DebugTeleportTarget values"
            )
        site_ids = tuple(target.site_id for target in registered_teleports)
        if len(site_ids) != len(set(site_ids)):
            raise ValueError("debug teleport site IDs must be unique")
        if on_teleport is not None and not callable(on_teleport):
            raise TypeError("on_teleport must be callable")
        if registered_teleports and on_teleport is None:
            raise ValueError("on_teleport is required for teleport targets")
        registered_shops = tuple(shop_targets)
        if not all(isinstance(target, DebugShopTarget) for target in registered_shops):
            raise TypeError("shop_targets must contain DebugShopTarget values")
        shop_keys = tuple(target.shop_key for target in registered_shops)
        if len(shop_keys) != len(set(shop_keys)):
            raise ValueError("debug shop keys must be unique")
        if on_shop is not None and not callable(on_shop):
            raise TypeError("on_shop must be callable")
        if registered_shops and on_shop is None:
            raise ValueError("on_shop is required for shop targets")

        self.editor = editor
        self.save_data = save_data
        self.settings = settings
        self.fonts = fonts
        self.alert = alert
        self.teleport_targets = registered_teleports
        self.on_teleport = on_teleport
        self.shop_targets = registered_shops
        self.on_shop = on_shop
        self.localizer = Localizer(settings.language)
        self.debug_texts = LocalizedWindowTextFactory.from_language(
            fonts,
            Language.JAPANESE,
        )
        self.member_texts = LocalizedWindowTextFactory.from_language(
            fonts,
            settings.language,
        )
        self.teleport_texts = LocalizedWindowTextFactory.from_language(
            fonts,
            settings.language,
            role=FontRole.LARGE,
        )
        self.windows = WindowFactory(fonts.font_for(Language.JAPANESE))
        self.phase = DebugMenuPhase.MAIN
        self.main_window: Window
        self.main_cursor: WindowCursor
        self.member_window: Window | None = None
        self.member_cursor: WindowCursor | None = None
        self.member_index = 0
        self.teleport_window: Window | None = None
        self.teleport_cursor: WindowCursor | None = None
        self.teleport_index = 0
        self.teleport_scroll_offset = 0
        self.shop_window: Window | None = None
        self.shop_cursor: WindowCursor | None = None
        self.shop_index = 0
        self.shop_scroll_offset = 0
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

    def _teleport_count_text(self) -> str:
        return DEBUG_TEXT.teleport_count(len(self.teleport_targets))

    def _shop_count_text(self) -> str:
        return DEBUG_TEXT.shop_count(len(self.shop_targets))

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
            "teleport": self._teleport_count_text(),
            "shop": self._shop_count_text(),
        }
        labels = {
            "party_level": DEBUG_TEXT.party_level,
            "gold": DEBUG_TEXT.gold,
            "members": DEBUG_TEXT.members,
            "teleport": DEBUG_TEXT.teleport,
            "shop": DEBUG_TEXT.shop,
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

    def _build_teleport_window(self) -> None:
        placements = [
            self.debug_texts.create(DEBUG_TEXT.teleport_destination, 4, 3)
        ]
        visible_targets = self.teleport_targets[
            self.teleport_scroll_offset :
            self.teleport_scroll_offset + TELEPORT_VISIBLE_COUNT
        ]
        cursor_targets: list[CursorTarget] = []
        if not visible_targets:
            placements.append(
                self.debug_texts.create(
                    DEBUG_TEXT.no_teleport_destinations,
                    TELEPORT_TEXT_X,
                    TELEPORT_FIRST_Y,
                    color=DISABLED_COLOR,
                )
            )
        else:
            for row, target in enumerate(visible_targets):
                y = TELEPORT_FIRST_Y + row * TELEPORT_ROW_HEIGHT
                placements.append(
                    self.teleport_texts.create(target.name, TELEPORT_TEXT_X, y)
                )
                cursor_targets.append(
                    CursorTarget(TELEPORT_CURSOR_X, y, key=target.site_id)
                )
        placements.append(self._guide_text())
        self.teleport_window = self.windows.create(
            *DEBUG_WINDOW_GRID,
            tuple(placements),
            vertical_navigation=(
                len(self.teleport_targets) > TELEPORT_VISIBLE_COUNT
            ),
            opened=True,
        )
        if not cursor_targets:
            self.teleport_cursor = None
            return
        self.teleport_cursor = self.teleport_window.set_cursor(
            tuple(cursor_targets)
        )
        self._select_cursor_key(
            self.teleport_cursor,
            self.teleport_targets[self.teleport_index].site_id,
        )

    def _open_teleport(self) -> None:
        self.phase = DebugMenuPhase.TELEPORT
        self.teleport_index = 0
        self.teleport_scroll_offset = 0
        self._build_teleport_window()

    def _close_teleport(self) -> None:
        self.phase = DebugMenuPhase.MAIN
        self.teleport_window = None
        self.teleport_cursor = None
        self._build_main_window(selected_key="teleport")

    def _move_teleport(self, distance: int) -> None:
        if distance not in (-1, 1):
            raise ValueError("teleport distance must be -1 or 1")
        if not self.teleport_targets:
            return
        self.teleport_index = (
            self.teleport_index + distance
        ) % len(self.teleport_targets)
        if self.teleport_index < self.teleport_scroll_offset:
            self.teleport_scroll_offset = self.teleport_index
        elif (
            self.teleport_index
            >= self.teleport_scroll_offset + TELEPORT_VISIBLE_COUNT
        ):
            self.teleport_scroll_offset = (
                self.teleport_index - TELEPORT_VISIBLE_COUNT + 1
            )
        self._build_teleport_window()

    def _confirm_teleport(self) -> None:
        if self.teleport_cursor is None or self.on_teleport is None:
            self.alert.start()
            return
        site_id = self.teleport_cursor.selected_key
        if not isinstance(site_id, str) or not self.on_teleport(site_id):
            self.alert.start()

    def _update_teleport(self, input_state: InputState) -> None:
        if input_state.cancel.triggered:
            self._close_teleport()
            return
        if input_state.confirm.triggered:
            self._confirm_teleport()
            return
        if input_state.navigation is Direction.UP:
            self._move_teleport(-1)
        elif input_state.navigation is Direction.DOWN:
            self._move_teleport(1)
        elif self.teleport_window is not None:
            self.teleport_window.update()

    def _build_shop_window(self) -> None:
        placements = [self.debug_texts.create(DEBUG_TEXT.shop_selection, 4, 3)]
        visible_targets = self.shop_targets[
            self.shop_scroll_offset : self.shop_scroll_offset + SHOP_VISIBLE_COUNT
        ]
        cursor_targets: list[CursorTarget] = []
        if not visible_targets:
            placements.append(
                self.debug_texts.create(
                    DEBUG_TEXT.no_shops,
                    SHOP_TEXT_X,
                    SHOP_FIRST_Y,
                    color=DISABLED_COLOR,
                )
            )
        else:
            for row, target in enumerate(visible_targets):
                y = SHOP_FIRST_Y + row * SHOP_ROW_HEIGHT
                placements.append(
                    self.debug_texts.create(target.name, SHOP_TEXT_X, y)
                )
                cursor_targets.append(
                    CursorTarget(SHOP_CURSOR_X, y, key=target.shop_key)
                )
        placements.append(self._guide_text())
        self.shop_window = self.windows.create(
            *DEBUG_WINDOW_GRID,
            tuple(placements),
            vertical_navigation=len(self.shop_targets) > SHOP_VISIBLE_COUNT,
            opened=True,
        )
        if not cursor_targets:
            self.shop_cursor = None
            return
        self.shop_cursor = self.shop_window.set_cursor(tuple(cursor_targets))
        self._select_cursor_key(
            self.shop_cursor,
            self.shop_targets[self.shop_index].shop_key,
        )

    def _open_shops(self) -> None:
        self.phase = DebugMenuPhase.SHOP
        self.shop_index = 0
        self.shop_scroll_offset = 0
        self._build_shop_window()

    def _close_shops(self) -> None:
        self.phase = DebugMenuPhase.MAIN
        self.shop_window = None
        self.shop_cursor = None
        self._build_main_window(selected_key="shop")

    def _move_shop(self, distance: int) -> None:
        if distance not in (-1, 1):
            raise ValueError("shop distance must be -1 or 1")
        if not self.shop_targets:
            return
        self.shop_index = (self.shop_index + distance) % len(self.shop_targets)
        if self.shop_index < self.shop_scroll_offset:
            self.shop_scroll_offset = self.shop_index
        elif self.shop_index >= self.shop_scroll_offset + SHOP_VISIBLE_COUNT:
            self.shop_scroll_offset = self.shop_index - SHOP_VISIBLE_COUNT + 1
        self._build_shop_window()

    def _confirm_shop(self) -> None:
        if self.shop_cursor is None or self.on_shop is None:
            self.alert.start()
            return
        shop_key = self.shop_cursor.selected_key
        if not isinstance(shop_key, str) or not self.on_shop(shop_key):
            self.alert.start()

    def _update_shop(self, input_state: InputState) -> None:
        if input_state.cancel.triggered:
            self._close_shops()
            return
        if input_state.confirm.triggered:
            self._confirm_shop()
            return
        if input_state.navigation is Direction.UP:
            self._move_shop(-1)
        elif input_state.navigation is Direction.DOWN:
            self._move_shop(1)
        elif self.shop_window is not None:
            self.shop_window.update()

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
        if self.phase is DebugMenuPhase.TELEPORT:
            self._update_teleport(input_state)
            return False
        if self.phase is DebugMenuPhase.SHOP:
            self._update_shop(input_state)
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
            elif key == "teleport":
                self._open_teleport()
            elif key == "shop":
                self._open_shops()
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
        elif (
            self.phase is DebugMenuPhase.TELEPORT
            and self.teleport_window is not None
        ):
            self.teleport_window.draw()
        elif self.phase is DebugMenuPhase.SHOP and self.shop_window is not None:
            self.shop_window.draw()
        else:
            self.main_window.draw()

    @staticmethod
    def _select_cursor_key(cursor: WindowCursor, key: object) -> None:
        cursor.select_key(key)


__all__ = [
    "DebugMenuPhase",
    "DebugMenuOverlay",
    "DebugShopTarget",
    "DebugTeleportTarget",
    "MAX_GOLD",
    "NumericEntry",
]
