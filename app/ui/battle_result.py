"""Render the six-member battle result and its 30-frame growth animation."""

from __future__ import annotations

from types import MappingProxyType

import pyxel

from input import InputState
from localization import Localizer
from member import EquipmentSlot, Member, ProficiencyKind
from resources import FontResources, TRANSPARENT_INDEX, play_se
from rendering.victory_pose import VICTORY_MOTION_LIMIT, victory_sprite_source_x
from spell import Spell
from state import Language, Settings
from text_catalog import TextCatalog
from systems.battle_progression import (
    BattleGrowthResult,
    MemberGrowthSnapshot,
    ProficiencySnapshot,
)

from .localized_text import LocalizedWindowTextFactory
from .spell_learned import SpellLearnedPopup, newly_learned_spells
from .text_format import pad
from .window import Window, WindowFactory, WindowText

RESULT_ANIMATION_FRAME_COUNT = 30
RESULT_WAIT_FRAME_COUNT = 12
RESULT_INCREMENT_SE_ID = "result_increment"
RESULT_WINDOW_COLUMNS = 2
RESULT_WINDOW_GRID_WIDTH = 32
RESULT_WINDOW_GRID_HEIGHT = 20
RESULT_CHARACTER_GRID_X = 2
RESULT_CHARACTER_GRID_Y = 2
RESULT_CHARACTER_SPRITE_WIDTH = 16
RESULT_CHARACTER_SPRITE_HEIGHT = 32
RESULT_AILMENT_SPRITE_SOURCE_X = 16 * 6
RESULT_DEAD_SPRITE_SOURCE_X = 16 * 9
RESULT_DEAD_SPRITE_WIDTH = 24
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


