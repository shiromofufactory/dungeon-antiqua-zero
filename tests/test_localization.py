from __future__ import annotations

import unittest

from app.localization import Localizer, ascii_to_fullwidth, language_candidates
from app.state import Language


class LocalizationTest(unittest.TestCase):
    def test_printable_ascii_is_converted_to_fullwidth(self) -> None:
        self.assertEqual(
            ascii_to_fullwidth("Hello, world! 123 /+-:*#()[]&"),
            "Ｈｅｌｌｏ，　ｗｏｒｌｄ！　１２３　／＋－：＊＃（）［］＆",
        )

    def test_display_tags_are_preserved_during_fullwidth_conversion(self) -> None:
        self.assertEqual(
            ascii_to_fullwidth("Fire %FIRE%!"),
            "Ｆｉｒｅ　%FIRE%！",
        )

    def test_language_candidates_are_deterministic(self) -> None:
        self.assertEqual(
            language_candidates(Language.SIMPLIFIED_CHINESE),
            (
                Language.SIMPLIFIED_CHINESE,
                Language.ENGLISH,
                Language.JAPANESE,
            ),
        )

    def test_selected_language_is_preferred(self) -> None:
        localizer = Localizer(Language.SIMPLIFIED_CHINESE)

        self.assertEqual(
            localizer.value(
                {"name_ja": "剣", "name_en": "Sword", "name_zhcn": "剑"},
                "name",
            ),
            "剑",
        )

    def test_empty_translation_uses_fallback_language(self) -> None:
        localizer = Localizer(Language.SIMPLIFIED_CHINESE)

        self.assertEqual(
            localizer.value(
                {"name_ja": "剣", "name_en": "Sword", "name_zhcn": ""},
                "name",
            ),
            "Sword",
        )

    def test_missing_translation_returns_explicit_default(self) -> None:
        localizer = Localizer(Language.ENGLISH)

        self.assertEqual(localizer.value({}, "name", default="?"), "?")

    def test_english_display_text_is_fullwidth_but_raw_value_is_unchanged(self) -> None:
        localizer = Localizer(Language.ENGLISH)
        record = {"name_en": "Sword +1"}

        self.assertEqual(localizer.value(record, "name"), "Sword +1")
        self.assertEqual(localizer.text(record, "name"), "Ｓｗｏｒｄ　＋１")

    def test_non_english_display_text_is_not_fullwidth_normalized(self) -> None:
        localizer = Localizer(Language.SIMPLIFIED_CHINESE)

        self.assertEqual(
            localizer.text({"name_zhcn": "Fiora"}, "name"),
            "Fiora",
        )


if __name__ == "__main__":
    unittest.main()
