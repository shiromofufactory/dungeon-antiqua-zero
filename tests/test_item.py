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
                "atk": 40,
                "hit": 108,
                "dfc": 2,
                "rst": 12,
                "tolerance": "炎冷炎止",
            }
        )

    def test_preserves_raw_english_name_as_lookup_key(self) -> None:
        self.assertEqual(self.item.key, "DAYBRINGER")

    def test_keeps_equipment_type_and_subtype(self) -> None:
        self.assertEqual(self.item.equip_type, ItemEquipType.RIGHT)
        self.assertEqual(self.item.subtype, "WAND")

    def test_keeps_battle_status_values(self) -> None:
        self.assertEqual(self.item.attack, 40)
        self.assertEqual(self.item.hit, 108)
        self.assertEqual(self.item.defense, 2)
        self.assertEqual(self.item.spell_resistance, 12)

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
            "rst": 12,
            "tolerance": "",
        }

        with self.assertRaisesRegex(ItemDataError, "atk"):
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
