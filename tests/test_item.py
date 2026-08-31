from __future__ import annotations

import unittest

from app.item import Item, ItemDataError, ItemEquipType
from app.localization import Localizer
from app.resistance import ResistanceType
from app.state import Language


class ItemTest(unittest.TestCase):
    def setUp(self) -> None:
        self.item = Item.from_record(
            {
                "name_en": "DAYBRINGER",
                "name_ja": "デイブリンガー",
                "type1": "RIGHT",
                "type2": "WAND",
                "requirements": "LV9",
                "atk": 40,
                "hit": 108,
                "reach": 3,
                "dfc": 2,
                "eva": -5,
                "rst": 12,
                "str": 1,
                "agi": -2,
                "mag": 2,
                "healing": 1,
                "tolerance": "炎冷炎止",
            }
        )

    def test_preserves_raw_english_name_as_lookup_key(self) -> None:
        self.assertEqual(self.item.key, "DAYBRINGER")

    def test_keeps_equipment_type_and_subtype(self) -> None:
        self.assertEqual(self.item.equip_type, ItemEquipType.RIGHT)
        self.assertEqual(self.item.subtype, "WAND")

    def test_keeps_battle_status_values(self) -> None:
        self.assertEqual(self.item.requirement, "LV9")
        self.assertEqual(self.item.attack, 40)
        self.assertEqual(self.item.hit, 108)
        self.assertEqual(self.item.reach, 3)
        self.assertEqual(self.item.defense, 2)
        self.assertEqual(self.item.evasion, -5)
        self.assertEqual(self.item.spell_resistance, 12)
        self.assertEqual(self.item.strength_modifier, 1)
        self.assertEqual(self.item.agility_modifier, -2)
        self.assertEqual(self.item.magic_modifier, 2)
        self.assertEqual(self.item.healing, 1)

    def test_missing_optional_detail_fields_default_to_empty_or_zero(self) -> None:
        record = {
            "name_en": "POTION",
            "name_ja": "ポーション",
            "type1": "ITEM",
            "type2": "GENERAL",
            "atk": 0,
            "hit": 0,
            "dfc": 0,
            "eva": 0,
            "rst": 0,
            "tolerance": "",
        }

        item = Item.from_record(record)

        self.assertEqual(item.requirement, "")
        self.assertEqual(item.reach, 0)
        self.assertEqual(item.strength_modifier, 0)
        self.assertEqual(item.agility_modifier, 0)
        self.assertEqual(item.magic_modifier, 0)
        self.assertEqual(item.healing, 0)

    def test_preserves_negative_healing(self) -> None:
        record = {
            "name_en": "CURSED RING",
            "name_ja": "のろいのゆびわ",
            "type1": "ARM",
            "type2": "GENERAL",
            "atk": 0,
            "hit": 0,
            "dfc": 0,
            "eva": 0,
            "rst": 0,
            "healing": -1,
            "tolerance": "",
        }

        self.assertEqual(Item.from_record(record).healing, -1)

    def test_rejects_non_integer_healing(self) -> None:
        record = {
            "name_en": "CURSED RING",
            "name_ja": "のろいのゆびわ",
            "type1": "ARM",
            "type2": "GENERAL",
            "atk": 0,
            "hit": 0,
            "dfc": 0,
            "eva": 0,
            "rst": 0,
            "healing": -1.5,
            "tolerance": "",
        }

        with self.assertRaisesRegex(ItemDataError, "healing"):
            Item.from_record(record)

    def test_rejects_invalid_optional_detail_fields(self) -> None:
        base_record = {
            "name_en": "DAYBRINGER",
            "name_ja": "デイブリンガー",
            "type1": "RIGHT",
            "type2": "WAND",
            "atk": 40,
            "hit": 108,
            "dfc": 2,
            "eva": -5,
            "rst": 12,
            "tolerance": "",
        }
        invalid_values = {
            "requirements": 9,
            "reach": -1,
            "str": 1.5,
            "agi": False,
            "mag": "2",
        }

        for field, value in invalid_values.items():
            with self.subTest(field=field):
                record = dict(base_record)
                record[field] = value
                with self.assertRaisesRegex(ItemDataError, field):
                    Item.from_record(record)

    def test_parses_recognized_tolerances_as_unique_resistances(self) -> None:
        self.assertEqual(
            self.item.resistances,
            frozenset(
                (
                    ResistanceType.FIRE,
                    ResistanceType.FREEZE,
                    ResistanceType.STUN,
                )
            ),
        )

    def test_rejects_invalid_battle_status_value(self) -> None:
        record = {
            "name_en": "DAYBRINGER",
            "name_ja": "デイブリンガー",
            "type1": "RIGHT",
            "type2": "WAND",
            "atk": -1,
            "hit": 108,
            "dfc": 2,
            "eva": -5,
            "rst": 12,
            "tolerance": "",
        }

        with self.assertRaisesRegex(ItemDataError, "atk"):
            Item.from_record(record)

    def test_rejects_non_integer_evasion(self) -> None:
        record = {
            "name_en": "DAYBRINGER",
            "name_ja": "デイブリンガー",
            "type1": "RIGHT",
            "type2": "WAND",
            "atk": 40,
            "hit": 108,
            "dfc": 2,
            "eva": 1.5,
            "rst": 12,
            "tolerance": "",
        }

        with self.assertRaisesRegex(ItemDataError, "eva"):
            Item.from_record(record)

    def test_returns_localized_display_name(self) -> None:
        self.assertEqual(
            self.item.localized_name(Localizer(Language.JAPANESE)),
            "デイブリンガー",
        )
        self.assertEqual(
            self.item.localized_name(Localizer(Language.ENGLISH)),
            "ＤＡＹＢＲＩＮＧＥＲ",
        )
        self.assertEqual(
            self.item.localized_name(Localizer(Language.SIMPLIFIED_CHINESE)),
            "DAYBRINGER",
        )

    def test_rejects_missing_lookup_key(self) -> None:
        with self.assertRaises(ItemDataError):
            Item.from_record({"name_ja": "デイブリンガー"})


if __name__ == "__main__":
    unittest.main()
