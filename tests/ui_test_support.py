"""Fixture builders for production menu-overlay regression tests."""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping

from tools._bootstrap import APP_ROOT

from game_data import create_party, load_items, load_shops, load_skills, load_spells
from input import InputDevice
from item import Item
from member import Member
from rendering import PaletteShifter
from resources import FontResources, ImageResources
from shop import Shop
from skill import Skill
from spell import Spell
from state import Settings
from systems import InventorySystem
from text_catalog import TextCatalog
from ui.equipment_menu import EquipmentMenuOverlay
from ui.item_menu import ItemMenuOverlay
from ui.spell_menu import SpellMenuOverlay
from ui.status_menu import FACES_IMAGE_ID, StatusMenuOverlay, WindowCursor, WindowFactory


TEST_PARTY_CHARACTER_KEYS = (
    "Fiora",
    "Cerion",
    "Alvan",
    "Elika",
    "Ragna",
    "Dain",
)
TEST_BACK_ROW_CHARACTER_KEYS = frozenset(("Cerion", "Elika"))


def load_test_items() -> dict[str, Item]:
    return load_items()


def load_test_skills() -> dict[str, Skill]:
    return load_skills()


def load_test_spells() -> dict[str, Spell]:
    return load_spells()


def load_test_shops(items: dict[str, Item]) -> tuple[Shop, ...]:
    return load_shops(items)


def load_test_party(
    items: dict[str, Item],
    skills: dict[str, Skill],
) -> tuple[Member, ...]:
    return create_party(
        items,
        skills,
        character_keys=TEST_PARTY_CHARACTER_KEYS,
        back_row_character_keys=TEST_BACK_ROW_CHARACTER_KEYS,
    )


class StatusMenuHarness(StatusMenuOverlay):
    """Build the production status menu with deterministic test data."""

    def __init__(
        self,
        *,
        party: tuple[Member, ...] | None = None,
        settings: Settings | None = None,
        texts: TextCatalog | None = None,
        fonts: FontResources | None = None,
        faces: object | None = None,
        palette_shifter: PaletteShifter | None = None,
        member_index: int = 0,
        input_device: InputDevice = InputDevice.KEYBOARD,
    ) -> None:
        if party is None:
            items = load_test_items()
            party = load_test_party(items, load_test_skills())
        super().__init__(
            party=party,
            settings=Settings() if settings is None else settings,
            texts=(
                TextCatalog.from_json(APP_ROOT / "data" / "texts.json")
                if texts is None
                else texts
            ),
            fonts=FontResources() if fonts is None else fonts,
            faces=(
                ImageResources().image(FACES_IMAGE_ID) if faces is None else faces
            ),
            palette_shifter=palette_shifter,
            member_index=member_index,
            input_device=input_device,
            window_factory_class=WindowFactory,
            window_cursor_class=WindowCursor,
        )


class SpellMenuHarness(SpellMenuOverlay):
    """Build the production spell menu with deterministic test data."""

    def __init__(
        self,
        *,
        party: tuple[Member, ...] | None = None,
        spells: Mapping[str, Spell] | None = None,
        settings: Settings | None = None,
        texts: TextCatalog | None = None,
        fonts: FontResources | None = None,
        faces: object | None = None,
        palette_shifter: PaletteShifter | None = None,
        member_index: int = 0,
        event_spell_keys: Collection[str] = (),
    ) -> None:
        if party is None:
            items = load_test_items()
            party = load_test_party(items, load_test_skills())
        super().__init__(
            party=party,
            spells=load_test_spells() if spells is None else spells,
            settings=Settings() if settings is None else settings,
            texts=(
                TextCatalog.from_json(APP_ROOT / "data" / "texts.json")
                if texts is None
                else texts
            ),
            fonts=FontResources() if fonts is None else fonts,
            faces=(
                ImageResources().image(FACES_IMAGE_ID) if faces is None else faces
            ),
            member_index=member_index,
            palette_shifter=palette_shifter,
            event_spell_keys=event_spell_keys,
        )


class ItemMenuHarness(ItemMenuOverlay):
    """Build the production item menu with deterministic test data."""

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
        inventory_system: InventorySystem | None = None,
        on_invalid_action: Callable[[], None] | None = None,
    ) -> None:
        item_catalog = load_test_items() if items is None else items
        spell_catalog = load_test_spells() if spells is None else spells
        if party is None:
            party = load_test_party(dict(item_catalog), load_test_skills())
        super().__init__(
            party=party,
            items=item_catalog,
            spells=spell_catalog,
            settings=Settings() if settings is None else settings,
            texts=(
                TextCatalog.from_json(APP_ROOT / "data" / "texts.json")
                if texts is None
                else texts
            ),
            fonts=FontResources() if fonts is None else fonts,
            faces=(
                ImageResources().image(FACES_IMAGE_ID) if faces is None else faces
            ),
            palette_shifter=palette_shifter,
            inventory_system=(
                InventorySystem.with_one_each(item_catalog)
                if inventory_system is None
                else inventory_system
            ),
            on_invalid_action=on_invalid_action,
        )


class EquipmentMenuHarness(EquipmentMenuOverlay):
    """Build the production equipment menu with deterministic test data."""

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
        inventory_system: InventorySystem | None = None,
        member_index: int = 0,
        on_invalid_action: Callable[[], None] | None = None,
    ) -> None:
        item_catalog = load_test_items() if items is None else items
        spell_catalog = load_test_spells() if spells is None else spells
        if party is None:
            party = load_test_party(dict(item_catalog), load_test_skills())
        super().__init__(
            party=party,
            items=item_catalog,
            spells=spell_catalog,
            settings=Settings() if settings is None else settings,
            texts=(
                TextCatalog.from_json(APP_ROOT / "data" / "texts.json")
                if texts is None
                else texts
            ),
            fonts=FontResources() if fonts is None else fonts,
            faces=(
                ImageResources().image(FACES_IMAGE_ID) if faces is None else faces
            ),
            inventory_system=(
                InventorySystem.with_one_each(item_catalog)
                if inventory_system is None
                else inventory_system
            ),
            member_index=member_index,
            on_invalid_action=on_invalid_action,
        )