def member_battle_sprite_region(
    member: Member, *, victory_frame: int | None = None,
) -> tuple[int, int, int, int] | None:
    if member.definition.key in MISSING_RESULT_SPRITE_CHARACTER_KEYS:
        return None
    if member.is_dead:
        source_x = RESULT_DEAD_SPRITE_SOURCE_X
        width = RESULT_DEAD_SPRITE_WIDTH
    elif victory_frame is not None:
        source_x = victory_sprite_source_x(victory_frame)
        width = RESULT_CHARACTER_SPRITE_WIDTH
    elif member.paralyzed or member.poisoned:
        source_x = RESULT_AILMENT_SPRITE_SOURCE_X
        width = RESULT_CHARACTER_SPRITE_WIDTH
    else:
        source_x = 0
        width = RESULT_CHARACTER_SPRITE_WIDTH
    return (
        source_x,
        member.definition.battle_sprite * RESULT_CHARACTER_SPRITE_HEIGHT,
        width,
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
        spells: tuple[Spell, ...] = (),
        texts: TextCatalog | None = None,
    ) -> None:
        if not party or len(party) > 6:
            raise ValueError("result party must contain from 1 to 6 members")
        if len(growth.before) != len(party) or len(growth.after) != len(party):
            raise ValueError("growth snapshots must match the result party")
        self.party = party
        self.growth = growth
        self.character_sprites = character_sprites
        self.frame = 0
        self.wait_frame = 0
        self.victory_motion_frame = 0
        self.celebrating_members = tuple(
            new.internal_level > old.internal_level
            or new.max_hp > old.max_hp
            or new.max_mp > old.max_mp
            or any(
                new.proficiencies[kind].level > old.proficiencies[kind].level
                for kind in ProficiencyKind
            )
            for old, new in zip(growth.before, growth.after)
        )
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
        learned = tuple(
            (member, spell)
            for index, member in enumerate(party)
            for kind in SPELL_PROFICIENCY_ORDER
            for spell in newly_learned_spells(
                kind,
                growth.before[index].proficiencies[kind].level,
                growth.after[index].proficiencies[kind].level,
                spells,
            )
        )
        self.spell_learned_popup = (
            SpellLearnedPopup(learned, settings=settings, texts=texts, fonts=fonts)
            if learned and texts is not None
            else None
        )

    @property
    def animation_complete(self) -> bool:
        return self.frame >= RESULT_ANIMATION_FRAME_COUNT

    def update(self, input_state: InputState) -> bool:
        """Advance numbers and return true on a new confirm after completion."""

        if not isinstance(input_state, InputState):
            raise TypeError("input_state must be an InputState")
        if self.wait_frame < RESULT_WAIT_FRAME_COUNT:
            self.wait_frame += 1
            return False
        if not self.animation_complete:
            before = tuple(
                self._displayed_numbers(index) for index in range(len(self.party))
            )
            self.frame += 1
            self._refresh()
            after = tuple(
                self._displayed_numbers(index) for index in range(len(self.party))
            )
            if after != before:
                play_se(RESULT_INCREMENT_SE_ID)
            return False
        self.victory_motion_frame = min(
            self.victory_motion_frame + 1, VICTORY_MOTION_LIMIT
        )
        if self.spell_learned_popup is not None:
            if self.spell_learned_popup.update(input_state):
                self.spell_learned_popup = None
            return False
        return input_state.confirm.triggered

    def _displayed_numbers(self, index: int) -> tuple[int, ...]:
        snapshot = self._snapshot(index)
        member = self.party[index]
        proficiency_kinds = (
            *(
                kind
                for slot in WEAPON_HAND_ORDER
                if (kind := _weapon_kind(member, slot)) is not None
            ),
            *(
                kind
                for kind in SPELL_PROFICIENCY_ORDER
                if member.proficiency(kind).max_level > 0
            ),
        )
        return (
            snapshot.hp,
            snapshot.max_hp,
            snapshot.mp,
            snapshot.max_mp,
            *(snapshot.proficiencies[kind].total for kind in proficiency_kinds),
        )

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
            hp_max = pad(current.max_hp, 3)
            if current.max_hp > before.max_hp:
                hp_max = f"%COL_POSITIVE%{hp_max}%COL_END%"
            mp_max = pad(current.max_mp, 3)
            if current.max_mp > before.max_mp:
                mp_max = f"%COL_POSITIVE%{mp_max}%COL_END%"
            window.add_text(
                f"ＨＰ　{pad(current.hp, 3)}／{hp_max}",
                RESULT_TEXT_GRID_X,
                RESULT_HP_GRID_Y,
            )
            window.add_text(
                f"ＭＰ　{pad(current.mp, 3)}／{mp_max}",
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
            source = member_battle_sprite_region(
                member,
                victory_frame=(
                    self.victory_motion_frame
                    if self.animation_complete and self.celebrating_members[index]
                    else None
                ),
            )
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
        if self.animation_complete and self.spell_learned_popup is not None:
            self.spell_learned_popup.draw()


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
    "RESULT_AILMENT_SPRITE_SOURCE_X",
    "RESULT_ANIMATION_FRAME_COUNT",
    "RESULT_INCREMENT_SE_ID",
    "RESULT_CHARACTER_GRID_X",
    "RESULT_CHARACTER_GRID_Y",
    "RESULT_CHARACTER_SPRITE_HEIGHT",
    "RESULT_CHARACTER_SPRITE_WIDTH",
    "RESULT_DEAD_SPRITE_SOURCE_X",
    "RESULT_DEAD_SPRITE_WIDTH",
    "RESULT_HP_GRID_Y",
    "RESULT_MP_GRID_Y",
    "RESULT_NAME_GRID_Y",
    "RESULT_SPELL_GRID_Y",
    "RESULT_TEXT_GRID_X",
    "RESULT_WEAPON_GRID_Y",
    "RESULT_WAIT_FRAME_COUNT",
    "RESULT_WINDOW_COLUMNS",
    "RESULT_WINDOW_GRID_HEIGHT",
    "RESULT_WINDOW_GRID_WIDTH",
    "member_battle_sprite_region",
    "result_window_grid",
]
