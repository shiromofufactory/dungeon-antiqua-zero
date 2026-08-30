"""Display the current menu-screen layout mock."""

from __future__ import annotations

import json
import os

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
from tools.screen_mocks.status import StatusMockDataError, StatusScreenMock
from input import (
    Direction,
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
from state import DisplayMode, Difficulty, Language, SaveData, Settings

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
SETTINGS_TEXT_KEYS = (
    "settings.language.label",
    "settings.language.ja",
    "settings.language.en",
    "settings.language.zhcn",
    "settings.se.label",
    "settings.screen_size.label",
    "settings.screen_size.fullscreen",
    "settings.display.label",
    "settings.display.pixel",
    "settings.display.smooth",
    "settings.return_title",
    "settings.quit",
    "settings.guide.language.0",
    "settings.guide.language.1",
    "settings.guide.se.0",
    "settings.guide.se.1",
    "settings.guide.screen_size.0",
    "settings.guide.screen_size.1",
    "settings.guide.display.0",
    "settings.guide.display.1",
    "settings.confirm.return_title",
    "settings.confirm.quit",
    "settings.yes",
    "settings.no",
)
SETTINGS_ROWS = (
    ("language", 2),
    ("se", 5),
    ("screen_size", 8),
    ("display", 11),
    ("return_title", 17),
    ("quit", 20),
)
SETTINGS_GUIDE_KEYS = {
    "language": (
        "settings.guide.language.0",
        "settings.guide.language.1",
    ),
    "se": ("settings.guide.se.0", "settings.guide.se.1"),
    "screen_size": (
        "settings.guide.screen_size.0",
        "settings.guide.screen_size.1",
    ),
    "display": ("settings.guide.display.0", "settings.guide.display.1"),
}
LANGUAGE_SEQUENCE = (
    Language.JAPANESE,
    Language.ENGLISH,
    Language.SIMPLIFIED_CHINESE,
)
DISPLAY_SEQUENCE = (DisplayMode.PIXEL, DisplayMode.SMOOTH)
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
SETTINGS_WINDOW_GRID = (4, 12, 56, 36)
SETTINGS_LABEL_X = 4
SETTINGS_VALUE_X = 30
SETTINGS_CURSOR_X = 2
SETTINGS_GUIDE_X = 4
SETTINGS_GUIDE_Y = 26
SETTINGS_GUIDE_ROW_HEIGHT = 3
CONFIRMATION_WINDOW_GRID = (8, 22, 48, 16)
CONFIRMATION_CURSOR_X = 4
CONFIRMATION_YES_Y = 8
CONFIRMATION_NO_Y = 11
SE_VOLUME_GAINS = (0.0, 0.05, 0.10, 0.15, 0.20)
SE_PREVIEW_SOUND_ID = 9
MENU_MOCK_SETTINGS_ENV = "DA0_MENU_MOCK_SETTINGS"


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
        *SETTINGS_TEXT_KEYS,
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
        self.settings = self._settings_from_environment()
        initialize_screen_mock(
            "Dungeon Antiqua ZERO Menu Screen Mock",
            display_scale=(
                None if self.settings.screen_scale == 5 else self.settings.screen_scale
            ),
        )
        if self.settings.screen_scale == 5:
            pyxel.fullscreen(True)
        self.input_reader = create_mock_input_reader()
        self.alert = MenuAlertEffect()

        self._apply_se_volume()
        if self.settings.display_mode is DisplayMode.SMOOTH:
            self._apply_display_mode()
        self.save_data = SaveData()
        self.items = load_mock_items()
        self.skills = load_mock_skills()
        self.party = load_mock_party(self.items, self.skills)
        self.texts = TextCatalog.from_json(APP_ROOT / "data" / "texts.json")
        self.fonts = FontResources()
        self.faces = ImageResources().image(FACES_IMAGE_ID)
        self.settings_window = None
        self.settings_cursor: WindowCursor | None = None
        self.confirmation_window = None
        self.confirmation_cursor: WindowCursor | None = None
        self.pending_settings_action: str | None = None
        self.status_screen: StatusScreenMock | None = None
        self.selected_member_index = 0
        self._build_main_windows()

        pyxel.run(self.update, self.draw)

    @staticmethod
    def _settings_from_environment() -> Settings:
        serialized = os.environ.get(MENU_MOCK_SETTINGS_ENV)
        if serialized is None:
            return Settings()
        try:
            data = json.loads(serialized)
            return Settings.from_dict(data)
        except (json.JSONDecodeError, TypeError, ValueError):
            os.environ.pop(MENU_MOCK_SETTINGS_ENV, None)
            return Settings()

    @staticmethod
    def _select_cursor_key(cursor: WindowCursor, key: object) -> None:
        """Move a newly built vertical cursor to one existing key."""

        if cursor.selected_key == key:
            return
        for _target in cursor.targets:
            cursor.move_down()
            if cursor.selected_key == key:
                return
        raise ValueError(f"cursor key is not registered: {key!r}")

    def _build_main_windows(
        self,
        selected_command: str = "item",
        *,
        animate: bool = True,
    ) -> None:
        localized = localized_menu_texts(
            self.texts,
            self.settings.language,
        )
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
            opened=not animate,
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
            opened=not animate,
        )
        self.command_cursor = self.command_window.set_cursor(
            tuple(
                CursorTarget(2, 2 + index * 3, key=key)
                for index, (key, _) in enumerate(MENU_COMMANDS)
            )
        )
        if selected_command != MENU_COMMANDS[0][0]:
            self._select_cursor_key(self.command_cursor, selected_command)
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
            opened=not animate,
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
            opened=not animate,
        )
        self.windows = [
            self.party_window,
            self.command_window,
            self.info_window,
            self.close_guide_window,
        ]
        if animate:
            for window in self.windows:
                window.open()

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
        self.party_cursor = self.party_window.set_cursor(self._sort_cursor_targets())
        selected_member_index = getattr(self, "selected_member_index", 0)
        if selected_member_index != 0:
            self._select_cursor_key(self.party_cursor, selected_member_index)

    def _finish_sort(self) -> None:
        self._clear_sort_source()
        self.party_window.clear_cursor()
        self.party_cursor = None
        self.command_cursor.active = True

    def _clear_sort_source(self) -> None:
        self.sort_source_index = None
        self.sort_source_cursor = None

    def _can_change_formation(self, member: Member) -> bool:
        return (
            not member.is_front_row
            or sum(party_member.is_front_row for party_member in self.party) > 1
        )

    def _confirm_sort_member(self) -> None:
        if self.party_cursor is None:
            return
        target_index = self.party_cursor.selected_key
        if not isinstance(target_index, int) or not 0 <= target_index < len(self.party):
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
                font_spans=placement.font_spans,
            )

    def _settings_value(self, key: str) -> str:
        if key == "language":
            return self.localized[f"settings.language.{self.settings.language.value}"]
        if key == "se":
            return format_number(self.settings.se_volume)
        if key == "screen_size":
            if self.settings.screen_scale == 5:
                return self.localized["settings.screen_size.fullscreen"]
            return (
                f"{format_number(self.settings.screen_scale * 256)}"
                f"×{format_number(self.settings.screen_scale * 240)}"
            )
        if key == "display":
            return self.localized[
                f"settings.display.{self.settings.display_mode.value}"
            ]
        raise ValueError(f"settings key has no value: {key}")

    def _settings_window_texts(
        self,
        selected_key: str,
    ) -> tuple[WindowText, ...]:
        texts: list[WindowText] = []
        label_keys = {
            "language": "settings.language.label",
            "se": "settings.se.label",
            "screen_size": "settings.screen_size.label",
            "display": "settings.display.label",
        }
        action_keys = {
            "return_title": "settings.return_title",
            "quit": "settings.quit",
        }
        for key, y in SETTINGS_ROWS:
            if key in label_keys:
                texts.extend(
                    (
                        self.localized_texts.create(
                            self.localized[label_keys[key]],
                            SETTINGS_LABEL_X,
                            y,
                        ),
                        self.localized_texts.create("：", 28, y),
                        self.localized_texts.create(
                            self._settings_value(key),
                            SETTINGS_VALUE_X,
                            y,
                        ),
                    )
                )
            else:
                texts.append(
                    self.localized_texts.create(
                        self.localized[action_keys[key]],
                        SETTINGS_LABEL_X,
                        y,
                    )
                )
        guide_keys = SETTINGS_GUIDE_KEYS.get(selected_key, ())
        if selected_key == "language" and self.settings.language is Language.ENGLISH:
            guide_keys = guide_keys[:1]
        for index, text_key in enumerate(guide_keys):
            texts.append(
                self.localized_texts.create(
                    self.localized[text_key],
                    SETTINGS_GUIDE_X,
                    SETTINGS_GUIDE_Y + index * SETTINGS_GUIDE_ROW_HEIGHT,
                )
            )
        return tuple(texts)

    def _build_settings_window(self, selected_key: str = "language") -> None:
        texts = self._settings_window_texts(selected_key)

        windows = WindowFactory(self.fonts.font_for(Language.JAPANESE))
        self.settings_window = windows.create(
            *SETTINGS_WINDOW_GRID,
            texts,
            opened=False,
        )
        self.settings_cursor = self.settings_window.set_cursor(
            tuple(
                CursorTarget(SETTINGS_CURSOR_X, y, key=key) for key, y in SETTINGS_ROWS
            )
        )
        self._select_cursor_key(self.settings_cursor, selected_key)
        self.settings_window.open()

    def _refresh_settings_window(self, selected_key: str) -> None:
        if self.settings_window is None:
            return
        self.settings_window.clear_texts()
        for placement in self._settings_window_texts(selected_key):
            self.settings_window.add_text(
                placement.text,
                placement.x,
                placement.y,
                color=placement.color,
                font=placement.font,
                shadow_color=placement.shadow_color,
                baseline_offset=placement.baseline_offset,
                font_spans=placement.font_spans,
            )

    def _start_settings(self) -> None:
        self.command_cursor.active = False
        self._build_settings_window()

    def _start_status(self) -> None:
        self.command_cursor.active = False
        self.status_screen = StatusScreenMock(
            party=self.party,
            settings=self.settings,
            texts=self.texts,
            fonts=self.fonts,
            faces=self.faces,
            member_index=self.selected_member_index,
        )

    def _finish_status(self) -> None:
        if self.status_screen is None:
            return
        status_settings = self.status_screen.settings
        self.selected_member_index = self.status_screen.member_index
        self.status_screen = None
        if status_settings != self.settings:
            self.settings = status_settings
            self._build_main_windows(selected_command="status")
        else:
            self.command_cursor.active = True

    def _finish_settings(self) -> None:
        self.settings_window = None
        self.settings_cursor = None
        self.command_cursor.active = True

    def _change_setting(self, distance: int) -> None:
        if distance not in (-1, 1) or self.settings_cursor is None:
            raise ValueError("settings distance must be -1 or 1")
        key = self.settings_cursor.selected_key
        if key == "language":
            index = LANGUAGE_SEQUENCE.index(self.settings.language)
            language = LANGUAGE_SEQUENCE[(index + 1) % len(LANGUAGE_SEQUENCE)]
            self.settings = self.settings.with_language(language)
            self._build_main_windows(
                selected_command="config",
                animate=False,
            )
            self.command_cursor.active = False
        elif key == "se":
            volume = (self.settings.se_volume + distance) % 5
            self.settings = self.settings.with_se_volume(volume)
            self._apply_se_volume()
            pyxel.play(ALERT_CHANNEL, SE_PREVIEW_SOUND_ID)
        elif key == "screen_size":
            scale = (self.settings.screen_scale - 1 + distance) % 5 + 1
            self.settings = self.settings.with_screen_scale(scale)
        elif key == "display":
            index = DISPLAY_SEQUENCE.index(self.settings.display_mode)
            mode = DISPLAY_SEQUENCE[(index + distance) % len(DISPLAY_SEQUENCE)]
            self.settings = self.settings.with_display_mode(mode)
            self._apply_display_mode()
        else:
            return
        self._refresh_settings_window(selected_key=key)

    def _apply_se_volume(self) -> None:
        if len(pyxel.channels) > ALERT_CHANNEL:
            pyxel.channels[ALERT_CHANNEL].gain = SE_VOLUME_GAINS[
                self.settings.se_volume
            ]

    def _apply_display_mode(self) -> None:
        pyxel.screen_mode(1 if self.settings.display_mode is DisplayMode.SMOOTH else 0)

    def _start_confirmation(self, action: str) -> None:
        if action not in ("return_title", "quit"):
            raise ValueError(f"unsupported settings action: {action}")
        if self.settings_cursor is None:
            return
        self.settings_cursor.active = False
        self.pending_settings_action = action
        windows = WindowFactory(self.fonts.font_for(Language.JAPANESE))
        confirmation_key = f"settings.confirm.{action}"
        confirmation_texts = tuple(
            self.localized_texts.create(
                line,
                4,
                2 + index * 3,
            )
            for index, line in enumerate(self.localized[confirmation_key].splitlines())
        )
        self.confirmation_window = windows.create(
            *CONFIRMATION_WINDOW_GRID,
            (
                *confirmation_texts,
                self.localized_texts.create(
                    self.localized["settings.yes"],
                    6,
                    CONFIRMATION_YES_Y,
                ),
                self.localized_texts.create(
                    self.localized["settings.no"],
                    6,
                    CONFIRMATION_NO_Y,
                ),
            ),
            opened=False,
        )
        self.confirmation_cursor = self.confirmation_window.set_cursor(
            (
                CursorTarget(
                    CONFIRMATION_CURSOR_X,
                    CONFIRMATION_YES_Y,
                    key="yes",
                ),
                CursorTarget(
                    CONFIRMATION_CURSOR_X,
                    CONFIRMATION_NO_Y,
                    key="no",
                ),
            )
        )
        self.confirmation_window.open()

    def _cancel_confirmation(self) -> None:
        self.confirmation_window = None
        self.confirmation_cursor = None
        self.pending_settings_action = None
        if self.settings_cursor is not None:
            self.settings_cursor.active = True

    def _restart_mock(self) -> None:
        os.environ[MENU_MOCK_SETTINGS_ENV] = json.dumps(
            self.settings.to_dict(),
            ensure_ascii=True,
        )
        os.environ.pop(pyxel.WINDOW_STATE_ENV, None)
        pyxel.reset()

    def _visible_windows(self) -> tuple[object, ...]:
        windows = list(getattr(self, "windows", ()))
        for attribute in ("settings_window", "confirmation_window"):
            window = getattr(self, attribute, None)
            if window is not None:
                windows.append(window)
        return tuple(windows)

    def _update_window_animations(self) -> bool:
        animating = tuple(
            window
            for window in self._visible_windows()
            if window.is_animating is True
        )
        for window in animating:
            window.update()
        return bool(animating)

    def update(self) -> None:
        self.alert.update()
        input_state = self.input_reader.poll()
        status_screen = getattr(self, "status_screen", None)
        if status_screen is not None:
            if status_screen.update(input_state):
                self._finish_status()
            return
        if self._update_window_animations():
            return

        if self.confirmation_cursor is not None:
            if input_state.cancel.triggered:
                self._cancel_confirmation()
                return
            if input_state.confirm.triggered:
                if self.confirmation_cursor.selected_key == "yes":
                    action = self.pending_settings_action
                    if action == "return_title":
                        self._restart_mock()
                    elif action == "quit":
                        pyxel.quit()
                    return
                self._cancel_confirmation()
                return
            self.confirmation_window.update(input_state.navigation)
            return

        if self.settings_cursor is not None:
            if input_state.cancel.triggered:
                self._finish_settings()
                return
            if input_state.navigation in (Direction.LEFT, Direction.RIGHT):
                self._change_setting(
                    -1 if input_state.navigation is Direction.LEFT else 1
                )
                return
            if input_state.confirm.triggered:
                key = self.settings_cursor.selected_key
                if key in ("return_title", "quit"):
                    self._start_confirmation(key)
                return
            if self.settings_window.update(input_state.navigation):
                self._refresh_settings_window(
                    selected_key=self.settings_cursor.selected_key
                )
            return

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
            selected_member_index = self.party_cursor.selected_key
            if isinstance(selected_member_index, int):
                self.selected_member_index = selected_member_index
            return

        if input_state.cancel.triggered:
            pyxel.quit()
            return
        if (
            input_state.confirm.triggered
            and self.command_cursor.selected_key == "status"
        ):
            self._start_status()
            return
        if input_state.confirm.triggered and self.command_cursor.selected_key == "sort":
            self._start_sort()
            return
        if (
            input_state.confirm.triggered
            and self.command_cursor.selected_key == "config"
        ):
            self._start_settings()
            return
        self.command_window.update(input_state.navigation)

    def draw(self) -> None:
        pyxel.cls(0)
        status_screen = getattr(self, "status_screen", None)
        if status_screen is not None:
            status_screen.draw()
            return
        pyxel.camera(self.alert.camera_x, 0)
        try:
            self.party_window.draw()
            if self.party_window.is_open:
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
            if self.settings_window is not None:
                self.settings_window.draw()
            if self.confirmation_window is not None:
                self.confirmation_window.draw()
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
            StatusMockDataError,
            TextCatalogError,
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
