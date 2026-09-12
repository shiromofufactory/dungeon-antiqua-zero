"""Monster identity and mutable battle state independent of presentation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
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

if __package__ == "":
    from localization import Localizer
    from resistance import ResistanceType, resistances_from_tolerance
else:
    from .localization import Localizer
    from .resistance import ResistanceType, resistances_from_tolerance


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


class MonsterSpecialAction(StrEnum):
    """Stable one-character monster special-action keys."""

    ESCAPE = "逃"
    CHARGE = "突"


def monster_special_actions_from_record(
    record: Mapping[str, object],
) -> tuple[MonsterSpecialAction, ...]:
    """Parse and validate a monster's concatenated special-action keys."""

    if not isinstance(record, Mapping):
        raise MonsterDataError("monster must be an object")
    value = record.get("special")
    if not isinstance(value, str) or "\n" in value or "\r" in value:
        raise MonsterDataError("monster.special must be a single-line string")
    try:
        actions = tuple(MonsterSpecialAction(key) for key in value)
    except ValueError as error:
        raise MonsterDataError(f"unsupported monster.special: {value}") from error
    if len(actions) != len(set(actions)):
        raise MonsterDataError("monster.special must not contain duplicate actions")
    return actions


def _required_monster_integer(
    record: Mapping[str, object],
    field_name: str,
    *,
    positive: bool = False,
) -> int:
    value = record.get(field_name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise MonsterDataError(f"monster.{field_name} must be an integer")
    minimum = 1 if positive else 0
    if value < minimum:
        qualifier = "positive" if positive else "non-negative"
        raise MonsterDataError(f"monster.{field_name} must be {qualifier}")
    return value


@dataclass(frozen=True)
class MonsterDefinition:
    """Immutable monster master data shared by non-battle features."""

    key: str
    names: Mapping[str, str]
    image_id: str
    width: int
    height: int
    is_boss: bool
    tribe: MonsterTribe
    max_hp: int
    max_mp: int
    level: int
    weaknesses: frozenset[ResistanceType]
    resistances: frozenset[ResistanceType]
    treasure_item_key: str
    is_shadow: bool = False

    @classmethod
    def from_record(cls, record: Mapping[str, object]) -> MonsterDefinition:
        """Validate the monster fields needed outside a battle instance."""

        if not isinstance(record, Mapping):
            raise MonsterDataError("monster must be an object")
        key = record.get("name_en")
        if not isinstance(key, str) or not key:
            raise MonsterDataError("monster.name_en must be a non-empty string")

        names: dict[str, str] = {}
        for field_name, value in record.items():
            if not field_name.startswith("name_"):
                continue
            if not isinstance(value, str):
                raise MonsterDataError(f"monster.{field_name} must be a string")
            names[field_name] = value
        if not any(names.values()):
            raise MonsterDataError("monster must have a localized name")

        image_id = record.get("image_id")
        if isinstance(image_id, bool) or not isinstance(image_id, (str, int)):
            raise MonsterDataError("monster.image_id must be a string or integer")
        image_id_text = str(image_id)
        if not image_id_text:
            raise MonsterDataError("monster.image_id must not be empty")

        try:
            tribe = MonsterTribe(record.get("tribe"))
        except (TypeError, ValueError) as error:
            raise MonsterDataError(
                f"unsupported monster.tribe: {record.get('tribe')}"
            ) from error

        weakness = record.get("weakness")
        tolerance = record.get("tolerance")
        treasure_item_key = record.get("treasure_item")
        for field_name, value in (
            ("weakness", weakness),
            ("tolerance", tolerance),
            ("treasure_item", treasure_item_key),
        ):
            if not isinstance(value, str):
                raise MonsterDataError(f"monster.{field_name} must be a string")
        if not treasure_item_key:
            raise MonsterDataError("monster.treasure_item must not be empty")

        flags: dict[str, bool] = {}
        for field_name in ("is_boss", "shadow"):
            value = record.get(field_name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value not in (0, 1)
            ):
                raise MonsterDataError(f"monster.{field_name} must be 0 or 1")
            flags[field_name] = bool(value)

        return cls(
            key=key,
            names=MappingProxyType(names),
            image_id=image_id_text,
            width=_required_monster_integer(record, "width", positive=True),
            height=_required_monster_integer(record, "height", positive=True),
            is_boss=flags["is_boss"],
            tribe=tribe,
            max_hp=_required_monster_integer(record, "mhp", positive=True),
            max_mp=_required_monster_integer(record, "mmp"),
            level=_required_monster_integer(record, "lv", positive=True),
            weaknesses=resistances_from_tolerance(weakness),
            resistances=resistances_from_tolerance(tolerance),
            treasure_item_key=treasure_item_key,
            is_shadow=flags["shadow"],
        )

    @property
    def image_resource_id(self) -> str:
        return f"monsters/{self.image_id}"

    def localized_name(self, localizer: Localizer) -> str:
        """Return the localized display name for the current language."""

        if not isinstance(localizer, Localizer):
            raise TypeError("localizer must be a Localizer")
        name = localizer.text(self.names, "name")
        if not name:
            raise MonsterDataError(f"localized monster name is missing: {self.key}")
        return name


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
    stunned: bool = False
    defense_modifier: int = 0
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
        if not isinstance(self.stunned, bool):
            raise TypeError("stunned must be a boolean")
        if (
            isinstance(self.defense_modifier, bool)
            or not isinstance(self.defense_modifier, int)
        ):
            raise TypeError("defense_modifier must be an integer")
        if self.defense_modifier not in (-1, 0):
            raise ValueError("defense_modifier must be -1 or 0")
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
            self.stunned = False
            self.defense_modifier = 0
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
            self.stunned = False
            self.defense_modifier = 0
            self.speed_modifier = 0
        return previous - self.hp

    def elapse_sleep_turn(self) -> bool:
        """Consume one sleeping action and report whether it was skipped."""

        if self.sleeping <= 0:
            return False
        self.sleeping -= 1
        return True

    def apply_stun(self) -> bool:
        """Mark the next timeline action to be skipped once."""

        if self.stunned or not self.is_alive:
            return False
        self.stunned = True
        return True

    def consume_stun(self) -> bool:
        """Clear one pending stun and report that this action must be skipped."""

        if not self.stunned:
            return False
        self.stunned = False
        return True

    def apply_defense_down(self) -> bool:
        """Apply DA2's single persistent physical-defense reduction."""

        if self.defense_modifier < 0 or not self.is_alive:
            return False
        self.defense_modifier = -1
        return True

    def modified_defense(self, base_defense: int) -> int:
        """Return base defense after DA2's negative defense-stage formula."""

        if isinstance(base_defense, bool) or not isinstance(base_defense, int):
            raise TypeError("base_defense must be an integer")
        if base_defense < 0:
            raise ValueError("base_defense must not be negative")
        if self.defense_modifier >= 0:
            return base_defense
        return max(0, int((base_defense - 10) * 0.5))

    def apply_slow(self) -> bool:
        """Apply SLOW once, cancelling a positive speed modifier first."""

        if self.speed_modifier <= MIN_SPEED_MODIFIER:
            return False
        self.speed_modifier = 0 if self.speed_modifier > 0 else MIN_SPEED_MODIFIER
        return True

    def defeat(self) -> None:
        """Set HP to zero for a mock attack that always defeats its target."""

        self.hp = 0
        self.stunned = False
        self.defense_modifier = 0
        self.speed_modifier = 0

    def restore(self) -> None:
        """Restore initial HP when restarting a battle fixture."""

        self.hp = self.max_hp
        self.poisoned = False
        self.sleeping = 0
        self.stunned = False
        self.defense_modifier = 0
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
    "MonsterSpecialAction",
    "MonsterTribe",
    "monster_special_actions_from_record",
    "promote_rear_monsters_if_front_empty",
]
