from __future__ import annotations

import unittest

from app.item import Item
from app.shop import Shop, ShopDataError


def make_item(key: str, *, price: int = 100, equip_type: str = "ITEM") -> Item:
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


class ShopTest(unittest.TestCase):
    def test_resolves_fixed_products_in_authored_order(self) -> None:
        potion = make_item("POTION")
        dagger = make_item("DAGGER", equip_type="RIGHT")

        shop = Shop.from_record(
            {
                "shop_key": "TEST_SHOP",
                "items": ["DAGGER", "POTION"],
                "note": "test",
            },
            {potion.key: potion, dagger.key: dagger},
        )

        self.assertEqual(shop.key, "TEST_SHOP")
        self.assertEqual([item.key for item in shop.items], ["DAGGER", "POTION"])
        self.assertEqual(shop.note, "test")

    def test_rejects_unknown_and_duplicate_products(self) -> None:
        potion = make_item("POTION")
        with self.assertRaises(ShopDataError):
            Shop.from_record(
                {"shop_key": "TEST", "items": ["UNKNOWN"]},
                {potion.key: potion},
            )
        with self.assertRaises(ShopDataError):
            Shop.from_record(
                {"shop_key": "TEST", "items": ["POTION", "POTION"]},
                {potion.key: potion},
            )


if __name__ == "__main__":
    unittest.main()
