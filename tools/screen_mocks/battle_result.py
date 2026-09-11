"""Display the standalone battle-victory result screen mock."""

from __future__ import annotations

from collections.abc import Mapping

import pyxel

from tools._bootstrap import APP_ROOT
from tools.screen_mocks._fixtures import (
    load_mock_character_records,
    load_mock_items,
    load_mock_skills,
)
from tools.screen_mocks._runner import run_screen_mock
from tools.screen_mocks._runtime import (
    create_mock_input_reader,
    initialize_screen_mock,
)

from game_data import GameDataError
from item import Item, ItemDataError
from localization import Localizer
from member import (
    EquipmentSlot,
    Member,
    MemberDataError,
    ProficiencyKind,
)
from resources import (
    TRANSPARENT_INDEX,
    DataResourceError,
    FontResourceError,
    FontResources,
    ImageResourceError,
    ImageResources,
)
from skill import Skill, SkillDataError
from state import Language
from ui import Window, WindowFactory, WindowText, pad
from ui.battle_result import (
    MISSING_RESULT_SPRITE_CHARACTER_KEYS,
    RESULT_CHARACTER_GRID_X,
    RESULT_CHARACTER_GRID_Y,
    RESULT_CHARACTER_SPRITE_HEIGHT,
    RESULT_CHARACTER_SPRITE_WIDTH,
    RESULT_HP_GRID_Y,
    RESULT_MP_GRID_Y,
    RESULT_NAME_GRID_Y,
    RESULT_SPELL_GRID_Y,
    RESULT_TEXT_GRID_X,
    RESULT_WEAPON_GRID_Y,
    RESULT_WINDOW_COLUMNS,
    RESULT_WINDOW_GRID_HEIGHT,
    RESULT_WINDOW_GRID_WIDTH,
    member_battle_sprite_region,
    result_window_grid,
)

CHARACTER_SPRITES_IMAGE_ID = "characters/ch_battle"
RESULT_PARTY_CHARACTER_KEYS = (
    "Fiora",
    "Cerion",
    "Alvan",
    "Elika",
    "Ragna",
    "Dain",
)
FIORA_INTERNAL_LEVEL = 50
WEAPON_HAND_ORDER = (EquipmentSlot.LEFT, EquipmentSlot.RIGHT)
SPELL_PROFICIENCY_ORDER = (
    ProficiencyKind.MYSTIC,
    ProficiencyKind.SACRED,
    ProficiencyKind.NETHER,
)


class BattleResultMockDataError(RuntimeError):
    """Raised when the result mock cannot resolve its configured party."""


def proficiency_display(member: Member, kind: ProficiencyKind) -> str:
    """Format a proficiency with the status screen's fullwidth number rules."""

    proficiency = member.proficiency(kind)
    level = pad(proficiency.level, 1, fill="0")
    progress = pad(proficiency.progress, 2, fill="0")
    return f"{level}－{progress}"


def _weapon_proficiency_kind(weapon: Item) -> ProficiencyKind:
    try:
        kind = ProficiencyKind[weapon.subtype]
    except KeyError as error:
        raise BattleResultMockDataError(
            f"武器の熟練度種別を解決できません: {weapon.key} ({weapon.subtype})"
        ) from error
    return kind


def weapon_proficiency_display(member: Member) -> str | None:
    """Format equipped left- then right-hand weapon proficiencies."""

    displays: list[str] = []
    for slot in WEAPON_HAND_ORDER:
        weapon = member.equipment.weapon_at(slot)
        if weapon is None:
            continue
        kind = _weapon_proficiency_kind(weapon)
        displays.append(f"%{kind.name}%{proficiency_display(member, kind)}")
    return "　".join(displays) or None


def spell_proficiency_display(member: Member) -> str | None:
    """Format every spell family available to one member."""

    displays = (
        f"%{kind.name}%{proficiency_display(member, kind)}"
        for kind in SPELL_PROFICIENCY_ORDER
        if member.proficiency(kind).max_level > 0
    )
    return "　".join(displays) or None


def member_result_texts(member: Member) -> tuple[WindowText, ...]:
    """Build the four requested rows for one result member."""

    texts = [
        WindowText(
            member.definition.localized_name(Localizer(Language.JAPANESE)),
            RESULT_TEXT_GRID_X,
            RESULT_NAME_GRID_Y,
        ),
        WindowText(
            f"ＨＰ　{pad(member.hp, 3)}／{pad(member.max_hp, 3)}",
            RESULT_TEXT_GRID_X,
            RESULT_HP_GRID_Y,
        ),
        WindowText(
            f"ＭＰ　{pad(member.mp, 3)}／{pad(member.max_mp, 3)}",
            RESULT_TEXT_GRID_X,
            RESULT_MP_GRID_Y,
        ),
    ]
    weapon_display = weapon_proficiency_display(member)
    if weapon_display is not None:
        texts.append(
            WindowText(
                weapon_display,
                RESULT_TEXT_GRID_X,
                RESULT_WEAPON_GRID_Y,
            )
        )
    spell_display = spell_proficiency_display(member)
    if spell_display is not None:
        texts.append(
            WindowText(
                spell_display,
                RESULT_TEXT_GRID_X,
                RESULT_SPELL_GRID_Y,
            )
        )
    return tuple(texts)


