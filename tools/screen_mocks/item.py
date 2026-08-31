"""Item-screen view used by the connected menu mock."""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum, StrEnum
import re

from tools._bootstrap import APP_ROOT
from tools.screen_mocks._fixtures import (
    load_mock_items,
    load_mock_party,
    load_mock_skills,
    load_mock_spells,
)
from tools.screen_mocks._party_status import PartyStatusPanel
from input import InputState
from item import Item
from item_detail import item_detail_lines
from localization import LocalizedText, Localizer, format_number
from member import Member
from rendering import PaletteShifter
from resources import FontResources, ImageResources
from spell import Spell
from state import Language, Settings
from text_catalog import TextCatalog
from ui import (
    CursorTarget,
    LocalizedWindowTextFactory,
    TEXT_COLORS,
    TEXT_ICONS,
    WindowCursor,
    WindowFactory,
    WindowText,
)

FACES_IMAGE_ID = "faces/faces_pc"
CATEGORY_WINDOW_GRID = (6, 0, 52, 5)
ITEM_LIST_WINDOW_GRID = (0, 5, 33, 39)
ITEM_INFO_WINDOW_GRID = (33, 5, 31, 39)

CATEGORY_TEXT_KEYS = {
    "use": "item.category.use",
    "drop": "item.category.drop",
    "index": "item.category.index",
    "important": "item.category.important",
}
CATEGORY_TEXT_X = (4, 14, 24, 36)
CATEGORY_CURSOR_X = tuple(x - 2 for x in CATEGORY_TEXT_X)
CATEGORY_TEXT_Y = 1

ITEM_VISIBLE_COUNT = 12
ITEM_TEXT_X = 4
ITEM_COUNT_X = 28
ITEM_FIRST_Y = 2
ITEM_ROW_HEIGHT = 3
ITEM_CURSOR_X = ITEM_TEXT_X - 2
ITEM_INFO_X = 2
ITEM_INFO_Y = 2
ITEM_INFO_ROW_HEIGHT = 3
ITEM_NAME_MAX_LENGTH = 11
ITEM_INFO_MAX_CELLS = 13
ITEM_INFO_MAX_ROWS = 12

_DISPLAY_TAG_PATTERN = re.compile(r"%[A-Z][A-Z0-9_]*%")


def _localized_slice(text: str, start: int, end: int) -> str:
    sliced = text[start:end]
    if not isinstance(text, LocalizedText):
        return sliced
    narrow_spans = tuple(
        (max(span_start, start) - start, min(span_end, end) - start)
        for span_start, span_end in text.narrow_spans
        if span_start < end and span_end > start
    )
    return LocalizedText(
        sliced,
        prefers_wide_font=text.prefers_wide_font,
        narrow_spans=narrow_spans,
    )


def _item_info_display_cells(text: str) -> int:
    cells = 0
    position = 0
    for match in _DISPLAY_TAG_PATTERN.finditer(text):
        tag = match.group()
        if tag not in TEXT_ICONS and tag not in TEXT_COLORS:
            continue
        cells += match.start() - position
        if tag in TEXT_ICONS:
            cells += 1
        position = match.end()
    return cells + len(text) - position


def _fit_item_info_lines(lines: tuple[str, ...]) -> tuple[str, ...]:
    """Wrap long tagged descriptions and keep the item window within 12 rows."""

    fitted: list[str] = []
    for line in lines:
        split_at = None
        if _item_info_display_cells(line) > ITEM_INFO_MAX_CELLS:
            split_at = next(
                (
                    match.start()
                    for match in _DISPLAY_TAG_PATTERN.finditer(line)
                    if match.start() > 0 and match.group() in TEXT_ICONS
                ),
                None,
            )
        if split_at is None:
            fitted.append(line)
        else:
            fitted.extend(
                (
                    _localized_slice(line, 0, split_at),
                    _localized_slice(line, split_at, len(line)),
                )
            )
    if len(fitted) > ITEM_INFO_MAX_ROWS and "" in fitted:
        fitted.remove("")
    if len(fitted) > ITEM_INFO_MAX_ROWS:
        raise ItemMockDataError(
            f"アイテム詳細が{ITEM_INFO_MAX_ROWS}行を超えています"
        )
    return tuple(fitted)

