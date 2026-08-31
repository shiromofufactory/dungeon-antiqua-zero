from __future__ import annotations

import unittest

from app.localization import (
    Localizer,
    LocalizedText,
    ascii_to_fullwidth,
    format_number,
    format_text_template,
    language_candidates,
)
from app.state import Language


class LocalizationTest(unittest.TestCase):
    def test_formats_named_text_placeholders(self) -> None:
        self.assertEqual(
            format_text_template(
                "$TARGET$に$ATTRIBUTE$ダメージ",
                {"TARGET": "てき", "ATTRIBUTE": "%FIRE%ほのお"},
            ),
            "てきに%FIRE%ほのおダメージ",
        )

    def test_rejects_missing_or_invalid_text_placeholder_values(self) -> None:
        with self.assertRaisesRegex(ValueError, "value is missing: ITEM"):
            format_text_template("Drop $ITEM$?", {})
        with self.assertRaisesRegex(ValueError, "uppercase snake case"):
            format_text_template("$ITEM$", {"item": "Potion"})
        with self.assertRaisesRegex(TypeError, "values must be strings"):
            format_text_template("$ITEM$", {"ITEM": 1})  # type: ignore[dict-item]

    def test_display_numbers_are_always_fullwidth(self) -> None:
        self.assertEqual(format_number(0), "０")
        self.assertEqual(format_number(123), "１２３")
        self.assertEqual(format_number(-45), "－４５")

        with self.assertRaises(TypeError):
            format_number(True)

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

    def test_empty_translation_array_uses_fallback_language(self) -> None:
        localizer = Localizer(Language.ENGLISH)

        self.assertEqual(
            localizer.value(
                {"text_ja": ["1ぎょうめ"], "text_en": []},
                "text",
            ),
            ["1ぎょうめ"],
        )

    def test_missing_translation_returns_explicit_default(self) -> None:
        localizer = Localizer(Language.ENGLISH)

        self.assertEqual(localizer.value({}, "name", default="?"), "?")

    def test_english_display_text_is_fullwidth_but_raw_value_is_unchanged(self) -> None:
        localizer = Localizer(Language.ENGLISH)
        record = {"name_en": "Sword +1"}

        self.assertEqual(localizer.value(record, "name"), "Sword +1")
        self.assertEqual(localizer.text(record, "name"), "Ｓｗｏｒｄ　＋１")

    def test_japanese_display_text_normalizes_embedded_ascii(self) -> None:
        localizer = Localizer(Language.JAPANESE)
        record = {"text_ja": "Language：SE 3"}

        self.assertEqual(localizer.value(record, "text"), "Language：SE 3")
        self.assertEqual(
            localizer.text(record, "text"),
            "Ｌａｎｇｕａｇｅ：ＳＥ　３",
        )
        self.assertEqual(
            localizer.text(record, "text").narrow_spans,
            ((0, 8), (9, 13)),
        )

    def test_authored_fullwidth_english_text_keeps_wide_font_intent(self) -> None:
        localizer = Localizer(Language.ENGLISH)

        authored_wide = localizer.text({"text_en": "ＳＴＲ"}, "text")
        normalized_ascii = localizer.text({"text_en": "STR"}, "text")

        self.assertIsInstance(authored_wide, LocalizedText)
        self.assertTrue(authored_wide.prefers_wide_font)
        self.assertEqual(authored_wide, "ＳＴＲ")
        self.assertFalse(normalized_ascii.prefers_wide_font)
        self.assertEqual(normalized_ascii, "ＳＴＲ")

    def test_display_tags_do_not_trigger_wide_font_intent(self) -> None:
        text = Localizer(Language.ENGLISH).text(
            {"text_en": "%RIGHT%:"},
            "text",
        )

        self.assertFalse(text.prefers_wide_font)

    def test_chinese_display_text_is_not_fullwidth_normalized(self) -> None:
        localizer = Localizer(Language.SIMPLIFIED_CHINESE)

        self.assertEqual(
            localizer.text({"name_zhcn": "Fiora"}, "name"),
            "Fiora",
        )


if __name__ == "__main__":
    unittest.main()
