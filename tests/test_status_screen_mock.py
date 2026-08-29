from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from tools.screen_mocks.status import (
    LOCALIZED_POSITIONS,
    Language,
    TRANSPARENT_INDEX,
    Settings,
    StatusScreenMock,
    next_language,
)


class StatusScreenMockTest(unittest.TestCase):
    def test_language_sequence_wraps_after_simplified_chinese(self) -> None:
        self.assertEqual(next_language(Language.JAPANESE), Language.ENGLISH)
        self.assertEqual(
            next_language(Language.ENGLISH),
            Language.SIMPLIFIED_CHINESE,
        )
        self.assertEqual(
            next_language(Language.SIMPLIFIED_CHINESE),
            Language.JAPANESE,
        )

    def test_first_three_lines_use_localized_member_identity(self) -> None:
        with (
            patch("tools.screen_mocks.status.pyxel.init"),
            patch("tools.screen_mocks.status.pyxel.load"),
            patch("tools.screen_mocks.status.pyxel.load_pal"),
            patch("tools.screen_mocks.status.pyxel.run"),
            patch("tools.screen_mocks.status.ImageResources") as images,
            patch("tools.screen_mocks.status.FontResources") as fonts,
            patch("tools.screen_mocks.status.WindowFactory") as factory,
        ):
            images.return_value.image.return_value = object()
            fonts.return_value.font_for.return_value = object()
            fonts.return_value.baseline_offset_for.return_value = 0

            StatusScreenMock()

        texts = tuple(factory.return_value.create.call_args.args[4])
        self.assertEqual(
            [item.text for item in texts[:3]],
            ["フィオラ", "ようせい", "おんな"],
        )
        placed = {(item.x, item.y): item.text for item in texts}
        self.assertEqual(placed[(6, 14)], "ＨＰ　９９９／９９９")
        self.assertEqual(placed[(6, 17)], "ＭＰ　２５５／２５５")
        self.assertEqual(placed[(22, 20)], "ＯＫ")
        self.assertEqual(placed[(6, 26)], "ちから")
        self.assertEqual(placed[(20, 26)], "１７")
        self.assertEqual(placed[(20, 29)], "２５")
        self.assertEqual(placed[(20, 32)], "２４")
        self.assertEqual(placed[(8, 41)], "")
        self.assertEqual(placed[(8, 44)], "")
        self.assertEqual(placed[(30, 8)], "みぎて　：%KNIFE%ダガー")
        self.assertEqual(placed[(30, 11)], "ひだりて：")
        self.assertEqual(placed[(30, 14)], "からだ　：ローブ")
        self.assertEqual(placed[(30, 17)], "あたま　：")
        self.assertEqual(placed[(30, 20)], "うで　　：")
        self.assertEqual(placed[(30, 38)], "じゅつぼうぎょ")

    def test_confirm_cycles_language_and_rebuilds_localized_window(self) -> None:
        mock = StatusScreenMock.__new__(StatusScreenMock)
        mock.settings = Settings()
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = Mock(
            confirm=Mock(triggered=True),
            cancel=Mock(triggered=False),
        )
        mock._rebuild_localized_window = Mock()

        mock.update()

        self.assertEqual(mock.settings.language, Language.ENGLISH)
        mock._rebuild_localized_window.assert_called_once_with()

    def test_english_localized_text_is_rebuilt_as_fullwidth(self) -> None:
        japanese_font = object()
        english_font = object()
        with (
            patch("tools.screen_mocks.status.pyxel.init"),
            patch("tools.screen_mocks.status.pyxel.load"),
            patch("tools.screen_mocks.status.pyxel.load_pal"),
            patch("tools.screen_mocks.status.pyxel.run"),
            patch("tools.screen_mocks.status.ImageResources") as images,
            patch("tools.screen_mocks.status.FontResources") as fonts,
        ):
            images.return_value.image.return_value = object()
            fonts.return_value.font_for.side_effect = (
                lambda language: english_font
                if language is Language.ENGLISH
                else japanese_font
            )
            fonts.return_value.baseline_offset_for.side_effect = (
                lambda language: 3
                if language is Language.ENGLISH
                else 0
            )
            mock = StatusScreenMock()

        mock.settings = mock.settings.with_language(Language.ENGLISH)
        mock._rebuild_localized_window()

        texts = {
            (item.x, item.y): item.text for item in mock.windows[0].texts
        }
        self.assertEqual(texts[(14, 2)], "Ｆｉｏｒａ")
        self.assertEqual(texts[(14, 5)], "Ｆａｉｒｙ")
        self.assertEqual(texts[(14, 8)], "Ｆｅｍａｌｅ")
        self.assertEqual(texts[(8, 41)], "")
        self.assertEqual(texts[(8, 44)], "")
        self.assertEqual(texts[(6, 20)], "Ｓｔａｔｕｓ")
        self.assertEqual(texts[(22, 20)], "ＯＫ")
        self.assertEqual(texts[(6, 26)], "ＳＴＲ")
        self.assertEqual(texts[(6, 29)], "ＡＧＩ")
        self.assertEqual(texts[(6, 32)], "ＭＡＧ")
        self.assertEqual(texts[(6, 38)], "Ｓｋｉｌｌ：")
        self.assertEqual(
            texts[(30, 8)],
            "%RIGHT%：%KNIFE%ＤＡＧＧＥＲ",
        )
        self.assertEqual(texts[(30, 11)], "%LEFT%：")
        self.assertEqual(texts[(30, 14)], "%BODY%：ＲＯＢＥ")
        self.assertEqual(texts[(30, 17)], "%HEAD%：")
        self.assertEqual(texts[(30, 20)], "%ARM%：")
        self.assertEqual(texts[(30, 26)], "Ａｔｔａｃｋ")
        self.assertEqual(texts[(30, 29)], "Ｈｉｔ")
        self.assertEqual(texts[(30, 32)], "Ｄｅｆｅｎｃｅ")
        self.assertEqual(texts[(30, 35)], "Ｅｖａｓｉｏｎ")
        self.assertEqual(texts[(30, 38)], "Ｓｐｅｌｌ　ｒｅｓ")
        self.assertEqual(texts[(30, 41)], "Ｔｏｌｅｒａｎｃｅ")
        self.assertEqual(
            {
                item.baseline_offset
                for item in mock.windows[0].texts
                if (item.x, item.y) in LOCALIZED_POSITIONS
            },
            {0, 3},
        )
        placements = {
            (item.x, item.y): item for item in mock.windows[0].texts
        }
        for position in ((6, 26), (6, 29), (6, 32)):
            self.assertIs(placements[position].font, japanese_font)
            self.assertEqual(placements[position].baseline_offset, 0)
        self.assertIs(placements[(6, 20)].font, english_font)
        self.assertEqual(placements[(6, 20)].baseline_offset, 3)

    def test_chinese_fixed_labels_are_rebuilt_from_text_catalog(self) -> None:
        with (
            patch("tools.screen_mocks.status.pyxel.init"),
            patch("tools.screen_mocks.status.pyxel.load"),
            patch("tools.screen_mocks.status.pyxel.load_pal"),
            patch("tools.screen_mocks.status.pyxel.run"),
            patch("tools.screen_mocks.status.ImageResources") as images,
            patch("tools.screen_mocks.status.FontResources") as fonts,
        ):
            images.return_value.image.return_value = object()
            fonts.return_value.font_for.return_value = object()
            fonts.return_value.baseline_offset_for.return_value = 0
            mock = StatusScreenMock()

        mock.settings = mock.settings.with_language(
            Language.SIMPLIFIED_CHINESE
        )
        mock._rebuild_localized_window()

        texts = {
            (item.x, item.y): item.text for item in mock.windows[0].texts
        }
        self.assertEqual(texts[(6, 20)], "状态")
        self.assertEqual(texts[(22, 20)], "ＯＫ")
        self.assertEqual(texts[(6, 26)], "力量")
        self.assertEqual(texts[(6, 29)], "敏捷")
        self.assertEqual(texts[(6, 32)], "魔力")
        self.assertEqual(texts[(6, 38)], "技能：")
        self.assertEqual(texts[(8, 41)], "")
        self.assertEqual(texts[(8, 44)], "")
        self.assertEqual(texts[(30, 8)], "右手：%KNIFE%DAGGER")
        self.assertEqual(texts[(30, 11)], "左手：")
        self.assertEqual(texts[(30, 14)], "身体：ROBE")
        self.assertEqual(texts[(30, 17)], "头部：")
        self.assertEqual(texts[(30, 20)], "手臂：")
        self.assertEqual(texts[(30, 26)], "攻击")
        self.assertEqual(texts[(30, 29)], "命中")
        self.assertEqual(texts[(30, 32)], "防御")
        self.assertEqual(texts[(30, 35)], "闪避")
        self.assertEqual(texts[(30, 38)], "抗性")
        self.assertEqual(texts[(30, 41)], "耐性")

    def test_cancel_quits_without_changing_language(self) -> None:
        mock = StatusScreenMock.__new__(StatusScreenMock)
        mock.settings = Settings()
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = Mock(
            confirm=Mock(triggered=False),
            cancel=Mock(triggered=True),
        )
        mock._rebuild_localized_window = Mock()

        with patch("tools.screen_mocks.status.pyxel.quit") as quit_mock:
            mock.update()

        quit_mock.assert_called_once_with()
        self.assertEqual(mock.settings.language, Language.JAPANESE)
        mock._rebuild_localized_window.assert_not_called()

    def test_draws_all_windows_before_face(self) -> None:
        mock = StatusScreenMock.__new__(StatusScreenMock)
        mock.faces = object()
        first_window = Mock()
        second_window = Mock()
        mock.windows = (first_window, second_window)
        draw_order: list[str] = []

        first_window.draw.side_effect = lambda: draw_order.append("first_window")
        second_window.draw.side_effect = lambda: draw_order.append("second_window")

        with patch(
            "tools.screen_mocks.status.pyxel.blt",
            side_effect=lambda *args: draw_order.append("face"),
        ) as blt:
            mock.draw()

        self.assertEqual(draw_order, ["first_window", "second_window", "face"])
        blt.assert_called_once_with(
            16,
            8,
            mock.faces,
            0,
            0,
            32,
            32,
            TRANSPARENT_INDEX,
        )


if __name__ == "__main__":
    unittest.main()
