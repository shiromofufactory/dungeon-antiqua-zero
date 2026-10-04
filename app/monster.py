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
    REINFORCE = "援"
    CALL = "呼"


def monster_spell_keys_from_record(
    record: Mapping[str, object],
) -> tuple[str, ...]:
    """Parse and validate a monster's newline-delimited spell keys."""

    if not isinstance(record, Mapping):
        raise MonsterDataError("monster must be an object")
    value = record.get("spells")
    if not isinstance(value, str):
        raise MonsterDataError("monster.spells must be a string")
    value = value.replace("\r\n", "\n")
    if "\r" in value:
        raise MonsterDataError("monster.spells contains an invalid line separator")
    if not value:
        return ()
    keys = tuple(value.split("\n"))
    if any(not key for key in keys):
        raise MonsterDataError("monster.spells must not contain empty keys")
    if len(keys) != len(set(keys)):
        raise MonsterDataError("monster.spells must not contain duplicate keys")
    return keys


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
    early_appear: bool
    max_occurrence: int
    is_large_animal: bool
    magic: int
    intelligence: int
    spell_keys: tuple[str, ...]
    weaknesses: frozenset[ResistanceType]
    resistances: frozenset[ResistanceType]
    treasure_item_key: str
    treasure_rate: int
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
        treasure_rate = _required_monster_integer(record, "treasure_rate")
        if treasure_rate > 16:
            raise MonsterDataError("monster.treasure_rate must be from 0 to 16")

        flags: dict[str, bool] = {}
        for field_name in ("is_boss", "shadow", "early_appear", "large_animal"):
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
            early_appear=flags["early_appear"],
            max_occurrence=_required_monster_integer(
                record,
                "max_occ",
                positive=True,
            ),
            is_large_animal=flags["large_animal"],
            magic=_required_monster_integer(record, "mag"),
            intelligence=_required_monster_integer(record, "int"),
            spell_keys=monster_spell_keys_from_record(record),
            weaknesses=resistances_from_tolerance(weakness),
            resistances=resistances_from_tolerance(tolerance),
            treasure_item_key=treasure_item_key,
            treasure_rate=treasure_rate,
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
    """Immutable combat and automatic recovery values from monster master data."""

    attack: int
    hit: int
    defense: int
    evasion: int
    spell_resistance: int = 0
    healing: int = 0

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
        healing = record.get("healing", 0)
        if isinstance(healing, bool) or not isinstance(healing, int):
            raise MonsterDataError("monster.healing must be an integer")
        values["healing"] = healing
        return cls(**values)


