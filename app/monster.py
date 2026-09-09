"""Monster identity and mutable battle state independent of presentation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class MonsterDataError(ValueError):
    """Raised when monster master data cannot initialize battle state."""


class MonsterFormationTarget(Protocol):
    """Mutable formation state required when an enemy front row collapses."""

    is_front_row: bool

    @property
    def is_alive(self) -> bool: ...


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


@dataclass(frozen=True)
class MonsterCombatStats:
    """Immutable physical-combat values read from monster master data."""

    attack: int
    hit: int
    defense: int
    evasion: int

    @classmethod
    def from_record(cls, record: Mapping[str, object]) -> MonsterCombatStats:
        """Read the four required non-negative combat values from one record."""

        if not isinstance(record, Mapping):
            raise MonsterDataError("monster must be an object")
        values: dict[str, int] = {}
        for field_name in ("attack", "hit", "defense", "evasion"):
            value = record.get(field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise MonsterDataError(
                    f"monster.{field_name} must be a non-negative integer"
                )
            values[field_name] = value
        return cls(**values)


@dataclass
class MonsterBattleState:
    """Per-battle HP copied from one monster's immutable master data."""

    max_hp: int
    hp: int | None = None

    def __post_init__(self) -> None:
        if isinstance(self.max_hp, bool) or not isinstance(self.max_hp, int):
            raise TypeError("max_hp must be an integer")
        if self.max_hp <= 0:
            raise ValueError("max_hp must be positive")
        if self.hp is None:
            self.hp = self.max_hp
        if isinstance(self.hp, bool) or not isinstance(self.hp, int):
            raise TypeError("hp must be an integer")
        if not 0 <= self.hp <= self.max_hp:
            raise ValueError("hp must be from 0 to max_hp")

    @classmethod
    def from_record(cls, record: Mapping[str, object]) -> MonsterBattleState:
        """Create full HP state from the record's ``mhp`` value."""

        if not isinstance(record, Mapping):
            raise MonsterDataError("monster must be an object")
        max_hp = record.get("mhp")
        if isinstance(max_hp, bool) or not isinstance(max_hp, int) or max_hp <= 0:
            raise MonsterDataError("monster.mhp must be a positive integer")
        return cls(max_hp=max_hp)

    @property
    def is_alive(self) -> bool:
        """Return whether the monster can remain in battle."""

        assert self.hp is not None
        return self.hp > 0

    def take_damage(self, damage: int) -> int:
        """Apply non-negative damage and return the actual HP reduction."""

        if isinstance(damage, bool) or not isinstance(damage, int):
            raise TypeError("damage must be an integer")
        if damage < 0:
            raise ValueError("damage must not be negative")
        previous = self.hp
        assert previous is not None
        self.hp = max(0, previous - damage)
        return previous - self.hp

    def defeat(self) -> None:
        """Set HP to zero for a mock attack that always defeats its target."""

        self.hp = 0

    def restore(self) -> None:
        """Restore initial HP when restarting a battle fixture."""

        self.hp = self.max_hp


def promote_rear_monsters_if_front_empty(
    monsters: Sequence[MonsterFormationTarget],
) -> bool:
    """Promote every living rear monster when no living front monster remains."""

    living = tuple(monster for monster in monsters if monster.is_alive)
    if not living or any(monster.is_front_row for monster in living):
        return False
    for monster in living:
        monster.is_front_row = True
    return True


__all__ = [
    "MonsterBattleState",
    "MonsterCombatStats",
    "MonsterDataError",
    "MonsterFormationTarget",
    "MonsterTribe",
    "promote_rear_monsters_if_front_empty",
]
