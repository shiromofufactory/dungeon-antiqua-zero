"""Item identity data independent of UI and Pyxel."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping

if __package__ == "":
    from localization import Localizer
    from resistance import ResistanceType, resistances_from_tolerance
else:
    from .localization import Localizer
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


class ItemEquipType(StrEnum):
    """Stable item categories used to validate equipment slots."""

    ITEM = "ITEM"
    RIGHT = "RIGHT"
    LEFT = "LEFT"
    TWO_HANDS = "TWO_HANDS"
    HEAD = "HEAD"
    BODY = "BODY"
    ARM = "ARM"


@dataclass(frozen=True)
class Item:
    """Item identity, equipment category, and battle status values."""

    key: str
    names: Mapping[str, str]
    equip_type: ItemEquipType
    subtype: str
    attack: int
    hit: int
    defense: int
    evasion: int
    spell_resistance: int
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
            attack=_non_negative_stat(record, "atk"),
            hit=_non_negative_stat(record, "hit"),
            defense=_non_negative_stat(record, "dfc"),
            evasion=_integer_stat(record, "eva"),
            spell_resistance=_non_negative_stat(record, "rst"),
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
