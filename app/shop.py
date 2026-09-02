"""Fixed shop master data independent of scenes and Pyxel."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

if __package__ == "":
    from item import Item
else:
    from .item import Item


class ShopDataError(ValueError):
    """Raised when one shop record cannot be resolved safely."""


@dataclass(frozen=True)
class Shop:
    """One shop and its immutable, data-authored product list."""

    key: str
    items: tuple[Item, ...]
    note: str = ""

    @classmethod
    def from_record(
        cls,
        record: Mapping[str, object],
        items: Mapping[str, Item],
    ) -> Shop:
        if not isinstance(record, Mapping):
            raise ShopDataError("shop must be an object")
        if not isinstance(items, Mapping) or not all(
            isinstance(key, str) and isinstance(item, Item) and key == item.key
            for key, item in items.items()
        ):
            raise TypeError("items must map each string key to its matching Item")

        key = record.get("shop_key")
        if not isinstance(key, str) or not key:
            raise ShopDataError("shop.shop_key must be a non-empty string")
        item_keys = record.get("items")
        if not isinstance(item_keys, list) or not all(
            isinstance(item_key, str) and item_key for item_key in item_keys
        ):
            raise ShopDataError("shop.items must be an array of non-empty strings")
        if len(set(item_keys)) != len(item_keys):
            raise ShopDataError(f"shop.items contains duplicates: {key}")
        try:
            products = tuple(items[item_key] for item_key in item_keys)
        except KeyError as error:
            raise ShopDataError(
                f"shop item is not defined: {error.args[0]!r}"
            ) from error
        note = record.get("note", "")
        if not isinstance(note, str):
            raise ShopDataError("shop.note must be a string")
        return cls(key=key, items=products, note=note)


__all__ = ["Shop", "ShopDataError"]
