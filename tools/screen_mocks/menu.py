"""Display an empty menu-screen layout mock."""

from __future__ import annotations

import json

import pyxel

from tools._bootstrap import APP_ROOT
from input import Direction, InputBindings, PyxelInputReader
from localization import Localizer
from member import (
    Member,
    MemberDataError,
)
from resources import (
    TRANSPARENT_INDEX,
    FontResourceError,
    FontResources,
    ImageResourceError,
    ImageResources,
)
from state import Language, Settings

from ui import WindowFactory
from text_catalog import TextCatalog, TextCatalogError

SCREEN_WIDTH = 256
SCREEN_HEIGHT = 240
FPS = 60
FACES_IMAGE_ID = "faces/faces_pc"
MOCK_PARTY_CHARACTER_KEYS = (
    "Fiora",
    "Cerion",
    "Alvan",
    "Elika",
    "Ragna",
)


class StatusMockDataError(RuntimeError):
    """Raised when generated data required by this mock is unavailable."""


def load_data_records(filename: str) -> list[dict[str, object]]:
    """Load one generated array dataset used by the status mock."""

    path = APP_ROOT / "data" / filename
    try:
        records = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise StatusMockDataError(f"ゲームデータがありません: {path}") from error
    except json.JSONDecodeError as error:
        raise StatusMockDataError(
            f"ゲームデータを読み込めません: {path}: {error}"
        ) from error

    if not isinstance(records, list) or not all(
        isinstance(record, dict) for record in records
    ):
        raise StatusMockDataError(
            f"{filename}のルートはオブジェクトの配列である必要があります"
        )
    return records


def load_mock_party() -> tuple[Member, ...]:
    """Load the ordered party used by this mock from generated game data."""

    records = load_data_records("characters.json")
    records_by_key = {
        key: record
        for record in records
        if isinstance(key := record.get("name_en"), str)
    }
    party: list[Member] = []
    for key in MOCK_PARTY_CHARACTER_KEYS:
        record = records_by_key.get(key)
        if record is None:
            raise MemberDataError(f"モック用キャラクターが見つかりません: {key}")
        party.append(Member.from_record(record))
    return tuple(party)


class MenuScreenMock:
    def __init__(self) -> None:
        pyxel.init(
            SCREEN_WIDTH,
            SCREEN_HEIGHT,
            title="Dungeon Antiqua ZERO Menu Screen Mock",
            fps=FPS,
        )
        pyxel.load(str(APP_ROOT / "assets.pyxres"))
        pyxel.load_pal(str(APP_ROOT / "assets.pyxpal"))
        self.input_reader = PyxelInputReader(
            InputBindings.default().with_cancel(pyxel.KEY_Q)
        )

        resources = ImageResources()
        self.faces = resources.image(FACES_IMAGE_ID)

        settings = Settings()
        self.texts = TextCatalog.from_json(APP_ROOT / "data" / "texts.json")
        fonts = FontResources()
        windows = WindowFactory(fonts.font_for(settings.language))
        self.windows = [windows.create(48, 0, 16, 60)]

        pyxel.run(self.update, self.draw)

    @staticmethod
    def update() -> None:
        if pyxel.btnp(pyxel.KEY_Q) or pyxel.btnp(pyxel.KEY_ESCAPE):
            pyxel.quit()

    def draw(self) -> None:
        for window in self.windows:
            window.draw()


def main() -> int:
    try:
        MenuScreenMock()
        return 0
    except FontResourceError as error:
        print(error)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
