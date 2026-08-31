from __future__ import annotations

import unittest

from app.localization import Localizer
from app.state import Language
from app.text_catalog import TextCatalog, TextCatalogError


class TextCatalogTest(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = TextCatalog.from_records(
            [
                {
                    "text_key": "race.FAIRY",
                    "text_ja": "ようせい",
                    "text_en": "Fairy",
                    "text_zhcn": "妖精",
                }
            ]
        )

    def test_resolves_text_for_selected_language(self) -> None:
        self.assertEqual(
            self.catalog.text(
                "race.FAIRY",
                Localizer(Language.SIMPLIFIED_CHINESE),
            ),
            "妖精",
        )

    def test_missing_key_returns_explicit_default(self) -> None:
        self.assertEqual(
            self.catalog.text(
                "race.UNKNOWN",
                Localizer(Language.JAPANESE),
                default="?",
            ),
            "？",
        )

    def test_english_default_is_normalized_for_display(self) -> None:
        self.assertEqual(
            self.catalog.text(
                "race.UNKNOWN",
                Localizer(Language.ENGLISH),
                default="Unknown?",
            ),
            "Ｕｎｋｎｏｗｎ？",
        )

    def test_formats_da2_numbered_placeholders_before_display_normalization(self) -> None:
        catalog = TextCatalog.from_records(
            [
                {
                    "text_key": "item.drop.confirm",
                    "text_ja": "&1 を すてますか？",
                    "text_en": "Drop &1?",
                    "text_zhcn": "要丢弃&1吗？",
                }
            ]
        )

        self.assertEqual(
            catalog.formatted_text(
                "item.drop.confirm",
                Localizer(Language.JAPANESE),
                "ポーション",
            ),
            "ポーション　を　すてますか？",
        )
        self.assertEqual(
            catalog.formatted_text(
                "item.drop.confirm",
                Localizer(Language.ENGLISH),
                "Potion",
            ),
            "Ｄｒｏｐ　Ｐｏｔｉｏｎ？",
        )

    def test_resolves_one_or_more_lines_from_string_or_array(self) -> None:
        catalog = TextCatalog.from_records(
            [
                {
                    "text_key": "single",
                    "text_ja": "1ぎょう",
                    "text_en": "One line",
                    "text_zhcn": "一行",
                },
                {
                    "text_key": "multiple",
                    "text_ja": ["1ぎょうめ", "2ぎょうめ"],
                    "text_en": ["First", "Second"],
                    "text_zhcn": ["第一行", "第二行"],
                },
            ]
        )

        self.assertEqual(
            catalog.lines("single", Localizer(Language.JAPANESE)),
            ("１ぎょう",),
        )
        self.assertEqual(
            catalog.lines("multiple", Localizer(Language.JAPANESE)),
            ("１ぎょうめ", "２ぎょうめ"),
        )

    def test_lines_fall_back_when_selected_language_array_is_empty(self) -> None:
        catalog = TextCatalog.from_records(
            [
                {
                    "text_key": "guide",
                    "text_ja": ["こうれつからも", "こうげきかのう"],
                    "text_en": [],
                    "text_zhcn": "",
                }
            ]
        )

        self.assertEqual(
            catalog.lines("guide", Localizer(Language.ENGLISH)),
            ("こうれつからも", "こうげきかのう"),
        )

    def test_rejects_duplicate_keys(self) -> None:
        with self.assertRaises(TextCatalogError):
            TextCatalog.from_records(
                [
                    {"text_key": "same", "text_ja": "a"},
                    {"text_key": "same", "text_ja": "b"},
                ]
            )

    def test_rejects_non_string_text_array_values(self) -> None:
        with self.assertRaisesRegex(TextCatalogError, "array of strings"):
            TextCatalog.from_records(
                [
                    {
                        "text_key": "invalid",
                        "text_ja": ["line", 2],
                    }
                ]
            )


if __name__ == "__main__":
    unittest.main()
