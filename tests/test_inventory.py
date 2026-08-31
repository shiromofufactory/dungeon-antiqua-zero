from __future__ import annotations

import unittest

from app.item import Item
from app.systems import InventorySystem


def item(key: str, price: int) -> Item:
    return Item.from_record(
        {
            "name_en": key,
            "name_ja": key,
            "type1": "ITEM",
            "type2": "GENERAL",
            "price": price,
            "atk": 0,
            "hit": 0,
            "dfc": 0,
            "eva": 0,
            "rst": 0,
            "tolerance": "",
        }
    )


class InventorySystemTest(unittest.TestCase):
    def setUp(self) -> None:
        self.potion = item("POTION", 100)
        self.quest_item = item("QUEST ITEM", 0)
        self.items = {
            self.potion.key: self.potion,
            self.quest_item.key: self.quest_item,
        }

    def test_discards_one_owned_item_and_removes_zero_quantity(self) -> None:
        inventory = InventorySystem(
            self.items,
            {self.potion.key: 2, self.quest_item.key: 1},
        )

        self.assertTrue(inventory.discard(self.potion))
        self.assertEqual(inventory.quantity(self.potion), 1)
        self.assertTrue(inventory.discard(self.potion.key))
        self.assertEqual(inventory.quantity(self.potion), 0)
        self.assertEqual(inventory.items, (self.quest_item,))

    def test_price_zero_item_cannot_be_discarded(self) -> None:
        inventory = InventorySystem(self.items, {self.quest_item.key: 1})

        self.assertFalse(inventory.can_discard(self.quest_item))
        self.assertFalse(inventory.discard(self.quest_item))
        self.assertEqual(inventory.quantity(self.quest_item), 1)

    def test_discarded_item_remains_in_recorded_items(self) -> None:
        inventory = InventorySystem(self.items, {self.potion.key: 1})

        self.assertTrue(inventory.discard(self.potion))

        self.assertEqual(inventory.items, ())
        self.assertEqual(inventory.recorded_items, (self.potion,))
        self.assertEqual(inventory.recorded_count, 1)
        self.assertEqual(inventory.catalog_count, 2)

    def test_unowned_item_cannot_be_discarded(self) -> None:
        inventory = InventorySystem(self.items)

        self.assertFalse(inventory.can_discard(self.potion))
        self.assertFalse(inventory.discard(self.potion))


if __name__ == "__main__":
    unittest.main()
