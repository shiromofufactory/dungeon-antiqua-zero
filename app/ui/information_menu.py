"""DA2-style information menu, conversation log, and monster bestiary."""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping, Sequence
from enum import StrEnum

import pyxel

if __package__ == "ui":
    from input import Direction, InputState
    from item import Item
    from localization import Localizer, format_number
    from monster import MonsterDefinition, MonsterTribe
    from resistance import ResistanceType
    from resources import (
        TRANSPARENT_INDEX,
        FontResources,
        FontRole,
        ImageResources,
    )
    from resources.event_messages import EventMessageCatalog
    from state import Language, Settings
    from systems import (
        MONSTER_COMBAT_FIELD_KEYS,
        MONSTER_TREASURE_ACQUIRED_FIELD_KEY,
        MONSTER_TREASURE_IDENTIFIED_FIELD_KEY,
    )
    from text_catalog import TextCatalog
else:
    from ..input import Direction, InputState
    from ..item import Item
    from ..localization import Localizer, format_number
    from ..monster import MonsterDefinition, MonsterTribe
    from ..resistance import ResistanceType
    from ..resources import (
        TRANSPARENT_INDEX,
        FontResources,
        FontRole,
        ImageResources,
    )
    from ..resources.event_messages import EventMessageCatalog
    from ..state import Language, Settings
    from ..systems import (
        MONSTER_COMBAT_FIELD_KEYS,
        MONSTER_TREASURE_ACQUIRED_FIELD_KEY,
        MONSTER_TREASURE_IDENTIFIED_FIELD_KEY,
    )
    from ..text_catalog import TextCatalog

from .colors import BLUE_TEXT_COLOR
from .localized_text import LocalizedWindowTextFactory
from .text_format import pad
from .window import (
    DEFAULT_TEXT_COLOR,
    FRAME_TILE_SIZE,
    TEXT_GRID_Y,
    CursorTarget,
    Window,
    WindowCursor,
    WindowFactory,
    WindowText,
)


INFORMATION_HEADER_WINDOW_GRID = (0, 0, 32, 15)
INFORMATION_MAIN_WINDOW_GRID = (0, 15, 64, 45)
MONSTER_LIST_WINDOW_GRID = (0, 15, 32, 45)
MONSTER_DETAIL_WINDOW_GRID = (30, 0, 34, 60)
INFORMATION_TEXT_X = 4
INFORMATION_CURSOR_X = 2
INFORMATION_TEXT_Y = 2
INFORMATION_CATEGORY_ROW_HEIGHT = 3
CONVERSATION_LOG_TEXT_X = 4
CONVERSATION_LOG_CURSOR_X = 2
CONVERSATION_LOG_FIRST_Y = 2
CONVERSATION_LOG_CJK_ROW_HEIGHT = 4
CONVERSATION_LOG_ENGLISH_ROW_HEIGHT = 3
MONSTER_LIST_TEXT_X = 4
MONSTER_LIST_CURSOR_X = 2
MONSTER_LIST_FIRST_Y = 2
MONSTER_LIST_ROW_HEIGHT = 3
MONSTER_LIST_VISIBLE_COUNT = 14
MONSTER_DETAIL_TEXT_X = 2
MONSTER_DETAIL_FIRST_Y = 2
MONSTER_DETAIL_ROW_HEIGHT = 3
MONSTER_IMAGE_CENTER_X = 58
MONSTER_IMAGE_CENTER_Y = 180
UNKNOWN_VALUE = "？？？？"

# DA2's bestiary has one icon position for each of these nine affinities.
# STUN is a battle-control rule and is intentionally omitted from the display.
MONSTER_BOOK_ICON_TYPES = (
    ResistanceType.FIRE,
    ResistanceType.FREEZE,
    ResistanceType.DARK,
    ResistanceType.SLEEP,
    ResistanceType.POISON,
    ResistanceType.PARALIZE,
    ResistanceType.CONFUSE,
    ResistanceType.SILENCE,
    ResistanceType.DEATH,
)

INFORMATION_TEXT_KEYS = (
    "information.mission",
    "information.conversation_log",
    "information.monster_book",
    "monster_book.number",
    "monster_book.hp",
    "monster_book.mp",
    "monster_book.level",
    "monster_book.treasure",
    "monster_book.treasure_unknown",
    "monster_book.tolerance",
    "monster_book.weakness",
    *(f"term.monster_tribe.{tribe.value}" for tribe in MonsterTribe),
)


