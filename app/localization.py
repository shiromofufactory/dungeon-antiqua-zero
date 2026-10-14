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
_TEXT_PLACEHOLDER_PATTERN = re.compile(r"\$([A-Z][A-Z0-9_]*)\$")


class LocalizedText(str):
    """Display text retaining whether wide glyphs were authored explicitly."""

    prefers_wide_font: bool
    narrow_spans: tuple[tuple[int, int], ...]

    def __new__(
        cls,
        value: str,
        *,
        prefers_wide_font: bool = False,
        narrow_spans: tuple[tuple[int, int], ...] = (),
    ) -> LocalizedText:
        instance = super().__new__(cls, value)
        instance.prefers_wide_font = prefers_wide_font
        instance.narrow_spans = narrow_spans
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


def ascii_source_spans(text: str) -> tuple[tuple[int, int], ...]:
    """Return source ranges that should use the 6x8 Latin font."""

    if not isinstance(text, str):
        raise TypeError("text must be a string")
    tag_positions: set[int] = set()
    for match in _DISPLAY_TAG_PATTERN.finditer(text):
        tag_positions.update(range(match.start(), match.end()))

    spans: list[tuple[int, int]] = []
    start: int | None = None
    for index, character in enumerate(text):
        is_ascii_source = (
            index not in tag_positions
            and (character == " " or "!" <= character <= "~")
        )
        if is_ascii_source and start is None:
            start = index
        elif not is_ascii_source and start is not None:
            spans.append((start, index))
            start = None
    if start is not None:
        spans.append((start, len(text)))
    return tuple(spans)


def normalize_ascii_display_text(
    text: str,
    *,
    prefers_wide_font: bool = False,
) -> LocalizedText:
    """Normalize ASCII while preserving its 6x8-font source ranges."""

    return LocalizedText(
        ascii_to_fullwidth(text),
        prefers_wide_font=prefers_wide_font,
        narrow_spans=ascii_source_spans(text),
    )


def format_number(value: int) -> str:
    """Format an integer with fullwidth digits for every display language."""

    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("display number must be an integer")
    return ascii_to_fullwidth(str(value))


def format_text_template(
    template: str,
    values: Mapping[str, str],
) -> str:
    """Substitute named ``$NAME$`` placeholders in authored text."""

    if not isinstance(template, str):
        raise TypeError("text template must be a string")
    if not isinstance(values, Mapping):
        raise TypeError("text template values must be a mapping")

    normalized: dict[str, str] = {}
    for name, value in values.items():
        if (
            not isinstance(name, str)
            or re.fullmatch(r"[A-Z][A-Z0-9_]*", name) is None
        ):
            raise ValueError(
                "text template value names must use uppercase snake case"
            )
        if not isinstance(value, str):
            raise TypeError("text template values must be strings")
        normalized[name] = value

    def substitute(match: re.Match[str]) -> str:
        name = match.group(1)
        try:
            return normalized[name]
        except KeyError as error:
            raise ValueError(
                f"text template value is missing: {name}"
            ) from error

    return _TEXT_PLACEHOLDER_PATTERN.sub(substitute, template)


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
            if field not in record:
                continue
            value = record[field]
            if value == "" or value == [] or value == ():
                continue
            return value
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
        if self.language in (Language.JAPANESE, Language.SIMPLIFIED_CHINESE):
            return LocalizedText(ascii_to_fullwidth(value))
        if self.language is Language.ENGLISH:
            return normalize_ascii_display_text(
                value,
                prefers_wide_font=prefers_wide_font,
            )
        return LocalizedText(
            value,
            prefers_wide_font=prefers_wide_font,
        )
