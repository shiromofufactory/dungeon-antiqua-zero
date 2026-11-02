"""Animate the title logo and accept one confirm input."""

from __future__ import annotations

import pyxel

if __package__ == "scenes":
    from input import InputState
    from localization import Localizer
    from resources import TRANSPARENT_INDEX, FontResources, ImageResources
    from state import Language
    from text_catalog import TextCatalog, TextCatalogError
    from ui.tagged_text import ICON_SIZE, ICON_Y_OFFSET, draw_tagged_text, tagged_text_width
    from ui.window import DEFAULT_TEXT_COLOR
else:
    from ..input import InputState
    from ..localization import Localizer
    from ..resources import TRANSPARENT_INDEX, FontResources, ImageResources
    from ..state import Language
    from ..text_catalog import TextCatalog, TextCatalogError
    from ..ui.tagged_text import ICON_SIZE, ICON_Y_OFFSET, draw_tagged_text, tagged_text_width
    from ..ui.window import DEFAULT_TEXT_COLOR


TITLE_PROMPT_TEXT_KEY = "title.press_start"
TITLE_LOGO_IMAGE_IDS = tuple(f"logo/logo_zero{frame}" for frame in range(1, 7))
TITLE_LOGO_WIDTH = 251
TITLE_LOGO_HEIGHT = 93
TITLE_LOGO_Y = 32
TITLE_LOGO_FRAME_DURATION = 6
TITLE_PROMPT_Y_OFFSET = 40


class TitleScene:
    def __init__(
        self,
        *,
        texts: TextCatalog,
        fonts: FontResources,
        images: ImageResources,
        screen_width: int,
        screen_height: int,
    ) -> None:
        self.prompt = texts.text(TITLE_PROMPT_TEXT_KEY, Localizer(Language.ENGLISH))
        if not self.prompt:
            raise TextCatalogError(f"ゲーム用テキストが見つかりません: {TITLE_PROMPT_TEXT_KEY}")
        self.font = fonts.font_for(Language.ENGLISH)
        self.x = (screen_width - tagged_text_width(self.prompt, self.font)) // 2
        self.y = (
            (screen_height - max(fonts.line_height_for(Language.ENGLISH), ICON_SIZE)) // 2
            + TITLE_PROMPT_Y_OFFSET
        )
        self._logo_images = tuple(images.image(image_id) for image_id in TITLE_LOGO_IMAGE_IDS)
        self._logo_x = (screen_width - TITLE_LOGO_WIDTH) // 2
        self._logo_tick = 0
        self._confirmed = False

    def update(self, input_state: InputState) -> bool:
        """Advance the logo and request the next screen once on confirm."""

        self._logo_tick = (self._logo_tick + 1) % (
            len(self._logo_images) * TITLE_LOGO_FRAME_DURATION
        )
        if self._confirmed or not input_state.confirm.triggered:
            return False
        self._confirmed = True
        return True

    def draw(self) -> None:
        pyxel.blt(
            self._logo_x,
            TITLE_LOGO_Y,
            self._logo_images[self._logo_tick // TITLE_LOGO_FRAME_DURATION],
            0,
            0,
            TITLE_LOGO_WIDTH,
            TITLE_LOGO_HEIGHT,
            TRANSPARENT_INDEX,
        )
        draw_tagged_text(
            self.x,
            self.y - ICON_Y_OFFSET,
            self.prompt,
            DEFAULT_TEXT_COLOR,
            self.font,
            shadow_color=None,
            text_y_offset=ICON_Y_OFFSET,
        )
