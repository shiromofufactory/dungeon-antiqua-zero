"""Display the current battle-screen layout mock."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TypeVar

import pyxel

from tools._bootstrap import APP_ROOT
from tools.screen_mocks._fixtures import (
    MOCK_PARTY_CHARACTER_KEYS,
    load_mock_character_records,
    load_mock_items,
    load_mock_party,
    load_mock_skills,
)
from tools.screen_mocks._runner import run_screen_mock
from tools.screen_mocks._runtime import (
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    create_mock_input_reader,
    initialize_screen_mock,
)
from localization import Localizer, ascii_to_fullwidth
from member import (
    BATTLE_PARTY_MEMBER_COUNT,
    MAX_INTERNAL_LEVEL,
    FormationRow,
    Member,
)
from resources import (
    TRANSPARENT_INDEX,
    FontResourceError,
    FontResources,
    ImageResourceError,
    ImageResources,
    load_record_array,
)
from state import Language, Settings
from ui import CursorTarget, WindowFactory, WindowText

BACKGROUND_IMAGE_ID = "background/bg_nector"
CH_BATTLE_IMAGE_ID = "characters/ch_battle"
BATTLE_MOCK_PARTY_CHARACTER_KEYS = MOCK_PARTY_CHARACTER_KEYS[:BATTLE_PARTY_MEMBER_COUNT]
BATTLE_MOCK_MONSTER_KEYS = (
    "Giant Spider",
    "Giant Spider",
    "Coyote",
    "Coyote",
    "Coyote",
)
PARTY_SPRITE_Y = (64, 92, 120, 148, 176)
MONSTER_POSITIONS = ((4, 56), (4, 120), (68, 24), (68, 88), (68, 152))
TIMELINE_ENTRY_KEYS = (
    ("character", "Fiora"),
    ("monster", "Coyote"),
    ("monster", "Giant Spider"),
    ("monster", "Coyote"),
    ("character", "Elika"),
    ("monster", "Coyote"),
)
TIMELINE_COLORS = (13, 49, 49, 49, 13, 49)
RecordValue = TypeVar("RecordValue")


class BattleMockDataError(ValueError):
    """Raised when generated battle display data cannot form the mock."""


def _required_text(record: Mapping[str, object], field: str, label: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value:
        raise BattleMockDataError(f"{label}.{field} must be a non-empty string")
    return value


def _required_nonnegative_integer(
    record: Mapping[str, object],
    field: str,
    label: str,
) -> int:
    value = record.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise BattleMockDataError(f"{label}.{field} must be a non-negative integer")
    return value


def _required_positive_integer(
    record: Mapping[str, object],
    field: str,
    label: str,
) -> int:
    value = record.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise BattleMockDataError(f"{label}.{field} must be a positive integer")
    return value


@dataclass(frozen=True)
class BattleMockCharacter:
    """One member plus the immutable display values for the battle mock."""

    member: Member
    icon_x: int
    icon_y: int
    battle_sprite: int

    @classmethod
    def from_record(
        cls,
        member: Member,
        record: Mapping[str, object],
    ) -> BattleMockCharacter:
        key = member.definition.key
        return cls(
            member=member,
            icon_x=_required_nonnegative_integer(record, "icon_x", key),
            icon_y=_required_nonnegative_integer(record, "icon_y", key),
            battle_sprite=_required_nonnegative_integer(
                record,
                "battle_sprite",
                key,
            ),
        )

    def display_name(self, localizer: Localizer) -> str:
        return self.member.definition.localized_name(localizer)


@dataclass(frozen=True)
class BattleMockMonster:
    """Immutable monster display data resolved from one generated record."""

    key: str
    names: Mapping[str, object]
    image_id: str
    width: int
    height: int
    icon_x: int
    icon_y: int

    @classmethod
    def from_record(cls, record: Mapping[str, object]) -> BattleMockMonster:
        key = _required_text(record, "name_en", "monster")
        image_id = record.get("image_id")
        if isinstance(image_id, bool) or not isinstance(image_id, (str, int)):
            raise BattleMockDataError(f"{key}.image_id must be a string or integer")
        image_id_text = str(image_id)
        if not image_id_text:
            raise BattleMockDataError(f"{key}.image_id must not be empty")
        return cls(
            key=key,
            names=record,
            image_id=image_id_text,
            width=_required_positive_integer(record, "width", key),
            height=_required_positive_integer(record, "height", key),
            icon_x=_required_nonnegative_integer(record, "icon_x", key),
            icon_y=_required_nonnegative_integer(record, "icon_y", key),
        )

    @property
    def image_resource_id(self) -> str:
        return f"monsters/{self.image_id}"

    def display_name(self, localizer: Localizer) -> str:
        return localizer.text(self.names, "name")


def _records_by_key(
    records: tuple[dict[str, object], ...] | list[dict[str, object]],
    *,
    label: str,
) -> dict[str, Mapping[str, object]]:
    records_by_key: dict[str, Mapping[str, object]] = {}
    for record in records:
        key = _required_text(record, "name_en", label)
        if key in records_by_key:
            raise BattleMockDataError(f"{label} key is duplicated: {key}")
        records_by_key[key] = record
    return records_by_key


def _record_for_key(
    records_by_key: Mapping[str, RecordValue],
    key: str,
    *,
    label: str,
) -> RecordValue:
    try:
        return records_by_key[key]
    except KeyError as error:
        raise BattleMockDataError(f"{label} is missing: {key}") from error


class BattleScreenMock:
    def __init__(self) -> None:
        initialize_screen_mock("Dungeon Antiqua ZERO Battle Screen Mock")
        self.input_reader = create_mock_input_reader()

        resources = ImageResources()
        background_entry = resources.entry(BACKGROUND_IMAGE_ID)
        if (
            background_entry.width != SCREEN_WIDTH
            or background_entry.height != SCREEN_HEIGHT
        ):
            raise ImageResourceError(
                f"背景画像のサイズが画面と一致しません: {BACKGROUND_IMAGE_ID} "
                f"{background_entry.width}x{background_entry.height} / "
                f"{SCREEN_WIDTH}x{SCREEN_HEIGHT}"
            )
        self.background = resources.image(BACKGROUND_IMAGE_ID)
        self.character_sprites = resources.image(CH_BATTLE_IMAGE_ID)
        settings = Settings()
        self.localizer = Localizer(settings.language)
        items = load_mock_items()
        character_records = _records_by_key(
            load_mock_character_records(),
            label="character",
        )
        self.party = load_mock_party(
            items,
            load_mock_skills(),
            character_keys=BATTLE_MOCK_PARTY_CHARACTER_KEYS,
            internal_level=MAX_INTERNAL_LEVEL,
        )
        self.party_visuals = tuple(
            BattleMockCharacter.from_record(
                member,
                _record_for_key(
                    character_records,
                    member.definition.key,
                    label="character",
                ),
            )
            for member in self.party
        )
        monsters_by_key = _records_by_key(
            load_record_array("monsters.json", APP_ROOT / "data"),
            label="monster",
        )
        self.monsters = tuple(
            BattleMockMonster.from_record(
                _record_for_key(monsters_by_key, key, label="monster")
            )
            for key in BATTLE_MOCK_MONSTER_KEYS
        )
        self.monster_images = {
            monster.key: resources.image(monster.image_resource_id)
            for monster in self.monsters
        }
        party_by_key = {
            visual.member.definition.key: visual for visual in self.party_visuals
        }
        monster_by_key = {monster.key: monster for monster in self.monsters}
        self.timeline = tuple(
            _record_for_key(
                party_by_key if kind == "character" else monster_by_key,
                key,
                label=kind,
            )
            for kind, key in TIMELINE_ENTRY_KEYS
        )
        fonts = FontResources()
        windows = WindowFactory(fonts.font_for(settings.language))
        font_6x8 = fonts.font_for(Language.ENGLISH)
        command_window = windows.create(
            34,
            0,
            30,
            13,
            (
                WindowText("たたかう", 4, 2),
                WindowText("ぼうぎょ", 4, 5),
                WindowText("じゅもん", 4, 8),
                WindowText("にげる", 18, 2),
                WindowText("アイテム", 18, 5),
                WindowText("こうたい", 18, 8),
            ),
            thin_frame=True,
            opened=False,
        )
        self.command_window = command_window
        self.command_cursor = command_window.set_cursor(
            (
                CursorTarget(2, 2, key="attack"),
                CursorTarget(2, 5, key="defend"),
                CursorTarget(2, 8, key="spell"),
                CursorTarget(16, 2, key="escape"),
                CursorTarget(16, 5, key="item"),
                CursorTarget(16, 8, key="formation"),
            )
        )
        self.selected_command: str | None = None
        self.windows = [command_window]

        for i, visual in enumerate(self.party_visuals):
            window = windows.create(52, 16 + i * 7, 7, 5, transparent=True)
            # 現在アクティブなキャラクターは白文字、それ以外は灰色
            c = 5 if i == 0 else 4
            member = visual.member
            window.add_text(visual.display_name(self.localizer), 0, 0, color=c)
            window.add_text(
                ascii_to_fullwidth(f"{member.hp:03d}/{member.max_hp:03d}"),
                0,
                4,
                font=font_6x8,
                color=c,
            )
            self.windows.append(window)

        for monster, (x, y) in zip(self.monsters, MONSTER_POSITIONS):
            window = windows.create(x // 4 + 2, y // 4 + 13, 20, 4, transparent=True)
            window.add_text(monster.display_name(self.localizer), 0, 0, color=4)
            self.windows.append(window)

        pyxel.run(self.update, self.draw)

    def update(self) -> None:
        input_state = self.input_reader.poll()
        if input_state.cancel.triggered:
            pyxel.quit()
            return

        if input_state.confirm.triggered:
            if self.command_window.is_closed:
                self.command_window.open()
            elif self.command_window.is_open:
                self.selected_command = self.command_cursor.selected_key
                self.command_window.close()

        self.command_window.update(input_state.navigation)

    def draw(self) -> None:
        """Draw the battle screen in explicit back-to-front order."""

        self._draw_background()
        self._draw_party()
        self._draw_monsters()
        self._draw_timeline()
        self._draw_windows()

    def _draw_background(self) -> None:
        pyxel.blt(
            0,
            0,
            self.background,
            0,
            0,
            SCREEN_WIDTH,
            SCREEN_HEIGHT,
        )

    def _draw_party(self) -> None:
        for index, (visual, y) in enumerate(zip(self.party_visuals, PARTY_SPRITE_Y)):
            member = visual.member
            x = 156 + index * 4
            if member.formation_row is FormationRow.BACK:
                x += 16
            pyxel.blt(
                x,
                y,
                self.character_sprites,
                0,
                visual.battle_sprite * 32,
                16,
                32,
                TRANSPARENT_INDEX,
            )

    def _draw_monsters(self) -> None:
        for monster, (x, y) in zip(self.monsters, MONSTER_POSITIONS):
            pyxel.blt(
                x,
                y,
                self.monster_images[monster.key],
                0,
                0,
                monster.width,
                monster.height,
                TRANSPARENT_INDEX,
            )

    def _draw_timeline(self) -> None:
        base_x, base_y = 70, 220
        for i, (entry, color) in enumerate(zip(self.timeline, TIMELINE_COLORS)):
            pyxel.blt(
                base_x + i * 20,
                base_y,
                1,
                entry.icon_x,
                entry.icon_y,
                16,
                16,
                TRANSPARENT_INDEX,
            )
            pyxel.rect(base_x + i * 20, base_y + 17, 16, 1, color)
            pyxel.rect(base_x + i * 20, base_y + 18, 16, 1, color - 1)
        pyxel.blt(
            base_x + 4,
            base_y - 4,
            0,
            88,
            16,
            8,
            8,
            TRANSPARENT_INDEX,
        )

    def _draw_windows(self) -> None:
        for window in self.windows:
            window.draw()


def main() -> int:
    return run_screen_mock(
        BattleScreenMock,
        expected_errors=(FontResourceError, ImageResourceError),
    )


if __name__ == "__main__":
    raise SystemExit(main())
