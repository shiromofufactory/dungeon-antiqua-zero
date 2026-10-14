from __future__ import annotations

import unittest
from unittest.mock import Mock, call

from tools import _bootstrap  # Register the app imports used by UI modules.
from app.localization import LocalizedText
from app.resources import FontResources, FontRole
from app.state import Language
from app.ui import LocalizedWindowTextFactory, WindowText
from app.ui.tagged_text import draw_tagged_text
from app.ui.window import WindowFactory


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
            ],
        )
        self.assertEqual(
            fonts.baseline_offset_for.call_args_list,
            [
                call(Language.JAPANESE, role=FontRole.LARGE),
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
        fonts = Mock(spec=FontResources)
        fonts.font_for.return_value = wide_font
        fonts.baseline_offset_for.return_value = 0
        factory = LocalizedWindowTextFactory.from_language(
            fonts,
            Language.JAPANESE,
        )

        placement = factory.create("Language：SE 3", 4, 2)

        self.assertEqual(placement.text, "Ｌａｎｇｕａｇｅ：ＳＥ　３")
        self.assertIs(placement.font, wide_font)
        self.assertEqual(placement.font_spans, ())

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

    def chinese_factory(self, role: FontRole = FontRole.STANDARD):
        chinese_font = Mock()
        chinese_font.text_width.side_effect = lambda text: len(text) * 12
        japanese_font = Mock()
        japanese_font.text_width.side_effect = lambda text: len(text) * 8
        fonts = Mock(spec=FontResources)
        fonts.font_for.side_effect = lambda language, **kwargs: (
            japanese_font if language is Language.JAPANESE else chinese_font
        )
        fonts.baseline_offset_for.return_value = 0
        factory = LocalizedWindowTextFactory.from_language(
            fonts, Language.SIMPLIFIED_CHINESE, role=role,
        )
        return factory, chinese_font, japanese_font, fonts

    def test_chinese_ascii_and_fullwidth_glyphs_use_japanese_font(self) -> None:
        factory, chinese_font, japanese_font, _ = self.chinese_factory()
        placement = factory.create("消耗HP １０／２０", 4, 2)

        self.assertEqual(placement.text, "消耗ＨＰ　１０／２０")
        self.assertIs(placement.font, chinese_font)
        self.assertEqual(
            [(span.start, span.end, span.font) for span in placement.font_spans],
            [(2, 10, japanese_font)],
        )
        self.assertEqual(factory.text_width(placement.text), 2 * 12 + 8 * 8)

    def test_chinese_tags_and_glyph_runs_share_drawing_and_measurement(self) -> None:
        from unittest.mock import patch

        factory, chinese_font, japanese_font, _ = self.chinese_factory()
        placement = factory.create("HP%FIRE%伤害３", 0, 0, shadow_color=None)
        self.assertEqual(factory.text_width(placement.text), 16 + 8 + 24 + 8)
        with patch("app.ui.tagged_text.pyxel") as pyxel:
            draw_tagged_text(
                0, 0, placement.text, placement.color, placement.font,
                shadow_color=None, font_spans=placement.font_spans,
            )
        self.assertEqual(pyxel.text.call_args_list, [
            call(0, 0, "ＨＰ", 5, japanese_font),
            call(24, 0, "伤害", 5, chinese_font),
            call(48, 0, "３", 5, japanese_font),
        ])
        self.assertEqual(pyxel.blt.call_args.args[:2], (16, 3))

    def test_chinese_large_text_uses_matching_japanese_font_role(self) -> None:
        factory, _, japanese_font, fonts = self.chinese_factory(FontRole.LARGE)
        placement = factory.create("HP恢复", 0, 0)

        self.assertIs(placement.font_spans[0].font, japanese_font)
        self.assertEqual(fonts.font_for.call_args_list, [
            call(Language.SIMPLIFIED_CHINESE, role=FontRole.LARGE),
            call(Language.JAPANESE, role=FontRole.LARGE),
        ])

    def test_chinese_window_styles_initial_and_added_text_but_keeps_overrides(self) -> None:
        factory, chinese_font, japanese_font, _ = self.chinese_factory()
        window = WindowFactory(chinese_font, text_style=factory.apply).create(
            0, 0, 32, 12, (WindowText("HP", 0, 0),),
        )
        added = window.add_text("金币 26", 0, 4)
        override_font = object()
        override = window.add_text("６１／６１", 0, 8, font=override_font)

        self.assertEqual(window.texts[0].text, "ＨＰ")
        self.assertIs(window.texts[0].font_spans[0].font, japanese_font)
        self.assertEqual(added.text, "金币　２６")
        self.assertEqual(factory.text_width(added.text), 24 + 24)
        self.assertIs(override.font, override_font)
        self.assertEqual(override.font_spans, ())


if __name__ == "__main__":
    unittest.main()