class ItemCategory(StrEnum):
    """DA2-style tabs shown at the top of the item screen."""

    USE = "use"
    DROP = "drop"
    INDEX = "index"
    IMPORTANT = "important"


class ItemSelectionPhase(Enum):
    """Selection stage used by the item screen."""

    CATEGORY = "category"
    ITEM = "item"


class ItemMockDataError(RuntimeError):
    """Raised when data required by the item mock is unavailable."""


class ItemScreenMock:
    def __init__(
        self,
        *,
        party: tuple[Member, ...] | None = None,
        items: Mapping[str, Item] | None = None,
        spells: Mapping[str, Spell] | None = None,
        settings: Settings | None = None,
        texts: TextCatalog | None = None,
        fonts: FontResources | None = None,
        faces: object | None = None,
        palette_shifter: PaletteShifter | None = None,
    ) -> None:
        """Build the DA2-style item view from menu-owned state."""

        item_catalog = load_mock_items() if items is None else items
        if not isinstance(item_catalog, Mapping) or not all(
            isinstance(key, str) and isinstance(item, Item) and key == item.key
            for key, item in item_catalog.items()
        ):
            raise TypeError("items must map each string key to its matching Item")
        spell_catalog = load_mock_spells() if spells is None else spells
        if not isinstance(spell_catalog, Mapping) or not all(
            isinstance(key, str) and isinstance(spell, Spell) and key == spell.key
            for key, spell in spell_catalog.items()
        ):
            raise TypeError("spells must map each string key to its matching Spell")
        if party is None:
            skills = load_mock_skills()
            party = load_mock_party(dict(item_catalog), skills)
        if not party:
            raise ValueError("party must contain at least one member")

        self.party = party
        self.items = dict(item_catalog)
        self.spells = dict(spell_catalog)
        self.item_counts = {key: 1 for key in self.items}
        self.inventory = tuple(self.items.values())
        self.important_items: tuple[Item, ...] = ()
        self.settings = settings if settings is not None else Settings()
        self.texts = (
            texts
            if texts is not None
            else TextCatalog.from_json(APP_ROOT / "data" / "texts.json")
        )
        self.fonts = fonts if fonts is not None else FontResources()
        self.faces = (
            faces if faces is not None else ImageResources().image(FACES_IMAGE_ID)
        )
        self.palette_shifter = palette_shifter
        self.phase = ItemSelectionPhase.CATEGORY
        self.selected_item_index = 0
        self.scroll_offset = 0
        self._build_windows()

    @property
    def category(self) -> ItemCategory:
        key = self.category_cursor.selected_key
        if not isinstance(key, ItemCategory):
            raise ItemMockDataError("item category cursor has no selection")
        return key

    @property
    def category_items(self) -> tuple[Item, ...]:
        if self.category is ItemCategory.IMPORTANT:
            return self.important_items
        return self.inventory

    @property
    def selected_item(self) -> Item | None:
        items = self.category_items
        if not items:
            return None
        return items[self.selected_item_index]

    @property
    def dimmed_member_indexes(self) -> frozenset[int]:
        """Return party positions unable to equip the selected equipment."""

        if self.phase is not ItemSelectionPhase.ITEM:
            return frozenset()
        item = self.selected_item
        if item is None or not item.is_equipment:
            return frozenset()
        return frozenset(
            index
            for index, member in enumerate(self.party)
            if not member.can_equip(item)
        )

    @property
    def page_index(self) -> int:
        return self.scroll_offset // ITEM_VISIBLE_COUNT

    def _localized_categories(self, localizer: Localizer) -> dict[ItemCategory, str]:
        localized: dict[ItemCategory, str] = {}
        for category in ItemCategory:
            key = CATEGORY_TEXT_KEYS[category.value]
            text = self.texts.text(key, localizer)
            if not text:
                raise ItemMockDataError(f"モック用テキストが見つかりません: {key}")
            localized[category] = text
        return localized

    def _build_windows(self) -> None:
        self.localizer = Localizer(self.settings.language)
        self.localized_texts = LocalizedWindowTextFactory.from_language(
            self.fonts,
            self.settings.language,
        )
        windows = WindowFactory(self.fonts.font_for(Language.JAPANESE))
        labels = self._localized_categories(self.localizer)
        self.category_window = windows.create(
            *CATEGORY_WINDOW_GRID,
            tuple(
                self.localized_texts.create(
                    labels[category],
                    CATEGORY_TEXT_X[index],
                    CATEGORY_TEXT_Y,
                )
                for index, category in enumerate(ItemCategory)
            ),
        )
        self.category_cursor = WindowCursor(
            self.category_window,
            tuple(
                CursorTarget(
                    CATEGORY_CURSOR_X[index],
                    CATEGORY_TEXT_Y,
                    key=category,
                )
                for index, category in enumerate(ItemCategory)
            ),
        )
        self.party_panel = PartyStatusPanel(
            party=self.party,
            localizer=self.localizer,
            texts=self.texts,
            text_factory=self.localized_texts,
            window_factory=windows,
            faces=self.faces,
            palette_shifter=self.palette_shifter,
        )
        self.party_window = self.party_panel.window
        self._window_factory = windows
        self._build_item_windows()

    def _build_item_windows(self) -> None:
        visible_items = self.category_items[
            self.scroll_offset : self.scroll_offset + ITEM_VISIBLE_COUNT
        ]
        list_texts: list[WindowText] = []
        targets: list[CursorTarget] = []
        show_count = self.category in (ItemCategory.USE, ItemCategory.DROP)
        for row, item in enumerate(visible_items):
            y = ITEM_FIRST_Y + row * ITEM_ROW_HEIGHT
            list_texts.append(
                self.localized_texts.create(
                    str(item.localized_name(self.localizer))[:ITEM_NAME_MAX_LENGTH],
                    ITEM_TEXT_X,
                    y,
                )
            )
            if show_count:
                list_texts.append(
                    self.localized_texts.create(
                        format_number(self.item_counts[item.key]),
                        ITEM_COUNT_X,
                        y,
                    )
                )
            targets.append(CursorTarget(ITEM_CURSOR_X, y, key=item.key))

        scrollable = len(self.category_items) > ITEM_VISIBLE_COUNT
        self.item_list_window = self._window_factory.create(
            *ITEM_LIST_WINDOW_GRID,
            tuple(list_texts),
            horizontal_navigation=scrollable,
            vertical_navigation=scrollable,
        )
        self.item_cursor = WindowCursor(
            self.item_list_window,
            tuple(targets),
            active=self.phase is ItemSelectionPhase.ITEM,
        )
        selected = self.selected_item
        if selected is not None and self.item_cursor.active:
            while self.item_cursor.selected_key != selected.key:
                self.item_cursor.move_down()
        info_texts: tuple[WindowText, ...] = ()
        if selected is not None:
            info_texts = tuple(
                self.localized_texts.create(
                    text,
                    ITEM_INFO_X,
                    ITEM_INFO_Y + row * ITEM_INFO_ROW_HEIGHT,
                )
                for row, text in enumerate(
                    _fit_item_info_lines(
                        item_detail_lines(
                            selected,
                            self.spells,
                            self.localizer,
                            self.texts,
                        )
                    )
                )
                if text
            )
        self.item_info_window = self._window_factory.create(
            *ITEM_INFO_WINDOW_GRID,
            info_texts,
        )
        self.windows = (
            self.category_window,
            self.item_list_window,
            self.item_info_window,
            self.party_window,
        )

    def _change_category(self, distance: int) -> None:
        if distance not in (-1, 1):
            raise ValueError("category distance must be -1 or 1")
        moved = (
            self.category_cursor.move_left()
            if distance < 0
            else self.category_cursor.move_right()
        )
        if moved:
            self.selected_item_index = 0
            self.scroll_offset = 0
            self._build_item_windows()

    def _move_item(self, distance: int) -> None:
        if distance not in (-1, 1):
            raise ValueError("item distance must be -1 or 1")
        items = self.category_items
        if not items:
            return
        previous_index = self.selected_item_index
        self.selected_item_index = (previous_index + distance) % len(items)
        if self.selected_item_index == 0 and previous_index == len(items) - 1:
            self.scroll_offset = 0
        elif self.selected_item_index == len(items) - 1 and previous_index == 0:
            self.scroll_offset = max(0, len(items) - ITEM_VISIBLE_COUNT)
        elif self.selected_item_index < self.scroll_offset:
            self.scroll_offset = self.selected_item_index
        elif self.selected_item_index >= self.scroll_offset + ITEM_VISIBLE_COUNT:
            self.scroll_offset = self.selected_item_index - ITEM_VISIBLE_COUNT + 1
        self._build_item_windows()

    def _move_page(self, distance: int) -> None:
        if distance not in (-1, 1):
            raise ValueError("page distance must be -1 or 1")
        items = self.category_items
        if not items:
            return
        row = self.selected_item_index - self.scroll_offset
        next_offset = self.scroll_offset + distance * ITEM_VISIBLE_COUNT
        if next_offset >= len(items):
            self.scroll_offset = 0
            self.selected_item_index = 0
        elif next_offset < 0:
            if self.scroll_offset > 0:
                self.scroll_offset = 0
            else:
                self.scroll_offset = (
                    (len(items) - 1) // ITEM_VISIBLE_COUNT
                ) * ITEM_VISIBLE_COUNT
            self.selected_item_index = min(
                self.scroll_offset + row,
                len(items) - 1,
            )
        else:
            self.scroll_offset = next_offset
            self.selected_item_index = min(
                self.scroll_offset + row,
                len(items) - 1,
            )
        self._build_item_windows()

    def _enter_item_selection(self) -> None:
        if self.selected_item is None:
            return
        self.phase = ItemSelectionPhase.ITEM
        self.category_cursor.active = False
        self.item_cursor.active = True

    def _return_to_category_selection(self) -> None:
        self.phase = ItemSelectionPhase.CATEGORY
        self.category_cursor.active = True
        self.item_cursor.active = False

    def update(self, input_state: InputState) -> bool:
        """Update selection and report whether the menu should be restored."""

        self.item_list_window.set_vertical_navigation_pressed()

        if self.phase is ItemSelectionPhase.CATEGORY:
            self.category_cursor.update()
            if input_state.cancel.triggered:
                return True
            if input_state.previous_page.triggered:
                self._change_category(-1)
                return False
            if input_state.next_page.triggered:
                self._change_category(1)
                return False
            navigation = input_state.navigation
            if navigation is not None and navigation.dx:
                self._change_category(-1 if navigation.dx < 0 else 1)
                return False
            if input_state.confirm.triggered:
                self._enter_item_selection()
            return False

        self.item_cursor.update()
        if input_state.cancel.triggered:
            self._return_to_category_selection()
            return False
        if input_state.previous_page.triggered:
            self._move_page(-1)
            return False
        if input_state.next_page.triggered:
            self._move_page(1)
            return False
        navigation = input_state.navigation
        if navigation is not None:
            if navigation.dy < 0:
                self._move_item(-1)
                self.item_list_window.set_vertical_navigation_pressed(-1)
            elif navigation.dy > 0:
                self._move_item(1)
                self.item_list_window.set_vertical_navigation_pressed(1)
            elif navigation.dx < 0:
                self._move_page(-1)
            elif navigation.dx > 0:
                self._move_page(1)
        # Confirm intentionally does nothing until item effects are implemented.
        return False

    def draw(self) -> None:
        for window in self.windows:
            window.draw()
        self.party_panel.draw_faces(self.dimmed_member_indexes)
        self.category_cursor.draw()
        if self.phase is ItemSelectionPhase.ITEM:
            self.item_cursor.draw()


__all__ = [
    "ItemCategory",
    "ItemMockDataError",
    "ItemScreenMock",
    "ItemSelectionPhase",
    "item_detail_lines",
]
