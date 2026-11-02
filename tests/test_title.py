from __future__ import annotations

import unittest
from unittest.mock import Mock, call, patch

from tools._bootstrap import APP_ROOT as _APP_ROOT
from app.input import InputButton, InputState
from app.localization import ascii_to_fullwidth
from app.scenes.title import TitleScene
from app.resources import TRANSPARENT_INDEX
from app.state import Language
from app.text_catalog import TextCatalog, TextCatalogError
from app.ui.tagged_text import ICON_BANK, ICON_COLKEY, ICON_SIZE
from app.ui.window import DEFAULT_TEXT_COLOR


class TitleSceneTest(unittest.TestCase):
    def title(self) -> TitleScene:
        self.fonts = Mock()
        self.font = self.fonts.font_for.return_value
        self.font.text_width.side_effect = lambda text: len(text) * 6
        self.fonts.line_height_for.return_value = 8
        self.images = Mock()
        self.logo_images = tuple(Mock(name=f"logo{frame}") for frame in range(1, 7))
        self.images.image.side_effect = self.logo_images
        return TitleScene(
            texts=TextCatalog.from_records([{
                "text_key": "title.press_start",
                "text_en": "Press %GAMEPAD_A% Button or %KEY_Z% Key",
                "text_ja": "Press %GAMEPAD_A% Button or %KEY_Z% Key",
            }]),
            fonts=self.fonts, images=self.images, screen_width=256, screen_height=240,
        )

    def test_renders_logo_above_lowered_english_prompt_without_mutation(self) -> None:
        title = self.title()
        prompt = ascii_to_fullwidth("Press %GAMEPAD_A% Button or %KEY_Z% Key")
        self.assertEqual(title.prompt, prompt)
        self.fonts.font_for.assert_called_once_with(Language.ENGLISH)
        with (
            patch("app.ui.tagged_text.pyxel.text") as draw_text,
            patch("app.ui.tagged_text.pyxel.blt") as draw_icon,
        ):
            title.draw()
            title.draw()
        self.assertEqual(draw_text.call_args_list, 2 * [
            call(57, 156, ascii_to_fullwidth("Press "), DEFAULT_TEXT_COLOR, self.font),
            call(101, 156, ascii_to_fullwidth(" Button or "), DEFAULT_TEXT_COLOR, self.font),
            call(175, 156, ascii_to_fullwidth(" Key"), DEFAULT_TEXT_COLOR, self.font),
        ])
        self.assertEqual(draw_icon.call_args_list, 2 * [
            call(2, 32, self.logo_images[0], 0, 0, 251, 93, TRANSPARENT_INDEX),
            call(93, 156, ICON_BANK, 160, 16, ICON_SIZE, ICON_SIZE, ICON_COLKEY),
            call(167, 156, ICON_BANK, 160, 24, ICON_SIZE, ICON_SIZE, ICON_COLKEY),
        ])
        self.assertTrue(title.update(InputState(confirm=InputButton(triggered=True))))

    def test_logo_advances_every_six_updates_and_loops_in_number_order(self) -> None:
        title = self.title()
        self.assertEqual(self.images.image.call_args_list, [
            call(f"logo/logo_zero{frame}") for frame in range(1, 7)
        ])
        with (
            patch("app.scenes.title.pyxel.blt") as draw_logo,
            patch("app.scenes.title.draw_tagged_text"),
        ):
            for tick in range(73):
                title.draw()
                self.assertIs(draw_logo.call_args.args[2], self.logo_images[(tick // 6) % 6])
                self.assertFalse(title.update(InputState()))
        self.assertEqual(self.images.image.call_count, 6)

    def test_only_a_new_confirm_press_requests_transition_once(self) -> None:
        title = self.title()
        for state in (
            InputState(), InputState(confirm=InputButton(held=True)),
            InputState(cancel=InputButton(triggered=True)),
            InputState(menu=InputButton(triggered=True)),
        ):
            self.assertFalse(title.update(state))
        press = InputState(confirm=InputButton(triggered=True, held=True))
        self.assertTrue(title.update(press))
        self.assertFalse(title.update(press))

    def test_missing_prompt_is_a_startup_data_error(self) -> None:
        with self.assertRaisesRegex(TextCatalogError, "title.press_start"):
            TitleScene(
                texts=TextCatalog.from_records([]), fonts=Mock(), images=Mock(),
                screen_width=256, screen_height=240,
            )


if __name__ == "__main__":
    unittest.main()
