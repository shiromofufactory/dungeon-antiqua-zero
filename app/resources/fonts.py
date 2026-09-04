"""Load and cache Pyxel fonts by language and display role."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable

import pyxel

if __package__ == "resources":
    from state import Language
else:
    from ..state import Language


class FontRole(Enum):
    """Semantic font roles selected by UI code."""

    STANDARD = "standard"
    LARGE = "large"


@dataclass(frozen=True)
class FontDefinition:
    """Configurable font resource and its drawing metrics."""

    filename: str
    baseline_offset: int
    line_height: int


FONT_DEFINITIONS = MappingProxyType(
    {
        FontRole.STANDARD: MappingProxyType(
            {
                Language.JAPANESE: FontDefinition("k8x12S.bdf", 0, 12),
                Language.ENGLISH: FontDefinition("k6x8_gothic.bdf", 3, 8),
                Language.SIMPLIFIED_CHINESE: FontDefinition(
                    "fusion-pixel-12px-monospaced-zh_hans.bdf",
                    0,
                    12,
                ),
            }
        ),
        FontRole.LARGE: MappingProxyType(
            {
                Language.JAPANESE: FontDefinition(
                    "umplus_j12r.bdf",
                    0,
                    13,
                ),
                Language.ENGLISH: FontDefinition(
                    "k6x8_gothic.bdf",
                    3,
                    8,
                ),
                Language.SIMPLIFIED_CHINESE: FontDefinition(
                    "fusion-pixel-12px-monospaced-zh_hans.bdf",
                    0,
                    12,
                ),
            }
        ),
    }
)
FONT_FILENAMES = MappingProxyType(
    {
        language: definition.filename
        for language, definition in FONT_DEFINITIONS[FontRole.STANDARD].items()
    }
)
FONT_BASELINE_OFFSETS = MappingProxyType(
    {
        language: definition.baseline_offset
        for language, definition in FONT_DEFINITIONS[FontRole.STANDARD].items()
    }
)


class FontResourceError(RuntimeError):
    """Raised when a configured language font cannot be loaded."""


class FontResources:
    """Own language fonts and load each resource file only on first use."""

    def __init__(
        self,
        fonts_dir: Path | None = None,
        *,
        loader: Callable[[str], Any] | None = None,
    ) -> None:
        app_dir = Path(__file__).resolve().parents[1]
        self.fonts_dir = (fonts_dir or app_dir / "fonts").resolve()
        self._loader = loader or pyxel.Font
        self._cache: dict[Path, Any] = {}
        self._loaded_languages: dict[Language, None] = {}

    def font_for(
        self,
        language: Language,
        *,
        role: FontRole = FontRole.STANDARD,
    ) -> Any:
        """Return the cached font for ``language`` and semantic ``role``."""

        definition = self._definition_for(language, role)
        path = self.fonts_dir / definition.filename

        cached = self._cache.get(path)
        if cached is not None:
            self._loaded_languages.setdefault(language, None)
            return cached

        if not path.is_file():
            raise FontResourceError(f"言語フォントがありません: {path}")
        try:
            font = self._loader(str(path))
        except Exception as error:
            raise FontResourceError(
                f"言語フォントを読み込めません: {path}: {error}"
            ) from error

        self._cache[path] = font
        self._loaded_languages.setdefault(language, None)
        return font

    @staticmethod
    def baseline_offset_for(
        language: Language,
        *,
        role: FontRole = FontRole.STANDARD,
    ) -> int:
        """Return the pixel offset that aligns the language font baseline."""

        return FontResources._definition_for(language, role).baseline_offset

    @staticmethod
    def line_height_for(
        language: Language,
        *,
        role: FontRole = FontRole.STANDARD,
    ) -> int:
        """Return the configured line height for the selected font."""

        return FontResources._definition_for(language, role).line_height

    @staticmethod
    def _definition_for(
        language: Language,
        role: FontRole,
    ) -> FontDefinition:
        if not isinstance(language, Language):
            raise TypeError("language must be a Language")
        if not isinstance(role, FontRole):
            raise TypeError("role must be a FontRole")
        return FONT_DEFINITIONS[role][language]

    @property
    def loaded_languages(self) -> tuple[Language, ...]:
        """Return languages whose fonts have already been constructed."""

        return tuple(self._loaded_languages)
