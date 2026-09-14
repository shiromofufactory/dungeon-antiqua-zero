"""Shared compact party status panel for menu overlays."""

from __future__ import annotations

from collections.abc import Iterable

import pyxel

from localization import Localizer
from member import BATTLE_PARTY_MEMBER_COUNT, Member
from rendering import DIMMED_PALETTE, PaletteShifter
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
    ) -> None:
        if not party:
            raise ValueError("party must contain at least one member")
        self.party = party[:BATTLE_PARTY_MEMBER_COUNT]
        self.faces = faces
        self.palette_shifter = palette_shifter
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
        hp_label = texts.text("menu.member.hp", localizer)
        if not hp_label:
            raise ValueError("menu.member.hp must not be empty")
        placements: list[WindowText] = []
        for index, member in enumerate(self.party):
            x = PARTY_TEXT_X + index * PARTY_COLUMN_WIDTH
            placements.extend(
                (
                    text_factory.create(
                        f"{hp_label}{pad(member.hp, 3)}",
                        x,
                        PARTY_HP_Y,
                    ),
                    text_factory.create(
                        f"／{pad(member.max_hp, 3)}",
                        x + 2,
                        PARTY_MAX_HP_Y,
                    ),
                )
            )
        return tuple(placements)

    def draw_faces(self, dimmed_member_indexes: Iterable[int] = ()) -> None:
        """Draw faces, optionally dimming selected members by palette shift."""

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
            face_position = member.face_position
            if index in dimmed and self.palette_shifter is not None:
                with self.palette_shifter.shifted(DIMMED_PALETTE):
                    self._draw_face(index, face_position.x, face_position.y)
            else:
                self._draw_face(index, face_position.x, face_position.y)
            self._draw_ailment_icons(index, member)

    def _draw_face(self, index: int, source_x: int, source_y: int) -> None:
        pyxel.blt(
            PARTY_FACE_X + index * PARTY_COLUMN_WIDTH * 4,
            PARTY_FACE_Y,
            self.faces,
            source_x,
            source_y,
            PARTY_FACE_SIZE,
            PARTY_FACE_SIZE,
            TRANSPARENT_INDEX,
        )

    def _draw_ailment_icons(self, index: int, member: Member) -> None:
        x = PARTY_AILMENT_ICON_X + index * PARTY_COLUMN_WIDTH * 4
        for active, tag in (
            (member.poisoned, "%POISON%"),
            (member.paralyzed, "%PARALIZE%"),
        ):
            if not active:
                continue
            icon = TEXT_ICONS[tag]
            pyxel.blt(
                x,
                PARTY_AILMENT_ICON_Y,
                ICON_BANK,
                icon.u,
                icon.v,
                ICON_SIZE,
                ICON_SIZE,
                ICON_COLKEY,
            )
            x += ICON_SIZE


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
]
