from __future__ import annotations

import unittest
from unittest.mock import Mock

from tools._bootstrap import APP_ROOT
from input import InputButton, InputState
from resources import FontResources, FontRole
from state import Language, Settings
from text_catalog import TextCatalog
from ui.hint import HintOverlay
from ui.window import WINDOW_ANIMATION_FRAME_COUNT, WindowState


class HintOverlayTest(unittest.TestCase):
    def overlay(self, language: Language = Language.JAPANESE) -> HintOverlay:
        fonts = Mock()
        fonts.baseline_offset_for.return_value = 0
        return HintOverlay(
            text_key="hint.load.mission", settings=Settings(language=language),
            texts=TextCatalog.from_json(APP_ROOT / "data" / "texts.json"), fonts=fonts,
        )

    def test_japanese_hint_has_heading_requested_lines_and_message_font(self) -> None:
        overlay = self.overlay()
        self.assertEqual([line.text for line in overlay.window.texts], [
            "【ヒント】", "次に何をするか　忘れてしまったら",
            "メニューを開いて「じょうほう」の", "「ミッション」を確認しよう！",
        ])
        self.assertEqual([line.y for line in overlay.window.texts], [2, 6, 10, 14])
        self.assertEqual(overlay.window.state, WindowState.OPENING)

    def test_dismissal_waits_for_release_opening_and_closing(self) -> None:
        for button in ("confirm", "cancel"):
            with self.subTest(button=button):
                overlay = self.overlay()
                pressed = InputState(**{button: InputButton(triggered=True, held=True)})
                for _ in range(WINDOW_ANIMATION_FRAME_COUNT + 2):
                    self.assertFalse(overlay.update(pressed))
                self.assertTrue(overlay.window.is_open)
                self.assertFalse(overlay.update(InputState()))
                self.assertFalse(overlay.update(pressed))
                self.assertEqual(overlay.window.state, WindowState.CLOSING)
                for _ in range(WINDOW_ANIMATION_FRAME_COUNT - 1):
                    self.assertFalse(overlay.update(pressed))
                self.assertTrue(overlay.update(pressed))
                self.assertTrue(overlay.window.is_closed)

    def test_all_languages_use_large_font_and_fit_inside_window(self) -> None:
        fonts = FontResources()
        for language in Language:
            overlay = HintOverlay(
                text_key="hint.load.mission", settings=Settings(language=language),
                texts=TextCatalog.from_json(APP_ROOT / "data" / "texts.json"), fonts=fonts,
            )
            row_height = 3 if language is Language.ENGLISH else 4
            self.assertEqual(
                [placement.y for placement in overlay.window.texts],
                [2 + index * row_height for index in range(4)],
            )
            self.assertIs(overlay.text_factory.font, fonts.font_for(language, role=FontRole.LARGE))
            for placement in overlay.window.texts:
                self.assertLessEqual(
                    placement.x * 4 + placement.font.text_width(placement.text),
                    overlay.window.pixel_width - 4,
                )
                self.assertLessEqual(
                    placement.y * 4 + placement.baseline_offset
                    + fonts.line_height_for(language, role=FontRole.LARGE),
                    overlay.window.pixel_height - 4,
                )


if __name__ == "__main__":
    unittest.main()
