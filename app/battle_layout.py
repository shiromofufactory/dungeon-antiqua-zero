"""Shared image-size constraints for enemy formations and battle placement."""

from collections.abc import Sequence
from dataclasses import dataclass


MONSTER_POSITIONS = ((4, 48), (4, 112), (68, 16), (68, 80), (68, 144))
MONSTER_SLOT_INDEXES = tuple(range(len(MONSTER_POSITIONS)))
MONSTER_AREA_RIGHT = 256
MONSTER_AREA_BOTTOM = 208
LARGE_MONSTER_Y_OFFSET = 16
LARGE_SQUARE_SIZE = (96, 96)
LARGE_SQUARE_SLOT = 0
LARGE_SQUARE_POSITION = (4, 32)
LARGE_SQUARE_COMPANION_SLOT = 3
LARGE_SQUARE_COMPANION_POSITION = (68, 128)


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

    def shares_space_with(self, other: "MonsterPlacement") -> bool:
        return self.slot == other.slot or (
            self.x < other.x + other.width and other.x < self.x + self.width
            and self.y < other.bottom and other.y < self.bottom
        )


@dataclass(frozen=True)
class MonsterLayout:
    monster_indexes: tuple[int, ...]
    slot_indexes: tuple[int, ...]
    positions: tuple[tuple[int, int], ...]


def _is_large_square(monster: object) -> bool:
    return (getattr(monster, "width", 64), getattr(monster, "height", 64)) == LARGE_SQUARE_SIZE


def _is_large_square_companion(placement: MonsterPlacement) -> bool:
    return (
        placement.slot == LARGE_SQUARE_COMPANION_SLOT
        and (placement.x, placement.y) == LARGE_SQUARE_COMPANION_POSITION
    )


def find_monster_placement(
    monster: object,
    occupied: Sequence[MonsterPlacement],
    slots: Sequence[int] = MONSTER_SLOT_INDEXES,
) -> MonsterPlacement | None:
    """Find room for one image while keeping occupied placements fixed."""

    width = getattr(monster, "width", 64)
    height = getattr(monster, "height", 64)
    y_offset = LARGE_MONSTER_Y_OFFSET if width > 64 or height > 64 else 0
    fixed_position = None
    if (width, height) == LARGE_SQUARE_SIZE:
        if LARGE_SQUARE_SLOT not in slots or any(
            not _is_large_square_companion(other) for other in occupied
        ):
            return None
        slots = (LARGE_SQUARE_SLOT,)
        fixed_position = LARGE_SQUARE_POSITION
    elif any(_is_large_square(other) for other in occupied):
        if LARGE_SQUARE_COMPANION_SLOT not in slots:
            return None
        slots = (LARGE_SQUARE_COMPANION_SLOT,)
        fixed_position = LARGE_SQUARE_COMPANION_POSITION

    occupied_slots = {placement.slot for placement in occupied}
    for slot in slots:
        if slot in occupied_slots:
            continue
        if fixed_position is None:
            x, y = MONSTER_POSITIONS[slot]
            y += y_offset
        else:
            x, y = fixed_position
        if x + width > MONSTER_AREA_RIGHT:
            continue
        neighbors = sorted(
            (other for other in occupied if x < other.x + other.width and other.x < x + width),
            key=lambda other: other.y,
        )
        if slot >= 2 and fixed_position is None:
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


def monster_revival_placement_available(
    placement: MonsterPlacement, occupied: Sequence[MonsterPlacement],
) -> bool:
    """Return whether a defeated monster can reappear at its original position."""

    if any(placement.shares_space_with(other) for other in occupied):
        return False
    if _is_large_square(placement):
        return all(_is_large_square_companion(other) for other in occupied)
    if any(_is_large_square(other) for other in occupied):
        return _is_large_square_companion(placement)
    return True


def monster_layout(monsters: Sequence[object]) -> MonsterLayout:
    """Reserve space for a 96px square enemy, then fit enemies in input order."""

    if any(
        getattr(monster, "width", 64) > 64 or getattr(monster, "height", 64) > 64
        for monster in monsters
    ):
        slots = (0, 2, 3, 4, 1)
    elif len(monsters) == 3:
        slots = (0, 2, 3, 1, 4)
    else:
        slots = MONSTER_SLOT_INDEXES

    # Reserve the square monster's space before fitting its companion.
    placement_order = sorted(
        range(len(monsters)), key=lambda index: not _is_large_square(monsters[index])
    )
    placements: dict[int, MonsterPlacement] = {}
    for index in placement_order:
        placement = find_monster_placement(monsters[index], tuple(placements.values()), slots)
        if placement is not None:
            placements[index] = placement
    monster_indexes = tuple(sorted(placements))
    return MonsterLayout(
        monster_indexes,
        tuple(placements[index].slot for index in monster_indexes),
        tuple((placements[index].x, placements[index].y) for index in monster_indexes),
    )
