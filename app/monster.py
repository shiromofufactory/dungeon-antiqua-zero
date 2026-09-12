"""Monster identity and mutable battle state independent of presentation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

if __package__ == "":
    from battle_speed import (
        MAX_SPEED_MODIFIER,
        MIN_SPEED_MODIFIER,
    )
else:
    from .battle_speed import (
        MAX_SPEED_MODIFIER,
        MIN_SPEED_MODIFIER,
    )


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
    """Immutable physical and spell-defense values from monster master data."""

    attack: int
    hit: int
    defense: int
    evasion: int
    spell_resistance: int = 0

    @classmethod
    def from_record(cls, record: Mapping[str, object]) -> MonsterCombatStats:
        """Read the required non-negative combat values from one record."""

        if not isinstance(record, Mapping):
            raise MonsterDataError("monster must be an object")
        values: dict[str, int] = {}
        for field_name in (
            "attack",
            "hit",
            "defense",
            "evasion",
            "resistance",
        ):
            value = record.get(field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise MonsterDataError(
                    f"monster.{field_name} must be a non-negative integer"
                )
            values[
                "spell_resistance" if field_name == "resistance" else field_name
            ] = value
        if values["spell_resistance"] > 100:
            raise MonsterDataError("monster.resistance must not exceed 100")
        return cls(**values)


@dataclass
class MonsterBattleState:
    """Per-battle HP copied from one monster's immutable master data."""

    max_hp: int
    hp: int | None = None
    poisoned: bool = False
    sleeping: int = 0
    speed_modifier: int = 0

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
        if not isinstance(self.poisoned, bool):
            raise TypeError("poisoned must be a boolean")
        if isinstance(self.sleeping, bool) or not isinstance(self.sleeping, int):
            raise TypeError("sleeping must be an integer")
        if self.sleeping < 0:
            raise ValueError("sleeping must not be negative")
        if (
            isinstance(self.speed_modifier, bool)
            or not isinstance(self.speed_modifier, int)
        ):
            raise TypeError("speed_modifier must be an integer")
        if not MIN_SPEED_MODIFIER <= self.speed_modifier <= MAX_SPEED_MODIFIER:
            raise ValueError(
                f"speed_modifier must be from {MIN_SPEED_MODIFIER} "
                f"to {MAX_SPEED_MODIFIER}"
            )

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
        if damage > 0:
            self.sleeping = 0
        if self.hp <= 0:
            self.speed_modifier = 0
        return previous - self.hp

    def apply_sleep(self, turns: int) -> None:
        """Apply DA2's non-shortening sleep duration."""

        if isinstance(turns, bool) or not isinstance(turns, int):
            raise TypeError("turns must be an integer")
        if turns <= 0:
            raise ValueError("turns must be positive")
        self.sleeping = max(self.sleeping, turns)

    def apply_poison(self) -> bool:
        """Apply persistent poison and report whether the state changed."""

        if self.poisoned or not self.is_alive:
            return False
        self.poisoned = True
        return True

    def take_poison_damage(self, damage: int) -> int:
        """Apply poison damage without waking the monster from sleep."""

        if isinstance(damage, bool) or not isinstance(damage, int):
            raise TypeError("damage must be an integer")
        if damage < 0:
            raise ValueError("damage must not be negative")
        previous = self.hp
        assert previous is not None
        self.hp = max(0, previous - damage)
        if self.hp <= 0:
            self.speed_modifier = 0
        return previous - self.hp

    def elapse_sleep_turn(self) -> bool:
        """Consume one sleeping action and report whether it was skipped."""

        if self.sleeping <= 0:
            return False
        self.sleeping -= 1
        return True

    def apply_slow(self) -> bool:
        """Apply SLOW once, cancelling a positive speed modifier first."""

        if self.speed_modifier <= MIN_SPEED_MODIFIER:
            return False
        self.speed_modifier = 0 if self.speed_modifier > 0 else MIN_SPEED_MODIFIER
        return True

    def defeat(self) -> None:
        """Set HP to zero for a mock attack that always defeats its target."""

        self.hp = 0
        self.speed_modifier = 0

    def restore(self) -> None:
        """Restore initial HP when restarting a battle fixture."""

        self.hp = self.max_hp
        self.poisoned = False
        self.sleeping = 0
        self.speed_modifier = 0


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
