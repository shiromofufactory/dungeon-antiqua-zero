from __future__ import annotations

import unittest

from app.item import Item
from app.member import EquipmentSlot
from app.shop import Shop
from app.state import SaveData
from app.systems import MAX_GOLD, InventorySystem, ShopSystem
from tests.test_inventory import member


def make_item(key: str, *, price: int, equip_type: str = "ITEM") -> Item:
    return Item.from_record(
        {
            "name_en": key,
            "name_ja": key,
            "type1": equip_type,
            "type2": "ITEM" if equip_type == "ITEM" else "KNIFE",
            "price": price,
            "atk": 0,
            "hit": 0,
            "dfc": 0,
            "eva": 0,
            "rst": 0,
            "tolerance": "",
        }
    )


class ShopSystemTest(unittest.TestCase):
    def setUp(self) -> None:
        self.potion = make_item("POTION", price=50)
        self.dagger = make_item("DAGGER", price=101, equip_type="RIGHT")
        self.rare = make_item("RARE", price=201, equip_type="RIGHT")
        self.protected = make_item("PROTECTED", price=0)
        self.items = {
            item.key: item
            for item in (self.potion, self.dagger, self.rare, self.protected)
        }
        self.shop = Shop("TEST", (self.potion, self.dagger))
        self.party = (member(),)
        self.inventory = InventorySystem(
            self.items,
            {self.rare.key: 2, self.protected.key: 1},
        )
        self.save_data = SaveData(gold=1_000)
        self.system = ShopSystem(
            shops=(self.shop,),
            inventory=self.inventory,
            party=self.party,
            save_data=self.save_data,
        )

    def test_buys_multiple_items_atomically(self) -> None:
        self.assertEqual(self.system.max_buy_quantity(self.shop, self.potion), 20)

        self.assertTrue(self.system.buy(self.shop, self.potion, 5))

        self.assertEqual(self.inventory.quantity(self.potion), 5)
        self.assertEqual(self.save_data.gold, 750)
        self.assertFalse(self.system.buy(self.shop, self.potion, 16))
        self.assertEqual(self.inventory.quantity(self.potion), 5)
        self.assertEqual(self.save_data.gold, 750)

    def test_equipped_item_reduces_purchase_capacity(self) -> None:
        equipped_party = (member(initial={EquipmentSlot.RIGHT: self.dagger}),)
        inventory = InventorySystem(self.items, {self.dagger.key: 7})
        system = ShopSystem(
            shops=(self.shop,),
            inventory=inventory,
            party=equipped_party,
            save_data=SaveData(gold=MAX_GOLD),
        )

        self.assertEqual(system.max_buy_quantity(self.shop, self.dagger), 1)
        self.assertTrue(system.buy(self.shop, self.dagger, 1))
        self.assertEqual(inventory.total_quantity(self.dagger, equipped_party), 9)
        self.assertFalse(system.buy(self.shop, self.dagger, 1))

    def test_sells_at_half_price_and_caps_gold_without_blocking_sale(self) -> None:
        self.assertEqual(self.system.sale_unit_price(self.rare), 100)
        self.assertEqual(self.system.max_sell_quantity(self.rare), 2)

        self.assertTrue(self.system.sell(self.rare, 2))

        self.assertEqual(self.inventory.quantity(self.rare), 0)
        self.assertEqual(self.save_data.gold, 1_200)

        capped_inventory = InventorySystem(self.items, {self.rare.key: 2})
        capped = ShopSystem(
            shops=(self.shop,),
            inventory=capped_inventory,
            party=self.party,
            save_data=SaveData(gold=MAX_GOLD - 50),
        )
        self.assertEqual(capped.max_sell_quantity(self.rare), 2)
        self.assertTrue(capped.sell(self.rare, 1))
        self.assertEqual(capped.save_data.gold, MAX_GOLD)
        self.assertEqual(capped.inventory.quantity(self.rare), 1)

    def test_price_zero_is_unsellable_and_global_non_stock_is_rare(self) -> None:
        self.assertFalse(self.system.can_sell(self.protected))
        self.assertEqual(self.system.max_sell_quantity(self.protected), 0)
        self.assertFalse(self.system.is_rare_sale(self.potion))
        self.assertTrue(self.system.is_rare_sale(self.rare))

    def test_sale_never_changes_fixed_shop_products(self) -> None:
        self.assertTrue(self.system.sell(self.rare, 1))
        self.assertEqual([item.key for item in self.shop.items], ["POTION", "DAGGER"])


if __name__ == "__main__":
    unittest.main()
