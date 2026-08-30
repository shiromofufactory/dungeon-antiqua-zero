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

    def test_rejects_duplicate_keys(self) -> None:
        with self.assertRaises(TextCatalogError):
            TextCatalog.from_records(
                [
                    {"text_key": "same", "text_ja": "a"},
                    {"text_key": "same", "text_ja": "b"},
                ]
            )


if __name__ == "__main__":
    unittest.main()
