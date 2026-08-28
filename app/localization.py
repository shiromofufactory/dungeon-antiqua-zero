"""Select localized values without depending on UI or global language state."""

from __future__ import annotations

from dataclasses import dataclass
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
