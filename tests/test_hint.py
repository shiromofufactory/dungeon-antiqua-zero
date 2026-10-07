from __future__ import annotations

import unittest
from unittest.mock import Mock

from tools._bootstrap import APP_ROOT
from input import InputButton, InputState
from localization import Localizer
from resources import FontResources, FontRole
from state import Language, Settings
from text_catalog import TextCatalog
from ui.hint import HINT_BOTTOM_WINDOW_GRID, HINT_TOP_WINDOW_GRID, HintOverlay
from ui.window import WINDOW_ANIMATION_FRAME_COUNT, WindowState


class HintOverlayTest(unittest.TestCase):
    def overlay(
        self,
        language: Language = Language.JAPANESE,
        text_key: str = "hint.load.mission",
    ) -> HintOverlay:
        fonts = Mock()
        fonts.baseline_offset_for.return_value = 0
        return HintOverlay(
            text_key=text_key, settings=Settings(language=language),
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

    def test_requested_hints_are_at_top_and_result_is_at_bottom(self) -> None:
        for text_key in (
            "hint.load.mission",
            "hint.first_battle",
            "hint.first_world_map",
            "hint.first_dungeon_exit",
            "hint.first_defeat_restart",
        ):
            with self.subTest(text_key=text_key):
                overlay = self.overlay(text_key=text_key)
                self.assertEqual(
                    (overlay.window.x, overlay.window.y,
                     overlay.window.width, overlay.window.height),
                    HINT_TOP_WINDOW_GRID,
                )

        overlay = self.overlay(text_key="hint.first_result")
        self.assertEqual(
            (overlay.window.x, overlay.window.y,
             overlay.window.width, overlay.window.height),
            HINT_BOTTOM_WINDOW_GRID,
        )
        self.assertEqual(
            overlay.window.pixel_y + overlay.window.pixel_height,
            240,
        )

    def test_progression_hints_have_displayable_text(self) -> None:
        texts = TextCatalog.from_json(APP_ROOT / "data" / "texts.json")
        for text_key in (
            "hint.first_battle",
            "hint.first_result",
            "hint.first_world_map",
            "hint.first_dungeon_exit",
            "hint.first_defeat_restart",
        ):
            for language in Language:
                self.assertTrue(texts.lines(text_key, Localizer(language)))

    def test_first_world_map_hint_has_requested_lines_and_fits_window(self) -> None:
        fonts = FontResources()
        overlay = HintOverlay(
            text_key="hint.first_world_map", settings=Settings(),
            texts=TextCatalog.from_json(APP_ROOT / "data" / "texts.json"),
            fonts=fonts,
        )
        self.assertEqual([line.text for line in overlay.window.texts], [
            "【ヒント】", "ワールドマップでは", "敵と遭遇することはありません",
            "自由に歩いてみても　いいですね！",
        ])
        self.assertEqual([line.y for line in overlay.window.texts], [2, 6, 10, 14])
        for line in overlay.window.texts:
            self.assertLessEqual(
                line.x * 4 + line.font.text_width(line.text),
                overlay.window.pixel_width - 4,
            )
            self.assertLessEqual(
                line.y * 4 + line.baseline_offset
                + fonts.line_height_for(Language.JAPANESE, role=FontRole.LARGE),
                overlay.window.pixel_height - 4,
            )

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
