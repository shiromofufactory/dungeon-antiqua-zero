from __future__ import annotations

import unittest
from unittest.mock import Mock, call

from app.localization import LocalizedText
from app.resources import FontResources
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
