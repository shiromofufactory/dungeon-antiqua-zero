"""Load and cache the standard Pyxel font for each supported language."""

from __future__ import annotations

from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable

import pyxel

if __package__ == "resources":
    from state import Language
else:
    from ..state import Language


FONT_FILENAMES = MappingProxyType(
    {
        Language.JAPANESE: "k8x12S.bdf",
        Language.ENGLISH: "k6x8_gothic.bdf",
        Language.SIMPLIFIED_CHINESE: (
            "fusion-pixel-12px-monospaced-zh_hans.bdf"
        ),
    }
)


class FontResourceError(RuntimeError):
    """Raised when a configured language font cannot be loaded."""


class FontResources:
    """Own language fonts and load each one only on first use."""

    def __init__(
        self,
        fonts_dir: Path | None = None,
        *,
        loader: Callable[[str], Any] | None = None,
    ) -> None:
        app_dir = Path(__file__).resolve().parents[1]
        self.fonts_dir = (fonts_dir or app_dir / "fonts").resolve()
        self._loader = loader or pyxel.Font
        self._cache: dict[Language, Any] = {}

    def font_for(self, language: Language) -> Any:
        """Return the cached standard font for ``language``."""

        if not isinstance(language, Language):
            raise TypeError("language must be a Language")

        cached = self._cache.get(language)
        if cached is not None:
            return cached

        path = self.fonts_dir / FONT_FILENAMES[language]
        if not path.is_file():
            raise FontResourceError(f"言語フォントがありません: {path}")
        try:
            font = self._loader(str(path))
        except Exception as error:
            raise FontResourceError(
                f"言語フォントを読み込めません: {path}: {error}"
            ) from error

        self._cache[language] = font
        return font

    @property
    def loaded_languages(self) -> tuple[Language, ...]:
        """Return languages whose fonts have already been constructed."""

        return tuple(self._cache)