class InformationPhase(StrEnum):
    """Current interaction layer of the information overlay."""

    MENU = "menu"
    CONVERSATION_LOG = "conversation_log"
    MISSION = "mission"
    MONSTER_BOOK = "monster_book"


class InformationMenuDataError(RuntimeError):
    """Raised when information-menu master data cannot be displayed."""


def monster_affinity_icon_row(
    affinities: frozenset[ResistanceType],
) -> str:
    """Build DA2's enabled/disabled affinity icon strip."""

    if not isinstance(affinities, frozenset) or not all(
        isinstance(value, ResistanceType) for value in affinities
    ):
        raise TypeError("affinities must be a frozenset of ResistanceType")
    return "　" + "".join(
        f"%{resistance.value}%"
        if resistance in affinities
        else f"%{resistance.value}_DISABLED%"
        for resistance in MONSTER_BOOK_ICON_TYPES
    )


def monster_detail_texts(
    *,
    number: int,
    monster: MonsterDefinition,
    revealed_fields: Collection[str],
    items: Mapping[str, Item],
    texts: TextCatalog,
    localizer: Localizer,
    text_factory: LocalizedWindowTextFactory,
    text_x: int = MONSTER_DETAIL_TEXT_X,
    first_y: int = MONSTER_DETAIL_FIRST_Y,
    row_height: int = MONSTER_DETAIL_ROW_HEIGHT,
) -> tuple[WindowText, ...]:
    """Build the detail shared by the monster book and battle Identify."""

    fully_identified = MONSTER_COMBAT_FIELD_KEYS.issubset(revealed_fields)
    hp_value = UNKNOWN_VALUE if not fully_identified else pad(monster.max_hp, 4)
    mp_value = UNKNOWN_VALUE if not fully_identified else pad(monster.max_mp, 4)

    def formatted(key: str, **values: str) -> str:
        return texts.formatted_text(key, localizer, values)

    lines: list[tuple[str, int]] = [
        (
            formatted(
                "monster_book.number",
                NUMBER=format_number(number),
            ),
            DEFAULT_TEXT_COLOR,
        ),
        (monster.localized_name(localizer), DEFAULT_TEXT_COLOR),
        (
            texts.text(f"term.monster_tribe.{monster.tribe.value}", localizer),
            DEFAULT_TEXT_COLOR,
        ),
        (
            formatted(
                "monster_book.level",
                VALUE=pad(monster.level, 4),
            ),
            DEFAULT_TEXT_COLOR,
        ),
        (
            formatted("monster_book.hp", VALUE=hp_value),
            DEFAULT_TEXT_COLOR,
        ),
        (
            formatted("monster_book.mp", VALUE=mp_value),
            DEFAULT_TEXT_COLOR,
        ),
    ]
    treasure_known = bool(
        {
            MONSTER_TREASURE_ACQUIRED_FIELD_KEY,
            MONSTER_TREASURE_IDENTIFIED_FIELD_KEY,
        }.intersection(revealed_fields)
    )
    if treasure_known:
        try:
            treasure_name = items[
                monster.treasure_item_key
            ].localized_name(localizer)
        except KeyError as error:
            raise InformationMenuDataError(
                "モンスターのお宝がアイテムデータにありません: "
                f"{monster.key}: {monster.treasure_item_key}"
            ) from error
        treasure = formatted(
            "monster_book.treasure",
            ITEM=treasure_name,
        )
    else:
        treasure = texts.text("monster_book.treasure_unknown", localizer)
    lines.extend(
        (
            (treasure, DEFAULT_TEXT_COLOR),
            (
                texts.text("monster_book.tolerance", localizer),
                DEFAULT_TEXT_COLOR,
            ),
            (
                monster_affinity_icon_row(monster.resistances),
                DEFAULT_TEXT_COLOR,
            ),
            (
                texts.text("monster_book.weakness", localizer),
                DEFAULT_TEXT_COLOR,
            ),
            (
                monster_affinity_icon_row(monster.weaknesses),
                DEFAULT_TEXT_COLOR,
            ),
        )
    )
    result: list[WindowText] = []
    affinity_rows = {8: monster.resistances, 10: monster.weaknesses}
    for index, (text, color) in enumerate(lines):
        y = first_y + index * row_height
        if index in affinity_rows and not fully_identified:
            # Keep each 8px slot fixed even when the language font is wider.
            for slot, resistance in enumerate(MONSTER_BOOK_ICON_TYPES):
                if resistance.value not in revealed_fields:
                    continue
                tag = resistance.value
                if resistance not in affinity_rows[index]:
                    tag += "_DISABLED"
                result.append(
                    text_factory.create(
                        f"%{tag}%", text_x + 2 + slot * 2, y, color=color,
                    )
                )
        else:
            result.append(text_factory.create(text, text_x, y, color=color))
    return tuple(result)


