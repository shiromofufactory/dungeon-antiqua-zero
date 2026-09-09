from __future__ import annotations

import unittest

from app.item import (
    AdditionalEffect,
    AttackAttribute,
    Item,
    ItemDataError,
    ItemEquipType,
    ItemSpecial,
)
from app.localization import Localizer
from app.monster import MonsterTribe
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
                "price": 60000,
                "use": "FIRE2",
                "weapon_img": "WAND-1",
                "break": 0,
                "source": "ようせいのさと",
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
                "attr": "炎",
                "extra": "破",
                "race": "DEMON",
                "special": "POWER_HIT",
            }
        )

    def test_preserves_raw_english_name_as_lookup_key(self) -> None:
        self.assertEqual(self.item.key, "DAYBRINGER")

    def test_keeps_equipment_type_and_subtype(self) -> None:
        self.assertEqual(self.item.equip_type, ItemEquipType.RIGHT)
        self.assertEqual(self.item.subtype, "WAND")

    def test_keeps_battle_status_values(self) -> None:
        self.assertEqual(self.item.requirement, "LV9")
        self.assertEqual(self.item.price, 60000)
        self.assertEqual(self.item.use_spell_key, "FIRE2")
        self.assertEqual(self.item.weapon_img, "WAND-1")
        self.assertFalse(self.item.breaks_on_use)
        self.assertEqual(self.item.source, "ようせいのさと")
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
        self.assertIs(self.item.attack_attribute, AttackAttribute.FIRE)
        self.assertIs(
            self.item.additional_effect,
            AdditionalEffect.DEFENSE_DOWN,
        )
        self.assertIs(self.item.effective_tribe, MonsterTribe.DEMON)
        self.assertIs(self.item.special, ItemSpecial.POWER_HIT)

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
        self.assertEqual(item.price, 0)
        self.assertEqual(item.use_spell_key, "")
        self.assertEqual(item.weapon_img, "")
        self.assertFalse(item.breaks_on_use)
        self.assertEqual(item.source, "")
        self.assertEqual(item.reach, 0)
        self.assertEqual(item.strength_modifier, 0)
        self.assertEqual(item.agility_modifier, 0)
        self.assertEqual(item.magic_modifier, 0)
        self.assertEqual(item.healing, 0)
        self.assertIsNone(item.attack_attribute)
        self.assertIsNone(item.additional_effect)
        self.assertIsNone(item.effective_tribe)
        self.assertIsNone(item.special)

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
            "attr": "光",
            "extra": "転",
            "race": "DEAMON",
            "price": -1,
            "use": 1,
            "break": 2,
            "source": [],
            "special": "UNKNOWN",
        }

        for field, value in invalid_values.items():
            with self.subTest(field=field):
                record = dict(base_record)
                record[field] = value
                with self.assertRaisesRegex(ItemDataError, field):
                    Item.from_record(record)

    def test_identifies_only_explicit_item_subtype_as_spell_book(self) -> None:
        base_record = {
            "name_en": "BOOK of FIRE",
            "name_ja": "ほのおのしょ",
            "type1": "ITEM",
            "type2": "BOOK",
            "atk": 0,
            "hit": 0,
            "dfc": 0,
            "eva": 0,
            "rst": 0,
            "tolerance": "",
        }

        self.assertTrue(Item.from_record(base_record).is_spell_book)
        self.assertFalse(
            Item.from_record({**base_record, "type2": "ITEM"}).is_spell_book
        )

    def test_parses_every_current_attribute_effect_and_monster_tribe(self) -> None:
        attributes = {
            "炎": AttackAttribute.FIRE,
            "冷": AttackAttribute.FREEZE,
            "闇": AttackAttribute.DARK,
        }
        effects = {
            "眠": AdditionalEffect.SLEEP,
            "乱": AdditionalEffect.CONFUSE,
            "死": AdditionalEffect.DEATH,
            "黙": AdditionalEffect.SILENCE,
            "吸": AdditionalEffect.DRAIN,
            "止": AdditionalEffect.STUN,
            "毒": AdditionalEffect.POISON,
            "麻": AdditionalEffect.PARALIZE,
            "破": AdditionalEffect.DEFENSE_DOWN,
        }
        base_record = {
            "name_en": "TEST",
            "name_ja": "テスト",
            "type1": "RIGHT",
            "type2": "SWORD",
            "atk": 1,
            "hit": 1,
            "dfc": 0,
            "eva": 0,
            "rst": 0,
            "tolerance": "",
        }

        for code, expected in attributes.items():
            with self.subTest(attribute=code):
                item = Item.from_record({**base_record, "attr": code})
                self.assertIs(item.attack_attribute, expected)
        for code, expected in effects.items():
            with self.subTest(effect=code):
                item = Item.from_record({**base_record, "extra": code})
                self.assertIs(item.additional_effect, expected)
        for tribe in MonsterTribe:
            with self.subTest(tribe=tribe):
                item = Item.from_record({**base_record, "race": tribe.value})
                self.assertIs(item.effective_tribe, tribe)
        for special in ItemSpecial:
            with self.subTest(special=special):
                item = Item.from_record({**base_record, "special": special.value})
                self.assertIs(item.special, special)

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
