"""Development adapter for the production equipment-menu overlay."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from tools._bootstrap import APP_ROOT
from tools.screen_mocks._fixtures import (
    load_mock_items,
    load_mock_party,
    load_mock_skills,
    load_mock_spells,
)
from item import Item
from member import Member
from resources import FontResources, ImageResources
from spell import Spell
from state import Settings
from systems import InventorySystem
from text_catalog import TextCatalog
from ui import equipment_menu as _production


for _name, _value in vars(_production).items():
    if not _name.startswith("__"):
        globals()[_name] = _value


EquipmentMockDataError = _production.EquipmentMenuDataError


class EquipmentScreenMock(_production.EquipmentMenuOverlay):
    """Supply fixture defaults while exercising the production equipment overlay."""

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
        item_catalog = load_mock_items() if items is None else items
        spell_catalog = load_mock_spells() if spells is None else spells
        if party is None:
            party = load_mock_party(dict(item_catalog), load_mock_skills())
        resolved_inventory = (
            InventorySystem.with_one_each(item_catalog)
            if inventory_system is None
            else inventory_system
        )
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
            inventory_system=resolved_inventory,
            member_index=member_index,
            on_invalid_action=on_invalid_action,
        )


__all__ = [
    *_production.__all__,
    "EquipmentMockDataError",
    "EquipmentScreenMock",
]
