"""Compact six-member equipment preview used by the shop buy screen."""

from __future__ import annotations

from enum import StrEnum

import pyxel

from tools._bootstrap import APP_ROOT as _APP_ROOT  # Initialize app imports.
from item import Item, ItemEquipType
from member import EquipmentSlot, Member
from rendering import DIMMED_PALETTE, PaletteShifter
from resources import FontResources, TRANSPARENT_INDEX
from state import Language
from ui import DEFAULT_TEXT_COLOR, Window, WindowFactory


SHOP_PARTY_WINDOW_GRID = (0, 47, 64, 13)
SHOP_PARTY_MEMBER_COUNT = 6
SHOP_PARTY_FACE_SIZE = 32
SHOP_PARTY_FACE_FIRST_X = 7
SHOP_PARTY_COLUMN_WIDTH = 42
SHOP_PARTY_ICON_Y = SHOP_PARTY_WINDOW_GRID[1] * 4 + 6
SHOP_PARTY_FACE_Y = SHOP_PARTY_ICON_Y + 8
SHOP_PARTY_ICON_RIGHT_OFFSET = 24
SHOP_PARTY_E_RIGHT_OFFSET = 24
SHOP_PARTY_ICON_BANK = 0
SHOP_PARTY_ICON_SIZE = 8
SHOP_PARTY_UP_SOURCE = (192, 24)
SHOP_PARTY_DOWN_SOURCE = (200, 24)
SHOP_PARTY_ICON_COLKEY = 1


class ShopEquipmentMarker(StrEnum):
    EQUIPPED = "equipped"
    UP = "up"
    DOWN = "down"


class ShopPartyPanel:
    """Draw party faces and equipment comparison markers for buy mode."""

    def __init__(
        self,
        *,
        party: tuple[Member, ...],
        window_factory: WindowFactory,
        faces: object,
        fonts: FontResources,
        palette_shifter: PaletteShifter | None = None,
    ) -> None:
        if not party:
            raise ValueError("party must contain at least one member")
        self.party = party[:SHOP_PARTY_MEMBER_COUNT]
        self.faces = faces
        self.palette_shifter = palette_shifter
        self.japanese_font = fonts.font_for(Language.JAPANESE)
        self.window: Window = window_factory.create(*SHOP_PARTY_WINDOW_GRID, ())

    @staticmethod
    def marker_for(
        member: Member,
        item: Item | None,
    ) -> ShopEquipmentMarker | None:
        if item is None or not item.is_equipment:
            return None
        if any(
            equipped.key == item.key
            for equipped in member.equipment.equipped_items()
        ):
            return ShopEquipmentMarker.EQUIPPED
        if not member.can_equip(item):
            return None

        slot = {
            ItemEquipType.RIGHT: EquipmentSlot.RIGHT,
            ItemEquipType.TWO_HANDS: EquipmentSlot.RIGHT,
            ItemEquipType.LEFT: EquipmentSlot.LEFT,
            ItemEquipType.HEAD: EquipmentSlot.HEAD,
            ItemEquipType.BODY: EquipmentSlot.BODY,
            ItemEquipType.ARM: EquipmentSlot.ARM,
        }[item.equip_type]
        equipped = member.equipment.item_at(slot)
        if item.equip_type in (ItemEquipType.RIGHT, ItemEquipType.TWO_HANDS):
            current_value = 0 if equipped is None else equipped.attack
            new_value = item.attack
        elif item.equip_type is ItemEquipType.LEFT:
            current_value = 0 if equipped is None else equipped.evasion
            new_value = item.evasion
        else:
            current_value = 0 if equipped is None else equipped.defense
            new_value = item.defense

        if new_value > current_value:
            return ShopEquipmentMarker.UP
        if new_value < current_value:
            return ShopEquipmentMarker.DOWN
        return None

    def draw(self, item: Item | None) -> None:
        for index, member in enumerate(self.party):
            face_x = SHOP_PARTY_FACE_FIRST_X + index * SHOP_PARTY_COLUMN_WIDTH
            if (
                item is not None
                and item.is_equipment
                and not member.can_equip(item)
                and self.palette_shifter is not None
            ):
                with self.palette_shifter.shifted(DIMMED_PALETTE):
                    self._draw_face(member, face_x)
            else:
                self._draw_face(member, face_x)
            self._draw_marker(self.marker_for(member, item), face_x)

    def _draw_face(self, member: Member, face_x: int) -> None:
        source = member.face_position
        pyxel.blt(
            face_x,
            SHOP_PARTY_FACE_Y,
            self.faces,
            source.x,
            source.y,
            SHOP_PARTY_FACE_SIZE,
            SHOP_PARTY_FACE_SIZE,
            TRANSPARENT_INDEX,
        )

    def _draw_marker(
        self,
        marker: ShopEquipmentMarker | None,
        face_x: int,
    ) -> None:
        if marker is ShopEquipmentMarker.EQUIPPED:
            pyxel.text(
                face_x + SHOP_PARTY_E_RIGHT_OFFSET,
                SHOP_PARTY_ICON_Y - 3,
                "Ｅ",
                DEFAULT_TEXT_COLOR,
                self.japanese_font,
            )
            return
        source = {
            ShopEquipmentMarker.UP: SHOP_PARTY_UP_SOURCE,
            ShopEquipmentMarker.DOWN: SHOP_PARTY_DOWN_SOURCE,
        }.get(marker)
        if source is None:
            return
        pyxel.blt(
            face_x + SHOP_PARTY_ICON_RIGHT_OFFSET,
            SHOP_PARTY_ICON_Y,
            SHOP_PARTY_ICON_BANK,
            source[0],
            source[1],
            SHOP_PARTY_ICON_SIZE,
            SHOP_PARTY_ICON_SIZE,
            SHOP_PARTY_ICON_COLKEY,
        )


__all__ = [
    "SHOP_PARTY_DOWN_SOURCE",
    "SHOP_PARTY_FACE_FIRST_X",
    "SHOP_PARTY_FACE_SIZE",
    "SHOP_PARTY_FACE_Y",
    "SHOP_PARTY_ICON_Y",
    "SHOP_PARTY_MEMBER_COUNT",
    "SHOP_PARTY_UP_SOURCE",
    "SHOP_PARTY_WINDOW_GRID",
    "ShopEquipmentMarker",
    "ShopPartyPanel",
]
