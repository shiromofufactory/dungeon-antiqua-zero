"""Development adapter for the production spell-menu overlay."""

from __future__ import annotations

from collections.abc import Collection, Mapping

from tools._bootstrap import APP_ROOT
from tools.screen_mocks._fixtures import (
    load_mock_items,
    load_mock_party,
    load_mock_skills,
    load_mock_spells,
)
from member import Member
from resources import FontResources, ImageResources
from spell import Spell
from state import Settings
from text_catalog import TextCatalog
from ui import spell_menu as _production


for _name, _value in vars(_production).items():
    if not _name.startswith("__"):
        globals()[_name] = _value


SpellMockDataError = _production.SpellMenuDataError


class SpellScreenMock(_production.SpellMenuOverlay):
    """Supply fixture defaults while exercising the production spell overlay."""

    def __init__(
        self,
        *,
        party: tuple[Member, ...] | None = None,
        spells: Mapping[str, Spell] | None = None,
        settings: Settings | None = None,
        texts: TextCatalog | None = None,
        fonts: FontResources | None = None,
        faces: object | None = None,
        member_index: int = 0,
        event_spell_keys: Collection[str] = (),
    ) -> None:
        if party is None:
            items = load_mock_items()
            party = load_mock_party(items, load_mock_skills())
        super().__init__(
            party=party,
            spells=load_mock_spells() if spells is None else spells,
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
            event_spell_keys=event_spell_keys,
        )


__all__ = [*_production.__all__, "SpellMockDataError", "SpellScreenMock"]
