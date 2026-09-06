from __future__ import annotations

import unittest

from app.item import Item
from app.resources import MapActor, MapCell, MapTreasureContents
from app.state import SaveData
from app.systems import (
    InventorySystem,
    TreasureOpenStatus,
    TreasureSystem,
)


def item(key: str) -> Item:
    return Item.from_record(
        {
            "name_en": key,
            "name_ja": key,
            "type1": "ITEM",
            "type2": "GENERAL",
            "price": 10,
            "atk": 0,
            "hit": 0,
            "dfc": 0,
            "eva": 0,
            "rst": 0,
            "tolerance": "",
        }
    )


class TreasureSystemTest(unittest.TestCase):
    def setUp(self) -> None:
        self.potion = item("POTION")
        self.save_data = SaveData(gold=100)
        self.inventory = InventorySystem({self.potion.key: self.potion})
        self.system = TreasureSystem(
            save_data=self.save_data,
            inventory=self.inventory,
        )

    @staticmethod
    def actor(contents: MapTreasureContents) -> MapActor:
        return MapActor(
            "entrance_treasure",
            MapCell(2, 3),
            "treasure",
            0,
            contents=contents,
        )

    def test_adds_all_gold_and_records_the_opened_treasure(self) -> None:
        status = self.system.open(
            "nectar_forest",
            self.actor(MapTreasureContents("gold", amount=500)),
        )

        self.assertIs(status, TreasureOpenStatus.OPENED)
        self.assertEqual(self.save_data.gold, 600)
        self.assertEqual(
            self.save_data.opened_treasures,
            {("nectar_forest", "entrance_treasure")},
        )

    def test_rejects_gold_overflow_without_partial_changes(self) -> None:
        self.save_data.gold = 999_900

        status = self.system.open(
            "nectar_forest",
            self.actor(MapTreasureContents("gold", amount=500)),
        )

        self.assertIs(status, TreasureOpenStatus.CAPACITY_EXCEEDED)
        self.assertEqual(self.save_data.gold, 999_900)
        self.assertEqual(self.save_data.opened_treasures, set())

    def test_adds_one_item_and_records_it_in_the_item_catalog(self) -> None:
        status = self.system.open(
            "nectar_forest",
            self.actor(MapTreasureContents("item", item_key="POTION")),
        )

        self.assertIs(status, TreasureOpenStatus.OPENED)
        self.assertEqual(self.inventory.quantity("POTION"), 1)
        self.assertEqual(self.inventory.recorded_items, (self.potion,))

    def test_rejects_an_item_at_its_ownership_limit(self) -> None:
        inventory = InventorySystem(
            {self.potion.key: self.potion},
            {self.potion.key: 99},
        )
        system = TreasureSystem(save_data=self.save_data, inventory=inventory)

        status = system.open(
            "nectar_forest",
            self.actor(MapTreasureContents("item", item_key="POTION")),
        )

        self.assertIs(status, TreasureOpenStatus.CAPACITY_EXCEEDED)
        self.assertEqual(inventory.quantity("POTION"), 99)
        self.assertEqual(self.save_data.opened_treasures, set())

    def test_opened_treasure_is_a_no_op(self) -> None:
        actor = self.actor(MapTreasureContents("gold", amount=500))
        self.assertIs(
            self.system.open("nectar_forest", actor),
            TreasureOpenStatus.OPENED,
        )

        status = self.system.open("nectar_forest", actor)

        self.assertIs(status, TreasureOpenStatus.ALREADY_OPENED)
        self.assertEqual(self.save_data.gold, 600)


if __name__ == "__main__":
    unittest.main()
