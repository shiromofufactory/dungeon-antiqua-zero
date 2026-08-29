"""Select localized values without depending on UI or global language state."""

from __future__ import annotations

from dataclasses import dataclass
import re
from types import MappingProxyType
from typing import Mapping

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
    ) -> str:
        """Resolve display text and apply language-specific normalization."""

        value = self.value(record, key, default)
        if not isinstance(value, str):
            raise TypeError("localized display text must be a string")
        if self.language is Language.ENGLISH:
            return ascii_to_fullwidth(value)
        return value
