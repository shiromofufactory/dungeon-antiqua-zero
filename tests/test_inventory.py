from __future__ import annotations

import unittest
from dataclasses import replace

from app.item import Item
from app.member import EquipmentSlot, FormationRow, Member, ProficiencyKind
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
    reach: int = 0,
    defense: int = 0,
    special: str = "",
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
            "reach": reach,
            "dfc": defense,
            "eva": 0,
            "rst": 0,
            "tolerance": "",
            "special": special,
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

    def test_catalog_items_include_unowned_items_in_master_order(self) -> None:
        inventory = InventorySystem(self.items, {self.quest_item.key: 1})

        self.assertEqual(
            inventory.catalog_items,
            (self.potion, self.quest_item),
        )

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

    def test_record_equipment_preserves_history_and_deduplicates_shared_gear(self) -> None:
        dagger = equipment("DAGGER", "RIGHT", "KNIFE")
        robe = equipment("ROBE", "BODY", "GENERAL")
        first = member(initial={EquipmentSlot.RIGHT: dagger, EquipmentSlot.BODY: robe})
        second = member(initial={EquipmentSlot.BODY: robe})
        inventory = InventorySystem(
            {**self.items, dagger.key: dagger, robe.key: robe},
            recorded_keys=(self.potion.key,),
        )
        original_equipment = (first.equipment, second.equipment)

        inventory.record_equipment((first, second))
        inventory.record_equipment(member for member in (first, second))

        self.assertEqual(inventory.recorded_items, (self.potion, dagger, robe))
        self.assertEqual(inventory.recorded_count, 3)
        self.assertEqual(dict(inventory.quantities), {})
        self.assertEqual((first.equipment, second.equipment), original_equipment)
        self.assertEqual(inventory.total_quantity(robe, (first, second)), 2)

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

    def test_front_row_auto_equip_does_not_penalize_reach_two_weapon(self) -> None:
        dagger = equipment("DAGGER", "RIGHT", "KNIFE", attack=8, hit=105, reach=1)
        spear = equipment(
            "BRONZE SPEAR", "TWO_HANDS", "SPEAR", attack=12, hit=95, reach=2
        )
        actor = member(initial={EquipmentSlot.RIGHT: dagger})
        inventory = InventorySystem(
            {dagger.key: dagger, spear.key: spear}, {spear.key: 1}
        )

        self.assertTrue(actor.is_front_row)
        self.assertTrue(inventory.auto_equip(actor))
        self.assertIs(actor.equipment.item_at(EquipmentSlot.RIGHT), spear)
        self.assertEqual(inventory.quantity(dagger), 1)
        self.assertEqual(inventory.quantity(spear), 0)

    def test_auto_equip_accounts_for_cursed_necklace_penalties(self) -> None:
        necklace = Item.from_record({
            "name_en": "CURSED NECKLACE", "type1": "HEAD",
            "type2": "GENERAL", "rst": 5, "tolerance": "乱死",
            "atk": 0, "hit": 0, "dfc": 0, "eva": 0,
            "str": -2, "agi": -2,
        })
        cap = equipment("LEATHER CAP", "HEAD", "GENERAL", defense=2)
        hachimaki = Item.from_record({
            "name_en": "HACHIMAKI", "type1": "HEAD",
            "type2": "GENERAL", "dfc": 1, "tolerance": "眠",
            "atk": 0, "hit": 0, "rst": 0, "eva": 0,
        })
        actor = member(initial={EquipmentSlot.HEAD: necklace})
        inventory = InventorySystem(
            {gear.key: gear for gear in (necklace, cap, hachimaki)},
            {cap.key: 1, hachimaki.key: 1},
        )

        self.assertAlmostEqual(inventory._armor_score(necklace) - 0.01, -0.4)
        self.assertTrue(inventory.auto_equip(actor))
        self.assertIs(actor.equipment.item_at(EquipmentSlot.HEAD), hachimaki)
        self.assertEqual(inventory.quantity(necklace), 1)

    def test_auto_equip_preserves_two_handed_weapon_over_left_hand_candidates(self) -> None:
        axe = equipment(
            "GREAT AXE", "TWO_HANDS", "AXE", attack=50, hit=90, reach=1
        )
        knife = equipment(
            "MAGE MASHER", "RIGHT", "KNIFE", attack=28, hit=105, reach=1
        )
        sword = equipment(
            "GOBLIN SLAYER", "RIGHT", "SWORD", attack=19, hit=100, reach=1
        )
        shield = equipment("SHIELD", "LEFT", "SHIELD", defense=5)
        items = {gear.key: gear for gear in (axe, knife, sword, shield)}
        for dual_wield in (False, True):
            for row in FormationRow:
                for fixed in (False, True):
                    with self.subTest(dual_wield=dual_wield, row=row, fixed=fixed):
                        actor = member(
                            dual_wield=dual_wield,
                            character_type="NPC" if fixed else "SUB",
                            initial={EquipmentSlot.RIGHT: axe} if fixed else None,
                        )
                        actor.formation_row = row
                        inventory = InventorySystem(
                            items,
                            {gear.key: 1 for gear in (knife, sword, shield)}
                            | ({} if fixed else {axe.key: 1}),
                        )
                        # Reproduce the reported right-empty/left-knife state.
                        if dual_wield and not fixed:
                            self.assertTrue(inventory.equip(actor, EquipmentSlot.LEFT, knife))

                        for _ in range(2):
                            inventory.auto_equip(actor)

                            self.assertIs(actor.equipment.item_at(EquipmentSlot.RIGHT), axe)
                            self.assertIsNone(actor.equipment.item_at(EquipmentSlot.LEFT))
                            self.assertEqual(dict(inventory.quantities), {
                                knife.key: 1, sword.key: 1, shield.key: 1,
                            })
                            for gear in items.values():
                                self.assertEqual(inventory.total_quantity(gear, (actor,)), 1)

    def test_auto_equip_chooses_dual_wield_over_stronger_individual_weapon(self) -> None:
        axe = equipment("DWARVEN AXE", "TWO_HANDS", "AXE", attack=36, hit=90, reach=1)
        knife = equipment("MAGE MASHER", "RIGHT", "KNIFE", attack=28, hit=105, reach=1)
        katana = equipment("KATANA", "RIGHT", "KATANA", attack=23, hit=100, reach=1)
        actor = member(dual_wield=True, initial={EquipmentSlot.LEFT: knife})
        inventory = InventorySystem(
            {gear.key: gear for gear in (axe, knife, katana)},
            {axe.key: 1, katana.key: 1},
        )

        inventory.auto_equip(actor)

        self.assertIs(actor.equipment.item_at(EquipmentSlot.RIGHT), knife)
        self.assertIs(actor.equipment.item_at(EquipmentSlot.LEFT), katana)
        stats = actor.battle_stats
        self.assertEqual((stats.attack_right, stats.attack_left), (28, 18))
        self.assertEqual(dict(inventory.quantities), {axe.key: 1})

    def test_auto_equip_keeps_back_row_attack_in_range(self) -> None:
        throwing = equipment("DART", "RIGHT", "THROWING", attack=10, hit=100, reach=2)
        knife = equipment("KNIFE", "RIGHT", "KNIFE", attack=25, hit=100, reach=1)
        actor = member(dual_wield=True)
        actor.formation_row = FormationRow.BACK
        inventory = InventorySystem(
            {gear.key: gear for gear in (throwing, knife)},
            {throwing.key: 1, knife.key: 1},
        )

        inventory.auto_equip(actor)

        self.assertIs(actor.equipment.item_at(EquipmentSlot.RIGHT), throwing)
        self.assertIsNone(actor.equipment.item_at(EquipmentSlot.LEFT))

    def test_auto_equip_uses_armor_skill_and_counts_both_copies_of_weapon(self) -> None:
        sword = equipment("SWORD", "RIGHT", "SWORD", attack=20, hit=100)
        gloves = equipment("GLOVES", "ARM", "HEAVY", special="DUAL_WIELD")
        items = {gear.key: gear for gear in (sword, gloves)}
        for copies in (1, 2):
            with self.subTest(copies=copies):
                actor = member()
                inventory = InventorySystem(items, {sword.key: copies, gloves.key: 1})

                inventory.auto_equip(actor)

                self.assertIs(actor.equipment.item_at(EquipmentSlot.RIGHT), sword)
                self.assertIs(
                    actor.equipment.item_at(EquipmentSlot.LEFT),
                    sword if copies == 2 else None,
                )
                self.assertIs(actor.equipment.item_at(EquipmentSlot.ARM), gloves)
                self.assertEqual(inventory.total_quantity(sword, (actor,)), copies)

    def test_auto_equip_compares_two_handed_skill_bonus_against_shield(self) -> None:
        sword = equipment("SWORD", "RIGHT", "SWORD", attack=20, hit=100)
        shield = equipment("SHIELD", "LEFT", "SHIELD", defense=5)
        gloves = equipment("GLOVES", "ARM", "HEAVY", special="TWO_HANDED")
        items = {gear.key: gear for gear in (sword, shield, gloves)}
        actor = member()
        inventory = InventorySystem(items, {key: 1 for key in items})

        inventory.auto_equip(actor)

        self.assertIs(actor.equipment.item_at(EquipmentSlot.RIGHT), sword)
        self.assertIsNone(actor.equipment.item_at(EquipmentSlot.LEFT))
        self.assertEqual(actor.battle_stats.attack_right, 30)
        self.assertEqual(inventory.quantity(shield), 1)

    def test_auto_equip_keeps_left_hand_selection_for_one_handed_weapon(self) -> None:
        sword = equipment("SWORD", "RIGHT", "SWORD", attack=30, hit=100)
        knife = equipment("KNIFE", "RIGHT", "KNIFE", attack=20, hit=100)
        shield = equipment("SHIELD", "LEFT", "SHIELD", defense=5)
        items = {gear.key: gear for gear in (sword, knife, shield)}
        for dual_wield in (False, True):
            with self.subTest(dual_wield=dual_wield):
                actor = member(dual_wield=dual_wield)
                inventory = InventorySystem(items, {key: 1 for key in items})

                inventory.auto_equip(actor)

                self.assertIs(actor.equipment.item_at(EquipmentSlot.RIGHT), sword)
                self.assertIs(
                    actor.equipment.item_at(EquipmentSlot.LEFT),
                    knife if dual_wield else shield,
                )
                for gear in items.values():
                    self.assertEqual(inventory.total_quantity(gear, (actor,)), 1)

    def test_auto_equip_adds_each_signed_ability_modifier(self) -> None:
        for modifier in ("strength_modifier", "agility_modifier", "magic_modifier"):
            for value in (-2, 2):
                with self.subTest(modifier=modifier, value=value):
                    plain = equipment("PLAIN", "HEAD", "GENERAL", defense=2)
                    modified = replace(plain, key="MODIFIED", **{modifier: value})
                    actor = member()
                    inventory = InventorySystem(
                        {plain.key: plain, modified.key: modified},
                        {plain.key: 1, modified.key: 1},
                    )

                    inventory.auto_equip(actor)

                    self.assertIs(
                        actor.equipment.item_at(EquipmentSlot.HEAD),
                        modified if value > 0 else plain,
                    )

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

    def test_dual_wield_equipment_allows_a_left_hand_weapon(self) -> None:
        dagger = equipment("DAGGER", "RIGHT", "KNIFE", attack=8, hit=100)
        gloves = equipment(
            "SILVER GLOVES+",
            "ARM",
            "HEAVY",
            special="DUAL_WIELD",
        )
        actor = member(initial={EquipmentSlot.ARM: gloves})
        inventory = InventorySystem({dagger.key: dagger}, {dagger.key: 1})

        self.assertTrue(inventory.equip(actor, EquipmentSlot.LEFT, dagger))
        self.assertIs(actor.equipment.weapon_at(EquipmentSlot.LEFT), dagger)

    def test_removing_dual_wield_equipment_returns_left_weapon(self) -> None:
        dagger = equipment("DAGGER", "RIGHT", "KNIFE", attack=8, hit=100)
        gloves = equipment(
            "SILVER GLOVES+",
            "ARM",
            "HEAVY",
            special="DUAL_WIELD",
        )
        actor = member(
            initial={
                EquipmentSlot.LEFT: dagger,
                EquipmentSlot.ARM: gloves,
            }
        )
        inventory = InventorySystem(
            {dagger.key: dagger, gloves.key: gloves},
        )

        preview = inventory.preview_equipment(actor, EquipmentSlot.ARM, None)
        self.assertIsNotNone(preview)
        assert preview is not None
        self.assertIsNone(preview.item_at(EquipmentSlot.LEFT))

        self.assertTrue(inventory.equip(actor, EquipmentSlot.ARM, None))
        self.assertIsNone(actor.equipment.item_at(EquipmentSlot.LEFT))
        self.assertIsNone(actor.equipment.item_at(EquipmentSlot.ARM))
        self.assertEqual(inventory.quantity(dagger), 1)
        self.assertEqual(inventory.quantity(gloves), 1)

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
