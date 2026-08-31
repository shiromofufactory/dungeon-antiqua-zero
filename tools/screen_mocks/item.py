"""Item-screen view used by the connected menu mock."""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum, StrEnum

from tools._bootstrap import APP_ROOT
from tools.screen_mocks._fixtures import (
    load_mock_items,
    load_mock_party,
    load_mock_skills,
)
from tools.screen_mocks._party_status import PartyStatusPanel
from input import InputState
from item import Item, ItemEquipType
from localization import LocalizedText, Localizer, format_number
from member import Member
from resources import FontResources, ImageResources
from state import Language, Settings
from text_catalog import TextCatalog
from ui import (
    CursorTarget,
    LocalizedWindowTextFactory,
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

ITEM_TYPE_TEXT_KEYS = {
    ItemEquipType.ITEM: "item.detail.type.ITEM",
    ItemEquipType.RIGHT: "item.detail.type.RIGHT",
    ItemEquipType.LEFT: "item.detail.type.LEFT",
    ItemEquipType.TWO_HANDS: "item.detail.type.TWO_HANDS",
    ItemEquipType.BODY: "item.detail.type.BODY",
    ItemEquipType.HEAD: "item.detail.type.HEAD",
    ItemEquipType.ARM: "item.detail.type.ARM",
}
ITEM_TYPES_WITH_SUBTYPE = frozenset(
    (
        ItemEquipType.RIGHT,
        ItemEquipType.TWO_HANDS,
        ItemEquipType.BODY,
        ItemEquipType.HEAD,
        ItemEquipType.ARM,
    )
)
ITEM_SUBTYPE_TEXT_KEYS = {
    subtype: f"item.detail.subtype.{subtype}"
    for subtype in (
        "ITEM",
        "SWORD",
        "KNIFE",
        "KATANA",
        "SPEAR",
        "HAMMER",
        "AXE",
        "THROWING",
        "ROD",
        "WAND",
        "SHIELD",
        "GENERAL",
        "HEAVY",
        "MAGICAL",
    )
}
ITEM_REQUIREMENT_TEXT_KEYS = {
    requirement: f"item.detail.requirement.{requirement}"
    for requirement in (
        "LV9",
        "NO_DRAGONS",
        "NO_FAIRYS",
        "ONLY_DRAGON",
        "ONLY_FAIRYS",
        "ONLY_FEMALE",
        "ONLY_MALE",
        "ONLY_RAGNA",
        "ONLY_ROBO",
    )
}
ITEM_STAT_ROWS = (
    ("attack", "item.detail.attack"),
    ("hit", "item.detail.hit"),
    ("defense", "item.detail.defense"),
    ("evasion", "item.detail.evasion"),
    ("spell_resistance", "status.spell_resistance"),
)
ITEM_ABILITY_ROWS = (
    ("strength_modifier", "status.strength"),
    ("agility_modifier", "status.agility"),
    ("magic_modifier", "status.magic"),
)
ITEM_TYPE_ICON_TAGS = {
    ItemEquipType.HEAD: "%HEAD%",
    ItemEquipType.BODY: "%BODY%",
    ItemEquipType.ARM: "%ARM%",
}


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


def _required_catalog_text(
    texts: TextCatalog,
    key: str,
    localizer: Localizer,
) -> str:
    text = texts.text(key, localizer)
    if not text:
        raise ItemMockDataError(f"モック用テキストが見つかりません: {key}")
    return text


def _required_catalog_lines(
    texts: TextCatalog,
    key: str,
    localizer: Localizer,
) -> tuple[str, ...]:
    lines = texts.lines(key, localizer)
    if not lines:
        raise ItemMockDataError(f"モック用テキストが見つかりません: {key}")
    return lines


def _composed_text(localizer: Localizer, *parts: str) -> str:
    text = "".join(str(part) for part in parts)
    if localizer.language is not Language.ENGLISH:
        return text
    return LocalizedText(
        text,
        prefers_wide_font=any(
            isinstance(part, LocalizedText) and part.prefers_wide_font for part in parts
        ),
    )


def _item_type_line(
    item: Item,
    localizer: Localizer,
    texts: TextCatalog,
) -> str:
    try:
        type_key = ITEM_TYPE_TEXT_KEYS[item.equip_type]
    except KeyError as error:
        raise ItemMockDataError(
            f"未対応のアイテム種別です: {item.equip_type}"
        ) from error
    type_text = _required_catalog_text(texts, type_key, localizer)
    type_icon = ITEM_TYPE_ICON_TAGS.get(item.equip_type, "")
    if type_icon:
        if type_icon not in TEXT_ICONS:
            raise ItemMockDataError(f"未対応の種別アイコンです: {type_icon}")
        type_text = _composed_text(localizer, type_icon, type_text)
    if item.equip_type not in ITEM_TYPES_WITH_SUBTYPE:
        return type_text

    try:
        subtype_key = ITEM_SUBTYPE_TEXT_KEYS[item.subtype]
    except KeyError as error:
        raise ItemMockDataError(
            f"未対応のアイテム副種別です: {item.subtype}"
        ) from error
    subtype_text = _required_catalog_text(texts, subtype_key, localizer)
    if item.equip_type in (ItemEquipType.RIGHT, ItemEquipType.TWO_HANDS):
        subtype_icon = f"%{item.subtype}%"
        if subtype_icon not in TEXT_ICONS:
            raise ItemMockDataError(f"未対応の武器種別アイコンです: {item.subtype}")
        subtype_text = _composed_text(localizer, subtype_icon, subtype_text)
    separator = "/" if localizer.language is Language.ENGLISH else " / "
    return _composed_text(localizer, type_text, separator, subtype_text)


def _item_requirement_line(
    item: Item,
    localizer: Localizer,
    texts: TextCatalog,
) -> str:
    if not item.requirement:
        return ""
    try:
        key = ITEM_REQUIREMENT_TEXT_KEYS[item.requirement]
    except KeyError as error:
        raise ItemMockDataError(f"未対応の装備条件です: {item.requirement}") from error
    return _required_catalog_text(texts, key, localizer)


def _signed_modifier(value: int) -> str:
    sign = "＋" if value > 0 else "－"
    return f"{sign}{format_number(abs(value))}"


def item_detail_lines(
    item: Item,
    localizer: Localizer,
    texts: TextCatalog,
) -> tuple[str, ...]:
    """Build the currently specified DA2-style item information rows."""

    lines = [
        item.localized_name(localizer),
        _item_type_line(item, localizer, texts),
    ]
    requirement = _item_requirement_line(item, localizer, texts)
    if requirement:
        lines.append(requirement)

    details: list[str] = []
    for attribute, text_key in ITEM_STAT_ROWS:
        value = getattr(item, attribute)
        if value:
            label = _required_catalog_text(texts, text_key, localizer)
            details.append(_composed_text(localizer, label, "：", format_number(value)))

    for attribute, text_key in ITEM_ABILITY_ROWS:
        value = getattr(item, attribute)
        if value:
            label = _required_catalog_text(texts, text_key, localizer)
            details.append(
                _composed_text(localizer, label, " ", _signed_modifier(value))
            )

    if item.healing:
        healing_key = (
            "item.detail.healing.positive"
            if item.healing > 0
            else "item.detail.healing.negative"
        )
        details.append(_required_catalog_text(texts, healing_key, localizer))

    if item.reach == 2:
        details.extend(
            _required_catalog_lines(
                texts,
                "item.detail.reach.2",
                localizer,
            )
        )
    elif item.reach == 3:
        details.append(_required_catalog_text(texts, "item.detail.reach.3", localizer))
    elif item.reach not in (0, 1):
        raise ItemMockDataError(f"未対応の射程です: {item.reach}")

    if details:
        lines.append("")
        lines.extend(details)
    return tuple(lines)


class ItemScreenMock:
    def __init__(
        self,
        *,
        party: tuple[Member, ...] | None = None,
        items: Mapping[str, Item] | None = None,
        settings: Settings | None = None,
        texts: TextCatalog | None = None,
        fonts: FontResources | None = None,
        faces: object | None = None,
    ) -> None:
        """Build the DA2-style item view from menu-owned state."""

        item_catalog = load_mock_items() if items is None else items
        if not isinstance(item_catalog, Mapping) or not all(
            isinstance(key, str) and isinstance(item, Item) and key == item.key
            for key, item in item_catalog.items()
        ):
            raise TypeError("items must map each string key to its matching Item")
        if party is None:
            skills = load_mock_skills()
            party = load_mock_party(dict(item_catalog), skills)
        if not party:
            raise ValueError("party must contain at least one member")

        self.party = party
        self.items = dict(item_catalog)
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
                    item_detail_lines(selected, self.localizer, self.texts)
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
        self.party_panel.draw_faces()
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
