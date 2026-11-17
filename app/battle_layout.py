"""Shared image-size constraints for enemy formations and battle placement."""

from collections.abc import Sequence
from dataclasses import dataclass


MONSTER_POSITIONS = ((4, 48), (4, 112), (68, 16), (68, 80), (68, 144))
TALL_MONSTER_SIZE = (64, 96)
TALL_MONSTER_SLOT_INDEXES = (0, 2, 3, 4)
MONSTER_AREA_BOTTOM = 208


def is_tall_monster(monster: object) -> bool:
    return (
        getattr(monster, "width", None), getattr(monster, "height", None)
    ) == TALL_MONSTER_SIZE


@dataclass(frozen=True)
class MonsterLayout:
    slot_indexes: tuple[int, ...]
    positions: tuple[tuple[int, int], ...]


def monster_layout(monsters: Sequence[object]) -> MonsterLayout:
    """Reserve one rear slot for tall enemies and stack the front by height."""

    tall_indexes = tuple(
        index for index, monster in enumerate(monsters) if is_tall_monster(monster)
    )
    if not tall_indexes:
        slots = (0, 2, 3) if len(monsters) == 3 else tuple(range(len(monsters)))
        if len(slots) > len(MONSTER_POSITIONS):
            raise ValueError("a battle supports at most 5 monsters")
        return MonsterLayout(slots, tuple(MONSTER_POSITIONS[slot] for slot in slots))
    if len(monsters) > len(TALL_MONSTER_SLOT_INDEXES):
        raise ValueError("a battle with a 64x96 monster supports at most 4 monsters")

    order = tall_indexes + tuple(
        index for index in range(len(monsters)) if index not in tall_indexes
    )
    slots = [0] * len(monsters)
    positions = [(4, 48)] * len(monsters)
    front_y = MONSTER_POSITIONS[2][1]
    for slot, index in zip(TALL_MONSTER_SLOT_INDEXES, order):
        slots[index] = slot
        if slot == 0:
            continue
        positions[index] = (68, front_y)
        front_y += getattr(monsters[index], "height", 64)
        if front_y > MONSTER_AREA_BOTTOM:
            raise ValueError("monster images exceed the available battle height")
    return MonsterLayout(tuple(slots), tuple(positions))
