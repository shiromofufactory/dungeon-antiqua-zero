from __future__ import annotations

import unittest
from unittest.mock import Mock, call

from app.localization import LocalizedText
from app.resources import FontResources, FontRole
from app.state import Language
from app.ui import LocalizedWindowTextFactory, WindowText


class LocalizedWindowTextFactoryTest(unittest.TestCase):
    def test_language_style_is_resolved_once_for_factory(self) -> None:
        font = object()
        fonts = Mock(spec=FontResources)
        fonts.font_for.return_value = font
        fonts.baseline_offset_for.return_value = 3

        factory = LocalizedWindowTextFactory.from_language(
            fonts,
            Language.ENGLISH,
        )

        self.assertEqual(factory.font, font)
        self.assertEqual(factory.baseline_offset, 3)
        self.assertEqual(
            fonts.font_for.call_args_list,
            [
                call(Language.ENGLISH),
                call(Language.JAPANESE),
            ],
        )
        self.assertEqual(
            fonts.baseline_offset_for.call_args_list,
            [
                call(Language.ENGLISH),
                call(Language.JAPANESE),
            ],
        )

    def test_font_role_is_applied_to_language_and_mixed_text_fonts(self) -> None:
        fonts = Mock(spec=FontResources)
        fonts.font_for.side_effect = (object(), object())
        fonts.baseline_offset_for.side_effect = (0, 3)

        LocalizedWindowTextFactory.from_language(
            fonts,
            Language.JAPANESE,
            role=FontRole.LARGE,
        )

        self.assertEqual(
            fonts.font_for.call_args_list,
            [
                call(Language.JAPANESE, role=FontRole.LARGE),
                call(Language.ENGLISH, role=FontRole.LARGE),
            ],
        )
        self.assertEqual(
            fonts.baseline_offset_for.call_args_list,
            [
                call(Language.JAPANESE, role=FontRole.LARGE),
                call(Language.ENGLISH, role=FontRole.LARGE),
            ],
        )

    def test_create_applies_bound_style_to_resolved_text(self) -> None:
        font = object()
        factory = LocalizedWindowTextFactory(font, 3)

        placement = factory.create(
            "Ｓｔｒｅｎｇｔｈ",
            6,
            26,
            color=12,
            shadow_color=None,
        )

        self.assertEqual(
            placement,
            WindowText(
                "Ｓｔｒｅｎｇｔｈ",
                6,
                26,
                color=12,
                font=font,
                shadow_color=None,
                baseline_offset=3,
            ),
        )

    def test_japanese_factory_normalizes_ascii_added_by_screen_code(self) -> None:
        wide_font = object()
        narrow_font = object()
        fonts = Mock(spec=FontResources)
        fonts.font_for.side_effect = (wide_font, narrow_font)
        fonts.baseline_offset_for.side_effect = (0, 3)
        factory = LocalizedWindowTextFactory.from_language(
            fonts,
            Language.JAPANESE,
        )

        placement = factory.create("Language：SE 3", 4, 2)

        self.assertEqual(placement.text, "Ｌａｎｇｕａｇｅ：ＳＥ　３")
        self.assertIs(placement.font, wide_font)
        self.assertEqual(
            [
                (span.start, span.end, span.font, span.text_y_offset)
                for span in placement.font_spans
            ],
            [
                (0, 8, narrow_font, 3),
                (9, 13, narrow_font, 3),
            ],
        )

    def test_japanese_factory_keeps_authored_fullwidth_on_wide_font(self) -> None:
        wide_font = object()
        narrow_font = object()
        factory = LocalizedWindowTextFactory(
            wide_font,
            0,
            normalize_ascii=True,
            narrow_font=narrow_font,
            narrow_baseline_offset=3,
        )

        placement = factory.create("ＳＴＲ", 4, 2)

        self.assertIs(placement.font, wide_font)
        self.assertEqual(placement.font_spans, ())

    def test_authored_fullwidth_text_uses_wide_font_style(self) -> None:
        language_font = object()
        wide_font = object()
        factory = LocalizedWindowTextFactory(
            language_font,
            3,
            wide_font=wide_font,
            wide_baseline_offset=0,
        )

        placement = factory.create(
            LocalizedText("ＳＴＲ", prefers_wide_font=True),
            6,
            26,
        )

        self.assertIs(placement.font, wide_font)
        self.assertEqual(placement.baseline_offset, 0)


if __name__ == "__main__":
    unittest.main()
