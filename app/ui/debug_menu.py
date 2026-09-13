"""Development-only debug menu overlay used by the game."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import Enum, auto

from input import Direction, InputAction, InputDevice, InputState
from item import Item
from localization import Localizer, format_number
from member import (
    FIORA_CHARACTER_KEY,
    MAX_INTERNAL_LEVEL,
    MIN_INTERNAL_LEVEL,
    Member,
)
from resources import FontResources, FontRole
from state import Language, SaveData, Settings
from systems import DebugPartyEditor, DebugPartyError, InventorySystem

from ui import (
    DEFAULT_TEXT_COLOR,
    DISABLED_COLOR,
    CursorTarget,
    LocalizedWindowTextFactory,
    Window,
    WindowCursor,
    WindowFactory,
    WindowText,
    input_icon_tag,
)
from ui.debug_text import DEBUG_TEXT

DEBUG_WINDOW_GRID = (2, 2, 60, 56)
DEBUG_ROW_HEIGHT = 3
MAIN_ITEM_KEYS = (
    "party_level",
    "gold",
    "members",
    "member_status",
    "items",
    "teleport",
    "shop",
)
MAIN_FIRST_Y = 9
MAIN_ROWS = tuple(
    (key, MAIN_FIRST_Y + index * DEBUG_ROW_HEIGHT)
    for index, key in enumerate(MAIN_ITEM_KEYS)
)
MAIN_CURSOR_X = 4
MAIN_LABEL_X = 6
MAIN_VALUE_X = 34
MEMBER_FIRST_Y = 9
MEMBER_ROW_HEIGHT = DEBUG_ROW_HEIGHT
MEMBER_ROW_COUNT = 10
MEMBER_TEXT_X = (6, 34)
MEMBER_CURSOR_X = (4, 32)
MEMBER_STATUS_FIRST_Y = 9
MEMBER_STATUS_LABEL_X = 6
MEMBER_STATUS_VALUE_X = 21
MEMBER_STATUS_COLON_X = 18
MEMBER_STATUS_ROWS = (
    ("hp", MEMBER_STATUS_FIRST_Y),
    ("mp", MEMBER_STATUS_FIRST_Y + DEBUG_ROW_HEIGHT),
    ("poisoned", MEMBER_STATUS_FIRST_Y + DEBUG_ROW_HEIGHT * 2),
    ("paralyzed", MEMBER_STATUS_FIRST_Y + DEBUG_ROW_HEIGHT * 3),
    ("skills", MEMBER_STATUS_FIRST_Y + DEBUG_ROW_HEIGHT * 4),
)
MEMBER_SKILL_FIRST_Y = 9
MEMBER_SKILL_ROW_COUNT = 10
MEMBER_SKILL_TEXT_X = (6, 34)
MEMBER_SKILL_CURSOR_X = (4, 32)
ITEM_FIRST_Y = 7
ITEM_ROW_HEIGHT = DEBUG_ROW_HEIGHT
ITEM_VISIBLE_COUNT = 13
ITEM_TEXT_X = (6, 36)
ITEM_CURSOR_X = (4, 34)
ITEM_GUIDE_X = 24
ITEM_QUANTITY_X = 28
ITEM_GUIDE_Y = 52
TELEPORT_FIRST_Y = 9
TELEPORT_ROW_HEIGHT = DEBUG_ROW_HEIGHT
TELEPORT_VISIBLE_COUNT = 13
TELEPORT_TEXT_X = 6
TELEPORT_CURSOR_X = 4
SHOP_FIRST_Y = 7
SHOP_ROW_HEIGHT = DEBUG_ROW_HEIGHT
SHOP_VISIBLE_COUNT = 13
SHOP_TEXT_X = 6
SHOP_CURSOR_X = 4
NUMERIC_WINDOW_GRID = (12, 14, 40, 30)
NUMERIC_DIGIT_X = (6, 10, 14, 18, 22)
NUMERIC_ROW_Y = (11, 11 + DEBUG_ROW_HEIGHT)
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
    MEMBER_STATUS_LIST = auto()
    MEMBER_STATUS = auto()
    MEMBER_SKILLS = auto()
    ITEMS = auto()
    TELEPORT = auto()
    SHOP = auto()
    NUMBER = auto()


class DebugItemPane(Enum):
    """Active column in the debug item warehouse."""

    INVENTORY = auto()
    WAREHOUSE = auto()


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
        inventory_system: InventorySystem,
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
        if not isinstance(inventory_system, InventorySystem):
            raise TypeError("inventory_system must be an InventorySystem")
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
        self.inventory_system = inventory_system
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
        self.member_status_list_window: Window | None = None
        self.member_status_list_cursor: WindowCursor | None = None
        self.member_status_window: Window | None = None
        self.member_status_cursor: WindowCursor | None = None
        self.member_status_index = 0
        self.member_status_key: str | None = None
        self.member_skill_window: Window | None = None
        self.member_skill_cursor: WindowCursor | None = None
        self.member_skill_index = 0
        self.item_window: Window | None = None
        self.item_cursor: WindowCursor | None = None
        self.item_pane = DebugItemPane.WAREHOUSE
        self.inventory_item_index = 0
        self.inventory_item_scroll_offset = 0
        self.warehouse_item_index = 0
        self.warehouse_item_scroll_offset = 0
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
        self.numeric_member_key: str | None = None
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

    def _item_count_text(self) -> str:
        return DEBUG_TEXT.item_count(len(self.inventory_system.items))

    def _party_member_count_text(self) -> str:
        return DEBUG_TEXT.party_member_count(len(self.editor.party))

    def _member_skill_count_text(self, member: Member) -> str:
        return DEBUG_TEXT.skill_count(len(member.skills))

    def _guide_text(self, y: int = GUIDE_Y) -> WindowText:
        return self.debug_texts.create(
            DEBUG_TEXT.close_guide.replace(
                "%CANCEL%",
                input_icon_tag(InputAction.CANCEL, InputDevice.KEYBOARD),
            ),
            GUIDE_X,
            y,
        )

    def _build_main_window(self, selected_key: str = "party_level") -> None:
        values = {
            "party_level": format_number(self.editor.baseline_level),
            "gold": format_number(self.save_data.gold),
            "members": self._member_count_text(),
            "member_status": self._party_member_count_text(),
            "items": self._item_count_text(),
            "teleport": self._teleport_count_text(),
            "shop": self._shop_count_text(),
        }
        labels = {
            "party_level": DEBUG_TEXT.party_level,
            "gold": DEBUG_TEXT.gold,
            "members": DEBUG_TEXT.members,
            "member_status": DEBUG_TEXT.member_status,
            "items": DEBUG_TEXT.items,
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

    def _build_member_status_list_window(self) -> None:
        party = self.editor.party
        placements = [
            self.debug_texts.create(DEBUG_TEXT.member_status_selection, 4, 3),
            self.debug_texts.create(self._party_member_count_text(), 34, 3),
        ]
        targets: list[CursorTarget] = []
        for index, member in enumerate(party):
            y = MEMBER_STATUS_FIRST_Y + index * DEBUG_ROW_HEIGHT
            key = member.definition.key
            placements.append(
                self.member_texts.create(
                    member.definition.localized_name(self.localizer),
                    MEMBER_STATUS_LABEL_X,
                    y,
                )
            )
            targets.append(CursorTarget(MAIN_CURSOR_X, y, key=key))
        placements.append(self._guide_text())
        self.member_status_list_window = self.windows.create(
            *DEBUG_WINDOW_GRID,
            tuple(placements),
            opened=True,
        )
        self.member_status_list_cursor = (
            self.member_status_list_window.set_cursor(tuple(targets))
        )
        selected_key = party[self.member_status_index].definition.key
        self._select_cursor_key(self.member_status_list_cursor, selected_key)

    def _open_member_status_list(self) -> None:
        self.phase = DebugMenuPhase.MEMBER_STATUS_LIST
        self.member_status_index = 0
        self.member_status_key = None
        self._build_member_status_list_window()

    def _close_member_status_list(self) -> None:
        self.phase = DebugMenuPhase.MAIN
        self.member_status_list_window = None
        self.member_status_list_cursor = None
        self._build_main_window(selected_key="member_status")

    def _build_member_status_window(self, selected_key: str = "hp") -> None:
        if self.member_status_key is None:
            raise RuntimeError("member status editing is not active")
        member = self.editor.member(self.member_status_key)
        condition = {
            True: DEBUG_TEXT.condition_on,
            False: DEBUG_TEXT.condition_off,
        }
        labels = {
            "hp": DEBUG_TEXT.hp,
            "mp": DEBUG_TEXT.mp,
            "poisoned": DEBUG_TEXT.poisoned,
            "paralyzed": DEBUG_TEXT.paralyzed,
            "skills": DEBUG_TEXT.skills,
        }
        values = {
            "hp": f"{format_number(member.hp)}／{format_number(member.max_hp)}",
            "mp": f"{format_number(member.mp)}／{format_number(member.max_mp)}",
            "poisoned": condition[member.poisoned],
            "paralyzed": condition[member.paralyzed],
            "skills": self._member_skill_count_text(member),
        }
        placements = [
            self.debug_texts.create(DEBUG_TEXT.member_status, 4, 3),
            self.member_texts.create(
                member.definition.localized_name(self.localizer),
                32,
                3,
            ),
        ]
        for key, y in MEMBER_STATUS_ROWS:
            placements.extend(
                (
                    self.debug_texts.create(
                        labels[key],
                        MEMBER_STATUS_LABEL_X,
                        y,
                    ),
                    self.debug_texts.create("：", MEMBER_STATUS_COLON_X, y),
                    self.debug_texts.create(
                        values[key],
                        MEMBER_STATUS_VALUE_X,
                        y,
                    ),
                )
            )
        placements.append(self._guide_text())
        self.member_status_window = self.windows.create(
            *DEBUG_WINDOW_GRID,
            tuple(placements),
            opened=True,
        )
        self.member_status_cursor = self.member_status_window.set_cursor(
            tuple(
                CursorTarget(MAIN_CURSOR_X, y, key=key)
                for key, y in MEMBER_STATUS_ROWS
            )
        )
        self._select_cursor_key(self.member_status_cursor, selected_key)

    def _open_selected_member_status(self) -> None:
        if self.member_status_list_cursor is None:
            self.alert.start()
            return
        key = self.member_status_list_cursor.selected_key
        if not isinstance(key, str):
            self.alert.start()
            return
        self.member_status_key = key
        self.phase = DebugMenuPhase.MEMBER_STATUS
        self._build_member_status_window()

    def _close_member_status(self) -> None:
        self.phase = DebugMenuPhase.MEMBER_STATUS_LIST
        self.member_status_key = None
        self.member_status_window = None
        self.member_status_cursor = None
        self._build_member_status_list_window()

    def _toggle_member_condition(self, target: str) -> None:
        if self.member_status_key is None:
            return
        member = self.editor.member(self.member_status_key)
        if target == "poisoned":
            self.editor.set_member_poisoned(
                self.member_status_key,
                not member.poisoned,
            )
        elif target == "paralyzed":
            self.editor.set_member_paralyzed(
                self.member_status_key,
                not member.paralyzed,
            )
        else:
            raise ValueError(f"unsupported member condition: {target}")
        self._build_member_status_window(selected_key=target)

    def _build_member_skill_window(self) -> None:
        if self.member_status_key is None:
            raise RuntimeError("member skill editing is not active")
        member = self.editor.member(self.member_status_key)
        skills = self.editor.candidate_skills
        placements = [
            self.debug_texts.create(DEBUG_TEXT.skill_selection, 4, 3),
            self.member_texts.create(
                member.definition.localized_name(self.localizer),
                32,
                3,
            ),
        ]
        targets: list[CursorTarget] = []
        for index, skill in enumerate(skills):
            column, row = divmod(index, MEMBER_SKILL_ROW_COUNT)
            y = MEMBER_SKILL_FIRST_Y + row * DEBUG_ROW_HEIGHT
            selected = member.has_skill(skill.key)
            marker = "●" if selected else "○"
            placements.extend(
                (
                    self.debug_texts.create(
                        marker,
                        MEMBER_SKILL_TEXT_X[column],
                        y,
                    ),
                    self.member_texts.create(
                        skill.localized_name(self.localizer),
                        MEMBER_SKILL_TEXT_X[column] + 2,
                        y,
                    ),
                )
            )
            targets.append(
                CursorTarget(
                    MEMBER_SKILL_CURSOR_X[column],
                    y,
                    key=skill.key,
                )
            )
        placements.append(self._guide_text())
        self.member_skill_window = self.windows.create(
            *DEBUG_WINDOW_GRID,
            tuple(placements),
            opened=True,
        )
        self.member_skill_cursor = self.member_skill_window.set_cursor(
            tuple(targets)
        )
        selected_key = skills[self.member_skill_index].key
        self._select_cursor_key(self.member_skill_cursor, selected_key)

    def _open_member_skills(self) -> None:
        self.phase = DebugMenuPhase.MEMBER_SKILLS
        self.member_skill_index = 0
        self._build_member_skill_window()

    def _close_member_skills(self) -> None:
        self.phase = DebugMenuPhase.MEMBER_STATUS
        self.member_skill_window = None
        self.member_skill_cursor = None
        self._build_member_status_window(selected_key="skills")

    def _toggle_selected_member_skill(self) -> None:
        if self.member_status_key is None or self.member_skill_cursor is None:
            return
        skill_key = self.member_skill_cursor.selected_key
        if not isinstance(skill_key, str):
            self.alert.start()
            return
        try:
            self.editor.toggle_member_skill(self.member_status_key, skill_key)
        except DebugPartyError:
            self.alert.start()
        self._build_member_skill_window()

    def _update_member_skills(self, input_state: InputState) -> None:
        if input_state.cancel.triggered:
            self._close_member_skills()
            return
        if input_state.confirm.triggered:
            self._toggle_selected_member_skill()
            return
        if (
            self.member_skill_window is not None
            and self.member_skill_window.update(input_state.navigation)
            and self.member_skill_cursor is not None
        ):
            selected_key = self.member_skill_cursor.selected_key
            self.member_skill_index = next(
                index
                for index, skill in enumerate(self.editor.candidate_skills)
                if skill.key == selected_key
            )

    def _update_member_status_list(self, input_state: InputState) -> None:
        if input_state.cancel.triggered:
            self._close_member_status_list()
            return
        if input_state.confirm.triggered:
            self._open_selected_member_status()
            return
        if (
            self.member_status_list_window is not None
            and self.member_status_list_window.update(input_state.navigation)
            and self.member_status_list_cursor is not None
        ):
            selected_key = self.member_status_list_cursor.selected_key
            self.member_status_index = next(
                index
                for index, member in enumerate(self.editor.party)
                if member.definition.key == selected_key
            )

    def _update_member_status(self, input_state: InputState) -> None:
        if input_state.cancel.triggered:
            self._close_member_status()
            return
        if input_state.confirm.triggered and self.member_status_cursor is not None:
            target = self.member_status_cursor.selected_key
            if target in ("hp", "mp"):
                self._open_member_numeric(target)
            elif target == "skills":
                self._open_member_skills()
            elif isinstance(target, str):
                self._toggle_member_condition(target)
            return
        if self.member_status_window is not None:
            self.member_status_window.update(input_state.navigation)

    def _item_entries(self, pane: DebugItemPane) -> tuple[Item, ...]:
        if pane is DebugItemPane.INVENTORY:
            return self.inventory_system.items
        return self.inventory_system.catalog_items

    def _item_position(self, pane: DebugItemPane) -> tuple[int, int]:
        if pane is DebugItemPane.INVENTORY:
            return self.inventory_item_index, self.inventory_item_scroll_offset
        return self.warehouse_item_index, self.warehouse_item_scroll_offset

    def _set_item_position(
        self,
        pane: DebugItemPane,
        index: int,
        scroll_offset: int,
    ) -> None:
        if pane is DebugItemPane.INVENTORY:
            self.inventory_item_index = index
            self.inventory_item_scroll_offset = scroll_offset
        else:
            self.warehouse_item_index = index
            self.warehouse_item_scroll_offset = scroll_offset

    def _selected_item(self) -> Item | None:
        entries = self._item_entries(self.item_pane)
        if not entries:
            return None
        index, _scroll_offset = self._item_position(self.item_pane)
        return entries[index]

    def _build_item_window(self) -> None:
        inventory_items = self.inventory_system.items
        warehouse_items = self.inventory_system.catalog_items
        pane_entries = {
            DebugItemPane.INVENTORY: inventory_items,
            DebugItemPane.WAREHOUSE: warehouse_items,
        }
        placements = [
            self.debug_texts.create(DEBUG_TEXT.item_inventory, 4, 3),
            self.debug_texts.create(DEBUG_TEXT.item_warehouse, 36, 3),
        ]
        cursor_targets: list[CursorTarget] = []
        for column, pane in enumerate(
            (DebugItemPane.INVENTORY, DebugItemPane.WAREHOUSE)
        ):
            entries = pane_entries[pane]
            _index, scroll_offset = self._item_position(pane)
            visible_entries = entries[
                scroll_offset : scroll_offset + ITEM_VISIBLE_COUNT
            ]
            if not visible_entries:
                placements.append(
                    self.debug_texts.create(
                        DEBUG_TEXT.no_items,
                        ITEM_TEXT_X[column],
                        ITEM_FIRST_Y,
                        color=DISABLED_COLOR,
                    )
                )
                continue
            for row, item in enumerate(visible_entries):
                y = ITEM_FIRST_Y + row * ITEM_ROW_HEIGHT
                placements.append(
                    self.member_texts.create(
                        item.localized_name(self.localizer),
                        ITEM_TEXT_X[column],
                        y,
                    )
                )
                if pane is DebugItemPane.INVENTORY:
                    placements.append(
                        self.debug_texts.create(
                            format_number(self.inventory_system.quantity(item)),
                            ITEM_QUANTITY_X,
                            y,
                        )
                    )
                if pane is self.item_pane:
                    cursor_targets.append(
                        CursorTarget(ITEM_CURSOR_X[column], y, key=item.key)
                    )

        placements.extend(
            (
                self._guide_text(ITEM_GUIDE_Y),
                self.debug_texts.create(
                    DEBUG_TEXT.item_switch_guide,
                    ITEM_GUIDE_X,
                    ITEM_GUIDE_Y,
                ),
            )
        )
        active_entries = pane_entries[self.item_pane]
        self.item_window = self.windows.create(
            *DEBUG_WINDOW_GRID,
            tuple(placements),
            vertical_navigation=len(active_entries) > ITEM_VISIBLE_COUNT,
            opened=True,
        )
        if not cursor_targets:
            self.item_cursor = None
            return
        self.item_cursor = self.item_window.set_cursor(tuple(cursor_targets))
        index, _scroll_offset = self._item_position(self.item_pane)
        self._select_cursor_key(self.item_cursor, active_entries[index].key)

    def _open_items(self) -> None:
        self.phase = DebugMenuPhase.ITEMS
        self.item_pane = DebugItemPane.WAREHOUSE
        self.inventory_item_index = 0
        self.inventory_item_scroll_offset = 0
        self.warehouse_item_index = 0
        self.warehouse_item_scroll_offset = 0
        self._build_item_window()

    def _close_items(self) -> None:
        self.phase = DebugMenuPhase.MAIN
        self.item_window = None
        self.item_cursor = None
        self._build_main_window(selected_key="items")

    def _switch_item_pane(self, pane: DebugItemPane) -> None:
        if pane is self.item_pane:
            return
        self.item_pane = pane
        entries = self._item_entries(pane)
        index, scroll_offset = self._item_position(pane)
        if entries:
            index = min(index, len(entries) - 1)
            scroll_offset = min(
                scroll_offset,
                max(0, len(entries) - ITEM_VISIBLE_COUNT),
            )
        else:
            index = 0
            scroll_offset = 0
        self._set_item_position(pane, index, scroll_offset)
        self._build_item_window()

    def _move_item(self, distance: int) -> None:
        if (
            isinstance(distance, bool)
            or not isinstance(distance, int)
            or distance == 0
        ):
            raise ValueError("item distance must be a non-zero integer")
        entries = self._item_entries(self.item_pane)
        if not entries:
            return
        index, scroll_offset = self._item_position(self.item_pane)
        index = (index + distance) % len(entries)
        if index < scroll_offset:
            scroll_offset = index
        elif index >= scroll_offset + ITEM_VISIBLE_COUNT:
            scroll_offset = index - ITEM_VISIBLE_COUNT + 1
        self._set_item_position(self.item_pane, index, scroll_offset)
        self._build_item_window()

    def _acquire_selected_item(self) -> None:
        if self.item_pane is not DebugItemPane.WAREHOUSE:
            self.alert.start()
            return
        item = self._selected_item()
        if item is None or not self.inventory_system.add(
            item,
            members=self.editor.party,
        ):
            self.alert.start()
            return
        self._build_item_window()

    def _update_items(self, input_state: InputState) -> None:
        if input_state.cancel.triggered:
            self._close_items()
            return
        if input_state.confirm.triggered:
            self._acquire_selected_item()
            return
        if input_state.navigation is Direction.LEFT:
            self._switch_item_pane(DebugItemPane.INVENTORY)
        elif input_state.navigation is Direction.RIGHT:
            self._switch_item_pane(DebugItemPane.WAREHOUSE)
        elif input_state.navigation is Direction.UP:
            self._move_item(-1)
        elif input_state.navigation is Direction.DOWN:
            self._move_item(1)
        elif self.item_window is not None:
            self.item_window.update()

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
        self.numeric_member_key = None
        self.numeric_entry = entry
        self._build_numeric_window()

    def _open_member_numeric(self, target: object) -> None:
        if (
            not isinstance(target, str)
            or target not in ("hp", "mp")
            or self.member_status_key is None
        ):
            raise ValueError(f"unsupported member numeric target: {target}")
        member = self.editor.member(self.member_status_key)
        maximum = member.max_hp if target == "hp" else member.max_mp
        self.phase = DebugMenuPhase.NUMBER
        self.numeric_target = target
        self.numeric_member_key = self.member_status_key
        self.numeric_entry = NumericEntry(
            0,
            maximum,
            len(str(maximum)),
        )
        self._build_numeric_window()

    def _build_numeric_window(self) -> None:
        if self.numeric_entry is None or self.numeric_target is None:
            raise RuntimeError("numeric input is not active")
        labels = {
            "party_level": DEBUG_TEXT.party_level,
            "gold": DEBUG_TEXT.gold,
            "hp": DEBUG_TEXT.hp,
            "mp": DEBUG_TEXT.mp,
        }
        label = labels[self.numeric_target]
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
        elif target == "gold":
            self.save_data.gold = value
        elif target == "hp" and self.numeric_member_key is not None:
            self.editor.set_member_hp(self.numeric_member_key, value)
        elif target == "mp" and self.numeric_member_key is not None:
            self.editor.set_member_mp(self.numeric_member_key, value)
        else:
            raise RuntimeError(f"numeric target has no destination: {target}")
        member_key = self.numeric_member_key
        self.numeric_entry = None
        self.numeric_target = None
        self.numeric_member_key = None
        self.numeric_window = None
        self.numeric_cursor = None
        if member_key is not None:
            self.phase = DebugMenuPhase.MEMBER_STATUS
            self._build_member_status_window(selected_key=target)
        else:
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
                member_key = self.numeric_member_key
                self.numeric_entry = None
                self.numeric_target = None
                self.numeric_member_key = None
                self.numeric_window = None
                self.numeric_cursor = None
                if member_key is not None:
                    self.phase = DebugMenuPhase.MEMBER_STATUS
                    self._build_member_status_window(selected_key=target)
                else:
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
        if self.phase is DebugMenuPhase.ITEMS:
            self._update_items(input_state)
            return False
        if self.phase is DebugMenuPhase.TELEPORT:
            self._update_teleport(input_state)
            return False
        if self.phase is DebugMenuPhase.SHOP:
            self._update_shop(input_state)
            return False
        if self.phase is DebugMenuPhase.MEMBER_STATUS_LIST:
            self._update_member_status_list(input_state)
            return False
        if self.phase is DebugMenuPhase.MEMBER_STATUS:
            self._update_member_status(input_state)
            return False
        if self.phase is DebugMenuPhase.MEMBER_SKILLS:
            self._update_member_skills(input_state)
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
            elif key == "member_status":
                self._open_member_status_list()
            elif key == "items":
                self._open_items()
            elif key == "teleport":
                self._open_teleport()
            elif key == "shop":
                self._open_shops()
            elif isinstance(key, str) and key in ("party_level", "gold"):
                self._open_numeric(key)
            else:
                self.alert.start()
            return False
        self.main_window.update(input_state.navigation)
        return False

    def draw(self) -> None:
        if self.phase is DebugMenuPhase.NUMBER and self.numeric_window is not None:
            self.numeric_window.draw()
        elif self.phase is DebugMenuPhase.MEMBERS and self.member_window is not None:
            self.member_window.draw()
        elif (
            self.phase is DebugMenuPhase.MEMBER_STATUS_LIST
            and self.member_status_list_window is not None
        ):
            self.member_status_list_window.draw()
        elif (
            self.phase is DebugMenuPhase.MEMBER_STATUS
            and self.member_status_window is not None
        ):
            self.member_status_window.draw()
        elif (
            self.phase is DebugMenuPhase.MEMBER_SKILLS
            and self.member_skill_window is not None
        ):
            self.member_skill_window.draw()
        elif self.phase is DebugMenuPhase.ITEMS and self.item_window is not None:
            self.item_window.draw()
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
    "MAX_GOLD",
    "DebugItemPane",
    "DebugMenuOverlay",
    "DebugMenuPhase",
    "DebugShopTarget",
    "DebugTeleportTarget",
    "NumericEntry",
]
