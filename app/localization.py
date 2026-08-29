"""Select localized values without depending on UI or global language state."""

from __future__ import annotations

from dataclasses import dataclass
import re
from types import MappingProxyType
from typing import Mapping
import unicodedata

if __package__ == "":
    from state import Language
else:
    from .state import Language


_LANGUAGE_FALLBACKS = MappingProxyType(
    {
        Language.JAPANESE: (Language.JAPANESE, Language.ENGLISH),
        Language.ENGLISH: (Language.ENGLISH, Language.JAPANESE),
        Language.SIMPLIFIED_CHINESE: (
            Language.SIMPLIFIED_CHINESE,
            Language.ENGLISH,
            Language.JAPANESE,
        ),
    }
)
_DISPLAY_TAG_PATTERN = re.compile(r"%[A-Z][A-Z0-9_]*%")


class LocalizedText(str):
    """Display text retaining whether wide glyphs were authored explicitly."""

    prefers_wide_font: bool

    def __new__(
        cls,
        value: str,
        *,
        prefers_wide_font: bool = False,
    ) -> LocalizedText:
        instance = super().__new__(cls, value)
        instance.prefers_wide_font = prefers_wide_font
        return instance


def _has_authored_wide_text(text: str) -> bool:
    """Return whether literal source text contains a full/wide character."""

    position = 0
    for match in _DISPLAY_TAG_PATTERN.finditer(text):
        if any(
            unicodedata.east_asian_width(character) in ("F", "W")
            for character in text[position : match.start()]
        ):
            return True
        position = match.end()
    return any(
        unicodedata.east_asian_width(character) in ("F", "W")
        for character in text[position:]
    )


def ascii_to_fullwidth(text: str) -> str:
    """Convert printable ASCII to fullwidth forms while preserving tags."""

    if not isinstance(text, str):
        raise TypeError("text must be a string")

    def convert_literal(literal: str) -> str:
        converted: list[str] = []
        for character in literal:
            if character == " ":
                converted.append("　")
            elif "!" <= character <= "~":
                converted.append(chr(ord(character) + 0xFEE0))
            else:
                converted.append(character)
        return "".join(converted)

    parts: list[str] = []
    position = 0
    for match in _DISPLAY_TAG_PATTERN.finditer(text):
        parts.append(convert_literal(text[position : match.start()]))
        parts.append(match.group())
        position = match.end()
    parts.append(convert_literal(text[position:]))
    return "".join(parts)


def format_number(value: int) -> str:
    """Format an integer with fullwidth digits for every display language."""

    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("display number must be an integer")
    return ascii_to_fullwidth(str(value))


def language_candidates(language: Language) -> tuple[Language, ...]:
    """Return the deterministic fallback order for a supported language."""

    if not isinstance(language, Language):
        raise TypeError("language must be a Language")
    return _LANGUAGE_FALLBACKS[language]


@dataclass(frozen=True)
class Localizer:
    """Resolve fields such as ``name_ja`` for one selected language."""

    language: Language

    def __post_init__(self) -> None:
        if not isinstance(self.language, Language):
            raise TypeError("language must be a Language")

    def value(
        self,
        record: Mapping[str, object],
        key: str,
        default: object = "",
    ) -> object:
        """Return the first non-empty localized field in fallback order."""

        if not isinstance(record, Mapping):
            raise TypeError("record must be a mapping")
        if not isinstance(key, str) or not key:
            raise ValueError("key must be a non-empty string")

        for language in language_candidates(self.language):
            field = f"{key}_{language.value}"
            if field in record and record[field] != "":
                return record[field]
        return default

    def text(
        self,
        record: Mapping[str, object],
        key: str,
        default: str = "",
    ) -> LocalizedText:
        """Resolve display text and apply language-specific normalization."""

        value = self.value(record, key, default)
        if not isinstance(value, str):
            raise TypeError("localized display text must be a string")
        prefers_wide_font = (
            self.language is Language.ENGLISH
            and _has_authored_wide_text(value)
        )
        if self.language is Language.ENGLISH:
            value = ascii_to_fullwidth(value)
        return LocalizedText(
            value,
            prefers_wide_font=prefers_wide_font,
        )
