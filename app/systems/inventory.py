"""Inventory operations shared by item screens and future game scenes."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from types import MappingProxyType

if __package__ == "systems":
    from item import Item
else:
    from ..item import Item


class InventorySystem:
    """Own item quantities and enforce rules for changing them."""

    def __init__(
        self,
        items: Mapping[str, Item],
        quantities: Mapping[str, int] | None = None,
        recorded_keys: Iterable[str] | None = None,
    ) -> None:
        if not isinstance(items, Mapping) or not all(
            isinstance(key, str) and isinstance(item, Item) and key == item.key
            for key, item in items.items()
        ):
            raise TypeError("items must map each string key to its matching Item")
        if quantities is None:
            quantities = {}
        if not isinstance(quantities, Mapping):
            raise TypeError("quantities must be a mapping")

        normalized: dict[str, int] = {}
        for key, quantity in quantities.items():
            if not isinstance(key, str) or key not in items:
                raise ValueError(f"unknown inventory item key: {key!r}")
            if isinstance(quantity, bool) or not isinstance(quantity, int):
                raise TypeError("item quantity must be an integer")
            if quantity < 0:
                raise ValueError("item quantity must not be negative")
            if quantity:
                normalized[key] = quantity

        if recorded_keys is None:
            normalized_recorded_keys = frozenset(normalized)
        else:
            if isinstance(recorded_keys, (str, bytes)):
                raise TypeError("recorded_keys must be an iterable of strings")
            try:
                normalized_recorded_keys = frozenset(recorded_keys)
            except TypeError as error:
                raise TypeError(
                    "recorded_keys must be an iterable of strings"
                ) from error
            if not all(isinstance(key, str) for key in normalized_recorded_keys):
                raise TypeError("recorded item keys must be strings")
            unknown_recorded_keys = normalized_recorded_keys - items.keys()
            if unknown_recorded_keys:
                unknown = sorted(unknown_recorded_keys)[0]
                raise ValueError(f"unknown recorded item key: {unknown!r}")

        self._items = dict(items)
        self._quantities = normalized
        self._recorded_keys = normalized_recorded_keys

    @classmethod
    def with_one_each(cls, items: Mapping[str, Item]) -> InventorySystem:
        """Build the current screen-mock inventory with one of every item."""

        return cls(items, {key: 1 for key in items})

    @property
    def items(self) -> tuple[Item, ...]:
        """Return owned item types in master-data order."""

        return tuple(
            item for key, item in self._items.items() if self.quantity(key) > 0
        )

    @property
    def quantities(self) -> Mapping[str, int]:
        """Expose current quantities without allowing callers to mutate them."""

        return MappingProxyType(self._quantities)

    @property
    def recorded_items(self) -> tuple[Item, ...]:
        """Return discovered item types in master-data order."""

        return tuple(
            item for key, item in self._items.items() if key in self._recorded_keys
        )

    @property
    def recorded_count(self) -> int:
        return len(self._recorded_keys)

    @property
    def catalog_count(self) -> int:
        return len(self._items)

    def quantity(self, item: Item | str) -> int:
        """Return the owned count for an item model or stable item key."""

        key = self._item_key(item)
        return self._quantities.get(key, 0)

    def can_discard(self, item: Item | str) -> bool:
        """Return whether one owned item may be discarded.

        DA2 treats a zero price as the protected-item marker.
        """

        key = self._item_key(item)
        return self._quantities.get(key, 0) > 0 and self._items[key].price > 0

    def discard(self, item: Item | str) -> bool:
        """Discard one item when allowed, returning whether state changed."""

        key = self._item_key(item)
        if not self.can_discard(key):
            return False
        remaining = self._quantities[key] - 1
        if remaining:
            self._quantities[key] = remaining
        else:
            del self._quantities[key]
        return True

    def _item_key(self, item: Item | str) -> str:
        if isinstance(item, Item):
            key = item.key
        elif isinstance(item, str):
            key = item
        else:
            raise TypeError("item must be an Item or string key")
        if key not in self._items:
            raise ValueError(f"unknown inventory item key: {key!r}")
        return key


__all__ = ["InventorySystem"]
