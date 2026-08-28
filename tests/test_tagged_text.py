from __future__ import annotations

import unittest
from unittest.mock import patch

from app.ui.tagged_text import (
    ICON_BANK,
    ICON_COLKEY,
    ICON_SIZE,
    TEXT_ICONS,
    TextIcon,
    draw_tagged_text,
    split_tagged_text,
)


class StubFont:
    @staticmethod
    def text_width(text: str) -> int:
        return len(text) * 6


class TaggedTextTest(unittest.TestCase):
    def test_all_icon_tags_use_the_expected_coordinates(self) -> None:
        expected = {
            "%FIRE%": (0, 16),
            "%FREEZE%": (8, 16),
            "%DARK%": (16, 16),
            "%SLEEP%": (24, 16),
            "%POISON%": (32, 16),
            "%PARALIZE%": (40, 16),
            "%CONFUSE%": (48, 16),
            "%SILENCE%": (56, 16),
            "%DEATH%": (64, 16),
            "%FIRE_DISABLED%": (0, 24),
            "%FREEZE_DISABLED%": (8, 24),
            "%DARK_DISABLED%": (16, 24),
            "%SLEEP_DISABLED%": (24, 24),
            "%POISON_DISABLED%": (32, 24),
            "%PARALIZE_DISABLED%": (40, 24),
            "%CONFUSE_DISABLED%": (48, 24),
            "%SILENCE_DISABLED%": (56, 24),
            "%DEATH_DISABLED%": (64, 24),
            "%RIGHT%": (72, 16),
            "%LEFT%": (80, 16),
            "%HEAD%": (72, 24),
            "%BODY%": (80, 24),
            "%ARM%": (88, 24),
            "%UNDEAD%": (96, 16),
            "%FLY%": (96, 24),
            "%SWORD%": (104, 16),
            "%KATANA%": (112, 16),
            "%KNIFE%": (120, 16),
            "%SPEAR%": (128, 16),
            "%AXE%": (136, 16),
            "%HAMMER%": (144, 16),
            "%THROWING%": (152, 16),
            "%ROD%": (104, 24),
            "%WAND%": (112, 24),
            "%SHIELD%": (120, 24),
            "%ELEMENT%": (128, 24),
            "%SACRED%": (136, 24),
            "%DARK_MAGIC%": (144, 24),
        }

        self.assertEqual(
            {tag: (icon.u, icon.v) for tag, icon in TEXT_ICONS.items()},
            expected,
        )

    def test_known_tags_are_split_from_literal_text(self) -> None:
        parts = split_tagged_text("炎%FIRE%と%FREEZE%冷気")

        self.assertEqual(parts[0], "炎")
        self.assertEqual(parts[1], TEXT_ICONS["%FIRE%"])
        self.assertEqual(parts[2], "と")
        self.assertEqual(parts[3], TEXT_ICONS["%FREEZE%"])
        self.assertEqual(parts[4], "冷気")

    def test_unknown_tags_and_percent_signs_remain_literal(self) -> None:
        self.assertEqual(
            split_tagged_text("100% %UNKNOWN% %fire%"),
            ("100% %UNKNOWN% %fire%",),
        )

    def test_mixed_content_advances_by_text_and_icon_width(self) -> None:
        font = StubFont()

        with (
            patch("app.ui.tagged_text.pyxel.text") as text,
            patch("app.ui.tagged_text.pyxel.blt") as blt,
        ):
            draw_tagged_text(
                10,
                20,
                "A%FIRE%BC",
                5,
                font,
                shadow_color=0,
            )

        self.assertEqual(
            [call.args for call in text.call_args_list],
            [
                (10, 21, "A", 0, font),
                (10, 20, "A", 5, font),
                (24, 21, "BC", 0, font),
                (24, 20, "BC", 5, font),
            ],
        )
        self.assertEqual(
            blt.call_args.args,
            (
                16,
                23,
                ICON_BANK,
                0,
                16,
                ICON_SIZE,
                ICON_SIZE,
                ICON_COLKEY,
            ),
        )

    def test_consecutive_icons_do_not_require_text_between_them(self) -> None:
        with (
            patch("app.ui.tagged_text.pyxel.text") as text,
            patch("app.ui.tagged_text.pyxel.blt") as blt,
        ):
            draw_tagged_text(3, 4, "%FIRE%%FREEZE%", 5)

        self.assertEqual(text.call_count, 0)
        self.assertEqual([call.args[0] for call in blt.call_args_list], [3, 11])

    def test_icon_value_is_a_frozen_description(self) -> None:
        self.assertEqual(TEXT_ICONS["%DARK_MAGIC%"], TextIcon("%DARK_MAGIC%", 144, 24))


if __name__ == "__main__":
    unittest.main()
