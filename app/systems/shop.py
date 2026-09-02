"""Purchase and sale rules shared by shop screens and future scenes."""

from __future__ import annotations

from collections.abc import Iterable

if __package__ == "systems":
    from item import Item
    from member import Member
    from shop import Shop
    from state import SaveData
    from systems.inventory import InventorySystem
else:
    from ..item import Item
    from ..member import Member
    from ..shop import Shop
    from ..state import SaveData
    from .inventory import InventorySystem


MAX_GOLD = 999_999


class ShopSystem:
    """Apply atomic shop transactions without knowing UI state."""

    def __init__(
        self,
        *,
        shops: Iterable[Shop],
        inventory: InventorySystem,
        party: Iterable[Member],
        save_data: SaveData,
    ) -> None:
        try:
            normalized_shops = tuple(shops)
            normalized_party = tuple(party)
        except TypeError as error:
            raise TypeError("shops and party must be iterable") from error
        if not normalized_shops or not all(
            isinstance(shop, Shop) for shop in normalized_shops
        ):
            raise TypeError("shops must contain at least one Shop")
        if len({shop.key for shop in normalized_shops}) != len(normalized_shops):
            raise ValueError("shop keys must be unique")
        if not normalized_party or not all(
            isinstance(member, Member) for member in normalized_party
        ):
            raise TypeError("party must contain at least one Member")
        if not isinstance(inventory, InventorySystem):
            raise TypeError("inventory must be an InventorySystem")
        if not isinstance(save_data, SaveData):
            raise TypeError("save_data must be SaveData")

        inventory.validate_total_quantities(normalized_party)
        self.shops = normalized_shops
        self.inventory = inventory
        self.party = normalized_party
        self.save_data = save_data
        self._sold_item_keys = frozenset(
            item.key for shop in normalized_shops for item in shop.items
        )

    def is_rare_sale(self, item: Item) -> bool:
        """Return whether no shop in the master data sells this item."""

        self._validate_item(item)
        return item.key not in self._sold_item_keys

    @staticmethod
    def sale_unit_price(item: Item) -> int:
        if not isinstance(item, Item):
            raise TypeError("item must be an Item")
        return item.price // 2

    def max_buy_quantity(self, shop: Shop, item: Item) -> int:
        self._validate_shop_item(shop, item)
        capacity = self.inventory.remaining_capacity(item, self.party)
        if item.price == 0:
            return capacity
        return min(capacity, self.save_data.gold // item.price)

    def buy(self, shop: Shop, item: Item, quantity: int) -> bool:
        self._validate_quantity(quantity)
        if quantity > self.max_buy_quantity(shop, item):
            return False
        cost = item.price * quantity
        if not self.inventory.add(item, quantity, members=self.party):
            return False
        self.save_data.gold -= cost
        return True

    def can_sell(self, item: Item) -> bool:
        self._validate_item(item)
        return item.price > 0 and self.inventory.quantity(item) > 0

    def max_sell_quantity(self, item: Item) -> int:
        if not self.can_sell(item):
            return 0
        return self.inventory.quantity(item)

    def sell(self, item: Item, quantity: int) -> bool:
        self._validate_quantity(quantity)
        if quantity > self.max_sell_quantity(item):
            return False
        if not self.inventory.remove(item, quantity):
            return False
        self.save_data.gold = min(
            MAX_GOLD,
            self.save_data.gold + self.sale_unit_price(item) * quantity,
        )
        return True

    def _validate_shop_item(self, shop: Shop, item: Item) -> None:
        if not isinstance(shop, Shop):
            raise TypeError("shop must be a Shop")
        if shop not in self.shops:
            raise ValueError(f"unknown shop: {shop.key!r}")
        self._validate_item(item)
        if item not in shop.items:
            raise ValueError(f"item is not sold by shop {shop.key!r}: {item.key!r}")

    def _validate_item(self, item: Item) -> None:
        if not isinstance(item, Item):
            raise TypeError("item must be an Item")
        try:
            self.inventory.quantity(item)
        except ValueError as error:
            raise ValueError(f"unknown shop item: {item.key!r}") from error

    @staticmethod
    def _validate_quantity(quantity: int) -> None:
        if isinstance(quantity, bool) or not isinstance(quantity, int):
            raise TypeError("quantity must be an integer")
        if quantity <= 0:
            raise ValueError("quantity must be positive")


__all__ = ["MAX_GOLD", "ShopSystem"]
