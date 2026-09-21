"""Item-menu overlay shared by the game and development harnesses."""

from __future__ import annotations

import random
from collections.abc import Callable, Mapping
from enum import Enum, StrEnum

from battle_magic import DA2_DEFAULT_ITEM_SPELL_ABILITY, resolve_healing
from input import InputState
from item import Item, ItemEquipType
from item_detail import item_detail_lines
from localization import Localizer, format_number
from member import Member
from rendering import PaletteShifter
from resources import FontResources, play_se
from spell import Spell, SpellAction
from state import Language, Settings
from systems import InventorySystem
from text_catalog import TextCatalog
from ui import (
    CursorTarget,
    LocalizedWindowTextFactory,
    WindowCursor,
    WindowFactory,
    WindowText,
    pad,
)
from ui.party_status import PartyStatusPanel
from ui.text_layout import right_aligned_grid_x

FACES_IMAGE_ID = "faces/faces"
CATEGORY_WINDOW_GRID = (6, 0, 52, 5)
ITEM_LIST_WINDOW_GRID = (0, 5, 32, 39)
ITEM_INFO_WINDOW_GRID = (31, 5, 33, 39)

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
ITEM_COUNT_X = 27
ITEM_FIRST_Y = 2
ITEM_ROW_HEIGHT = 3
ITEM_CURSOR_X = ITEM_TEXT_X - 2
ITEM_INFO_X = 2
ITEM_INFO_Y = 2
ITEM_INFO_ROW_HEIGHT = 3
ITEM_INFO_MAX_ROWS = 12
ITEM_SUMMARY_VALUE_X = 13
ITEM_SUMMARY_COUNT_LABEL_Y = 2
ITEM_SUMMARY_COUNT_VALUE_Y = 5
ITEM_SUMMARY_RECORDED_LABEL_Y = 8
ITEM_SUMMARY_RECORDED_VALUE_Y = 11
DROP_CONFIRM_WINDOW_GRID = (0, 0, 64, 10)
DROP_CONFIRM_CHOICE_WINDOW_GRID = (52, 0, 12, 10)
DROP_CONFIRM_TEXT_X = 4
DROP_CONFIRM_TEXT_Y = 2
DROP_CONFIRM_CHOICE_TEXT_X = 4
DROP_CONFIRM_CURSOR_X = 2
DROP_CONFIRM_YES_Y = 2
DROP_CONFIRM_NO_Y = 5
HEALING_SE_ID = "spell_healing1"
FIELD_USE_ITEM_KEYS = frozenset(("POTION", "DIVINE TEAR", "DARK CHRISM"))


def _validate_item_info_lines(lines: tuple[str, ...]) -> tuple[str, ...]:
    """Keep authored line boundaries and reject details that exceed the window."""

    if len(lines) > ITEM_INFO_MAX_ROWS:
        raise ItemMenuDataError(f"アイテム詳細が{ITEM_INFO_MAX_ROWS}行を超えています")
    return lines


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
    TARGET = "target"
    CONFIRMATION = "confirmation"


class ItemMenuDataError(RuntimeError):
    """Raised when data required by the item menu is unavailable."""


