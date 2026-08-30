"""Display the current menu-screen layout mock."""

from __future__ import annotations

import pyxel

from tools._bootstrap import APP_ROOT
from tools.screen_mocks._runner import run_screen_mock
from tools.screen_mocks._runtime import (
    FPS,
    create_mock_input_reader,
    initialize_screen_mock,
)
from input import (
    InputAction,
    InputDevice,
)
from localization import Localizer
from resources import (
    FontResourceError,
    FontResources,
)
from state import Difficulty, Language, SaveData, Settings

from text_catalog import TextCatalog, TextCatalogError
from ui import (
    CursorTarget,
    LocalizedWindowTextFactory,
    WindowFactory,
    WindowText,
    format_play_time,
    input_icon_tag,
    pad,
)

MENU_COMMANDS = (
    ("item", "menu.command.item"),
    ("spell", "menu.command.spell"),
    ("equip", "menu.command.equip"),
    ("skill", "menu.command.skill"),
    ("status", "menu.command.status"),
    ("sort", "menu.command.sort"),
    ("info", "menu.command.info"),
    ("config", "menu.command.settings"),
    ("save", "menu.command.save"),
)
DIFFICULTY_TEXT_KEYS = {
    Difficulty.NORMAL: "menu.difficulty.normal",
    Difficulty.HARD: "menu.difficulty.hard",
}
MENU_INFO_TEXT_KEYS = (
    "menu.info.gold",
    "menu.info.experience",
    "menu.info.difficulty",
    "menu.info.play_time",
)
MENU_CLOSE_GUIDE_TEXT_KEY = "menu.close_guide"
MOCK_INPUT_DEVICE = InputDevice.KEYBOARD


class MenuMockDataError(RuntimeError):
    """Raised when localized data required by the menu mock is unavailable."""


def localized_menu_texts(
    catalog: TextCatalog,
    language: Language,
) -> dict[str, str]:
    """Resolve every menu term from the shared text catalog."""

    if not isinstance(catalog, TextCatalog):
        raise TypeError("catalog must be a TextCatalog")
    localizer = Localizer(language)
    keys = (
        *(text_key for _command_key, text_key in MENU_COMMANDS),
        *MENU_INFO_TEXT_KEYS,
        *DIFFICULTY_TEXT_KEYS.values(),
        MENU_CLOSE_GUIDE_TEXT_KEY,
    )
    localized: dict[str, str] = {}
    for key in keys:
        text = catalog.text(key, localizer)
        if not text:
            raise MenuMockDataError(f"メニューモック用テキストが見つかりません: {key}")
        localized[key] = text

    close_guide = localized[MENU_CLOSE_GUIDE_TEXT_KEY]
    if close_guide.count("%CANCEL%") != 1:
        raise MenuMockDataError(f"{MENU_CLOSE_GUIDE_TEXT_KEY}には%CANCEL%が1つ必要です")
    return localized


class MenuScreenMock:
    def __init__(self) -> None:
        initialize_screen_mock("Dungeon Antiqua ZERO Menu Screen Mock")
        self.input_reader = create_mock_input_reader()

        self.settings = Settings()
        self.save_data = SaveData()
        self.texts = TextCatalog.from_json(APP_ROOT / "data" / "texts.json")
        localized = localized_menu_texts(
            self.texts,
            self.settings.language,
        )
        self.fonts = FontResources()
        localized_texts = LocalizedWindowTextFactory.from_language(
            self.fonts,
            self.settings.language,
        )
        windows = WindowFactory(self.fonts.font_for(Language.JAPANESE))
        command_texts = tuple(
            localized_texts.create(
                localized[text_key],
                4,
                2 + index * 3,
            )
            for index, (_command_key, text_key) in enumerate(MENU_COMMANDS)
        )
        self.command_window = windows.create(
            48,
            0,
            16,
            30,
            command_texts,
        )
        self.command_cursor = self.command_window.set_cursor(
            tuple(
                CursorTarget(2, 2 + index * 3, key=key)
                for index, (key, _) in enumerate(MENU_COMMANDS)
            )
        )
        self.info_window = windows.create(
            48,
            30,
            16,
            27,
            (
                localized_texts.create(localized["menu.info.gold"], 2, 2),
                WindowText(pad(self.save_data.gold, 6), 2, 5),
                localized_texts.create(
                    localized["menu.info.experience"],
                    2,
                    8,
                ),
                WindowText(pad(self.save_data.experience, 6), 2, 11),
                localized_texts.create(
                    localized["menu.info.difficulty"],
                    2,
                    14,
                ),
                localized_texts.create(
                    localized[DIFFICULTY_TEXT_KEYS[self.save_data.difficulty]],
                    4,
                    17,
                ),
                localized_texts.create(
                    localized["menu.info.play_time"],
                    2,
                    20,
                ),
                WindowText(
                    "　"
                    + format_play_time(
                        self.save_data.play_time_frames,
                        fps=FPS,
                        include_seconds=False,
                    ),
                    2,
                    23,
                ),
            ),
        )
        self.close_guide_window = windows.create(
            48,
            57,
            16,
            4,
            (
                localized_texts.create(
                    localized[MENU_CLOSE_GUIDE_TEXT_KEY].replace(
                        "%CANCEL%",
                        input_icon_tag(
                            InputAction.CANCEL,
                            MOCK_INPUT_DEVICE,
                        ),
                    ),
                    2,
                    0,
                ),
            ),
            transparent=True,
        )
        self.windows = [
            self.command_window,
            self.info_window,
            self.close_guide_window,
        ]

        pyxel.run(self.update, self.draw)

    def update(self) -> None:
        input_state = self.input_reader.poll()
        if input_state.cancel.triggered:
            pyxel.quit()
            return

        self.command_window.update(input_state.navigation)

    def draw(self) -> None:
        for window in self.windows:
            window.draw()


def main() -> int:
    return run_screen_mock(
        MenuScreenMock,
        expected_errors=(
            FontResourceError,
            MenuMockDataError,
            TextCatalogError,
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
