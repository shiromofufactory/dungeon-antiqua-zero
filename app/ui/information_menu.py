"""DA2-style information menu and monster bestiary overlay."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from enum import StrEnum

import pyxel

if __package__ == "ui":
    from input import Direction, InputState
    from item import Item
    from localization import Localizer, format_number
    from monster import MonsterDefinition, MonsterTribe
    from resistance import ResistanceType
    from resources import FontResources, ImageResources, TRANSPARENT_INDEX
    from state import Settings
    from systems import (
        MONSTER_COMBAT_FIELD_KEYS,
        MONSTER_TREASURE_ACQUIRED_FIELD_KEY,
    )
    from text_catalog import TextCatalog
else:
    from ..input import Direction, InputState
    from ..item import Item
    from ..localization import Localizer, format_number
    from ..monster import MonsterDefinition, MonsterTribe
    from ..resistance import ResistanceType
    from ..resources import FontResources, ImageResources, TRANSPARENT_INDEX
    from ..state import Settings
    from ..systems import (
        MONSTER_COMBAT_FIELD_KEYS,
        MONSTER_TREASURE_ACQUIRED_FIELD_KEY,
    )
    from ..text_catalog import TextCatalog

from .colors import (
    BLUE_TEXT_COLOR,
    DISABLED_COLOR,
    NEGATIVE_COLOR,
    POSITIVE_COLOR,
)
from .localized_text import LocalizedWindowTextFactory
from .text_format import pad
from .window import (
    DEFAULT_TEXT_COLOR,
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
MONSTER_STUN_MARKER_X = 22
MONSTER_STUN_MARKER = "止"
UNKNOWN_VALUE = "？？？？"

# DA2's bestiary has one icon position for each of these nine affinities. ZERO's
# additional STUN resistance is placed after them as a one-character marker
# because the current common icon sheet does not have a STUN icon.
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
    "information.monster_book",
    "monster_book.number",
    "monster_book.hp",
    "monster_book.mp",
    "monster_book.level",
    "monster_book.treasure",
    "monster_book.treasure_unknown",
    "monster_book.tolerance",
    "monster_book.weakness",
    "monster_book.unidentified",
    *(f"term.monster_tribe.{tribe.value}" for tribe in MonsterTribe),
)


class InformationPhase(StrEnum):
    """Current interaction layer of the information overlay."""

    MENU = "menu"
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


class InformationMenuOverlay:
    """Own the information submenu and its DA2-style monster book."""

    def __init__(
        self,
        *,
        monsters: Sequence[MonsterDefinition],
        monster_records: Mapping[str, set[str]],
        items: Mapping[str, Item],
        settings: Settings,
        texts: TextCatalog,
        fonts: FontResources,
        images: ImageResources,
        on_invalid_action: Callable[[], None] | None = None,
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
        if not isinstance(settings, Settings):
            raise TypeError("settings must be Settings")
        if not isinstance(texts, TextCatalog):
            raise TypeError("texts must be TextCatalog")
        if on_invalid_action is not None and not callable(on_invalid_action):
            raise TypeError("on_invalid_action must be callable")

        self.monsters = tuple(monsters)
        self.monster_records = monster_records
        self.items = items
        self.settings = settings
        self.texts = texts
        self.fonts = fonts
        self.images = images
        self.on_invalid_action = on_invalid_action
        self.phase = InformationPhase.MENU
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
        self.window_factory = WindowFactory(fonts.font_for(settings.language))
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
            (
                self.text_factory.create(
                    self.localized["information.monster_book"],
                    INFORMATION_TEXT_X,
                    INFORMATION_TEXT_Y,
                ),
            ),
        )
        self.header_cursor = self.header_window.set_cursor(
            (
                CursorTarget(
                    INFORMATION_CURSOR_X,
                    INFORMATION_TEXT_Y,
                    key="monster_book",
                ),
            )
        )
        self.main_window = self.window_factory.create(*INFORMATION_MAIN_WINDOW_GRID)
        self.monster_list_window: Window | None = None
        self.monster_list_cursor: WindowCursor | None = None
        self.monster_detail_window: Window | None = None
        self.windows = [self.header_window, self.main_window]

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
        self.main_window = self.window_factory.create(*INFORMATION_MAIN_WINDOW_GRID)
        self.monster_list_window = None
        self.monster_list_cursor = None
        self.monster_detail_window = None
        self.windows = [self.header_window, self.main_window]

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

    def _formatted(self, key: str, **values: str) -> str:
        return self.texts.formatted_text(key, self.localizer, values)

    def _monster_detail_texts(self) -> tuple[WindowText, ...]:
        selected = self.selected_monster
        if selected is None:
            return ()
        number, monster = selected
        fields = self.monster_records[monster.key]
        fully_identified = MONSTER_COMBAT_FIELD_KEYS.issubset(fields)
        hp_value = (
            UNKNOWN_VALUE
            if monster.is_boss or not fully_identified
            else pad(monster.max_hp, 4)
        )
        mp_value = UNKNOWN_VALUE if not fully_identified else pad(monster.max_mp, 4)
        lines: list[tuple[str, int]] = [
            (
                self._formatted(
                    "monster_book.number",
                    NUMBER=format_number(number),
                ),
                DEFAULT_TEXT_COLOR,
            ),
            (monster.localized_name(self.localizer), DEFAULT_TEXT_COLOR),
            (
                self.localized[f"term.monster_tribe.{monster.tribe.value}"],
                DEFAULT_TEXT_COLOR,
            ),
            (
                self._formatted("monster_book.hp", VALUE=hp_value),
                DEFAULT_TEXT_COLOR,
            ),
            (
                self._formatted("monster_book.mp", VALUE=mp_value),
                DEFAULT_TEXT_COLOR,
            ),
        ]
        if not fully_identified:
            lines.extend(
                (
                    ("", DEFAULT_TEXT_COLOR),
                    (self.localized["monster_book.unidentified"], NEGATIVE_COLOR),
                )
            )
        else:
            treasure_known = MONSTER_TREASURE_ACQUIRED_FIELD_KEY in fields
            if treasure_known:
                try:
                    treasure_name = self.items[
                        monster.treasure_item_key
                    ].localized_name(self.localizer)
                except KeyError as error:
                    raise InformationMenuDataError(
                        "モンスターのお宝がアイテムデータにありません: "
                        f"{monster.key}: {monster.treasure_item_key}"
                    ) from error
                treasure = self._formatted(
                    "monster_book.treasure",
                    ITEM=treasure_name,
                )
                treasure_color = DEFAULT_TEXT_COLOR
            else:
                treasure = self.localized["monster_book.treasure_unknown"]
                treasure_color = NEGATIVE_COLOR
            lines.extend(
                (
                    (
                        self._formatted(
                            "monster_book.level",
                            VALUE=format_number(monster.level),
                        ),
                        DEFAULT_TEXT_COLOR,
                    ),
                    (treasure, treasure_color),
                    (self.localized["monster_book.tolerance"], BLUE_TEXT_COLOR),
                    (
                        monster_affinity_icon_row(monster.resistances),
                        DEFAULT_TEXT_COLOR,
                    ),
                    (self.localized["monster_book.weakness"], POSITIVE_COLOR),
                    (
                        monster_affinity_icon_row(monster.weaknesses),
                        DEFAULT_TEXT_COLOR,
                    ),
                )
            )
        placements = [
            self.text_factory.create(
                text,
                MONSTER_DETAIL_TEXT_X,
                MONSTER_DETAIL_FIRST_Y + index * MONSTER_DETAIL_ROW_HEIGHT,
                color=color,
            )
            for index, (text, color) in enumerate(lines)
        ]
        if fully_identified:
            placements.extend(
                (
                    self.text_factory.create(
                        MONSTER_STUN_MARKER,
                        MONSTER_STUN_MARKER_X,
                        MONSTER_DETAIL_FIRST_Y
                        + 8 * MONSTER_DETAIL_ROW_HEIGHT,
                        color=(
                            DEFAULT_TEXT_COLOR
                            if ResistanceType.STUN in monster.resistances
                            else DISABLED_COLOR
                        ),
                    ),
                    self.text_factory.create(
                        MONSTER_STUN_MARKER,
                        MONSTER_STUN_MARKER_X,
                        MONSTER_DETAIL_FIRST_Y
                        + 10 * MONSTER_DETAIL_ROW_HEIGHT,
                        color=(
                            DEFAULT_TEXT_COLOR
                            if ResistanceType.STUN in monster.weaknesses
                            else DISABLED_COLOR
                        ),
                    ),
                )
            )
        return tuple(placements)

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
                self._open_monster_book()
                return False
            self.header_window.update(input_state.navigation)
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
    "MONSTER_LIST_VISIBLE_COUNT",
    "MONSTER_LIST_WINDOW_GRID",
    "MONSTER_STUN_MARKER",
    "MONSTER_STUN_MARKER_X",
    "monster_affinity_icon_row",
]
