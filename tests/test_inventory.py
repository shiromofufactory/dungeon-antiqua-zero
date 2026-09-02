from __future__ import annotations

import unittest

from app.item import Item
from app.member import EquipmentSlot, Member, ProficiencyKind
from app.skill import Skill
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


def equipment(
    key: str,
    equip_type: str,
    subtype: str,
    *,
    attack: int = 0,
    hit: int = 0,
    defense: int = 0,
) -> Item:
    return Item.from_record(
        {
            "name_en": key,
            "name_ja": key,
            "type1": equip_type,
            "type2": subtype,
            "price": 100,
            "atk": attack,
            "hit": hit,
            "dfc": defense,
            "eva": 0,
            "rst": 0,
            "tolerance": "",
        }
    )


def member(
    *,
    character_type: str = "SUB",
    initial: dict[EquipmentSlot, Item] | None = None,
    dual_wield: bool = False,
) -> Member:
    items = {item.key: item for item in (initial or {}).values()}
    skills = {"Dual-Wield": Skill.from_record({"name_en": "Dual-Wield"})}
    record = {
        "name_en": "Tester",
        "type": character_type,
        "race": "HUMAN",
        "gender": "MALE",
        "skills": ["Dual-Wield"] if dual_wield else [],
        "lv_diff": 0,
        "base_hp": 40,
        "base_mp": 0,
        "base_str": 20,
        "base_agi": 20,
        "base_mag": 20,
        "face_x": 0,
        "face_y": 0,
        **{kind.value: 1 for kind in ProficiencyKind},
    }
    for slot in EquipmentSlot:
        record[f"equip_{slot.value.lower()}"] = (
            initial[slot].key if initial and slot in initial else ""
        )
    return Member.from_record(record, items=items, skills=skills)


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

    def test_item_and_equipment_stack_limits_are_enforced(self) -> None:
        dagger = equipment("DAGGER", "RIGHT", "KNIFE")

        consumables = InventorySystem(self.items, {self.potion.key: 99})
        equipment_inventory = InventorySystem({dagger.key: dagger}, {dagger.key: 9})

        self.assertFalse(consumables.add(self.potion))
        self.assertFalse(equipment_inventory.add(dagger))
        with self.assertRaises(ValueError):
            InventorySystem(self.items, {self.potion.key: 100})
        with self.assertRaises(ValueError):
            InventorySystem({dagger.key: dagger}, {dagger.key: 10})

    def test_multiple_add_and_remove_are_atomic(self) -> None:
        inventory = InventorySystem(self.items, {self.potion.key: 95})

        self.assertTrue(inventory.add(self.potion, 4))
        self.assertEqual(inventory.quantity(self.potion), 99)
        self.assertFalse(inventory.add(self.potion, 2))
        self.assertEqual(inventory.quantity(self.potion), 99)
        self.assertTrue(inventory.remove(self.potion, 98))
        self.assertEqual(inventory.quantity(self.potion), 1)
        self.assertFalse(inventory.remove(self.potion, 2))
        self.assertEqual(inventory.quantity(self.potion), 1)

    def test_equipped_copies_count_toward_equipment_limit(self) -> None:
        dagger = equipment("DAGGER", "RIGHT", "KNIFE")
        actor = member(initial={EquipmentSlot.RIGHT: dagger})
        inventory = InventorySystem({dagger.key: dagger}, {dagger.key: 8})

        self.assertEqual(inventory.equipped_quantity(dagger, (actor,)), 1)
        self.assertEqual(inventory.total_quantity(dagger, (actor,)), 9)
        self.assertEqual(inventory.remaining_capacity(dagger, (actor,)), 0)
        self.assertFalse(inventory.add(dagger, members=(actor,)))

        self.assertTrue(inventory.equip(actor, EquipmentSlot.RIGHT, None))
        self.assertEqual(inventory.quantity(dagger), 9)
        self.assertEqual(inventory.total_quantity(dagger, (actor,)), 9)

    def test_loaded_total_quantity_rejects_inventory_plus_equipment_over_limit(self) -> None:
        dagger = equipment("DAGGER", "RIGHT", "KNIFE")
        actor = member(initial={EquipmentSlot.RIGHT: dagger})
        inventory = InventorySystem({dagger.key: dagger}, {dagger.key: 9})

        with self.assertRaises(ValueError):
            inventory.validate_total_quantities((actor,))

    def test_equipment_exchange_returns_old_item_to_inventory(self) -> None:
        dagger = equipment("DAGGER", "RIGHT", "KNIFE", attack=8, hit=100)
        sword = equipment("SWORD", "RIGHT", "SWORD", attack=20, hit=100)
        actor = member(initial={EquipmentSlot.RIGHT: dagger})
        inventory = InventorySystem(
            {dagger.key: dagger, sword.key: sword},
            {sword.key: 1},
        )

        self.assertTrue(inventory.equip(actor, EquipmentSlot.RIGHT, sword))

        self.assertIs(actor.equipment.item_at(EquipmentSlot.RIGHT), sword)
        self.assertEqual(inventory.quantity(sword), 0)
        self.assertEqual(inventory.quantity(dagger), 1)

    def test_two_handed_weapon_returns_left_item_to_inventory(self) -> None:
        spear = equipment("SPEAR", "TWO_HANDS", "SPEAR", attack=20, hit=95)
        shield = equipment("SHIELD", "LEFT", "SHIELD", defense=5)
        actor = member(initial={EquipmentSlot.LEFT: shield})
        inventory = InventorySystem(
            {spear.key: spear, shield.key: shield},
            {spear.key: 1},
        )

        self.assertTrue(inventory.equip(actor, EquipmentSlot.RIGHT, spear))

        self.assertIs(actor.equipment.item_at(EquipmentSlot.RIGHT), spear)
        self.assertIsNone(actor.equipment.item_at(EquipmentSlot.LEFT))
        self.assertEqual(inventory.quantity(shield), 1)

    def test_left_hand_weapon_requires_dual_wield(self) -> None:
        dagger = equipment("DAGGER", "RIGHT", "KNIFE", attack=8, hit=100)
        inventory = InventorySystem({dagger.key: dagger}, {dagger.key: 1})

        self.assertFalse(
            inventory.can_equip(member(), EquipmentSlot.LEFT, dagger)
        )
        self.assertTrue(
            inventory.can_equip(
                member(dual_wield=True),
                EquipmentSlot.LEFT,
                dagger,
            )
        )

    def test_only_npc_initial_equipment_is_fixed(self) -> None:
        dagger = equipment("DAGGER", "RIGHT", "KNIFE", attack=8, hit=100)
        helm = equipment("HELM", "HEAD", "GENERAL", defense=3)
        actor = member(
            character_type="NPC",
            initial={EquipmentSlot.RIGHT: dagger},
        )
        inventory = InventorySystem(
            {dagger.key: dagger, helm.key: helm},
            {helm.key: 1},
        )

        self.assertTrue(actor.is_equipment_fixed(EquipmentSlot.RIGHT))
        self.assertFalse(actor.is_equipment_fixed(EquipmentSlot.HEAD))
        self.assertFalse(inventory.can_equip(actor, EquipmentSlot.RIGHT, None))
        self.assertFalse(inventory.equip(actor, EquipmentSlot.RIGHT, None))
        self.assertTrue(inventory.equip(actor, EquipmentSlot.HEAD, helm))
        self.assertFalse(actor.is_equipment_fixed(EquipmentSlot.HEAD))
        self.assertTrue(inventory.can_equip(actor, EquipmentSlot.HEAD, None))
        self.assertTrue(inventory.equip(actor, EquipmentSlot.HEAD, None))
        self.assertIs(actor.equipment.item_at(EquipmentSlot.RIGHT), dagger)
        self.assertIsNone(actor.equipment.item_at(EquipmentSlot.HEAD))
        self.assertEqual(inventory.quantity(helm), 1)

    def test_npc_auto_equip_preserves_initial_and_replaces_added_gear(self) -> None:
        dagger = equipment("DAGGER", "RIGHT", "KNIFE", attack=8, hit=100)
        leather = equipment("LEATHER HELM", "HEAD", "GENERAL", defense=1)
        plate = equipment("PLATE HELM", "HEAD", "GENERAL", defense=5)
        actor = member(
            character_type="NPC",
            initial={EquipmentSlot.RIGHT: dagger},
        )
        inventory = InventorySystem(
            {
                dagger.key: dagger,
                leather.key: leather,
                plate.key: plate,
            },
            {leather.key: 1, plate.key: 1},
        )
        self.assertTrue(inventory.equip(actor, EquipmentSlot.HEAD, leather))

        self.assertTrue(inventory.auto_equip(actor))

        self.assertIs(actor.equipment.item_at(EquipmentSlot.RIGHT), dagger)
        self.assertIs(actor.equipment.item_at(EquipmentSlot.HEAD), plate)
        self.assertEqual(inventory.quantity(leather), 1)
        self.assertEqual(inventory.quantity(plate), 0)


if __name__ == "__main__":
    unittest.main()
