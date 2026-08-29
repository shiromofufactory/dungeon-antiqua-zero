"""Display the current status-screen layout mock."""

from __future__ import annotations

import json

import pyxel

from tools._bootstrap import APP_ROOT
from input import InputBindings, PyxelInputReader
from localization import Localizer
from member import Member, MemberDataError
from resources import (
    TRANSPARENT_INDEX,
    FontResourceError,
    FontResources,
    ImageResourceError,
    ImageResources,
)
from state import Language, Settings
from text_catalog import TextCatalog, TextCatalogError
from ui import WindowFactory, WindowText

SCREEN_WIDTH = 256
SCREEN_HEIGHT = 240
FPS = 60
FACES_IMAGE_ID = "faces/faces_pc"
MOCK_CHARACTER_KEY = "Fiora"
LANGUAGE_SEQUENCE = (
    Language.JAPANESE,
    Language.ENGLISH,
    Language.SIMPLIFIED_CHINESE,
)


def next_language(language: Language) -> Language:
    """Return the next language used by the status mock."""

    if not isinstance(language, Language):
        raise TypeError("language must be a Language")
    index = LANGUAGE_SEQUENCE.index(language)
    return LANGUAGE_SEQUENCE[(index + 1) % len(LANGUAGE_SEQUENCE)]


def load_mock_member() -> Member:
    """Load the character used by this mock from generated game data."""

    path = APP_ROOT / "data" / "characters.json"
    try:
        records = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise MemberDataError(f"キャラクターデータがありません: {path}") from error
    except json.JSONDecodeError as error:
        raise MemberDataError(
            f"キャラクターデータを読み込めません: {path}: {error}"
        ) from error

    if not isinstance(records, list):
        raise MemberDataError("characters.jsonのルートは配列である必要があります")
    record = next(
        (
            candidate
            for candidate in records
            if isinstance(candidate, dict)
            and candidate.get("name_en") == MOCK_CHARACTER_KEY
        ),
        None,
    )
    if record is None:
        raise MemberDataError(
            f"モック用キャラクターが見つかりません: {MOCK_CHARACTER_KEY}"
        )
    return Member.from_record(record)


class StatusScreenMock:
    def __init__(self) -> None:
        pyxel.init(
            SCREEN_WIDTH,
            SCREEN_HEIGHT,
            title="Dungeon Antiqua ZERO Status Screen Mock",
            fps=FPS,
        )
        pyxel.load(str(APP_ROOT / "assets.pyxres"))
        pyxel.load_pal(str(APP_ROOT / "assets.pyxpal"))
        self.input_reader = PyxelInputReader(
            InputBindings.default().with_cancel(pyxel.KEY_Q)
        )

        resources = ImageResources()
        self.faces = resources.image(FACES_IMAGE_ID)

        self.settings = Settings()
        self.texts = TextCatalog.from_json(APP_ROOT / "data" / "texts.json")
        self.member = load_mock_member()
        self.fonts = FontResources()
        localizer = Localizer(self.settings.language)
        identity = self.member.display_identity(localizer, self.texts)
        identity_font = self.fonts.font_for(self.settings.language)
        windows = WindowFactory(self.fonts.font_for(Language.JAPANESE))
        self.windows = [
            windows.create(
                0,
                0,
                64,
                60,
                (
                    WindowText(identity.name, 14, 2, font=identity_font),
                    WindowText(identity.race, 14, 5, font=identity_font),
                    WindowText(identity.gender, 14, 8, font=identity_font),
                    WindowText("ＨＰ　９９９／９９９", 6, 14),
                    WindowText("ＭＰ　２５５／２５５", 6, 17),
                    WindowText("じょうたい　　　ＯＫ", 6, 20),
                    WindowText("ちから　　　　１７", 6, 26),
                    WindowText("すばやさ　　　２５", 6, 29),
                    WindowText("まりょく　　　２４", 6, 32),
                    WindowText("スキル：", 6, 38),
                    WindowText("　ふくつのとうし", 6, 41),
                    WindowText("　りょうてもち", 6, 44),
                    WindowText("みぎて　：%WAND%デイブリンガー", 30, 8),
                    WindowText("ひだりて：", 30, 11),
                    WindowText("からだ　：エインシーのはごろも", 30, 14),
                    WindowText("あたま　：はなかんむり", 30, 17),
                    WindowText("うで　　：タイニーリング", 30, 20),
                    WindowText("こうげき　　　　９６", 30, 26),
                    WindowText("めいちゅう　　１１６（＋１６）", 30, 29),
                    WindowText("ぼうぎょ　　　　２０", 30, 32),
                    WindowText("かいひりつ　　　１５", 30, 35),
                    WindowText("じゅつぼうぎょ　４０", 30, 38),
                    WindowText("たいせい", 30, 41),
                    WindowText("%FIRE%", 32, 44),
                    WindowText("%FREEZE%", 34, 44),
                    WindowText("%DARK%", 36, 44),
                    WindowText("%SLEEP%", 38, 44),
                    WindowText("%POISON%", 40, 44),
                    WindowText("%PARALIZE%", 42, 44),
                    WindowText("%CONFUSE%", 44, 44),
                    WindowText("%SILENCE%", 46, 44),
                    WindowText("%DEATH%", 48, 44),
                    WindowText("%SWORD%：９－９９", 6, 49),
                    WindowText("%KATANA%：９－９９", 20, 49),
                    WindowText("%KNIFE%：９－９９", 34, 49),
                    WindowText("%SPEAR%：９－９９", 48, 49),
                    WindowText("%AXE%：９－９９", 6, 52),
                    WindowText("%HAMMER%：９－９９", 20, 52),
                    WindowText("%THROWING%：９－９９", 34, 52),
                    WindowText("%ROD%：９－９９", 48, 52),
                    WindowText("%WAND%：９－９９", 6, 55),
                    WindowText("%MYSTIC%：９－９９", 20, 55),
                    WindowText("%SACRED%：９－９９", 34, 55),
                    WindowText("%NETHER%：９－９９", 48, 55),
                ),
            ),
        ]
        pyxel.run(self.update, self.draw)

    def _rebuild_identity_window(self) -> None:
        """Rebuild the window with the identity text in the selected language."""

        current_window = self.windows[0]
        localizer = Localizer(self.settings.language)
        identity = self.member.display_identity(localizer, self.texts)
        identity_font = self.fonts.font_for(self.settings.language)
        texts = (
            WindowText(identity.name, 14, 2, font=identity_font),
            WindowText(identity.race, 14, 5, font=identity_font),
            WindowText(identity.gender, 14, 8, font=identity_font),
            *current_window.texts[3:],
        )
        windows = WindowFactory(self.fonts.font_for(Language.JAPANESE))
        self.windows = [windows.create(0, 0, 64, 60, texts)]

    def update(self) -> None:
        input_state = self.input_reader.poll()
        if input_state.cancel.triggered:
            pyxel.quit()
            return

        if input_state.confirm.triggered:
            language = next_language(self.settings.language)
            self.settings = self.settings.with_language(language)
            self._rebuild_identity_window()

    def draw(self) -> None:
        # ウィンドウ
        for window in self.windows:
            window.draw()
        # 顔
        pyxel.blt(
            16,
            8,
            self.faces,
            0,
            0,
            32,
            32,
            TRANSPARENT_INDEX,
        )


def main() -> int:
    try:
        StatusScreenMock()
        return 0
    except (
        FontResourceError,
        ImageResourceError,
        MemberDataError,
        TextCatalogError,
    ) as error:
        print(error)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
