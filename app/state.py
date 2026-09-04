"""Persistent device settings and per-playthrough game state."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
import re
from typing import Mapping


class Language(StrEnum):
    """Stable language identifiers used by settings and localized data."""

    JAPANESE = "ja"
    ENGLISH = "en"
    SIMPLIFIED_CHINESE = "zhcn"


class Difficulty(StrEnum):
    """Stable difficulty identifiers stored in game save data."""

    NORMAL = "normal"
    HARD = "hard"


class DisplayMode(StrEnum):
    """Stable desktop rendering styles used by Pyxel."""

    PIXEL = "pixel"
    SMOOTH = "smooth"


class SettingsDataError(ValueError):
    """Raised when persisted settings cannot be interpreted safely."""


_STABLE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class Settings:
    """Device and player preferences stored separately from game progress."""

    language: Language = Language.JAPANESE
    bgm_volume: int = 3
    se_volume: int = 3
    screen_scale: int = 3
    display_mode: DisplayMode = DisplayMode.PIXEL

    def __post_init__(self) -> None:
        if not isinstance(self.language, Language):
            raise TypeError("language must be a Language")
        if isinstance(self.bgm_volume, bool) or not isinstance(
            self.bgm_volume,
            int,
        ):
            raise TypeError("bgm_volume must be an integer")
        if not 0 <= self.bgm_volume <= 4:
            raise ValueError("bgm_volume must be from 0 to 4")
        if isinstance(self.se_volume, bool) or not isinstance(
            self.se_volume,
            int,
        ):
            raise TypeError("se_volume must be an integer")
        if not 0 <= self.se_volume <= 4:
            raise ValueError("se_volume must be from 0 to 4")
        if isinstance(self.screen_scale, bool) or not isinstance(
            self.screen_scale,
            int,
        ):
            raise TypeError("screen_scale must be an integer")
        if not 1 <= self.screen_scale <= 5:
            raise ValueError("screen_scale must be from 1 to 5")
        if not isinstance(self.display_mode, DisplayMode):
            raise TypeError("display_mode must be a DisplayMode")

    def to_dict(self) -> dict[str, object]:
        """Return the JSON-compatible representation of these settings."""

        return {
            "language": self.language.value,
            "bgm_volume": self.bgm_volume,
            "se_volume": self.se_volume,
            "screen_scale": self.screen_scale,
            "display_mode": self.display_mode.value,
        }

    def with_language(self, language: Language) -> Settings:
        """Return updated settings without mutating the active snapshot."""

        if not isinstance(language, Language):
            raise TypeError("language must be a Language")
        return replace(self, language=language)

    def with_se_volume(self, volume: int) -> Settings:
        """Return updated settings after validating the DA2 volume range."""

        return replace(self, se_volume=volume)

    def with_bgm_volume(self, volume: int) -> Settings:
        """Return updated settings after validating the DA2 volume range."""

        return replace(self, bgm_volume=volume)

    def with_screen_scale(self, scale: int) -> Settings:
        """Return updated settings after validating the desktop scale."""

        return replace(self, screen_scale=scale)

    def with_display_mode(self, mode: DisplayMode) -> Settings:
        """Return updated settings for the desktop rendering style."""

        if not isinstance(mode, DisplayMode):
            raise TypeError("mode must be a DisplayMode")
        return replace(self, display_mode=mode)

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> Settings:
        """Build settings from persisted data with DA2-compatible defaults."""

        if not isinstance(data, Mapping):
            raise SettingsDataError("settings must be an object")

        language_value = data.get("language", Language.JAPANESE.value)
        if not isinstance(language_value, str):
            raise SettingsDataError("settings.language must be a string")
        try:
            language = Language(language_value)
        except ValueError as error:
            raise SettingsDataError(
                f"unsupported language: {language_value}"
            ) from error

        display_value = data.get("display_mode", DisplayMode.PIXEL.value)
        if not isinstance(display_value, str):
            raise SettingsDataError("settings.display_mode must be a string")
        try:
            display_mode = DisplayMode(display_value)
        except ValueError as error:
            raise SettingsDataError(
                f"unsupported display mode: {display_value}"
            ) from error
        try:
            return cls(
                language=language,
                bgm_volume=data.get("bgm_volume", 3),
                se_volume=data.get("se_volume", 3),
                screen_scale=data.get("screen_scale", 3),
                display_mode=display_mode,
            )
        except (TypeError, ValueError) as error:
            raise SettingsDataError(str(error)) from error


@dataclass
class SaveData:
    """Mutable, saveable state shared by one game playthrough."""

    gold: int = 0
    experience: int = 0
    difficulty: Difficulty = Difficulty.NORMAL
    play_time_frames: int = 0
    visited_site_ids: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        for name in ("gold", "experience", "play_time_frames"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if value < 0:
                raise ValueError(f"{name} must not be negative")
        if not isinstance(self.difficulty, Difficulty):
            raise TypeError("difficulty must be a Difficulty")
        if not isinstance(self.visited_site_ids, set) or not all(
            isinstance(site_id, str)
            and _STABLE_ID_PATTERN.fullmatch(site_id) is not None
            for site_id in self.visited_site_ids
        ):
            raise TypeError("visited_site_ids must be a set of stable IDs")

    def advance_play_time(self, frames: int = 1) -> None:
        """Add active gameplay frames to the persisted play time."""

        if isinstance(frames, bool) or not isinstance(frames, int):
            raise TypeError("frames must be an integer")
        if frames < 0:
            raise ValueError("frames must not be negative")
        self.play_time_frames += frames

    def remember_site(self, site_id: str) -> None:
        """Remember one entered site as a future teleport destination."""

        if (
            not isinstance(site_id, str)
            or _STABLE_ID_PATTERN.fullmatch(site_id) is None
        ):
            raise ValueError("site ID must be lower_snake_case")
        self.visited_site_ids.add(site_id)