class ItemMenuOverlay:
    def __init__(
        self,
        *,
        party: tuple[Member, ...],
        items: Mapping[str, Item],
        spells: Mapping[str, Spell],
        settings: Settings,
        texts: TextCatalog,
        fonts: FontResources,
        faces: object,
        palette_shifter: PaletteShifter | None = None,
        inventory_system: InventorySystem,
        on_field_fade: Callable[[], bool] | None = None,
        on_invalid_action: Callable[[], None] | None = None,
    ) -> None:
        """Build the DA2-style item view from menu-owned state."""

        item_catalog = items
        if not isinstance(item_catalog, Mapping) or not all(
            isinstance(key, str) and isinstance(item, Item) and key == item.key
            for key, item in item_catalog.items()
        ):
            raise TypeError("items must map each string key to its matching Item")
        spell_catalog = spells
        if not isinstance(spell_catalog, Mapping) or not all(
            isinstance(key, str) and isinstance(spell, Spell) and key == spell.key
            for key, spell in spell_catalog.items()
        ):
            raise TypeError("spells must map each string key to its matching Spell")
        if not party:
            raise ValueError("party must contain at least one member")
        if not isinstance(inventory_system, InventorySystem):
            raise TypeError("inventory_system must be an InventorySystem")
        if on_invalid_action is not None and not callable(on_invalid_action):
            raise TypeError("on_invalid_action must be callable")
        if on_field_fade is not None and not callable(on_field_fade):
            raise TypeError("on_field_fade must be callable")

        self.party = party
        self.items = dict(item_catalog)
        self.spells = dict(spell_catalog)
        self.inventory_system = inventory_system
        self.important_items: tuple[Item, ...] = ()
        self.settings = settings
        self.texts = texts
        self.fonts = fonts
        self.faces = faces
        self.palette_shifter = palette_shifter
        self.on_field_fade = on_field_fade
        self.on_invalid_action = on_invalid_action
        self.phase = ItemSelectionPhase.CATEGORY
        self.selected_item_index = 0
        self.scroll_offset = 0
        self.pending_drop_item: Item | None = None
        self.drop_confirmation_window = None
        self.drop_confirmation_choice_window = None
        self.drop_confirmation_cursor: WindowCursor | None = None
        self._build_windows()

    @property
    def inventory(self) -> tuple[Item, ...]:
        return self.inventory_system.items

    @property
    def item_counts(self) -> Mapping[str, int]:
        return self.inventory_system.quantities

    @property
    def category(self) -> ItemCategory:
        key = self.category_cursor.selected_key
        if not isinstance(key, ItemCategory):
            raise ItemMenuDataError("item category cursor has no selection")
        return key

    @property
    def category_items(self) -> tuple[Item, ...]:
        if self.category is ItemCategory.IMPORTANT:
            return self.important_items
        if self.category is ItemCategory.INDEX:
            return self.inventory_system.recorded_items
        return self.inventory

    @property
    def selected_item(self) -> Item | None:
        items = self.category_items
        if not items:
            return None
        return items[self.selected_item_index]

    @property
    def dimmed_member_indexes(self) -> frozenset[int]:
        """Return party positions unable to receive the effect or equip the item."""

        if self.phase is ItemSelectionPhase.TARGET:
            spell = self._field_use_spell(self.selected_item)
            usable = self._usable_target_indexes(spell) if spell is not None else ()
            return frozenset(range(len(self.party_panel.party))).difference(usable)
        if self.phase is not ItemSelectionPhase.ITEM:
            return frozenset()
        item = self.selected_item
        if item is None or not item.is_equipment:
            return frozenset()
        return frozenset(
            index
            for index, member in enumerate(self.party_panel.party)
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
                raise ItemMenuDataError(f"アイテム用テキストが見つかりません: {key}")
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
        self._window_factory = windows
        self._build_party_panel()
        self._build_item_windows()

    def _build_party_panel(self, *, selected_target_index: int | None = None) -> None:
        self.party_panel = PartyStatusPanel(
            party=self.party,
            localizer=self.localizer,
            texts=self.texts,
            text_factory=self.localized_texts,
            window_factory=self._window_factory,
            faces=self.faces,
            palette_shifter=self.palette_shifter,
            cursor_active=self.phase is ItemSelectionPhase.TARGET,
        )
        self.party_window = self.party_panel.window
        self.member_cursor = self.party_panel.cursor
        if selected_target_index is not None:
            self.member_cursor.select_key(selected_target_index)
        if hasattr(self, "item_info_window"):
            self._refresh_windows()

    def _refresh_windows(self) -> None:
        self.windows = (
            self.category_window,
            self.item_info_window,
            self.item_list_window,
            self.party_window,
        )

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
                    str(item.localized_name(self.localizer)),
                    ITEM_TEXT_X,
                    y,
                )
            )
            if show_count:
                count_text = format_number(self.item_counts[item.key])
                list_texts.append(
                    self.localized_texts.create(
                        count_text,
                        right_aligned_grid_x(
                            count_text,
                            reference_text=format_number(0),
                            reference_x=ITEM_COUNT_X,
                            font=self.localized_texts.font,
                        ),
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
            active=self.phase is ItemSelectionPhase.ITEM,
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
        if (
            self.phase is ItemSelectionPhase.CATEGORY
            and self.category is not ItemCategory.IMPORTANT
        ):
            info_texts = self._item_summary_texts()
        elif selected is not None:
            info_texts = tuple(
                self.localized_texts.create(
                    text,
                    ITEM_INFO_X,
                    ITEM_INFO_Y + row * ITEM_INFO_ROW_HEIGHT,
                )
                for row, text in enumerate(
                    _validate_item_info_lines(
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
        self._refresh_windows()

    def _item_summary_texts(self) -> tuple[WindowText, ...]:
        count_label = self.texts.text("item.inventory.count", self.localizer)
        recorded_label = self.texts.text("item.recorded.count", self.localizer)
        if not count_label or not recorded_label:
            raise ItemMenuDataError("アイテム集計用テキストが見つかりません")

        placements: list[WindowText] = []
        owned_count = sum(self.item_counts.values())
        if owned_count:
            placements.extend(
                (
                    self.localized_texts.create(
                        count_label,
                        ITEM_INFO_X,
                        ITEM_SUMMARY_COUNT_LABEL_Y,
                    ),
                    self.localized_texts.create(
                        pad(owned_count, 3),
                        ITEM_SUMMARY_VALUE_X,
                        ITEM_SUMMARY_COUNT_VALUE_Y,
                    ),
                )
            )

        recorded_count = self.inventory_system.recorded_count
        catalog_count = self.inventory_system.catalog_count
        recorded_total = (
            pad(catalog_count, 3) if recorded_count == catalog_count else "　？？"
        )
        placements.extend(
            (
                self.localized_texts.create(
                    recorded_label,
                    ITEM_INFO_X,
                    ITEM_SUMMARY_RECORDED_LABEL_Y,
                ),
                self.localized_texts.create(
                    f"{pad(recorded_count, 3)}／{recorded_total}",
                    ITEM_SUMMARY_VALUE_X,
                    ITEM_SUMMARY_RECORDED_VALUE_Y,
                ),
            )
        )
        return tuple(placements)

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
        self._build_item_windows()

    def _return_to_category_selection(self) -> None:
        self.phase = ItemSelectionPhase.CATEGORY
        self.category_cursor.active = True
        self._build_item_windows()

    def _field_use_spell(self, item: Item | None) -> Spell | None:
        """Resolve the currently supported camp-use item effect."""

        if (
            item is None
            or item.key not in FIELD_USE_ITEM_KEYS
            or item.equip_type is not ItemEquipType.ITEM
            or not item.use_spell_key
        ):
            return None
        spell = self.spells.get(item.use_spell_key)
        if (
            spell is None
            or not spell.on_camp
            or spell.to_enemy
            or spell.action
            not in (SpellAction.HEAL, SpellAction.REVIVE, SpellAction.FADE)
            or (
                spell.action is SpellAction.FADE
                and self.on_field_fade is None
            )
        ):
            return None
        return spell

    @staticmethod
    def _has_curable_ailment(member: Member) -> bool:
        return bool(
            member.poisoned
            or member.paralyzed
            or member.sleeping
            or member.confused
        )

    def _can_use_recovery_on_target(self, spell: Spell, target: Member) -> bool:
        if spell.action is SpellAction.REVIVE:
            return target.is_dead
        if target.hp <= 0:
            return False
        if target.hp < target.max_hp:
            return True
        return spell.intensity == 0 and self._has_curable_ailment(target)

    def _usable_target_indexes(self, spell: Spell) -> tuple[int, ...]:
        return tuple(
            index
            for index, target in enumerate(self.party_panel.party)
            if self._can_use_recovery_on_target(spell, target)
        )

    def _notify_invalid_action(self) -> None:
        if self.on_invalid_action is not None:
            self.on_invalid_action()

    def _enter_target_selection(self) -> None:
        spell = self._field_use_spell(self.selected_item)
        if spell is None:
            self._notify_invalid_action()
            return
        if spell.action is SpellAction.FADE:
            self._use_selected_fade_item()
            return
        target_indexes = self._usable_target_indexes(spell)
        if not target_indexes:
            self._notify_invalid_action()
            return
        self.phase = ItemSelectionPhase.TARGET
        self.item_cursor.active = False
        self.item_list_window.active = False
        self.member_cursor.active = True
        self.member_cursor.select_key(target_indexes[0])

    def _return_to_item_selection(self) -> None:
        self.phase = ItemSelectionPhase.ITEM
        self.item_cursor.active = True
        self.item_list_window.active = True
        self.member_cursor.active = False

    def _refresh_after_recovery_item(
        self,
        item: Item,
        spell: Spell,
        preferred_target_index: int,
    ) -> None:
        items = self.category_items
        if item in items:
            self.selected_item_index = items.index(item)
        elif items:
            self.selected_item_index = min(self.selected_item_index, len(items) - 1)
        else:
            self.selected_item_index = 0
        self.scroll_offset = min(
            self.scroll_offset,
            max(0, len(items) - ITEM_VISIBLE_COUNT),
        )

        can_reuse = item in items and bool(self._usable_target_indexes(spell))
        self.phase = (
            ItemSelectionPhase.TARGET
            if can_reuse and len(self.party_panel.party) > 1
            else ItemSelectionPhase.ITEM
        )
        self._build_item_windows()
        next_target_index = None
        if self.phase is ItemSelectionPhase.TARGET:
            usable = frozenset(self._usable_target_indexes(spell))
            member_count = len(self.party_panel.party)
            next_target_index = next(
                (
                    (preferred_target_index + distance) % member_count
                    for distance in range(member_count)
                    if (preferred_target_index + distance) % member_count in usable
                ),
                None,
            )
        self._build_party_panel(selected_target_index=next_target_index)

    def _use_selected_recovery_item(self) -> bool:
        item = self.selected_item
        spell = self._field_use_spell(item)
        selected_target = self.member_cursor.selected_key
        if (
            item is None
            or spell is None
            or not isinstance(selected_target, int)
            or self.inventory_system.quantity(item) <= 0
        ):
            self._notify_invalid_action()
            return False

        usable = self._usable_target_indexes(spell)
        target_indexes = usable if spell.to_all else (selected_target,)
        if not target_indexes or any(index not in usable for index in target_indexes):
            self._notify_invalid_action()
            return False

        for index in target_indexes:
            target = self.party_panel.party[index]
            if spell.action is SpellAction.REVIVE:
                target.revive(spell.intensity)
            else:
                result = resolve_healing(
                    intensity=spell.intensity,
                    ability=DA2_DEFAULT_ITEM_SPELL_ABILITY,
                    current_hp=target.hp,
                    max_hp=target.max_hp,
                    random_factor=random.random(),
                )
                target.apply_healing(
                    result.amount,
                    cure_ailments=result.cures_ailments,
                )
        if item.breaks_on_use and not self.inventory_system.remove(item):
            self._notify_invalid_action()
            return False
        play_se(HEALING_SE_ID)
        self._refresh_after_recovery_item(item, spell, selected_target)
        return True

    def _use_selected_fade_item(self) -> bool:
        """Consume a camp-use FADE item after activating the floor effect."""

        item = self.selected_item
        spell = self._field_use_spell(item)
        if (
            item is None
            or spell is None
            or spell.action is not SpellAction.FADE
            or self.inventory_system.quantity(item) <= 0
            or self.on_field_fade is None
            or not self.on_field_fade()
        ):
            self._notify_invalid_action()
            return False
        if item.breaks_on_use and not self.inventory_system.remove(item):
            self._notify_invalid_action()
            return False
        play_se(HEALING_SE_ID)
        items = self.category_items
        self.selected_item_index = min(
            self.selected_item_index,
            max(0, len(items) - 1),
        )
        self.scroll_offset = min(
            self.scroll_offset,
            max(0, len(items) - ITEM_VISIBLE_COUNT),
        )
        self.phase = ItemSelectionPhase.ITEM
        self._build_item_windows()
        self._build_party_panel()
        return True

    def _start_drop_confirmation(self, item: Item) -> None:
        raw_name = self.localizer.value(item.names, "name")
        if not isinstance(raw_name, str) or not raw_name:
            raise ItemMenuDataError(f"アイテム表示名が見つかりません: {item.key}")
        prompt = self.texts.formatted_text(
            "item.drop.confirm",
            self.localizer,
            {"ITEM": raw_name},
        )
        yes = self.texts.text("settings.yes", self.localizer)
        no = self.texts.text("settings.no", self.localizer)
        if not prompt or not yes or not no:
            raise ItemMenuDataError("アイテム破棄確認用テキストが見つかりません")

        self.phase = ItemSelectionPhase.CONFIRMATION
        self.item_cursor.active = False
        self.item_list_window.active = False
        self.pending_drop_item = item
        self.drop_confirmation_window = self._window_factory.create(
            *DROP_CONFIRM_WINDOW_GRID,
            (
                self.localized_texts.create(
                    prompt,
                    DROP_CONFIRM_TEXT_X,
                    DROP_CONFIRM_TEXT_Y,
                ),
            ),
        )
        self.drop_confirmation_choice_window = self._window_factory.create(
            *DROP_CONFIRM_CHOICE_WINDOW_GRID,
            (
                self.localized_texts.create(
                    yes,
                    DROP_CONFIRM_CHOICE_TEXT_X,
                    DROP_CONFIRM_YES_Y,
                ),
                self.localized_texts.create(
                    no,
                    DROP_CONFIRM_CHOICE_TEXT_X,
                    DROP_CONFIRM_NO_Y,
                ),
            ),
        )
        self.drop_confirmation_cursor = WindowCursor(
            self.drop_confirmation_choice_window,
            (
                CursorTarget(
                    DROP_CONFIRM_CURSOR_X,
                    DROP_CONFIRM_YES_Y,
                    key="yes",
                ),
                CursorTarget(
                    DROP_CONFIRM_CURSOR_X,
                    DROP_CONFIRM_NO_Y,
                    key="no",
                ),
            ),
        )

    def _finish_drop_confirmation(self, *, discard: bool) -> None:
        item = self.pending_drop_item
        if discard and item is not None:
            self.inventory_system.discard(item)

        self.pending_drop_item = None
        self.drop_confirmation_window = None
        self.drop_confirmation_choice_window = None
        self.drop_confirmation_cursor = None
        self.phase = ItemSelectionPhase.ITEM

        items = self.category_items
        if items:
            self.selected_item_index = min(self.selected_item_index, len(items) - 1)
            max_offset = max(0, len(items) - ITEM_VISIBLE_COUNT)
            self.scroll_offset = min(self.scroll_offset, max_offset)
            if self.selected_item_index < self.scroll_offset:
                self.scroll_offset = self.selected_item_index
        else:
            self.selected_item_index = 0
            self.scroll_offset = 0
        self._build_item_windows()

    def _update_drop_confirmation(self, input_state: InputState) -> None:
        if self.drop_confirmation_cursor is None:
            raise ItemMenuDataError("アイテム破棄確認カーソルがありません")
        if input_state.cancel.triggered:
            self._finish_drop_confirmation(discard=False)
            return
        if input_state.confirm.triggered:
            self._finish_drop_confirmation(
                discard=self.drop_confirmation_cursor.selected_key == "yes",
            )
            return
        self.drop_confirmation_cursor.update(input_state.navigation)

    def update(self, input_state: InputState) -> bool:
        """Update selection and report whether the menu should be restored."""

        self.item_list_window.set_vertical_navigation_pressed()

        if self.phase is ItemSelectionPhase.CONFIRMATION:
            self._update_drop_confirmation(input_state)
            return False

        if self.phase is ItemSelectionPhase.TARGET:
            if input_state.cancel.triggered:
                self._return_to_item_selection()
                return False
            self.member_cursor.update(input_state.navigation)
            if input_state.confirm.triggered:
                self._use_selected_recovery_item()
            return False

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
            return False
        if input_state.confirm.triggered:
            item = self.selected_item
            if item is None:
                return False
            if self.category is ItemCategory.USE:
                self._enter_target_selection()
            elif self.category is ItemCategory.DROP:
                if not self.inventory_system.can_discard(item):
                    self._notify_invalid_action()
                    return False
                self._start_drop_confirmation(item)
        return False

    def draw(self) -> None:
        for window in self.windows:
            window.draw()
        self.party_panel.draw_faces(self.dimmed_member_indexes)
        self.category_cursor.draw()
        if self.phase is not ItemSelectionPhase.CATEGORY:
            self.item_cursor.draw()
        if self.phase is ItemSelectionPhase.TARGET:
            self.member_cursor.draw()
        if self.drop_confirmation_window is not None:
            self.drop_confirmation_window.draw()
        if self.drop_confirmation_choice_window is not None:
            self.drop_confirmation_choice_window.draw()
        if self.drop_confirmation_cursor is not None:
            self.drop_confirmation_cursor.draw()


__all__ = [
    "HEALING_SE_ID",
    "ItemCategory",
    "ItemMenuDataError",
    "ItemMenuOverlay",
    "ItemSelectionPhase",
    "item_detail_lines",
]
