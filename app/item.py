"""Item identity data independent of UI and Pyxel."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping, TypeVar

if __package__ == "":
    from localization import Localizer
    from monster import MonsterTribe
    from resistance import ResistanceType, resistances_from_tolerance
else:
    from .localization import Localizer
    from .monster import MonsterTribe
    from .resistance import ResistanceType, resistances_from_tolerance


class ItemDataError(ValueError):
    """Raised when an item record cannot be interpreted safely."""


def _non_negative_stat(record: Mapping[str, object], field: str) -> int:
    value = record.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ItemDataError(f"item.{field} must be an integer")
    if value < 0:
        raise ItemDataError(f"item.{field} must not be negative")
    return value


def _integer_stat(record: Mapping[str, object], field: str) -> int:
    value = record.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ItemDataError(f"item.{field} must be an integer")
    return value


def _optional_integer_stat(
    record: Mapping[str, object],
    field: str,
    *,
    default: int = 0,
) -> int:
    value = record.get(field, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ItemDataError(f"item.{field} must be an integer")
    return value


def _optional_non_negative_stat(
    record: Mapping[str, object],
    field: str,
    *,
    default: int = 0,
) -> int:
    value = _optional_integer_stat(record, field, default=default)
    if value < 0:
        raise ItemDataError(f"item.{field} must not be negative")
    return value


def _optional_flag(
    record: Mapping[str, object],
    field: str,
    *,
    default: int = 0,
) -> bool:
    value = record.get(field, default)
    if isinstance(value, bool) or not isinstance(value, int) or value not in (0, 1):
        raise ItemDataError(f"item.{field} must be 0 or 1")
    return bool(value)


def _optional_string(
    record: Mapping[str, object],
    field: str,
    *,
    default: str = "",
) -> str:
    value = record.get(field, default)
    if not isinstance(value, str):
        raise ItemDataError(f"item.{field} must be a string")
    return value


class ItemEquipType(StrEnum):
    """Stable item categories used to validate equipment slots."""

    ITEM = "ITEM"
    RIGHT = "RIGHT"
    LEFT = "LEFT"
    TWO_HANDS = "TWO_HANDS"
    HEAD = "HEAD"
    BODY = "BODY"
    ARM = "ARM"


class AttackAttribute(StrEnum):
    """Stable elemental attributes applied by weapon attacks."""

    FIRE = "FIRE"
    FREEZE = "FREEZE"
    DARK = "DARK"


class AdditionalEffect(StrEnum):
    """Stable status effects that a weapon attack can add."""

    SLEEP = "SLEEP"
    CONFUSE = "CONFUSE"
    DEATH = "DEATH"
    SILENCE = "SILENCE"
    DRAIN = "DRAIN"
    STUN = "STUN"
    POISON = "POISON"
    PARALIZE = "PARALIZE"
    DEFENSE_DOWN = "DEFENSE_DOWN"


class ItemSpecial(StrEnum):
    """Stable identifiers for item-specific traits."""

    ATK_REDUCE_WT = "ATK_REDUCE_WT"
    COUNTER_STUN = "COUNTER_STUN"
    DUAL_WIELD = "DUAL_WIELD"
    GAIN_TWICE = "GAIN_TWICE"
    LURE = "LURE"
    POWER_HIT = "POWER_HIT"
    REFLECT = "REFLECT"
    SPL_REDUCE_WT = "SPL_REDUCE_WT"
    TWO_HANDED = "TWO_HANDED"
    VIGILANCE = "VIGILANCE"


_ATTACK_ATTRIBUTE_BY_CHARACTER = MappingProxyType(
    {
        "炎": AttackAttribute.FIRE,
        "冷": AttackAttribute.FREEZE,
        "闇": AttackAttribute.DARK,
    }
)
_ADDITIONAL_EFFECT_BY_CHARACTER = MappingProxyType(
    {
        "眠": AdditionalEffect.SLEEP,
        "乱": AdditionalEffect.CONFUSE,
        "死": AdditionalEffect.DEATH,
        "黙": AdditionalEffect.SILENCE,
        "吸": AdditionalEffect.DRAIN,
        "止": AdditionalEffect.STUN,
        "毒": AdditionalEffect.POISON,
        "麻": AdditionalEffect.PARALIZE,
        "破": AdditionalEffect.DEFENSE_DOWN,
    }
)

Code = TypeVar("Code")


def _optional_code(
    record: Mapping[str, object],
    field: str,
    values: Mapping[str, Code],
) -> Code | None:
    value = _optional_string(record, field)
    if not value:
        return None
    try:
        return values[value]
    except KeyError as error:
        raise ItemDataError(f"unsupported item.{field}: {value}") from error


def _optional_monster_tribe(record: Mapping[str, object]) -> MonsterTribe | None:
    value = _optional_string(record, "race")
    if not value:
        return None
    try:
        return MonsterTribe(value)
    except ValueError as error:
        raise ItemDataError(f"unsupported item.race: {value}") from error


def _optional_item_special(record: Mapping[str, object]) -> ItemSpecial | None:
    value = _optional_string(record, "special")
    if not value:
        return None
    try:
        return ItemSpecial(value)
    except ValueError as error:
        raise ItemDataError(f"unsupported item.special: {value}") from error


@dataclass(frozen=True)
class Item:
    """Item identity, equipment category, and battle status values."""

    key: str
    names: Mapping[str, str]
    equip_type: ItemEquipType
    subtype: str
    requirement: str
    attack_attribute: AttackAttribute | None
    additional_effect: AdditionalEffect | None
    special: ItemSpecial | None
    effective_tribe: MonsterTribe | None
    price: int
    use_spell_key: str
    breaks_on_use: bool
    source: str
    attack: int
    hit: int
    reach: int
    defense: int
    evasion: int
    spell_resistance: int
    strength_modifier: int
    agility_modifier: int
    magic_modifier: int
    healing: int
    resistances: frozenset[ResistanceType]

    @classmethod
    def from_record(cls, record: Mapping[str, object]) -> Item:
        """Validate and normalize one item master-data record."""

        if not isinstance(record, Mapping):
            raise ItemDataError("item must be an object")

        key = record.get("name_en")
        if not isinstance(key, str) or not key:
            raise ItemDataError("item.name_en must be a non-empty string")

        names: dict[str, str] = {}
        for field, value in record.items():
            if not field.startswith("name_"):
                continue
            if not isinstance(value, str):
                raise ItemDataError(f"item.{field} must be a string")
            names[field] = value
        if not any(names.values()):
            raise ItemDataError("item must have a non-empty localized name")

        equip_type_value = record.get("type1")
        if not isinstance(equip_type_value, str):
            raise ItemDataError("item.type1 must be a string")
        try:
            equip_type = ItemEquipType(equip_type_value)
        except ValueError as error:
            raise ItemDataError(
                f"unsupported item.type1: {equip_type_value}"
            ) from error

        subtype = record.get("type2")
        if not isinstance(subtype, str) or not subtype:
            raise ItemDataError("item.type2 must be a non-empty string")
        tolerance = record.get("tolerance")
        if not isinstance(tolerance, str):
            raise ItemDataError("item.tolerance must be a string")

        return cls(
            key=key,
            names=MappingProxyType(names),
            equip_type=equip_type,
            subtype=subtype,
            requirement=_optional_string(record, "requirements"),
            attack_attribute=_optional_code(
                record,
                "attr",
                _ATTACK_ATTRIBUTE_BY_CHARACTER,
            ),
            additional_effect=_optional_code(
                record,
                "extra",
                _ADDITIONAL_EFFECT_BY_CHARACTER,
            ),
            special=_optional_item_special(record),
            effective_tribe=_optional_monster_tribe(record),
            price=_optional_non_negative_stat(record, "price"),
            use_spell_key=_optional_string(record, "use"),
            breaks_on_use=_optional_flag(record, "break"),
            source=_optional_string(record, "source"),
            attack=_non_negative_stat(record, "atk"),
            hit=_non_negative_stat(record, "hit"),
            reach=_optional_non_negative_stat(record, "reach"),
            defense=_non_negative_stat(record, "dfc"),
            evasion=_integer_stat(record, "eva"),
            spell_resistance=_non_negative_stat(record, "rst"),
            strength_modifier=_optional_integer_stat(record, "str"),
            agility_modifier=_optional_integer_stat(record, "agi"),
            magic_modifier=_optional_integer_stat(record, "mag"),
            healing=_optional_integer_stat(record, "healing"),
            resistances=resistances_from_tolerance(tolerance),
        )

    @property
    def is_weapon(self) -> bool:
        """Return whether this item supplies weapon attack and hit values."""

        return self.equip_type in (
            ItemEquipType.RIGHT,
            ItemEquipType.TWO_HANDS,
        )

    @property
    def is_equipment(self) -> bool:
        """Return whether this item can occupy an equipment slot."""

        return self.equip_type is not ItemEquipType.ITEM

    @property
    def is_spell_book(self) -> bool:
        """Return whether this consumable is explicitly classified as a spell book."""

        return self.equip_type is ItemEquipType.ITEM and self.subtype == "BOOK"

    @property
    def is_armor(self) -> bool:
        """Return whether this item contributes defensive status values."""

        return self.equip_type in (
            ItemEquipType.LEFT,
            ItemEquipType.HEAD,
            ItemEquipType.BODY,
            ItemEquipType.ARM,
        )

    def localized_name(self, localizer: Localizer) -> str:
        """Return the item name normalized for the selected language."""

        if not isinstance(localizer, Localizer):
            raise TypeError("localizer must be a Localizer")
        try:
            name = localizer.text(self.names, "name")
        except TypeError as error:
            raise ItemDataError("localized item name must be a string") from error
        if not name:
            raise ItemDataError(f"localized item name is missing: {self.key}")
        return name
