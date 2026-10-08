"""Show the temporary title prompt and accept one confirm input."""

from __future__ import annotations

if __package__ == "scenes":
    from input import InputState
    from localization import Localizer
    from resources import FontResources
    from state import Language
    from text_catalog import TextCatalog, TextCatalogError
    from ui.tagged_text import ICON_SIZE, ICON_Y_OFFSET, draw_tagged_text, tagged_text_width
    from ui.window import DEFAULT_TEXT_COLOR
else:
    from ..input import InputState
    from ..localization import Localizer
    from ..resources import FontResources
    from ..state import Language
    from ..text_catalog import TextCatalog, TextCatalogError
    from ..ui.tagged_text import ICON_SIZE, ICON_Y_OFFSET, draw_tagged_text, tagged_text_width
    from ..ui.window import DEFAULT_TEXT_COLOR


TITLE_PROMPT_TEXT_KEY = "title.press_start"


class TitleScene:
    def __init__(
        self,
        *,
        texts: TextCatalog,
        fonts: FontResources,
        screen_width: int,
        screen_height: int,
    ) -> None:
        self.prompt = texts.text(TITLE_PROMPT_TEXT_KEY, Localizer(Language.ENGLISH))
        if not self.prompt:
            raise TextCatalogError(f"ゲーム用テキストが見つかりません: {TITLE_PROMPT_TEXT_KEY}")
        self.font = fonts.font_for(Language.ENGLISH)
        self.x = (screen_width - tagged_text_width(self.prompt, self.font)) // 2
        self.y = (screen_height - max(fonts.line_height_for(Language.ENGLISH), ICON_SIZE)) // 2
        self._confirmed = False

    def update(self, input_state: InputState) -> bool:
        """Request the next screen once when the confirm button is pressed."""

        if self._confirmed or not input_state.confirm.triggered:
            return False
        self._confirmed = True
        return True

    def draw(self) -> None:
        draw_tagged_text(
            self.x,
            self.y - ICON_Y_OFFSET,
            self.prompt,
            DEFAULT_TEXT_COLOR,
            self.font,
            shadow_color=None,
            text_y_offset=ICON_Y_OFFSET,
        )
