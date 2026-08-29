"""Item identity data independent of UI and Pyxel."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

if __package__ == "":
    from localization import Localizer
else:
    from .localization import Localizer


class ItemDataError(ValueError):
    """Raised when an item record cannot be interpreted safely."""


@dataclass(frozen=True)
class Item:
    """Minimal item model with its current lookup key and localized names."""

    key: str
    names: Mapping[str, str]

    @classmethod
    def from_record(cls, record: Mapping[str, object]) -> Item:
        """Validate and normalize the identity portion of an item record."""

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

        return cls(key=key, names=MappingProxyType(names))

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