@dataclass
class MonsterBattleState:
    """Per-battle HP and MP copied from immutable monster master data."""

    max_hp: int
    hp: int | None = None
    max_mp: int = 0
    mp: int | None = None
    poisoned: bool = False
    sleeping: int = 0
    confused: int = 0
    silenced: int = 0
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
        if isinstance(self.max_mp, bool) or not isinstance(self.max_mp, int):
            raise TypeError("max_mp must be an integer")
        if self.max_mp < 0:
            raise ValueError("max_mp must not be negative")
        if self.mp is None:
            self.mp = self.max_mp
        if isinstance(self.mp, bool) or not isinstance(self.mp, int):
            raise TypeError("mp must be an integer")
        if not 0 <= self.mp <= self.max_mp:
            raise ValueError("mp must be from 0 to max_mp")
        if not isinstance(self.poisoned, bool):
            raise TypeError("poisoned must be a boolean")
        if isinstance(self.sleeping, bool) or not isinstance(self.sleeping, int):
            raise TypeError("sleeping must be an integer")
        if self.sleeping < 0:
            raise ValueError("sleeping must not be negative")
        if isinstance(self.confused, bool) or not isinstance(self.confused, int):
            raise TypeError("confused must be an integer")
        if self.confused < 0:
            raise ValueError("confused must not be negative")
        if isinstance(self.silenced, bool) or not isinstance(self.silenced, int):
            raise TypeError("silenced must be an integer")
        if self.silenced < 0:
            raise ValueError("silenced must not be negative")
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
        """Create full HP/MP state from the record's master values."""

        if not isinstance(record, Mapping):
            raise MonsterDataError("monster must be an object")
        max_hp = record.get("mhp")
        if isinstance(max_hp, bool) or not isinstance(max_hp, int) or max_hp <= 0:
            raise MonsterDataError("monster.mhp must be a positive integer")
        max_mp = record.get("mmp", 0)
        if isinstance(max_mp, bool) or not isinstance(max_mp, int) or max_mp < 0:
            raise MonsterDataError("monster.mmp must be a non-negative integer")
        return cls(max_hp=max_hp, max_mp=max_mp)

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
            self.confused = 0
        if self.hp <= 0:
            self.confused = 0
            self.silenced = 0
            self.stunned = False
            self.defense_modifier = 0
            self.speed_modifier = 0
        return previous - self.hp

    def apply_healing(self, amount: int) -> int:
        """Recover living monsters up to max HP without changing ailments."""

        if isinstance(amount, bool) or not isinstance(amount, int):
            raise TypeError("healing amount must be an integer")
        if amount < 0:
            raise ValueError("healing amount must not be negative")
        if not self.is_alive:
            return 0
        previous = self.hp
        assert previous is not None
        self.hp = min(self.max_hp, previous + amount)
        return self.hp - previous

    def apply_sleep(self, turns: int) -> None:
        """Apply DA2's non-shortening sleep duration and clear confusion."""

        if isinstance(turns, bool) or not isinstance(turns, int):
            raise TypeError("turns must be an integer")
        if turns <= 0:
            raise ValueError("turns must be positive")
        self.sleeping = max(self.sleeping, turns)
        self.confused = 0

    def apply_confusion(self, turns: int) -> bool:
        """Apply DA2's non-shortening confusion duration and clear sleep."""

        if isinstance(turns, bool) or not isinstance(turns, int):
            raise TypeError("turns must be an integer")
        if turns <= 0:
            raise ValueError("turns must be positive")
        if not self.is_alive:
            return False
        previous = self.confused
        self.confused = max(self.confused, turns)
        self.sleeping = 0
        return self.confused != previous

    def elapse_confusion_turn(self) -> bool:
        """Consume one confused action and report whether confusion was active."""

        if self.confused <= 0:
            return False
        self.confused -= 1
        return True

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
            self.confused = 0
            self.silenced = 0
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

    def apply_silence(self, turns: int) -> bool:
        """Apply DA2's non-shortening silence duration."""

        if isinstance(turns, bool) or not isinstance(turns, int):
            raise TypeError("turns must be an integer")
        if turns <= 0:
            raise ValueError("turns must be positive")
        if not self.is_alive:
            return False
        previous = self.silenced
        self.silenced = max(self.silenced, turns)
        return self.silenced != previous

    def elapse_silence_turn(self) -> bool:
        """Consume one silenced turn and report whether silence was active."""

        if self.silenced <= 0:
            return False
        self.silenced -= 1
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

    def apply_haste(self) -> bool:
        """Raise battle speed by one stage, up to DA2's second stage."""

        if self.speed_modifier >= MAX_SPEED_MODIFIER or not self.is_alive:
            return False
        self.speed_modifier += 1
        return True

    def spend_mp(self, amount: int) -> bool:
        """Spend MP when possible and report whether the spell can proceed."""

        if isinstance(amount, bool) or not isinstance(amount, int):
            raise TypeError("MP amount must be an integer")
        if amount < 0:
            raise ValueError("MP amount must not be negative")
        assert self.mp is not None
        if self.mp < amount:
            return False
        self.mp -= amount
        return True

    def defeat(self) -> None:
        """Set HP to zero for a mock attack that always defeats its target."""

        self.hp = 0
        self.confused = 0
        self.silenced = 0
        self.stunned = False
        self.defense_modifier = 0
        self.speed_modifier = 0

    def restore(self) -> None:
        """Restore initial HP when restarting a battle fixture."""

        self.hp = self.max_hp
        self.mp = self.max_mp
        self.poisoned = False
        self.sleeping = 0
        self.confused = 0
        self.silenced = 0
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
    "monster_spell_keys_from_record",
    "monster_special_actions_from_record",
    "promote_rear_monsters_if_front_empty",
]
