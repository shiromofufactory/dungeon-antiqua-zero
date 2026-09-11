"""Render the six-member battle result and its 30-frame growth animation."""

from __future__ import annotations

from types import MappingProxyType

import pyxel

from input import InputState
from localization import Localizer
from member import EquipmentSlot, Member, ProficiencyKind
from resources import FontResources, TRANSPARENT_INDEX
from state import Language, Settings
from systems.battle_progression import (
    BattleGrowthResult,
    MemberGrowthSnapshot,
    ProficiencySnapshot,
)

from .localized_text import LocalizedWindowTextFactory
from .text_format import pad
from .window import Window, WindowFactory, WindowText

RESULT_ANIMATION_FRAME_COUNT = 30
RESULT_WINDOW_COLUMNS = 2
RESULT_WINDOW_GRID_WIDTH = 32
RESULT_WINDOW_GRID_HEIGHT = 20
RESULT_CHARACTER_GRID_X = 2
RESULT_CHARACTER_GRID_Y = 2
RESULT_CHARACTER_SPRITE_WIDTH = 16
RESULT_CHARACTER_SPRITE_HEIGHT = 32
RESULT_TEXT_GRID_X = 8
RESULT_NAME_GRID_Y = 2
RESULT_HP_GRID_Y = 5
RESULT_MP_GRID_Y = 8
RESULT_WEAPON_GRID_Y = 13
RESULT_SPELL_GRID_Y = 16
MISSING_RESULT_SPRITE_CHARACTER_KEYS = frozenset(("Dain",))
WEAPON_HAND_ORDER = (EquipmentSlot.LEFT, EquipmentSlot.RIGHT)
SPELL_PROFICIENCY_ORDER = (
    ProficiencyKind.MYSTIC,
    ProficiencyKind.SACRED,
    ProficiencyKind.NETHER,
)


def result_window_grid(member_index: int) -> tuple[int, int, int, int]:
    if isinstance(member_index, bool) or not isinstance(member_index, int):
        raise TypeError("member_index must be an integer")
    if not 0 <= member_index < 6:
        raise ValueError("member_index must identify a result member")
    return (
        member_index % RESULT_WINDOW_COLUMNS * RESULT_WINDOW_GRID_WIDTH,
        member_index // RESULT_WINDOW_COLUMNS * RESULT_WINDOW_GRID_HEIGHT,
        RESULT_WINDOW_GRID_WIDTH,
        RESULT_WINDOW_GRID_HEIGHT,
    )


def member_battle_sprite_region(member: Member) -> tuple[int, int, int, int] | None:
    if member.definition.key in MISSING_RESULT_SPRITE_CHARACTER_KEYS:
        return None
    return (
        0,
        member.definition.battle_sprite * RESULT_CHARACTER_SPRITE_HEIGHT,
        RESULT_CHARACTER_SPRITE_WIDTH,
        RESULT_CHARACTER_SPRITE_HEIGHT,
    )


def _interpolate(start: int, end: int, frame: int) -> int:
    return start + (end - start) * frame // RESULT_ANIMATION_FRAME_COUNT


def _proficiency_display(total: int) -> str:
    level, progress = divmod(total, 100)
    return f"{pad(level, 1, fill='0')}－{pad(progress, 2, fill='0')}"


def _weapon_kind(member: Member, slot: EquipmentSlot) -> ProficiencyKind | None:
    weapon = member.equipment.weapon_at(slot)
    if weapon is None:
        return None
    try:
        return ProficiencyKind[weapon.subtype]
    except KeyError as error:
        raise ValueError(f"unsupported weapon proficiency: {weapon.subtype}") from error


