"""Create window text styled for one selected language."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

if __package__ == "ui":
    from localization import LocalizedText
    from resources import FontResources
    from state import Language
else:
    from ..localization import LocalizedText
    from ..resources import FontResources
    from ..state import Language

from .window import (
    DEFAULT_TEXT_COLOR,
    DEFAULT_TEXT_SHADOW_COLOR,
    WindowText,
)


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

    @classmethod
    def from_language(
        cls,
        fonts: FontResources,
        language: Language,
    ) -> LocalizedWindowTextFactory:
        """Create a factory using the standard style for ``language``."""

        font = fonts.font_for(language)
        baseline_offset = fonts.baseline_offset_for(language)
        if language is not Language.ENGLISH:
            return cls(font, baseline_offset)
        return cls(
            font,
            baseline_offset,
            wide_font=fonts.font_for(Language.JAPANESE),
            wide_baseline_offset=fonts.baseline_offset_for(
                Language.JAPANESE
            ),
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
        )
