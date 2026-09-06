"""Apply treasure rewards atomically against persistent game state."""

from __future__ import annotations

from enum import StrEnum
from typing import Iterable

if __package__ == "systems":
    from member import Member
    from resources.maps import MapActor
    from state import SaveData
else:
    from ..member import Member
    from ..resources.maps import MapActor
    from ..state import SaveData

from .inventory import InventorySystem
from .shop import MAX_GOLD


class TreasureOpenStatus(StrEnum):
    OPENED = "opened"
    CAPACITY_EXCEEDED = "capacity_exceeded"
    ALREADY_OPENED = "already_opened"


class TreasureSystem:
    """Coordinate treasure ownership rules without depending on Field or UI."""

    def __init__(
        self,
        *,
        save_data: SaveData,
        inventory: InventorySystem,
    ) -> None:
        if not isinstance(save_data, SaveData):
            raise TypeError("treasure system requires SaveData")
        if not isinstance(inventory, InventorySystem):
            raise TypeError("treasure system requires InventorySystem")
        self.save_data = save_data
        self.inventory = inventory

    def open(
        self,
        map_id: str,
        actor: MapActor,
        *,
        members: Iterable[Member] = (),
    ) -> TreasureOpenStatus:
        if not isinstance(map_id, str) or not map_id:
            raise ValueError("treasure map ID must be a non-empty string")
        if not isinstance(actor, MapActor) or actor.kind != "treasure":
            raise TypeError("treasure actor is required")
        contents = actor.contents
        if contents is None:
            raise ValueError("treasure contents are missing")
        treasure_key = (map_id, actor.id)
        if treasure_key in self.save_data.opened_treasures:
            return TreasureOpenStatus.ALREADY_OPENED

        if contents.type == "gold":
            if contents.amount is None:
                raise ValueError("gold treasure amount is missing")
            if self.save_data.gold > MAX_GOLD - contents.amount:
                return TreasureOpenStatus.CAPACITY_EXCEEDED
            self.save_data.gold += contents.amount
        elif contents.type == "item":
            if contents.item_key is None:
                raise ValueError("item treasure key is missing")
            if not self.inventory.add(
                contents.item_key,
                members=members,
            ):
                return TreasureOpenStatus.CAPACITY_EXCEEDED
        else:
            raise ValueError(f"unsupported treasure contents: {contents.type}")

        self.save_data.opened_treasures.add(treasure_key)
        return TreasureOpenStatus.OPENED


__all__ = ["TreasureOpenStatus", "TreasureSystem"]
