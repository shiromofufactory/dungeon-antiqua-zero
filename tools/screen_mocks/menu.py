"""Display the current menu-screen layout mock."""

from __future__ import annotations

import pyxel

from tools._bootstrap import APP_ROOT
from tools.screen_mocks._fixtures import (
    MockFixtureError,
    load_mock_items,
    load_mock_party,
    load_mock_skills,
)
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
from item import ItemDataError
from localization import Localizer, format_number
from member import Member, MemberDataError
from resources import (
    TRANSPARENT_INDEX,
    DataResourceError,
    FontResourceError,
    FontResources,
    ImageResourceError,
    ImageResources,
)
from skill import SkillDataError
from state import Difficulty, Language, SaveData, Settings

from text_catalog import TextCatalog, TextCatalogError
from ui import (
    CursorTarget,
    DEFAULT_TEXT_COLOR,
    DISABLED_COLOR,
    LocalizedWindowTextFactory,
    NEGATIVE_COLOR,
    POSITIVE_COLOR,
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
MENU_MEMBER_TEXT_KEYS = (
    "menu.member.hp",
    "menu.member.mp",
)
MOCK_INPUT_DEVICE = InputDevice.KEYBOARD
FACES_IMAGE_ID = "faces/faces_pc"
PARTY_WINDOW_GRID = (0, 0, 48, 60)
PARTY_MEMBER_ROW_HEIGHT = 11
PARTY_FACE_X = {
    True: 20,
    False: 32,
}
PARTY_FACE_Y = 14
PARTY_FACE_SIZE = 32
PARTY_TEXT_X = 18
PARTY_RECOVERY_TEXT_X = 38


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
        *MENU_MEMBER_TEXT_KEYS,
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
        self.party = load_mock_party(
            load_mock_items(),
            load_mock_skills(),
        )
        self.texts = TextCatalog.from_json(APP_ROOT / "data" / "texts.json")
        localized = localized_menu_texts(
            self.texts,
            self.settings.language,
        )
        self.fonts = FontResources()
        self.faces = ImageResources().image(FACES_IMAGE_ID)
        localized_texts = LocalizedWindowTextFactory.from_language(
            self.fonts,
            self.settings.language,
        )
        windows = WindowFactory(self.fonts.font_for(Language.JAPANESE))
        self.party_window = windows.create(
            *PARTY_WINDOW_GRID,
            self._party_window_texts(
                self.party,
                localized,
                localized_texts,
            ),
        )
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
            self.party_window,
            self.command_window,
            self.info_window,
            self.close_guide_window,
        ]

        pyxel.run(self.update, self.draw)

    def _party_window_texts(
        self,
        party: tuple[Member, ...],
        localized: dict[str, str],
        text_factory: LocalizedWindowTextFactory,
    ) -> tuple[WindowText, ...]:
        """Build the five compact name/HP/MP rows for the main window."""

        localizer = Localizer(self.settings.language)
        texts: list[WindowText] = []
        for index, member in enumerate(party):
            row_y = 3 + index * PARTY_MEMBER_ROW_HEIGHT
            texts.extend(
                (
                    text_factory.create(
                        member.definition.localized_name(localizer),
                        PARTY_TEXT_X,
                        row_y,
                    ),
                    text_factory.create(
                        self._point_text(
                            localized["menu.member.hp"],
                            member.hp,
                            member.max_hp,
                        ),
                        PARTY_TEXT_X,
                        row_y + 3,
                    ),
                    text_factory.create(
                        self._point_text(
                            localized["menu.member.mp"],
                            member.mp,
                            member.max_mp,
                        ),
                        PARTY_TEXT_X,
                        row_y + 6,
                        color=(
                            DISABLED_COLOR if member.max_mp == 0 else DEFAULT_TEXT_COLOR
                        ),
                    ),
                )
            )
            condition = member.status(
                localizer,
                self.texts,
                show_mhp=False,
            )
            if condition:
                texts.append(
                    text_factory.create(
                        condition,
                        PARTY_RECOVERY_TEXT_X,
                        row_y + 3,
                    )
                )
                continue
            amount = member.heal_and_poison_amount
            if amount:
                sign = "＋" if amount > 0 else "－"
                texts.append(
                    text_factory.create(
                        f"（{sign}{format_number(abs(amount))}）",
                        PARTY_RECOVERY_TEXT_X,
                        row_y + 3,
                        color=(POSITIVE_COLOR if amount > 0 else NEGATIVE_COLOR),
                    )
                )
        return tuple(texts)

    @staticmethod
    def _point_text(label: str, current: int, maximum: int) -> str:
        return f"{label}　{pad(current, 3)}／{pad(maximum, 3)}"

    def update(self) -> None:
        input_state = self.input_reader.poll()
        if input_state.cancel.triggered:
            pyxel.quit()
            return

        self.command_window.update(input_state.navigation)

    def draw(self) -> None:
        self.party_window.draw()
        for index, member in enumerate(self.party):
            face_position = member.face_position
            pyxel.blt(
                PARTY_FACE_X[member.is_front_row],
                PARTY_FACE_Y + index * PARTY_MEMBER_ROW_HEIGHT * 4,
                self.faces,
                face_position.x,
                face_position.y,
                PARTY_FACE_SIZE,
                PARTY_FACE_SIZE,
                TRANSPARENT_INDEX,
            )
        for window in self.windows[1:]:
            window.draw()


def main() -> int:
    return run_screen_mock(
        MenuScreenMock,
        expected_errors=(
            DataResourceError,
            FontResourceError,
            ImageResourceError,
            ItemDataError,
            MemberDataError,
            MenuMockDataError,
            MockFixtureError,
            SkillDataError,
            TextCatalogError,
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
