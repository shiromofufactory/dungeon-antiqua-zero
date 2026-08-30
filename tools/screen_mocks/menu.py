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
from member import FormationRow, Member, MemberDataError
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
    WindowCursor,
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
PARTY_CURSOR_X = 3
PARTY_CURSOR_Y = 5
SORT_SOURCE_CURSOR_X_OFFSET = 1
FORMATION_ARROW_BANK = 0
FORMATION_ARROW_LEFT_X = (96, 112)
FORMATION_ARROW_RIGHT_X = (104, 120)
FORMATION_ARROW_Y = 0
FORMATION_ARROW_WIDTH = 8
FORMATION_ARROW_HEIGHT = 16
FORMATION_ARROW_COLKEY = 1
FORMATION_ARROW_FRAME_DURATION = 30
ALERT_CHANNEL = 1
ALERT_SOUND_ID = 7
ALERT_FRAME_COUNT = 3
ALERT_CAMERA_X = (0, 0, 1, -1)


class MenuMockDataError(RuntimeError):
    """Raised when localized data required by the menu mock is unavailable."""


class MenuAlertEffect:
    """Reproduce DA2's short error sound and horizontal screen shake."""

    def __init__(self) -> None:
        self.remaining_frames = 0

    @property
    def camera_x(self) -> int:
        return ALERT_CAMERA_X[self.remaining_frames]

    def start(self) -> None:
        pyxel.play(ALERT_CHANNEL, ALERT_SOUND_ID)
        self.remaining_frames = ALERT_FRAME_COUNT

    def update(self) -> None:
        if self.remaining_frames > 0:
            self.remaining_frames -= 1


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
        self.alert = MenuAlertEffect()

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
        self.localized = localized
        self.localized_texts = localized_texts
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
        self.party_cursor: WindowCursor | None = None
        self.sort_source_index: int | None = None
        self.sort_source_cursor: WindowCursor | None = None
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
            row_y = 2 + index * PARTY_MEMBER_ROW_HEIGHT
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

    def _sort_cursor_targets(self) -> tuple[CursorTarget, ...]:
        return tuple(
            CursorTarget(
                PARTY_CURSOR_X,
                PARTY_CURSOR_Y + index * PARTY_MEMBER_ROW_HEIGHT,
                key=index,
            )
            for index in range(len(self.party))
        )

    def _sort_source_target(self, index: int) -> CursorTarget:
        target = self._sort_cursor_targets()[index]
        return CursorTarget(
            target.x + SORT_SOURCE_CURSOR_X_OFFSET,
            target.y,
            key=target.key,
        )

    def _start_sort(self) -> None:
        self.command_cursor.active = False
        self.party_cursor = self.party_window.set_cursor(
            self._sort_cursor_targets()
        )

    def _finish_sort(self) -> None:
        self._clear_sort_source()
        self.party_window.clear_cursor()
        self.party_cursor = None
        self.command_cursor.active = True

    def _clear_sort_source(self) -> None:
        self.sort_source_index = None
        self.sort_source_cursor = None

    def _can_change_formation(self, member: Member) -> bool:
        return not member.is_front_row or sum(
            party_member.is_front_row for party_member in self.party
        ) > 1

    def _confirm_sort_member(self) -> None:
        if self.party_cursor is None:
            return
        target_index = self.party_cursor.selected_key
        if (
            not isinstance(target_index, int)
            or not 0 <= target_index < len(self.party)
        ):
            return

        if self.sort_source_index is None:
            self.sort_source_index = target_index
            self.sort_source_cursor = WindowCursor(
                self.party_window,
                (self._sort_source_target(target_index),),
                active=False,
                draw_shadow=False,
            )
            return

        source_index = self.sort_source_index
        if source_index == target_index:
            member = self.party[target_index]
            if not self._can_change_formation(member):
                self.alert.start()
            elif member.is_front_row:
                member.formation_row = FormationRow.BACK
            else:
                member.formation_row = FormationRow.FRONT
        else:
            party = list(self.party)
            party[source_index], party[target_index] = (
                party[target_index],
                party[source_index],
            )
            self.party = tuple(party)
            self._refresh_party_window_texts()
        self._clear_sort_source()

    def _refresh_party_window_texts(self) -> None:
        self.party_window.clear_texts()
        for placement in self._party_window_texts(
            self.party,
            self.localized,
            self.localized_texts,
        ):
            self.party_window.add_text(
                placement.text,
                placement.x,
                placement.y,
                color=placement.color,
                font=placement.font,
                shadow_color=placement.shadow_color,
                baseline_offset=placement.baseline_offset,
            )

    def update(self) -> None:
        self.alert.update()
        input_state = self.input_reader.poll()

        if self.party_cursor is not None:
            if input_state.cancel.triggered:
                if self.sort_source_index is None:
                    self._finish_sort()
                else:
                    self._clear_sort_source()
                return
            if input_state.confirm.triggered:
                self._confirm_sort_member()
            self.party_window.update(input_state.navigation)
            return

        if input_state.cancel.triggered:
            pyxel.quit()
            return
        if (
            input_state.confirm.triggered
            and self.command_cursor.selected_key == "sort"
        ):
            self._start_sort()
            return
        self.command_window.update(input_state.navigation)

    def draw(self) -> None:
        pyxel.camera(self.alert.camera_x, 0)
        try:
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
            if self.party_cursor is not None:
                if self.sort_source_cursor is not None:
                    self.sort_source_cursor.draw()
                    self._draw_formation_arrow()
                self.party_cursor.draw()
            for window in self.windows[1:]:
                window.draw()
        finally:
            pyxel.camera()

    def _draw_formation_arrow(self) -> None:
        if (
            self.sort_source_index is None
            or self.party_cursor is None
            or self.party_cursor.selected_key != self.sort_source_index
        ):
            return
        member = self.party[self.sort_source_index]
        if not self._can_change_formation(member):
            return
        if member.is_front_row:
            x = PARTY_FACE_X[True] + PARTY_FACE_SIZE
            source_x = FORMATION_ARROW_RIGHT_X
        else:
            x = PARTY_FACE_X[False] - FORMATION_ARROW_WIDTH
            source_x = FORMATION_ARROW_LEFT_X
        y = (
            PARTY_FACE_Y
            + self.sort_source_index * PARTY_MEMBER_ROW_HEIGHT * 4
            + (PARTY_FACE_SIZE - FORMATION_ARROW_HEIGHT) // 2
        )
        frame = (pyxel.frame_count // FORMATION_ARROW_FRAME_DURATION) % 2
        pyxel.blt(
            x,
            y,
            FORMATION_ARROW_BANK,
            source_x[frame],
            FORMATION_ARROW_Y,
            FORMATION_ARROW_WIDTH,
            FORMATION_ARROW_HEIGHT,
            FORMATION_ARROW_COLKEY,
        )


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