class BattleResultOverlay:
    """Own result windows, interpolation state, and confirm-only completion."""

    def __init__(
        self,
        *,
        party: tuple[Member, ...],
        growth: BattleGrowthResult,
        settings: Settings,
        fonts: FontResources,
        character_sprites: object,
    ) -> None:
        if not party or len(party) > 6:
            raise ValueError("result party must contain from 1 to 6 members")
        if len(growth.before) != len(party) or len(growth.after) != len(party):
            raise ValueError("growth snapshots must match the result party")
        self.party = party
        self.growth = growth
        self.character_sprites = character_sprites
        self.frame = 0
        self.localizer = Localizer(settings.language)
        self.localized_texts = LocalizedWindowTextFactory.from_language(
            fonts,
            settings.language,
        )
        windows = WindowFactory(fonts.font_for(Language.JAPANESE))
        self.windows: tuple[Window, ...] = tuple(
            windows.create(*result_window_grid(index), ())
            for index in range(len(party))
        )
        self._refresh()

    @property
    def animation_complete(self) -> bool:
        return self.frame >= RESULT_ANIMATION_FRAME_COUNT

    def update(self, input_state: InputState) -> bool:
        """Advance numbers and return true on a new confirm after completion."""

        if not isinstance(input_state, InputState):
            raise TypeError("input_state must be an InputState")
        if not self.animation_complete:
            self.frame += 1
            self._refresh()
            return False
        return input_state.confirm.triggered

    def _snapshot(self, index: int) -> MemberGrowthSnapshot:
        before = self.growth.before[index]
        after = self.growth.after[index]
        proficiencies = {
            kind: _interpolated_proficiency(
                old,
                after.proficiencies[kind],
                self.frame,
            )
            for kind, old in before.proficiencies.items()
        }
        return MemberGrowthSnapshot(
            internal_level=_interpolate(
                before.internal_level, after.internal_level, self.frame
            ),
            hp=_interpolate(before.hp, after.hp, self.frame),
            max_hp=_interpolate(before.max_hp, after.max_hp, self.frame),
            mp=_interpolate(before.mp, after.mp, self.frame),
            max_mp=_interpolate(before.max_mp, after.max_mp, self.frame),
            proficiencies=MappingProxyType(proficiencies),
        )

    def _refresh(self) -> None:
        for index, (window, member) in enumerate(zip(self.windows, self.party)):
            before = self.growth.before[index]
            after = self.growth.after[index]
            current = self._snapshot(index)
            window.clear_texts()
            name = member.definition.localized_name(self.localizer)
            placement = self.localized_texts.create(
                name,
                RESULT_TEXT_GRID_X,
                RESULT_NAME_GRID_Y,
            )
            window.add_text(
                placement.text,
                placement.x,
                placement.y,
                font=placement.font,
                baseline_offset=placement.baseline_offset,
                font_spans=placement.font_spans,
            )
            hp_color = "%COL_POSITIVE%" if after.max_hp > before.max_hp else ""
            mp_color = "%COL_POSITIVE%" if after.max_mp > before.max_mp else ""
            window.add_text(
                f"{hp_color}ＨＰ　{pad(current.hp, 3)}／{pad(current.max_hp, 3)}",
                RESULT_TEXT_GRID_X,
                RESULT_HP_GRID_Y,
            )
            window.add_text(
                f"{mp_color}ＭＰ　{pad(current.mp, 3)}／{pad(current.max_mp, 3)}",
                RESULT_TEXT_GRID_X,
                RESULT_MP_GRID_Y,
            )
            weapon_text = self._proficiency_line(
                index,
                tuple(
                    kind
                    for slot in WEAPON_HAND_ORDER
                    if (kind := _weapon_kind(member, slot)) is not None
                ),
            )
            if weapon_text:
                window.add_text(
                    weapon_text,
                    RESULT_TEXT_GRID_X,
                    RESULT_WEAPON_GRID_Y,
                )
            spell_text = self._proficiency_line(
                index,
                tuple(
                    kind
                    for kind in SPELL_PROFICIENCY_ORDER
                    if member.proficiency(kind).max_level > 0
                ),
            )
            if spell_text:
                window.add_text(
                    spell_text,
                    RESULT_TEXT_GRID_X,
                    RESULT_SPELL_GRID_Y,
                )

    def _proficiency_line(
        self,
        member_index: int,
        kinds: tuple[ProficiencyKind, ...],
    ) -> str:
        before = self.growth.before[member_index]
        after = self.growth.after[member_index]
        current = self._snapshot(member_index)
        displays: list[str] = []
        for kind in kinds:
            old = before.proficiencies[kind]
            new = after.proficiencies[kind]
            color = "%COL_POSITIVE%" if new.level > old.level else ""
            end = "%COL_END%" if color else ""
            displays.append(
                f"{color}%{kind.name}%{_proficiency_display(current.proficiencies[kind].total)}{end}"
            )
        return "　".join(displays)

    def draw(self) -> None:
        pyxel.cls(0)
        for window in self.windows:
            window.draw()
        for index, member in enumerate(self.party):
            source = member_battle_sprite_region(member)
            if source is None:
                continue
            window_x, window_y, _width, _height = result_window_grid(index)
            pyxel.blt(
                (window_x + RESULT_CHARACTER_GRID_X) * 4,
                (window_y + RESULT_CHARACTER_GRID_Y) * 4,
                self.character_sprites,
                *source,
                TRANSPARENT_INDEX,
            )


def _interpolated_proficiency(
    old: ProficiencySnapshot,
    new: ProficiencySnapshot,
    frame: int,
) -> ProficiencySnapshot:
    total = _interpolate(old.total, new.total, frame)
    return ProficiencySnapshot(*divmod(total, 100))


__all__ = [
    "BattleResultOverlay",
    "MISSING_RESULT_SPRITE_CHARACTER_KEYS",
    "RESULT_ANIMATION_FRAME_COUNT",
    "RESULT_CHARACTER_GRID_X",
    "RESULT_CHARACTER_GRID_Y",
    "RESULT_CHARACTER_SPRITE_HEIGHT",
    "RESULT_CHARACTER_SPRITE_WIDTH",
    "RESULT_HP_GRID_Y",
    "RESULT_MP_GRID_Y",
    "RESULT_NAME_GRID_Y",
    "RESULT_SPELL_GRID_Y",
    "RESULT_TEXT_GRID_X",
    "RESULT_WEAPON_GRID_Y",
    "RESULT_WINDOW_COLUMNS",
    "RESULT_WINDOW_GRID_HEIGHT",
    "RESULT_WINDOW_GRID_WIDTH",
    "member_battle_sprite_region",
    "result_window_grid",
]
