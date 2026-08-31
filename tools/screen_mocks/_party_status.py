"""Shared compact party status panel for menu child-screen mocks."""

from __future__ import annotations

import pyxel

from tools._bootstrap import APP_ROOT as _APP_ROOT  # Initialize app imports.
from localization import Localizer
from member import Member
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

PARTY_WINDOW_GRID = (0, 44, 64, 16)
PARTY_COLUMN_WIDTH = 12
PARTY_FACE_X = 16
PARTY_FACE_Y = PARTY_WINDOW_GRID[1] * 4 + 4
PARTY_TEXT_X = 3
PARTY_HP_Y = 9
PARTY_MAX_HP_Y = 12
PARTY_CURSOR_Y = 1
PARTY_FACE_SIZE = 32


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
        cursor_active: bool = False,
    ) -> None:
        if not party:
            raise ValueError("party must contain at least one member")
        self.party = party
        self.faces = faces
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
                for index in range(len(party))
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

    def draw_faces(self) -> None:
        """Draw every member face above the HP fields."""

        for index, member in enumerate(self.party):
            face_position = member.face_position
            pyxel.blt(
                PARTY_FACE_X + index * PARTY_COLUMN_WIDTH * 4,
                PARTY_FACE_Y,
                self.faces,
                face_position.x,
                face_position.y,
                PARTY_FACE_SIZE,
                PARTY_FACE_SIZE,
                TRANSPARENT_INDEX,
            )


__all__ = [
    "PARTY_COLUMN_WIDTH",
    "PARTY_CURSOR_Y",
    "PARTY_FACE_SIZE",
    "PARTY_FACE_X",
    "PARTY_FACE_Y",
    "PARTY_HP_Y",
    "PARTY_MAX_HP_Y",
    "PARTY_TEXT_X",
    "PARTY_WINDOW_GRID",
    "PartyStatusPanel",
]
