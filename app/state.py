"""Persistent player and device settings kept outside game save data."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Mapping


class Language(StrEnum):
    """Stable language identifiers used by settings and localized data."""

    JAPANESE = "ja"
    ENGLISH = "en"
    SIMPLIFIED_CHINESE = "zhcn"


class SettingsDataError(ValueError):
    """Raised when persisted settings cannot be interpreted safely."""


@dataclass(frozen=True)
class Settings:
    """Device and player preferences stored separately from game progress."""

    language: Language = Language.JAPANESE

    def __post_init__(self) -> None:
        if not isinstance(self.language, Language):
            raise TypeError("language must be a Language")

    def to_dict(self) -> dict[str, object]:
        """Return the JSON-compatible representation of these settings."""

        return {"language": self.language.value}

    def with_language(self, language: Language) -> Settings:
        """Return updated settings without mutating the active snapshot."""

        if not isinstance(language, Language):
            raise TypeError("language must be a Language")
        return replace(self, language=language)

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> Settings:
        """Build settings from persisted data, defaulting a missing language to ja."""

        if not isinstance(data, Mapping):
            raise SettingsDataError("settings must be an object")

        value = data.get("language", Language.JAPANESE.value)
        if not isinstance(value, str):
            raise SettingsDataError("settings.language must be a string")
        try:
            language = Language(value)
        except ValueError as error:
            raise SettingsDataError(f"unsupported language: {value}") from error
        return cls(language=language)
