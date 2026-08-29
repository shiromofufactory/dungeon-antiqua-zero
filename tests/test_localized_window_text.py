from __future__ import annotations

import unittest
from unittest.mock import Mock

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
        fonts.font_for.assert_called_once_with(Language.ENGLISH)
        fonts.baseline_offset_for.assert_called_once_with(Language.ENGLISH)

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


if __name__ == "__main__":
    unittest.main()
