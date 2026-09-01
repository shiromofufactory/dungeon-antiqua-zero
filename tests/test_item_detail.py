from __future__ import annotations

import unittest

from app.item import Item
from app.item_detail import (
    ItemDetailContext,
    ItemDetailError,
    build_item_detail,
)
from app.localization import Localizer
from app.resources import load_record_array
from app.spell import Spell
from app.state import Language
from app.text_catalog import TextCatalog


class ItemDetailTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.items = {
            item.key: item
            for record in load_record_array("items.json")
            for item in (Item.from_record(record),)
        }
        cls.spells = {
            spell.key: spell
            for record in load_record_array("spells.json")
            for spell in (Spell.from_record(record),)
        }
        cls.texts = TextCatalog.from_records(load_record_array("texts.json"))
        cls.localizer = Localizer(Language.JAPANESE)

    def detail(
        self,
        item_key: str,
        context: ItemDetailContext = ItemDetailContext.MENU,
    ):
        return build_item_detail(
            self.items[item_key],
            self.spells,
            self.localizer,
            self.texts,
            context=context,
        )

    def test_normal_consumable_shows_effect_description_without_spell_or_break(self) -> None:
        detail = self.detail("POTION")

        self.assertEqual(
            detail.lines,
            (
                "きずぐすり",
                "どうぐ",
                "",
                "みかたひとりの　きずを",
                "かいふく（ばいりつ：３０）",
            ),
        )
        self.assertNotIn("こわれる", "".join(detail.lines))

    def test_consumable_referencing_normal_spell_still_omits_spell_name(self) -> None:
        lines = self.detail("REMEDY").lines

        self.assertFalse(any("キュアー" in line for line in lines))
        self.assertTrue(any("ちりょうする" in line for line in lines))

    def test_spell_book_shows_normal_spell_name_and_description(self) -> None:
        lines = self.detail("BOOK of FIRE").lines

        self.assertIn("つかうと%MYSTIC%ファイア１", lines)
        self.assertIn("てき１たいに%FIRE%ほのおぞくせいの", lines)
        description_index = lines.index("てき１たいに%FIRE%ほのおぞくせいの")
        self.assertEqual(lines[description_index - 1], "")
        self.assertNotIn("（こわれる）", lines)

    def test_equipment_shows_icon_and_spell_name_without_effect_description(self) -> None:
        expected = {
            "WAND of FIRE": "つかうと%MYSTIC%ファイア２",
            "ROD of SILENCE": "つかうと%SACRED%サイレンス",
            "ROD of DISCORD": "つかうと%NETHER%コンフュージョン",
            "WAND of DARK": "つかうと%NETHER%ブラッドサック",
        }

        for item_key, use_line in expected.items():
            with self.subTest(item=item_key):
                item = self.items[item_key]
                spell = self.spells[item.use_spell_key]
                lines = self.detail(item_key).lines
                self.assertIn(use_line, lines)
                self.assertFalse(
                    set(spell.localized_description(self.localizer)) & set(lines)
                )

    def test_only_breakable_equipment_displays_breakage(self) -> None:
        teleport = self.detail("TELEPORT RING").lines

        self.assertIn("つかうと%MYSTIC%テレポート", teleport)
        self.assertFalse(any("まほうじん" in line for line in teleport))
        self.assertTrue(any("（こわれる）" in line for line in teleport))
        for key, item in self.items.items():
            if item.equip_type.value == "ITEM" or key == "TELEPORT RING":
                continue
            with self.subTest(item=key):
                self.assertFalse(
                    any(
                        "（こわれる）" in line
                        for line in self.detail(key).lines
                    )
                )

    def test_spell_resistance_uses_item_detail_text_key(self) -> None:
        records = load_record_array("texts.json")
        for record in records:
            if record.get("text_key") == "item.detail.spell_resistance":
                record["text_ja"] = "アイテムせんよう"
            elif record.get("text_key") == "status.spell_resistance":
                record["text_ja"] = "ステータスせんよう"
        texts = TextCatalog.from_records(records)

        detail = build_item_detail(
            self.items["EAN SI MANTLE"],
            self.spells,
            self.localizer,
            texts,
        )

        self.assertIn("アイテムせんよう：１０", detail.lines)
        self.assertNotIn("ステータスせんよう：１０", detail.lines)

    def test_defined_special_texts_are_shown_with_converted_color_tags(self) -> None:
        expected = {
            "ORDEAL RING": (
                "かくとくできる",
                "じゅくれんどが　２ばいになる",
            ),
            "DAYBRINGER": (
                "たまに　%COL_BLUE%かいしん%COL_END%はつどう",
            ),
            "SILVER GLOVES+": (
                "ぶきの　%COL_BLUE%にとうりゅう%COL_END%　が",
                "かのうに　なる",
            ),
            "MIRROR SHIELD": (
                "じゅもんを　たまにはんしゃ",
            ),
        }

        for item_key, special_lines in expected.items():
            with self.subTest(item=item_key):
                lines = self.detail(item_key).lines
                for special_line in special_lines:
                    self.assertIn(special_line, lines)

    def test_pending_special_text_is_omitted_until_authored(self) -> None:
        lines = self.detail("FALCON DAGGER").lines

        self.assertFalse(any("ATK_REDUCE_WT" in line for line in lines))

    def test_resistance_follows_attribute_and_additional_effect(self) -> None:
        lines = self.detail("CHIZAKURA!").lines

        self.assertEqual(
            lines[5:8],
            (
                "ぞくせい　　：%DARK%やみ",
                "ついかこうか：きゅうしゅう",
                "%DARK%やみを　ふせぐ",
            ),
        )

    def test_healing_and_special_are_the_last_item_traits(self) -> None:
        lines = self.detail("DAYBRINGER").lines

        self.assertEqual(
            lines[-2:],
            (
                "ＨＰ　じどうかいふく",
                "たまに　%COL_BLUE%かいしん%COL_END%はつどう",
            ),
        )
        self.assertLess(lines.index("%DEATH%そくしを　ふせぐ"), len(lines) - 2)

    def test_common_condition_term_is_used_by_effect_and_resistance_templates(self) -> None:
        records = load_record_array("texts.json")
        for record in records:
            if record.get("text_key") == "term.condition.POISON":
                record["text_ja"] = "%POISON%きょうつう"
        texts = TextCatalog.from_records(records)

        effect = build_item_detail(
            self.items["MACE of SNAKE"],
            self.spells,
            self.localizer,
            texts,
        )
        resistance = build_item_detail(
            self.items["EAN SI MANTLE"],
            self.spells,
            self.localizer,
            texts,
        )

        self.assertIn("ついかこうか：%POISON%きょうつう", effect.lines)
        self.assertIn("%POISON%きょうつうを　ふせぐ", resistance.lines)

    def test_additional_effects_use_shared_terms_with_available_icons(self) -> None:
        expected = {
            "SLEEP BLADE": "ついかこうか：%SLEEP%ねむり",
            "TYRFING": "ついかこうか：%CONFUSE%こんらん",
            "ELIKA": "ついかこうか：%DEATH%そくし",
            "MAGE MASHER": "ついかこうか：%SILENCE%ちんもく",
            "MACE of SNAKE": "ついかこうか：%POISON%どく",
        }

        for item_key, effect_line in expected.items():
            with self.subTest(item=item_key):
                self.assertIn(effect_line, self.detail(item_key).lines)

    def test_repeated_item_detail_sentences_are_templates_not_per_term_keys(self) -> None:
        keys = {
            record["text_key"] for record in load_record_array("texts.json")
        }

        self.assertIn("item.detail.attribute", keys)
        self.assertIn("item.detail.additional_effect", keys)
        self.assertIn("item.detail.resistance", keys)
        self.assertIn("item.detail.effective_tribe", keys)
        self.assertIn("item.detail.requirement.only", keys)
        self.assertIn("item.detail.requirement.excludes", keys)
        self.assertFalse(
            any(
                key.startswith(
                    (
                        "item.detail.attribute.",
                        "item.detail.additional_effect.",
                        "item.detail.resistance.",
                        "item.detail.tribe.",
                    )
                )
                for key in keys
            )
        )
        self.assertFalse(
            any(
                key.startswith("item.detail.requirement.ONLY_")
                and key != "item.detail.requirement.ONLY_RAGNA"
                for key in keys
            )
        )
        self.assertFalse(
            any(key.startswith("item.detail.requirement.NO_") for key in keys)
        )

    def test_price_and_source_are_exposed_only_to_shop_context(self) -> None:
        menu = self.detail("POTION")
        shop = self.detail("POTION", ItemDetailContext.SHOP)
        battle = self.detail("POTION", ItemDetailContext.BATTLE)

        self.assertIsNone(menu.price)
        self.assertIsNone(menu.source)
        self.assertEqual(shop.price, 50)
        self.assertEqual(shop.source, "店売り")
        self.assertIsNone(battle.price)
        self.assertIsNone(battle.source)

    def test_battle_context_contains_only_use_effect_lines(self) -> None:
        menu = self.detail("BOOK of FIRE")
        battle = self.detail("BOOK of FIRE", ItemDetailContext.BATTLE)

        self.assertNotIn("ほのおのしょ", battle.lines)
        self.assertNotIn("どうぐ", battle.lines)
        self.assertEqual(battle.lines, menu.lines[-4:])

    def test_rejects_undefined_use_spell(self) -> None:
        item = Item.from_record(
            {
                "name_en": "UNKNOWN EFFECT",
                "name_ja": "なぞのどうぐ",
                "type1": "ITEM",
                "type2": "ITEM",
                "use": "MISSING",
                "atk": 0,
                "hit": 0,
                "dfc": 0,
                "eva": 0,
                "rst": 0,
                "tolerance": "",
            }
        )

        with self.assertRaisesRegex(ItemDetailError, "MISSING"):
            build_item_detail(
                item,
                self.spells,
                self.localizer,
                self.texts,
            )


if __name__ == "__main__":
    unittest.main()
