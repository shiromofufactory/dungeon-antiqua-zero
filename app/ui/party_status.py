"""Shared compact party status panel for menu overlays."""

from __future__ import annotations

from collections.abc import Iterable

import pyxel

from localization import Localizer
from member import BATTLE_PARTY_MEMBER_COUNT, Member
from rendering import DIMMED_PALETTE, MONOCHROME_PALETTE, PaletteShifter
from resources import TRANSPARENT_INDEX
from text_catalog import TextCatalog
from ui import (
    CursorTarget,
    LocalizedWindowTextFactory,
    WindowCursor,
    WindowFactory,
    WindowText,
    pad,
)
from ui.tagged_text import ICON_BANK, ICON_COLKEY, ICON_SIZE, TEXT_ICONS

PARTY_WINDOW_GRID = (0, 44, 64, 16)
PARTY_COLUMN_WIDTH = 12
PARTY_FACE_X = 16
PARTY_FACE_Y = PARTY_WINDOW_GRID[1] * 4 + 4
PARTY_TEXT_X = 3
PARTY_HP_Y = 9
PARTY_MAX_HP_Y = 12
PARTY_CURSOR_Y = 1
PARTY_FACE_SIZE = 32
PARTY_AILMENT_ICON_X = PARTY_FACE_X + PARTY_FACE_SIZE
PARTY_AILMENT_ICON_Y = PARTY_FACE_Y


def draw_member_face_at(
    member: Member,
    *,
    x: int,
    y: int,
    faces: object,
    palette_shifter: PaletteShifter | None = None,
    dimmed: bool = False,
) -> None:
    """Draw one face and the same poison/paralysis markers in any panel."""

    position = member.face_position

    def draw_face() -> None:
        pyxel.blt(
            x, y, faces, position.x, position.y,
            PARTY_FACE_SIZE, PARTY_FACE_SIZE, TRANSPARENT_INDEX,
        )

    if member.is_dead and palette_shifter is not None:
        with palette_shifter.shifted(MONOCHROME_PALETTE):
            draw_face()
    elif dimmed and palette_shifter is not None:
        with palette_shifter.shifted(DIMMED_PALETTE):
            draw_face()
    else:
        draw_face()
    icon_x = x + PARTY_FACE_SIZE
    for active, tag in (
        (member.poisoned, "%POISON%"),
        (member.paralyzed, "%PARALIZE%"),
    ):
        if active:
            icon = TEXT_ICONS[tag]
            pyxel.blt(
                icon_x, y, ICON_BANK, icon.u, icon.v,
                ICON_SIZE, ICON_SIZE, ICON_COLKEY,
            )
            icon_x += ICON_SIZE


class PartyStatusPanel:
    """Own the window, faces, and optional target cursor shared by child menus."""

    def __init__(
        self,
        *,
        party: tuple[Member, ...],
        localizer: Localizer,
        texts: TextCatalog,
        text_factory: LocalizedWindowTextFactory,
        window_factory: WindowFactory,
        faces: object,
        palette_shifter: PaletteShifter | None = None,
        cursor_active: bool = False,
        show_mp: bool = False,
    ) -> None:
        if not party:
            raise ValueError("party must contain at least one member")
        if not isinstance(show_mp, bool):
            raise TypeError("show_mp must be a boolean")
        self.party = party[:BATTLE_PARTY_MEMBER_COUNT]
        self.faces = faces
        self.palette_shifter = palette_shifter
        self.show_mp = show_mp
        self.window = window_factory.create(
            *PARTY_WINDOW_GRID,
            self._party_texts(localizer, texts, text_factory),
        )
        self.cursor = WindowCursor(
            self.window,
            tuple(
                CursorTarget(
                    PARTY_TEXT_X + index * PARTY_COLUMN_WIDTH,
                    PARTY_CURSOR_Y,
                    key=index,
                )
                for index in range(len(self.party))
            ),
            active=cursor_active,
        )

    def _party_texts(
        self,
        localizer: Localizer,
        texts: TextCatalog,
        text_factory: LocalizedWindowTextFactory,
    ) -> tuple[WindowText, ...]:
        label_key = "menu.member.mp" if self.show_mp else "menu.member.hp"
        label = texts.text(label_key, localizer)
        if not label:
            raise ValueError(f"{label_key} must not be empty")
        placements: list[WindowText] = []
        for index, member in enumerate(self.party):
            x = PARTY_TEXT_X + index * PARTY_COLUMN_WIDTH
            placements.extend(
                (
                    text_factory.create(
                        f"{label}{pad(member.mp if self.show_mp else member.hp, 3)}",
                        x,
                        PARTY_HP_Y,
                    ),
                    text_factory.create(
                        f"／{pad(member.max_mp if self.show_mp else member.max_hp, 3)}",
                        x + 2,
                        PARTY_MAX_HP_Y,
                    ),
                )
            )
        return tuple(placements)

    def draw_faces(self, dimmed_member_indexes: Iterable[int] = ()) -> None:
        """Draw faces with death taking priority over optional dimming."""

        try:
            dimmed = frozenset(dimmed_member_indexes)
        except TypeError as error:
            raise TypeError("dimmed member indexes must be iterable") from error
        if any(
            isinstance(index, bool)
            or not isinstance(index, int)
            or not 0 <= index < len(self.party)
            for index in dimmed
        ):
            raise ValueError("dimmed member index is outside the party")

        for index, member in enumerate(self.party):
            draw_member_face_at(
                member,
                x=PARTY_FACE_X + index * PARTY_COLUMN_WIDTH * 4,
                y=PARTY_FACE_Y,
                faces=self.faces,
                palette_shifter=self.palette_shifter,
                dimmed=index in dimmed,
            )

__all__ = [
    "PARTY_COLUMN_WIDTH",
    "PARTY_CURSOR_Y",
    "PARTY_AILMENT_ICON_X",
    "PARTY_AILMENT_ICON_Y",
    "PARTY_FACE_SIZE",
    "PARTY_FACE_X",
    "PARTY_FACE_Y",
    "PARTY_HP_Y",
    "PARTY_MAX_HP_Y",
    "PARTY_TEXT_X",
    "PARTY_WINDOW_GRID",
    "PartyStatusPanel",
    "draw_member_face_at",
]