def build_result_party(
    character_records: tuple[dict[str, object], ...],
    items: Mapping[str, Item],
    skills: Mapping[str, Skill],
) -> tuple[Member, ...]:
    """Build the six members with Fiora at level 50 and normal level offsets."""

    records_by_key = {
        key: record
        for record in character_records
        if isinstance(key := record.get("name_en"), str)
    }
    party: list[Member] = []
    for character_key in RESULT_PARTY_CHARACTER_KEYS:
        try:
            record = records_by_key[character_key]
        except KeyError as error:
            raise BattleResultMockDataError(
                f"キャラクターが見つかりません: {character_key}"
            ) from error
        if character_key == "Fiora":
            member = Member.from_record_at_internal_level(
                record,
                FIORA_INTERNAL_LEVEL,
                items=items,
                skills=skills,
            )
        else:
            member = Member.from_record(
                record,
                items=items,
                skills=skills,
                fiora_internal_level=FIORA_INTERNAL_LEVEL,
            )
        party.append(member)
    return tuple(party)


class BattleResultMock:
    """Composition root for the static battle-victory result mock."""

    def __init__(self) -> None:
        initialize_screen_mock("Dungeon Antiqua ZERO Battle Result Mock")
        self.input_reader = create_mock_input_reader()
        fonts = FontResources()
        windows = WindowFactory(fonts.font_for(Language.JAPANESE))
        self.character_sprites = ImageResources(APP_ROOT / "images").image(
            CHARACTER_SPRITES_IMAGE_ID
        )
        self.party = build_result_party(
            load_mock_character_records(),
            load_mock_items(),
            load_mock_skills(),
        )
        self.windows: tuple[Window, ...] = tuple(
            windows.create(
                *result_window_grid(member_index),
                member_result_texts(member),
            )
            for member_index, member in enumerate(self.party)
        )
        pyxel.run(self.update, self.draw)

    def update(self) -> None:
        """Allow Q or Escape to close the otherwise static mock."""

        if self.input_reader.poll().cancel.triggered:
            pyxel.quit()

    def draw(self) -> None:
        pyxel.cls(0)
        for window in self.windows:
            window.draw()
        for member_index, member in enumerate(self.party):
            window_x, window_y, _width, _height = result_window_grid(member_index)
            source = member_battle_sprite_region(member)
            if source is None:
                continue
            pyxel.blt(
                (window_x + RESULT_CHARACTER_GRID_X) * 4,
                (window_y + RESULT_CHARACTER_GRID_Y) * 4,
                self.character_sprites,
                *source,
                TRANSPARENT_INDEX,
            )


def main() -> int:
    return run_screen_mock(
        BattleResultMock,
        expected_errors=(
            BattleResultMockDataError,
            DataResourceError,
            FontResourceError,
            GameDataError,
            ImageResourceError,
            ItemDataError,
            MemberDataError,
            SkillDataError,
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "BattleResultMock",
    "BattleResultMockDataError",
    "CHARACTER_SPRITES_IMAGE_ID",
    "FIORA_INTERNAL_LEVEL",
    "MISSING_RESULT_SPRITE_CHARACTER_KEYS",
    "RESULT_CHARACTER_GRID_X",
    "RESULT_CHARACTER_GRID_Y",
    "RESULT_CHARACTER_SPRITE_HEIGHT",
    "RESULT_CHARACTER_SPRITE_WIDTH",
    "RESULT_HP_GRID_Y",
    "RESULT_MP_GRID_Y",
    "RESULT_NAME_GRID_Y",
    "RESULT_PARTY_CHARACTER_KEYS",
    "RESULT_SPELL_GRID_Y",
    "RESULT_TEXT_GRID_X",
    "RESULT_WEAPON_GRID_Y",
    "RESULT_WINDOW_COLUMNS",
    "RESULT_WINDOW_GRID_HEIGHT",
    "RESULT_WINDOW_GRID_WIDTH",
    "build_result_party",
    "member_battle_sprite_region",
    "member_result_texts",
    "proficiency_display",
    "result_window_grid",
    "spell_proficiency_display",
    "weapon_proficiency_display",
]
