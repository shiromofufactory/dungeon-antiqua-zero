"""Development adapter for the production status-menu overlay."""

from __future__ import annotations

from tools._bootstrap import APP_ROOT
from tools.screen_mocks._fixtures import (
    load_mock_items,
    load_mock_party,
    load_mock_skills,
)
from input import InputDevice
from member import Member
from resources import FontResources, ImageResources
from state import Settings
from text_catalog import TextCatalog
from ui import status_menu as _production


for _name, _value in vars(_production).items():
    if not _name.startswith("__"):
        globals()[_name] = _value


StatusMockDataError = _production.StatusMenuDataError


class StatusScreenMock(_production.StatusMenuOverlay):
    """Supply fixture defaults while exercising the production status overlay."""

    def __init__(
        self,
        *,
        party: tuple[Member, ...] | None = None,
        settings: Settings | None = None,
        texts: TextCatalog | None = None,
        fonts: FontResources | None = None,
        faces: object | None = None,
        member_index: int = 0,
        input_device: InputDevice = InputDevice.KEYBOARD,
    ) -> None:
        if party is None:
            items = load_mock_items()
            party = load_mock_party(items, load_mock_skills())
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
            member_index=member_index,
            input_device=input_device,
            window_factory_class=WindowFactory,
            window_cursor_class=WindowCursor,
        )