class InformationMenuOverlay:
    """Own the information submenu and its DA2-style monster book."""

    def __init__(
        self,
        *,
        monsters: Sequence[MonsterDefinition],
        monster_records: Mapping[str, set[str]],
        items: Mapping[str, Item],
        logs: Sequence[Mapping[str, object]],
        settings: Settings,
        texts: TextCatalog,
        event_messages: EventMessageCatalog,
        fonts: FontResources,
        images: ImageResources,
        on_invalid_action: Callable[[], None] | None = None,
        mission_message_ids: Sequence[str] = (),
    ) -> None:
        if not isinstance(monsters, Sequence) or not all(
            isinstance(monster, MonsterDefinition) for monster in monsters
        ):
            raise TypeError("monsters must contain MonsterDefinition values")
        if not isinstance(monster_records, Mapping) or not all(
            isinstance(key, str)
            and key
            and isinstance(fields, set)
            and all(isinstance(field, str) and field for field in fields)
            for key, fields in monster_records.items()
        ):
            raise TypeError("monster_records must map monster keys to field sets")
        if not isinstance(items, Mapping) or not all(
            isinstance(key, str) and isinstance(item, Item)
            for key, item in items.items()
        ):
            raise TypeError("items must map stable keys to Item values")
        if not isinstance(logs, Sequence) or isinstance(logs, (str, bytes)):
            raise TypeError("logs must be a sequence of mappings")
        if not all(isinstance(log, Mapping) for log in logs):
            raise TypeError("logs must contain mappings")
        if not isinstance(settings, Settings):
            raise TypeError("settings must be Settings")
        if not isinstance(texts, TextCatalog):
            raise TypeError("texts must be TextCatalog")
        if not isinstance(event_messages, EventMessageCatalog):
            raise TypeError("event_messages must be EventMessageCatalog")
        if on_invalid_action is not None and not callable(on_invalid_action):
            raise TypeError("on_invalid_action must be callable")

        if (
            not isinstance(mission_message_ids, Sequence)
            or isinstance(mission_message_ids, (str, bytes))
            or not all(isinstance(message_id, str) and message_id for message_id in mission_message_ids)
        ):
            raise TypeError("mission_message_ids must contain non-empty message IDs")

        self.monsters = tuple(monsters)
        self.monster_records = monster_records
        self.items = items
        self.logs = tuple(dict(log) for log in logs)
        self.settings = settings
        self.texts = texts
        self.event_messages = event_messages
        self.fonts = fonts
        self.images = images
        self.on_invalid_action = on_invalid_action
        self.mission_scroll_row = 0
        self.mission_message_ids = tuple(mission_message_ids)
        self.phase = InformationPhase.MENU
        self.selected_log_index = 0
        self.conversation_scroll_row = 0
        self.selected_monster_index = 0
        self._monster_image_cache: dict[str, object] = {}

        self.localizer = Localizer(settings.language)
        self.localized = {
            key: texts.text(key, self.localizer) for key in INFORMATION_TEXT_KEYS
        }
        missing = tuple(key for key, value in self.localized.items() if not value)
        if missing:
            raise InformationMenuDataError(
                f"情報メニュー用テキストが見つかりません: {missing}"
            )
        self.text_factory = LocalizedWindowTextFactory.from_language(
            fonts,
            settings.language,
        )
        self.log_text_factory = LocalizedWindowTextFactory.from_language(
            fonts,
            settings.language,
            role=FontRole.LARGE,
        )
        # Log counters always use ZERO's Japanese 8x12 standard font so the
        # fullwidth digits and slash have identical metrics in every language.
        self.log_number_text_factory = LocalizedWindowTextFactory.from_language(
            fonts,
            Language.JAPANESE,
            role=FontRole.STANDARD,
        )
        self.window_factory = WindowFactory(fonts.font_for(settings.language))
        self._mission_rows = self._resolve_mission_rows()
        self._conversation_entries = self._resolve_conversation_entries()
        self._build_information_menu()

    @property
    def registered_monsters(self) -> tuple[tuple[int, MonsterDefinition], ...]:
        """Return encountered monsters in master order with one-based numbers."""

        return tuple(
            (number, monster)
            for number, monster in enumerate(self.monsters, start=1)
            if monster.key in self.monster_records
        )

    @property
    def selected_monster(self) -> tuple[int, MonsterDefinition] | None:
        entries = self.registered_monsters
        if not entries:
            return None
        return entries[self.selected_monster_index]

    def _build_information_menu(self) -> None:
        self.header_window = self.window_factory.create(
            *INFORMATION_HEADER_WINDOW_GRID,
            tuple(
                self.text_factory.create(
                    self.localized[key],
                    INFORMATION_TEXT_X,
                    INFORMATION_TEXT_Y
                    + index * INFORMATION_CATEGORY_ROW_HEIGHT,
                )
                for index, key in enumerate(
                    (
                        "information.mission",
                        "information.conversation_log",
                        "information.monster_book",
                    )
                )
            ),
        )
        self.header_cursor = self.header_window.set_cursor(
            tuple(
                CursorTarget(
                    INFORMATION_CURSOR_X,
                    INFORMATION_TEXT_Y + index * INFORMATION_CATEGORY_ROW_HEIGHT,
                    key=key,
                )
                for index, key in enumerate(
                    ("mission", "conversation_log", "monster_book")
                )
            )
        )
        self.main_window = self.window_factory.create(*INFORMATION_MAIN_WINDOW_GRID)
        self.conversation_cursor: WindowCursor | None = None
        self.monster_list_window: Window | None = None
        self.monster_list_cursor: WindowCursor | None = None
        self.monster_detail_window: Window | None = None
        self._show_selected_category()

    @staticmethod
    def _format_log_arguments(arguments: object) -> dict[str, str]:
        if not isinstance(arguments, Mapping):
            return {}
        converted: dict[str, str] = {}
        for key, value in arguments.items():
            if not isinstance(key, str) or not key:
                continue
            if value is None:
                converted[key] = ""
            elif isinstance(value, bool):
                converted[key] = "true" if value else "false"
            elif isinstance(value, (str, int)):
                converted[key] = str(value)
        return converted

    def _resolve_conversation_entries(self) -> tuple[tuple[str, ...], ...]:
        entries: list[tuple[str, ...]] = []
        for log in self.logs:
            values = self._format_log_arguments(log.get("arguments"))
            text_key = log.get("text_key")
            message_id = log.get("message_id")
            if isinstance(text_key, str) and text_key:
                lines = self.texts.formatted_lines(
                    text_key,
                    self.localizer,
                    values,
                )
            elif isinstance(message_id, str) and message_id:
                lines = self.event_messages.formatted_lines(
                    message_id,
                    self.localizer,
                    values,
                )
            else:
                continue
            visible_lines = tuple(line for line in lines if line)
            if visible_lines:
                entries.append(visible_lines)
        return tuple(entries)

    @property
    def conversation_row_height(self) -> int:
        if self.settings.language is Language.ENGLISH:
            return CONVERSATION_LOG_ENGLISH_ROW_HEIGHT
        return CONVERSATION_LOG_CJK_ROW_HEIGHT

    @property
    def conversation_visible_row_count(self) -> int:
        message_extent = (
            self.log_text_factory.baseline_offset
            + FontResources.line_height_for(
                self.settings.language,
                role=FontRole.LARGE,
            )
        )
        counter_extent = (
            self.log_number_text_factory.baseline_offset
            + FontResources.line_height_for(
                Language.JAPANESE,
                role=FontRole.STANDARD,
            )
        )
        line_extent = max(message_extent, counter_extent)
        available_pixels = (
            INFORMATION_MAIN_WINDOW_GRID[3] * TEXT_GRID_Y
            - FRAME_TILE_SIZE
            - CONVERSATION_LOG_FIRST_Y * TEXT_GRID_Y
            - line_extent
        )
        return (
            available_pixels // (self.conversation_row_height * TEXT_GRID_Y)
            + 1
        )

    def _conversation_rows(self) -> tuple[tuple[str, int, int | None], ...]:
        rows: list[tuple[str, int, int | None]] = []
        count = len(self._conversation_entries)
        for index, lines in enumerate(self._conversation_entries):
            rows.append((f"{index + 1}/{count}", BLUE_TEXT_COLOR, index))
            rows.extend((line, DEFAULT_TEXT_COLOR, None) for line in lines)
            rows.append(("", DEFAULT_TEXT_COLOR, None))
        return tuple(rows)

    def _build_conversation_window(self, *, cursor_active: bool) -> None:
        rows = self._conversation_rows()
        if self._conversation_entries:
            self.selected_log_index %= len(self._conversation_entries)
        else:
            self.selected_log_index = 0
            self.conversation_scroll_row = 0

        header_rows = {
            log_index: row_index
            for row_index, (_text, _color, log_index) in enumerate(rows)
            if log_index is not None
        }
        selected_row = header_rows.get(self.selected_log_index, 0)
        selected_end_row = selected_row
        if self._conversation_entries:
            selected_end_row += len(
                self._conversation_entries[self.selected_log_index]
            )
        visible_count = self.conversation_visible_row_count
        self.conversation_scroll_row = min(
            self.conversation_scroll_row,
            selected_row,
        )
        if selected_end_row >= self.conversation_scroll_row + visible_count:
            self.conversation_scroll_row = selected_end_row - visible_count + 1
        max_scroll = max(0, len(rows) - visible_count)
        self.conversation_scroll_row = min(
            max(0, self.conversation_scroll_row),
            max_scroll,
        )

        visible_rows = rows[
            self.conversation_scroll_row :
            self.conversation_scroll_row + visible_count
        ]
        placements = tuple(
            (
                self.log_number_text_factory
                if log_index is not None
                else self.log_text_factory
            ).create(
                text,
                CONVERSATION_LOG_TEXT_X,
                CONVERSATION_LOG_FIRST_Y + index * self.conversation_row_height,
                color=color,
            )
            for index, (text, color, log_index) in enumerate(visible_rows)
        )
        self.main_window = self.window_factory.create(
            *INFORMATION_MAIN_WINDOW_GRID,
            placements,
            vertical_navigation=len(rows) > visible_count,
        )
        selected_visible_row = selected_row - self.conversation_scroll_row
        if (
            cursor_active
            and self._conversation_entries
            and 0 <= selected_visible_row < visible_count
        ):
            self.conversation_cursor = self.main_window.set_cursor(
                (
                    CursorTarget(
                        CONVERSATION_LOG_CURSOR_X,
                        CONVERSATION_LOG_FIRST_Y
                        + selected_visible_row * self.conversation_row_height,
                        key=self.selected_log_index,
                    ),
                ),
            )
        else:
            self.conversation_cursor = None

    def _resolve_mission_rows(self) -> tuple[str, ...]:
        rows: list[str] = []
        for message_id in self.mission_message_ids:
            lines = self.event_messages.formatted_lines(message_id, self.localizer, {})
            if any(lines):
                if rows:
                    rows.append("")
                rows.extend(lines)
        return tuple(rows)

    def _build_mission_window(self) -> None:
        visible_count = self.conversation_visible_row_count
        max_scroll = max(0, len(self._mission_rows) - visible_count)
        self.mission_scroll_row = min(max_scroll, max(0, self.mission_scroll_row))
        self.main_window = self.window_factory.create(
            *INFORMATION_MAIN_WINDOW_GRID,
            tuple(
                self.log_text_factory.create(
                    text, CONVERSATION_LOG_TEXT_X,
                    CONVERSATION_LOG_FIRST_Y + index * self.conversation_row_height,
                )
                for index, text in enumerate(self._mission_rows[
                    self.mission_scroll_row:self.mission_scroll_row + visible_count
                ])
            ),
            vertical_navigation=max_scroll > 0,
        )
        self.conversation_cursor = None

    def _show_selected_category(self) -> None:
        if self.header_cursor.selected_key == "mission":
            self._build_mission_window()
        elif self.header_cursor.selected_key == "conversation_log":
            self._build_conversation_window(
                cursor_active=self.phase is InformationPhase.CONVERSATION_LOG
            )
        else:
            self.main_window = self.window_factory.create(
                *INFORMATION_MAIN_WINDOW_GRID
            )
            self.conversation_cursor = None
        self.windows = [self.header_window, self.main_window]

    def _open_conversation_log(self) -> None:
        if not self._conversation_entries:
            if self.on_invalid_action is not None:
                self.on_invalid_action()
            return
        self.phase = InformationPhase.CONVERSATION_LOG
        self.header_cursor.active = False
        self._build_conversation_window(cursor_active=True)
        self.windows = [self.header_window, self.main_window]

    def _close_conversation_log(self) -> None:
        self.phase = InformationPhase.MENU
        self.header_cursor.active = True
        self._show_selected_category()

    def _open_monster_book(self) -> None:
        if not self.registered_monsters:
            if self.on_invalid_action is not None:
                self.on_invalid_action()
            return
        self.phase = InformationPhase.MONSTER_BOOK
        self.header_cursor.active = False
        self.selected_monster_index = min(
            self.selected_monster_index,
            len(self.registered_monsters) - 1,
        )
        self._build_monster_book_windows()

    def _close_monster_book(self) -> None:
        self.phase = InformationPhase.MENU
        self.header_cursor.active = True
        self.monster_list_window = None
        self.monster_list_cursor = None
        self.monster_detail_window = None
        self._show_selected_category()

    def _build_monster_book_windows(self) -> None:
        entries = self.registered_monsters
        page_start = (
            self.selected_monster_index // MONSTER_LIST_VISIBLE_COUNT
        ) * MONSTER_LIST_VISIBLE_COUNT
        visible_entries = entries[
            page_start : page_start + MONSTER_LIST_VISIBLE_COUNT
        ]
        list_texts = tuple(
            self.text_factory.create(
                monster.localized_name(self.localizer),
                MONSTER_LIST_TEXT_X,
                MONSTER_LIST_FIRST_Y + row * MONSTER_LIST_ROW_HEIGHT,
            )
            for row, (_number, monster) in enumerate(visible_entries)
        )
        self.monster_list_window = self.window_factory.create(
            *MONSTER_LIST_WINDOW_GRID,
            list_texts,
            vertical_navigation=len(entries) > MONSTER_LIST_VISIBLE_COUNT,
        )
        self.monster_list_cursor = self.monster_list_window.set_cursor(
            tuple(
                CursorTarget(
                    MONSTER_LIST_CURSOR_X,
                    MONSTER_LIST_FIRST_Y + row * MONSTER_LIST_ROW_HEIGHT,
                    key=page_start + row,
                )
                for row in range(len(visible_entries))
            )
        )
        for _row in range(self.selected_monster_index - page_start):
            self.monster_list_cursor.move_down()

        self.monster_detail_window = self.window_factory.create(
            *MONSTER_DETAIL_WINDOW_GRID,
            self._monster_detail_texts(),
        )
        self.windows = [
            self.header_window,
            self.monster_list_window,
            self.monster_detail_window,
        ]

    def _monster_detail_texts(self) -> tuple[WindowText, ...]:
        selected = self.selected_monster
        if selected is None:
            return ()
        number, monster = selected
        return monster_detail_texts(
            number=number,
            monster=monster,
            revealed_fields=self.monster_records[monster.key],
            items=self.items,
            texts=self.texts,
            localizer=self.localizer,
            text_factory=self.text_factory,
        )

    def _move_monster_selection(self, distance: int) -> None:
        entries = self.registered_monsters
        if not entries:
            return
        self.selected_monster_index = (
            self.selected_monster_index + distance
        ) % len(entries)
        self._build_monster_book_windows()

    def _move_monster_page(self, distance: int) -> None:
        entries = self.registered_monsters
        if not entries:
            return
        current = self.selected_monster_index
        last_page_start = (
            (len(entries) - 1) // MONSTER_LIST_VISIBLE_COUNT
        ) * MONSTER_LIST_VISIBLE_COUNT
        if distance > 0:
            target = (
                0
                if current >= last_page_start
                else min(current + MONSTER_LIST_VISIBLE_COUNT, len(entries) - 1)
            )
        else:
            target = (
                last_page_start
                if current < MONSTER_LIST_VISIBLE_COUNT
                else current - MONSTER_LIST_VISIBLE_COUNT
            )
        self.selected_monster_index = target
        self._build_monster_book_windows()

    def update(self, input_state: InputState) -> bool:
        """Update the topmost information layer and report an outer close."""

        if not isinstance(input_state, InputState):
            raise TypeError("input_state must be an InputState")
        if self.phase is InformationPhase.MENU:
            if input_state.cancel.triggered:
                return True
            if input_state.confirm.triggered:
                if self.header_cursor.selected_key == "mission" and self._mission_rows:
                    self.phase = InformationPhase.MISSION
                    self.header_cursor.active = False
                elif self.header_cursor.selected_key == "conversation_log":
                    self._open_conversation_log()
                elif self.header_cursor.selected_key == "monster_book":
                    self._open_monster_book()
                return False
            if self.header_window.update(input_state.navigation):
                self._show_selected_category()
            return False

        if self.phase is InformationPhase.MISSION:
            if input_state.cancel.triggered:
                self.phase = InformationPhase.MENU
                self.header_cursor.active = True
                self._show_selected_category()
                return False
            direction = 0
            if input_state.navigation in (Direction.UP, Direction.DOWN):
                direction = -1 if input_state.navigation is Direction.UP else 1
            page = self.conversation_visible_row_count
            if input_state.previous_page.triggered:
                direction = -page
            elif input_state.next_page.triggered:
                direction = page
            if direction:
                self.mission_scroll_row += direction
                self._build_mission_window()
                self.windows = [self.header_window, self.main_window]
            self.main_window.set_vertical_navigation_pressed((direction > 0) - (direction < 0))
            return False

        if self.phase is InformationPhase.CONVERSATION_LOG:
            if input_state.cancel.triggered:
                self._close_conversation_log()
                return False
            if input_state.navigation in (Direction.UP, Direction.DOWN):
                direction = -1 if input_state.navigation is Direction.UP else 1
                self.selected_log_index = (
                    self.selected_log_index + direction
                ) % len(self._conversation_entries)
                self._build_conversation_window(cursor_active=True)
                self.main_window.set_vertical_navigation_pressed(direction)
                self.windows = [self.header_window, self.main_window]
                return False
            self.main_window.set_vertical_navigation_pressed()
            if self.conversation_cursor is not None:
                self.conversation_cursor.update()
            return False

        if input_state.cancel.triggered:
            self._close_monster_book()
            return False
        if input_state.previous_page.triggered:
            self._move_monster_page(-1)
            return False
        if input_state.next_page.triggered:
            self._move_monster_page(1)
            return False
        if input_state.navigation in (Direction.UP, Direction.DOWN):
            direction = -1 if input_state.navigation is Direction.UP else 1
            self._move_monster_selection(direction)
            if self.monster_list_window is not None:
                self.monster_list_window.set_vertical_navigation_pressed(direction)
            return False
        if self.monster_list_window is not None:
            self.monster_list_window.set_vertical_navigation_pressed()
        if self.monster_list_cursor is not None:
            self.monster_list_cursor.update()
        return False

    def draw(self) -> None:
        for window in self.windows:
            window.draw()
        if (
            self.phase is not InformationPhase.MONSTER_BOOK
            or self.monster_detail_window is None
        ):
            return
        selected = self.selected_monster
        if selected is None:
            return
        _number, monster = selected
        image = self._monster_image_cache.get(monster.key)
        if image is None:
            image = self.images.image(monster.image_resource_id)
            self._monster_image_cache[monster.key] = image
        pyxel.blt(
            self.monster_detail_window.content_x
            + MONSTER_IMAGE_CENTER_X
            - monster.width // 2,
            self.monster_detail_window.content_y
            + MONSTER_IMAGE_CENTER_Y
            - monster.height // 2,
            image,
            0,
            0,
            monster.width,
            monster.height,
            TRANSPARENT_INDEX,
        )


__all__ = [
    "INFORMATION_HEADER_WINDOW_GRID",
    "INFORMATION_MAIN_WINDOW_GRID",
    "InformationMenuDataError",
    "InformationMenuOverlay",
    "InformationPhase",
    "MONSTER_BOOK_ICON_TYPES",
    "MONSTER_DETAIL_WINDOW_GRID",
    "MONSTER_IMAGE_CENTER_X",
    "MONSTER_IMAGE_CENTER_Y",
    "MONSTER_LIST_VISIBLE_COUNT",
    "MONSTER_LIST_WINDOW_GRID",
    "monster_affinity_icon_row",
    "monster_detail_texts",
]
