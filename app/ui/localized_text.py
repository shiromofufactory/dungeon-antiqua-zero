"""Create window text styled for one selected language."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

if __package__ == "ui":
    from localization import LocalizedText, normalize_ascii_display_text
    from resources import FontResources
    from state import Language
else:
    from ..localization import LocalizedText, normalize_ascii_display_text
    from ..resources import FontResources
    from ..state import Language

from .window import (
    DEFAULT_TEXT_COLOR,
    DEFAULT_TEXT_SHADOW_COLOR,
    WindowText,
)
from .tagged_text import TextFontSpan


@dataclass(frozen=True)
class LocalizedWindowTextFactory:
    """Bind a language font and baseline offset to ``WindowText`` creation.

    The factory accepts already-localized display text. Translation lookup,
    screen-specific composition, and coordinates remain with the caller.
    """

    font: Any
    baseline_offset: int
    wide_font: Any | None = None
    wide_baseline_offset: int = 0
    normalize_ascii: bool = False
    narrow_font: Any | None = None
    narrow_baseline_offset: int = 0

    def __post_init__(self) -> None:
        if self.font is None:
            raise ValueError("localized window text font must not be None")
        if not isinstance(self.baseline_offset, int):
            raise TypeError(
                "localized window text baseline offset must be an integer"
            )
        if not isinstance(self.wide_baseline_offset, int):
            raise TypeError(
                "wide text baseline offset must be an integer"
            )
        if not isinstance(self.normalize_ascii, bool):
            raise TypeError("normalize_ascii must be a boolean")
        if not isinstance(self.narrow_baseline_offset, int):
            raise TypeError(
                "narrow text baseline offset must be an integer"
            )

    @classmethod
    def from_language(
        cls,
        fonts: FontResources,
        language: Language,
    ) -> LocalizedWindowTextFactory:
        """Create a factory using the standard style for ``language``."""

        font = fonts.font_for(language)
        baseline_offset = fonts.baseline_offset_for(language)
        if language is Language.JAPANESE:
            return cls(
                font,
                baseline_offset,
                normalize_ascii=True,
                narrow_font=fonts.font_for(Language.ENGLISH),
                narrow_baseline_offset=fonts.baseline_offset_for(
                    Language.ENGLISH
                ),
            )
        if language is not Language.ENGLISH:
            return cls(font, baseline_offset)
        return cls(
            font,
            baseline_offset,
            wide_font=fonts.font_for(Language.JAPANESE),
            wide_baseline_offset=fonts.baseline_offset_for(
                Language.JAPANESE
            ),
            normalize_ascii=True,
        )

    def create(
        self,
        text: str,
        x: int,
        y: int,
        *,
        color: int = DEFAULT_TEXT_COLOR,
        shadow_color: int | None = DEFAULT_TEXT_SHADOW_COLOR,
    ) -> WindowText:
        """Place already-localized text in the window's text grid."""

        use_wide_font = (
            isinstance(text, LocalizedText)
            and text.prefers_wide_font
            and self.wide_font is not None
        )
        if self.normalize_ascii and not isinstance(text, LocalizedText):
            text = normalize_ascii_display_text(text)
        font_spans: tuple[TextFontSpan, ...] = ()
        if (
            isinstance(text, LocalizedText)
            and text.narrow_spans
            and self.narrow_font is not None
            and not use_wide_font
        ):
            font_spans = tuple(
                TextFontSpan(
                    start,
                    end,
                    self.narrow_font,
                    self.narrow_baseline_offset,
                )
                for start, end in text.narrow_spans
            )
        return WindowText(
            text,
            x,
            y,
            color=color,
            font=self.wide_font if use_wide_font else self.font,
            shadow_color=shadow_color,
            baseline_offset=(
                self.wide_baseline_offset
                if use_wide_font
                else self.baseline_offset
            ),
            font_spans=font_spans,
        )
