"""DA2-style equipment overlay shared by the game and development harnesses."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from enum import Enum

import pyxel

from ui.status_menu import RESISTANCE_POSITIONS, hit_display
from input import InputState
from item import Item, ItemEquipType
from item_detail import item_detail_lines
from localization import Localizer, format_number
from member import (
    BATTLE_PARTY_MEMBER_COUNT,
    BattleStats,
    EquipmentSlot,
    FormationRow,
    Member,
    ProficiencyAptitude,
    ProficiencyKind,
)
from resistance import ResistanceType
from resources import TRANSPARENT_INDEX, FontResources, play_se
from spell import Spell
from state import Language, Settings
from systems import InventorySystem
from text_catalog import TextCatalog
from ui import (
    DEFAULT_TEXT_COLOR,
    DISABLED_COLOR,
    TEXT_GRID_X,
    TEXT_GRID_Y,
    TEXT_ICONS,
    CursorTarget,
    LocalizedWindowTextFactory,
    WindowCursor,
    WindowFactory,
    WindowText,
    pad,
)
from ui.tagged_text import (
    ICON_BANK,
    ICON_COLKEY,
    ICON_SIZE,
    ICON_Y_OFFSET,
)

FACES_IMAGE_ID = "faces/faces"

MAIN_WINDOW_GRID = (0, 0, 33, 60)
ITEM_LIST_WINDOW_GRID = (33, 0, 31, 24)
ITEM_INFO_WINDOW_GRID = (33, 24, 31, 36)

FACE_X = 12
FACE_Y = 10
FACE_SIZE = 32
HEADER_TEXT_X = 12
HEADER_NAME_Y = 2
HEADER_FORMATION_Y = 5
HEADER_EQUIPMENT_TYPES_Y = 8
HEADER_EQUIPMENT_ICON_GAP = 2
HEADER_EQUIPMENT_COLUMN_PIXEL_WIDTH = ICON_SIZE + HEADER_EQUIPMENT_ICON_GAP
HEADER_EQUIPMENT_ICON_PIXEL_Y = HEADER_EQUIPMENT_TYPES_Y * TEXT_GRID_Y + ICON_Y_OFFSET
PYXEL_TEXT_GLYPH_WIDTH = 3
HEADER_EQUIPMENT_LEVEL_RIGHT_OFFSET = ICON_SIZE - PYXEL_TEXT_GLYPH_WIDTH
HEADER_EQUIPMENT_LEVEL_PIXEL_Y = HEADER_EQUIPMENT_ICON_PIXEL_Y + ICON_SIZE + 1

EQUIPMENT_SLOTS = (
    EquipmentSlot.RIGHT,
    EquipmentSlot.LEFT,
    EquipmentSlot.BODY,
    EquipmentSlot.HEAD,
    EquipmentSlot.ARM,
)
SLOT_Y = {
    EquipmentSlot.RIGHT: 14,
    EquipmentSlot.LEFT: 17,
    EquipmentSlot.BODY: 20,
    EquipmentSlot.HEAD: 23,
    EquipmentSlot.ARM: 26,
}
MAIN_TEXT_X = 4
MAIN_CURSOR_X = 2
AUTO_Y = 29
AUTO_KEY = "auto"
EQUIP_SE_ID = "equip_complete"

STAT_Y = {
    "attack": 35,
    "hit": 38,
    "defense": 41,
    "evasion": 44,
    "spell_resistance": 47,
}
STAT_LABEL_X = 3
STAT_VALUE_X = {
    "attack": 16,
    "hit": 16,
    "defense": 16,
    "evasion": 16,
    "spell_resistance": 16,
}
TOLERANCE_LABEL_Y = 50
TOLERANCE_ICON_Y = 53
TOLERANCE_PREVIEW_Y = 56

ITEM_VISIBLE_COUNT = 7
ITEM_TEXT_X = 3
ITEM_COUNT_X = 26
ITEM_FIRST_Y = 2
ITEM_ROW_HEIGHT = 3
ITEM_CURSOR_X = 1
ITEM_INFO_X = 2
ITEM_INFO_Y = 2
ITEM_INFO_ROW_HEIGHT = 3
ITEM_INFO_MAX_ROWS = 12
REMOVE_KEY = "__remove__"

EQUIPPABLE_ICON_ORDER = (
    ProficiencyKind.SWORD,
    ProficiencyKind.KATANA,
    ProficiencyKind.SPEAR,
    ProficiencyKind.KNIFE,
    ProficiencyKind.AXE,
    ProficiencyKind.HAMMER,
    ProficiencyKind.THROWING,
    ProficiencyKind.ROD,
    ProficiencyKind.WAND,
    ProficiencyKind.SHIELD,
)
EQUIPMENT_TEXT_KEYS = {
    "formation.front": "equip.formation.front",
    "formation.back": "equip.formation.back",
    "formation.reserve": "term.formation.reserve",
    "slot.right": "equip.slot.right",
    "slot.left": "equip.slot.left",
    "slot.body": "equip.slot.body",
    "slot.head": "equip.slot.head",
    "slot.arm": "equip.slot.arm",
    "slot.both": "equip.slot.both",
    "auto": "equip.auto",
    "remove": "equip.remove",
    "stat.attack": "status.attack",
    "stat.hit": "status.hit",
    "stat.defense": "status.defense",
    "stat.evasion": "status.evasion",
    "stat.spell_resistance": "status.spell_resistance",
    "stat.tolerance": "status.tolerance",
}


class EquipmentSelectionPhase(Enum):
    """Selection stage used by the equipment screen."""

    MAIN = "main"
    ITEM = "item"


class EquipmentMenuDataError(RuntimeError):
    """Raised when data required by the equipment menu is unavailable."""


class EquipmentMenuOverlay:
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
        inventory_system: InventorySystem,
        member_index: int = 0,
        on_invalid_action: Callable[[], None] | None = None,
    ) -> None:
        """Build the equipment view, reusing menu-owned runtime state."""

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
        if (
            isinstance(member_index, bool)
            or not isinstance(member_index, int)
            or not 0 <= member_index < len(party)
        ):
            raise ValueError("member_index must identify a party member")
        if not isinstance(inventory_system, InventorySystem):
            raise TypeError("inventory_system must be an InventorySystem")
        if on_invalid_action is not None and not callable(on_invalid_action):
            raise TypeError("on_invalid_action must be callable")

        self.party = party
        self.items = dict(item_catalog)
        self.spells = dict(spell_catalog)
        self.inventory_system = inventory_system
        self.settings = settings
        self.texts = texts
        self.fonts = fonts
        self.faces = faces
        self.member_index = member_index
        self.on_invalid_action = on_invalid_action
        self.phase = EquipmentSelectionPhase.MAIN
        self.selected_main_key: EquipmentSlot | str = EquipmentSlot.RIGHT
        self.selected_item_index = 0
        self.scroll_offset = 0
        self._build_windows()

    @property
    def member(self) -> Member:
        return self.party[self.member_index]

    @property
    def selected_slot(self) -> EquipmentSlot | None:
        key = self.selected_main_key
        return key if isinstance(key, EquipmentSlot) else None

    @property
    def candidates(self) -> tuple[Item | None, ...]:
        slot = self.selected_slot
        if slot is None:
            return ()
        values: list[Item | None] = []
        if self.inventory_system.can_equip(self.member, slot, None):
            values.append(None)
        items = [
            item
            for item in self.inventory_system.items
            if self._is_item_for_slot(item, slot)
        ]
        items.sort(
            key=lambda item: not self.inventory_system.can_equip(
                self.member,
                slot,
                item,
            )
        )
        values.extend(items)
        return tuple(values)

    def _is_item_for_slot(self, item: Item, slot: EquipmentSlot) -> bool:
        if slot is EquipmentSlot.RIGHT:
            return item.equip_type in (
                ItemEquipType.RIGHT,
                ItemEquipType.TWO_HANDS,
            )
        if slot is EquipmentSlot.LEFT:
            return item.equip_type is ItemEquipType.LEFT or (
                item.equip_type is ItemEquipType.RIGHT
                and self.member.has_skill("Dual-Wield")
            )
        return item.equip_type.value == slot.value

    def _candidate_is_equippable(self, index: int) -> bool:
        candidates = self.candidates
        slot = self.selected_slot
        return (
            slot is not None
            and 0 <= index < len(candidates)
            and self.inventory_system.can_equip(
                self.member,
                slot,
                candidates[index],
            )
        )

    @property
    def equippable_candidate_indexes(self) -> tuple[int, ...]:
        return tuple(
            index
            for index in range(len(self.candidates))
            if self._candidate_is_equippable(index)
        )

    @property
    def selected_candidate(self) -> Item | None:
        candidates = self.candidates
        if not candidates or not 0 <= self.selected_item_index < len(candidates):
            return None
        return candidates[self.selected_item_index]

    def _localized_labels(self) -> dict[str, str]:
        labels: dict[str, str] = {}
        for display_key, text_key in EQUIPMENT_TEXT_KEYS.items():
            text = self.texts.text(text_key, self.localizer)
            if not text:
                raise EquipmentMenuDataError(
                    "装備用テキストが見つかりません: " f"{text_key}"
                )
            labels[display_key] = text
        return labels

    def _build_windows(self) -> None:
        self.localizer = Localizer(self.settings.language)
        self.localized_texts = LocalizedWindowTextFactory.from_language(
            self.fonts,
            self.settings.language,
        )
        self.labels = self._localized_labels()
        self._window_factory = WindowFactory(self.fonts.font_for(Language.JAPANESE))
        self.main_window = self._window_factory.create(
            *MAIN_WINDOW_GRID,
            self._main_texts(),
            horizontal_navigation=len(self.party) > 1,
            active=self.phase is EquipmentSelectionPhase.MAIN,
        )
        self.main_cursor = WindowCursor(
            self.main_window,
            tuple(
                CursorTarget(MAIN_CURSOR_X, SLOT_Y[slot], key=slot)
                for slot in EQUIPMENT_SLOTS
            )
            + (CursorTarget(MAIN_CURSOR_X, AUTO_Y, key=AUTO_KEY),),
            active=self.phase is EquipmentSelectionPhase.MAIN,
        )
        self._select_main_key(self.selected_main_key)
        self._build_item_windows()

    def _main_texts(self) -> tuple[WindowText, ...]:
        stats, resistances = self._preview_values()
        current_stats = self.member.battle_stats
        current_resistances = self.member.resistances
        identity = self.member.definition.localized_name(self.localizer)
        if (
            len(self.party) > BATTLE_PARTY_MEMBER_COUNT
            and self.member_index == len(self.party) - 1
        ):
            formation_key = "formation.reserve"
        elif self.member.formation_row is FormationRow.FRONT:
            formation_key = "formation.front"
        else:
            formation_key = "formation.back"
        formation = self.labels[formation_key]
        texts: list[WindowText] = [
            self.localized_texts.create(
                identity,
                HEADER_TEXT_X,
                HEADER_NAME_Y,
            ),
            self.localized_texts.create(
                formation,
                HEADER_TEXT_X,
                HEADER_FORMATION_Y,
            ),
        ]
        for slot in EQUIPMENT_SLOTS:
            texts.append(self._equipment_text(slot))
        texts.append(
            self.localized_texts.create(
                self.labels["auto"],
                MAIN_TEXT_X,
                AUTO_Y,
            )
        )

        previewing = (
            self.phase is EquipmentSelectionPhase.ITEM
            and self._candidate_is_equippable(self.selected_item_index)
        )
        current_values = self._stat_displays(
            current_stats,
            include_hit_bonus=not previewing,
        )
        preview_values = self._stat_displays(
            stats,
            include_hit_bonus=not previewing,
        )
        for key, y in STAT_Y.items():
            texts.append(
                self.localized_texts.create(
                    self.labels[f"stat.{key}"],
                    STAT_LABEL_X,
                    y,
                )
            )
            value = current_values[key]
            if preview_values[key] != value:
                value += "→" + preview_values[key]
            texts.append(WindowText(value, STAT_VALUE_X[key], y))

        texts.append(
            self.localized_texts.create(
                self.labels["stat.tolerance"],
                STAT_LABEL_X,
                TOLERANCE_LABEL_Y,
            )
        )
        for index, resistance in enumerate(
            resistance for resistance, _x, _y in RESISTANCE_POSITIONS
        ):
            enabled = resistance in current_resistances
            suffix = "" if enabled else "_DISABLED"
            texts.append(
                WindowText(
                    f"%{resistance.value}{suffix}%",
                    STAT_LABEL_X + index * 2 + 2,
                    TOLERANCE_ICON_Y,
                )
            )
        if previewing:
            texts.append(WindowText("→", STAT_LABEL_X, TOLERANCE_PREVIEW_Y))
            for index, resistance in enumerate(
                resistance for resistance, _x, _y in RESISTANCE_POSITIONS
            ):
                current_enabled = resistance in current_resistances
                preview_enabled = resistance in resistances
                if current_enabled == preview_enabled:
                    continue
                suffix = "" if preview_enabled else "_DISABLED"
                texts.append(
                    WindowText(
                        f"%{resistance.value}{suffix}%",
                        STAT_LABEL_X + index * 2 + 2,
                        TOLERANCE_PREVIEW_Y,
                    )
                )
        return tuple(texts)

    def _equipment_text(self, slot: EquipmentSlot) -> WindowText:
        item = self.member.equipment.item_at(slot)
        if slot is EquipmentSlot.LEFT and self.member.equipment.uses_both_hands:
            text = ""
        else:
            label_key = f"slot.{slot.value.lower()}"
            if slot is EquipmentSlot.RIGHT and self.member.equipment.uses_both_hands:
                label_key = "slot.both"
            name = ""
            if item is not None:
                icon = f"%{item.subtype}%"
                if icon not in TEXT_ICONS:
                    icon = ""
                name = icon + item.localized_name(self.localizer)
            color_tag = "%COL_POSITIVE%" if self.member.is_equipment_fixed(slot) else ""
            text = self.labels[label_key] + color_tag + name
        return self.localized_texts.create(
            text,
            MAIN_TEXT_X,
            SLOT_Y[slot],
        )

    def _equippable_proficiency_kinds(self) -> tuple[ProficiencyKind, ...]:
        return tuple(
            kind
            for kind in EQUIPPABLE_ICON_ORDER
            if self.member.proficiency(kind).aptitude
            is not ProficiencyAptitude.DISABLED
        )

    @staticmethod
    def _stat_displays(
        stats: BattleStats,
        *,
        include_hit_bonus: bool,
    ) -> dict[str, str]:
        return {
            "attack": pad(
                stats.attack_right
                + (stats.attack_left if stats.attack_left is not None else 0),
                3,
            ),
            "hit": (hit_display(stats) if include_hit_bonus else pad(stats.hit, 3)),
            "defense": pad(stats.defense, 3),
            "evasion": pad(stats.evasion, 3),
            "spell_resistance": pad(stats.spell_resistance, 3),
        }

    def _preview_values(self) -> tuple[BattleStats, frozenset[ResistanceType]]:
        if self.phase is not EquipmentSelectionPhase.ITEM:
            return self.member.battle_stats, self.member.resistances
        if not self._candidate_is_equippable(self.selected_item_index):
            return self.member.battle_stats, self.member.resistances
        slot = self.selected_slot
        if slot is None:
            return self.member.battle_stats, self.member.resistances
        preview = self.inventory_system.preview_equipment(
            self.member,
            slot,
            self.selected_candidate,
        )
        if preview is None:
            return self.member.battle_stats, self.member.resistances
        current = self.member.equipment
        self.member.equipment = preview
        try:
            return self.member.battle_stats, self.member.resistances
        finally:
            self.member.equipment = current

    def _build_item_windows(self) -> None:
        candidates = self.candidates
        visible = candidates[
            self.scroll_offset : self.scroll_offset + ITEM_VISIBLE_COUNT
        ]
        list_texts: list[WindowText] = []
        targets: list[CursorTarget] = []
        for row, item in enumerate(visible):
            candidate_index = self.scroll_offset + row
            equippable = self._candidate_is_equippable(candidate_index)
            y = ITEM_FIRST_Y + row * ITEM_ROW_HEIGHT
            if item is None:
                name = self.labels["remove"]
                key = REMOVE_KEY
            else:
                icon = f"%{item.subtype}%"
                if not item.is_weapon or icon not in TEXT_ICONS:
                    icon = ""
                name = icon + str(item.localized_name(self.localizer))
                key = item.key
            color = DEFAULT_TEXT_COLOR if equippable else DISABLED_COLOR
            list_texts.append(
                self.localized_texts.create(
                    name,
                    ITEM_TEXT_X,
                    y,
                    color=color,
                )
            )
            if item is not None:
                list_texts.append(
                    self.localized_texts.create(
                        format_number(self.inventory_system.quantity(item)),
                        ITEM_COUNT_X,
                        y,
                        color=color,
                    )
                )
            targets.append(
                CursorTarget(
                    ITEM_CURSOR_X,
                    y,
                    key=key,
                )
            )

        scrollable = len(candidates) > ITEM_VISIBLE_COUNT
        self.item_list_window = self._window_factory.create(
            *ITEM_LIST_WINDOW_GRID,
            tuple(list_texts),
            horizontal_navigation=scrollable,
            vertical_navigation=scrollable,
            active=self.phase is EquipmentSelectionPhase.ITEM,
        )
        self.item_cursor = WindowCursor(
            self.item_list_window,
            tuple(targets),
            active=self.phase is EquipmentSelectionPhase.ITEM,
        )
        selected = self.selected_candidate
        selected_key = REMOVE_KEY if selected is None else selected.key
        if self.item_cursor.active and candidates:
            for _target in self.item_cursor.targets:
                if self.item_cursor.selected_key == selected_key:
                    break
                self.item_cursor.move_down()

        detail_item = selected
        if (
            self.phase is EquipmentSelectionPhase.MAIN
            and self.selected_slot is not None
        ):
            detail_item = self.member.equipment.item_at(self.selected_slot)
        detail_texts: tuple[WindowText, ...] = ()
        if detail_item is not None:
            lines = item_detail_lines(
                detail_item,
                self.spells,
                self.localizer,
                self.texts,
            )
            if len(lines) > ITEM_INFO_MAX_ROWS:
                raise EquipmentMenuDataError(
                    f"装備詳細が{ITEM_INFO_MAX_ROWS}行を超えています: "
                    f"{detail_item.key}"
                )
            detail_texts = tuple(
                self.localized_texts.create(
                    line,
                    ITEM_INFO_X,
                    ITEM_INFO_Y + row * ITEM_INFO_ROW_HEIGHT,
                )
                for row, line in enumerate(lines)
                if line
            )
        self.item_info_window = self._window_factory.create(
            *ITEM_INFO_WINDOW_GRID,
            detail_texts,
        )
        self.windows = (
            self.main_window,
            self.item_list_window,
            self.item_info_window,
        )

    def _select_main_key(self, key: EquipmentSlot | str) -> None:
        was_active = self.main_cursor.active
        self.main_cursor.active = True
        try:
            for _target in self.main_cursor.targets:
                if self.main_cursor.selected_key == key:
                    self.selected_main_key = key
                    return
                self.main_cursor.move_down()
        finally:
            self.main_cursor.active = was_active
        raise EquipmentMenuDataError(f"装備カーソル項目がありません: {key!r}")

    def _rebuild(self) -> None:
        self._build_windows()

    def _switch_member(self, distance: int) -> None:
        if distance not in (-1, 1):
            raise ValueError("member switch distance must be -1 or 1")
        self.member_index = (self.member_index + distance) % len(self.party)
        self.phase = EquipmentSelectionPhase.MAIN
        self.selected_item_index = 0
        self.scroll_offset = 0
        self._rebuild()

    def _move_main(self, distance: int) -> None:
        moved = (
            self.main_cursor.move_up() if distance < 0 else self.main_cursor.move_down()
        )
        if moved:
            self.selected_main_key = self.main_cursor.selected_key
            self.selected_item_index = 0
            self.scroll_offset = 0
            self._rebuild()

    def _advance_main(self) -> None:
        keys: tuple[EquipmentSlot | str, ...] = (*EQUIPMENT_SLOTS, AUTO_KEY)
        index = keys.index(self.selected_main_key)
        self.selected_main_key = keys[(index + 1) % len(keys)]

    def _enter_item_selection(self) -> None:
        slot = self.selected_slot
        if slot is not None and self.member.is_equipment_fixed(slot):
            if self.on_invalid_action is not None:
                self.on_invalid_action()
            return
        if not self.candidates:
            self._advance_main()
            self._rebuild()
            return
        self.phase = EquipmentSelectionPhase.ITEM
        self.selected_item_index = 0
        self.scroll_offset = 0
        self._rebuild()

    def _return_to_main(self) -> None:
        self.phase = EquipmentSelectionPhase.MAIN
        self.selected_item_index = 0
        self.scroll_offset = 0
        self._rebuild()

    def _move_item(self, distance: int) -> None:
        candidates = self.candidates
        if not candidates:
            return
        previous = self.selected_item_index
        self.selected_item_index = (previous + distance) % len(candidates)
        if self.selected_item_index == 0 and previous == len(candidates) - 1:
            self.scroll_offset = 0
        elif self.selected_item_index == len(candidates) - 1 and previous == 0:
            self.scroll_offset = max(0, len(candidates) - ITEM_VISIBLE_COUNT)
        elif self.selected_item_index < self.scroll_offset:
            self.scroll_offset = self.selected_item_index
        elif self.selected_item_index >= self.scroll_offset + ITEM_VISIBLE_COUNT:
            self.scroll_offset = self.selected_item_index - ITEM_VISIBLE_COUNT + 1
        self._rebuild()

    def _move_page(self, distance: int) -> None:
        candidates = self.candidates
        if not candidates:
            return
        row = self.selected_item_index - self.scroll_offset
        next_offset = self.scroll_offset + distance * ITEM_VISIBLE_COUNT
        if next_offset >= len(candidates):
            self.scroll_offset = 0
            self.selected_item_index = 0
        elif next_offset < 0:
            self.scroll_offset = (
                0
                if self.scroll_offset > 0
                else (len(candidates) - 1) // ITEM_VISIBLE_COUNT * ITEM_VISIBLE_COUNT
            )
            self.selected_item_index = min(
                self.scroll_offset + row,
                len(candidates) - 1,
            )
        else:
            self.scroll_offset = next_offset
            self.selected_item_index = min(
                self.scroll_offset + row,
                len(candidates) - 1,
            )
        self._rebuild()

    def update(self, input_state: InputState) -> bool:
        """Update equipment selection and report whether the menu should return."""

        self.item_list_window.set_vertical_navigation_pressed()
        if self.phase is EquipmentSelectionPhase.MAIN:
            if input_state.cancel.triggered:
                return True
            if input_state.previous_page.triggered:
                self._switch_member(-1)
                return False
            if input_state.next_page.triggered:
                self._switch_member(1)
                return False
            if input_state.navigation is not None:
                if input_state.navigation.dx:
                    self._switch_member(-1 if input_state.navigation.dx < 0 else 1)
                elif input_state.navigation.dy:
                    self._move_main(-1 if input_state.navigation.dy < 0 else 1)
                return False
            if input_state.confirm.triggered:
                if self.selected_main_key == AUTO_KEY:
                    self.inventory_system.auto_equip(self.member)
                    self._rebuild()
                    play_se(EQUIP_SE_ID)
                else:
                    self._enter_item_selection()
            return False

        if input_state.cancel.triggered:
            self._return_to_main()
            return False
        if input_state.previous_page.triggered:
            self._move_page(-1)
            return False
        if input_state.next_page.triggered:
            self._move_page(1)
            return False
        if input_state.navigation is not None:
            if input_state.navigation.dy:
                distance = -1 if input_state.navigation.dy < 0 else 1
                self._move_item(distance)
                self.item_list_window.set_vertical_navigation_pressed(distance)
            elif input_state.navigation.dx:
                self._move_page(-1 if input_state.navigation.dx < 0 else 1)
            return False
        if input_state.confirm.triggered:
            if not self._candidate_is_equippable(self.selected_item_index):
                if self.on_invalid_action is not None:
                    self.on_invalid_action()
                return False
            slot = self.selected_slot
            if slot is not None:
                if self.inventory_system.equip(
                    self.member,
                    slot,
                    self.selected_candidate,
                ):
                    play_se(EQUIP_SE_ID)
            self.phase = EquipmentSelectionPhase.MAIN
            self.selected_item_index = 0
            self.scroll_offset = 0
            self._rebuild()
        return False

    def draw(self) -> None:
        for window in self.windows:
            window.draw()
        self._draw_equipment_icons()
        self._draw_equipment_levels()
        face_position = self.member.face_position
        pyxel.blt(
            FACE_X,
            FACE_Y,
            self.faces,
            face_position.x,
            face_position.y,
            FACE_SIZE,
            FACE_SIZE,
            TRANSPARENT_INDEX,
        )
        self.main_cursor.draw()
        if self.phase is EquipmentSelectionPhase.ITEM:
            self.item_cursor.draw()

    def _draw_equipment_icons(self) -> None:
        origin_x = self.main_window.pixel_x + HEADER_TEXT_X * TEXT_GRID_X
        y = self.main_window.pixel_y + HEADER_EQUIPMENT_ICON_PIXEL_Y
        for index, kind in enumerate(self._equippable_proficiency_kinds()):
            icon = TEXT_ICONS[f"%{kind.name}%"]
            pyxel.blt(
                origin_x + index * HEADER_EQUIPMENT_COLUMN_PIXEL_WIDTH,
                y,
                ICON_BANK,
                icon.u,
                icon.v,
                ICON_SIZE,
                ICON_SIZE,
                ICON_COLKEY,
            )

    def _draw_equipment_levels(self) -> None:
        icon_origin_x = self.main_window.pixel_x + HEADER_TEXT_X * TEXT_GRID_X
        y = self.main_window.pixel_y + HEADER_EQUIPMENT_LEVEL_PIXEL_Y
        for index, kind in enumerate(self._equippable_proficiency_kinds()):
            level_text = (
                "-"
                if kind is ProficiencyKind.SHIELD
                else str(self.member.proficiency(kind).level)
            )
            pyxel.text(
                icon_origin_x
                + index * HEADER_EQUIPMENT_COLUMN_PIXEL_WIDTH
                + HEADER_EQUIPMENT_LEVEL_RIGHT_OFFSET,
                y,
                level_text,
                DEFAULT_TEXT_COLOR,
            )


__all__ = [
    "EquipmentMenuDataError",
    "EquipmentMenuOverlay",
    "EquipmentSelectionPhase",
]
