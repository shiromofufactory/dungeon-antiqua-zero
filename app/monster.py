"""Monster identity vocabulary shared by combat data and equipment."""

from __future__ import annotations

from enum import StrEnum


class MonsterTribe(StrEnum):
    """Stable monster tribes used by race-effective attacks."""

    ANIMAL = "ANIMAL"
    UNDEAD = "UNDEAD"
    GOBLIN = "GOBLIN"
    HUMAN = "HUMAN"
    MAGE = "MAGE"
    GIANT = "GIANT"
    DRAGON = "DRAGON"
    ANIMATED = "ANIMATED"
    DEMON = "DEMON"
