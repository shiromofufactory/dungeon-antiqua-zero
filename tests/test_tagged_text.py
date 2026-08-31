from __future__ import annotations

import unittest
from unittest.mock import patch

from app.ui.colors import BLUE_TEXT_COLOR, POSITIVE_COLOR
from app.ui.tagged_text import (
    ICON_BANK,
    ICON_COLKEY,
    ICON_SIZE,
    TEXT_COLORS,
    TEXT_ICONS,
    TextColor,
    TextFontSpan,
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
            "%MYSTIC%": (128, 24),
            "%SACRED%": (136, 24),
            "%NETHER%": (144, 24),
            "%FAVORED%": (152, 24),
            "%GAMEPAD_A%": (160, 16),
            "%GAMEPAD_B%": (168, 16),
            "%GAMEPAD_X%": (176, 16),
            "%GAMEPAD_Y%": (184, 16),
            "%KEY_Z%": (160, 24),
            "%KEY_X%": (168, 24),
            "%KEY_S%": (176, 24),
            "%KEY_TAB%": (184, 24),
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

    def test_input_icon_tag_can_be_embedded_anywhere_in_text(self) -> None:
        parts = split_tagged_text("操作：%KEY_X%：とじる")

        self.assertEqual(
            parts,
            ("操作：", TEXT_ICONS["%KEY_X%"], "：とじる"),
        )

    def test_color_tags_are_split_from_literal_text(self) -> None:
        self.assertEqual(
            split_tagged_text("白%COL_BLUE%青%COL_END%白"),
            (
                "白",
                TEXT_COLORS["%COL_BLUE%"],
                "青",
                TEXT_COLORS["%COL_END%"],
                "白",
            ),
        )

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

    def test_color_tags_change_color_without_advancing_and_end_restores_white(self) -> None:
        font = StubFont()

        with patch("app.ui.tagged_text.pyxel.text") as text:
            draw_tagged_text(
                10,
                20,
                "A%COL_BLUE%B%COL_END%C",
                7,
                font,
                shadow_color=None,
            )

        self.assertEqual(
            [call.args for call in text.call_args_list],
            [
                (10, 20, "A", 7, font),
                (16, 20, "B", BLUE_TEXT_COLOR, font),
                (22, 20, "C", 5, font),
            ],
        )

    def test_positive_color_tag_changes_only_text_after_colon(self) -> None:
        font = StubFont()

        with patch("app.ui.tagged_text.pyxel.text") as text:
            draw_tagged_text(
                10,
                20,
                "：%COL_POSITIVE%FIXED",
                5,
                font,
                shadow_color=None,
            )

        self.assertEqual(
            [call.args for call in text.call_args_list],
            [
                (10, 20, "：", 5, font),
                (16, 20, "FIXED", POSITIVE_COLOR, font),
            ],
        )

    def test_icon_advance_is_eight_pixels_with_six_pixel_font(self) -> None:
        font = StubFont()

        with (
            patch("app.ui.tagged_text.pyxel.text") as text,
            patch("app.ui.tagged_text.pyxel.blt") as blt,
        ):
            draw_tagged_text(10, 20, "%WAND%X", 5, font, shadow_color=None)

        self.assertEqual(blt.call_args.args[0], 10)
        self.assertEqual(text.call_args.args, (18, 20, "X", 5, font))

    def test_text_y_offset_does_not_move_icon(self) -> None:
        font = StubFont()

        with (
            patch("app.ui.tagged_text.pyxel.text") as text,
            patch("app.ui.tagged_text.pyxel.blt") as blt,
        ):
            draw_tagged_text(
                10,
                20,
                "%WAND%X",
                5,
                font,
                shadow_color=None,
                text_y_offset=3,
            )

        self.assertEqual(blt.call_args.args[1], 23)
        self.assertEqual(text.call_args.args, (18, 23, "X", 5, font))

    def test_font_span_draws_ascii_origin_with_narrow_font(self) -> None:
        wide_font = StubFont()
        narrow_font = StubFont()

        with patch("app.ui.tagged_text.pyxel.text") as text:
            draw_tagged_text(
                10,
                20,
                "ＳＥおんりょう",
                5,
                wide_font,
                shadow_color=None,
                font_spans=(TextFontSpan(0, 2, narrow_font, 3),),
            )

        self.assertEqual(
            [call.args for call in text.call_args_list],
            [
                (10, 23, "ＳＥ", 5, narrow_font),
                (22, 20, "おんりょう", 5, wide_font),
            ],
        )

    def test_icon_value_is_a_frozen_description(self) -> None:
        self.assertEqual(
            TEXT_ICONS["%FAVORED%"],
            TextIcon("%FAVORED%", 152, 24),
        )

    def test_color_values_are_frozen_descriptions(self) -> None:
        self.assertEqual(
            TEXT_COLORS,
            {
                "%COL_BLUE%": TextColor("%COL_BLUE%", BLUE_TEXT_COLOR),
                "%COL_POSITIVE%": TextColor(
                    "%COL_POSITIVE%",
                    POSITIVE_COLOR,
                ),
                "%COL_END%": TextColor("%COL_END%", 5),
            },
        )


if __name__ == "__main__":
    unittest.main()
