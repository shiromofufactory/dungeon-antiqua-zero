"""Shared image-size constraints for enemy formations and battle placement."""

from collections.abc import Sequence
from dataclasses import dataclass


MONSTER_POSITIONS = ((4, 48), (4, 112), (68, 16), (68, 80), (68, 144))
MONSTER_SLOT_INDEXES = tuple(range(len(MONSTER_POSITIONS)))
MONSTER_AREA_RIGHT = 256
MONSTER_AREA_BOTTOM = 208
LARGE_MONSTER_Y_OFFSET = 16


@dataclass(frozen=True)
class MonsterPlacement:
    slot: int
    x: int
    y: int
    width: int
    height: int

    @property
    def bottom(self) -> int:
        return self.y + self.height


@dataclass(frozen=True)
class MonsterLayout:
    monster_indexes: tuple[int, ...]
    slot_indexes: tuple[int, ...]
    positions: tuple[tuple[int, int], ...]


def find_monster_placement(
    monster: object,
    occupied: Sequence[MonsterPlacement],
    slots: Sequence[int] = MONSTER_SLOT_INDEXES,
) -> MonsterPlacement | None:
    """Find room for one image while keeping occupied placements fixed."""

    width = getattr(monster, "width", 64)
    height = getattr(monster, "height", 64)
    y_offset = LARGE_MONSTER_Y_OFFSET if width > 64 or height > 64 else 0
    occupied_slots = {placement.slot for placement in occupied}
    for slot in slots:
        if slot in occupied_slots:
            continue
        x, y = MONSTER_POSITIONS[slot]
        y += y_offset
        if x + width > MONSTER_AREA_RIGHT:
            continue
        neighbors = sorted(
            (other for other in occupied if x < other.x + other.width and other.x < x + width),
            key=lambda other: other.y,
        )
        if slot >= 2:
            for other in neighbors:
                if 2 <= other.slot < slot or (
                    other.slot < 2 and y < other.bottom and other.y < y + height
                ):
                    y = max(y, other.bottom)
        if y + height <= MONSTER_AREA_BOTTOM and all(
            y >= other.bottom or y + height <= other.y for other in neighbors
        ):
            return MonsterPlacement(slot, x, y, width, height)
    return None


def monster_layout(monsters: Sequence[object]) -> MonsterLayout:
    """Place each enemy in input order, skipping images that cannot fit."""

    if any(
        getattr(monster, "width", 64) > 64 or getattr(monster, "height", 64) > 64
        for monster in monsters
    ):
        slots = (0, 2, 3, 4, 1)
    elif len(monsters) == 3:
        slots = (0, 2, 3, 1, 4)
    else:
        slots = MONSTER_SLOT_INDEXES

    monster_indexes = []
    placements: list[MonsterPlacement] = []
    for index, monster in enumerate(monsters):
        placement = find_monster_placement(monster, placements, slots)
        if placement is not None:
            monster_indexes.append(index)
            placements.append(placement)
    return MonsterLayout(
        tuple(monster_indexes),
        tuple(placement.slot for placement in placements),
        tuple((placement.x, placement.y) for placement in placements),
    )
