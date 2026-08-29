"""Create window text styled for one selected language."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

if __package__ == "ui":
    from resources import FontResources
    from state import Language
else:
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

    def __post_init__(self) -> None:
        if self.font is None:
            raise ValueError("localized window text font must not be None")
        if not isinstance(self.baseline_offset, int):
            raise TypeError(
                "localized window text baseline offset must be an integer"
            )

    @classmethod
    def from_language(
        cls,
        fonts: FontResources,
        language: Language,
    ) -> LocalizedWindowTextFactory:
        """Create a factory using the standard style for ``language``."""

        return cls(
            fonts.font_for(language),
            fonts.baseline_offset_for(language),
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

        return WindowText(
            text,
            x,
            y,
            color=color,
            font=self.font,
            shadow_color=shadow_color,
            baseline_offset=self.baseline_offset,
        )
