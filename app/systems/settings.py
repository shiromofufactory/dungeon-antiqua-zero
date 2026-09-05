"""Persist device settings separately from game progress."""

from __future__ import annotations

import json
from pathlib import Path

if __package__ == "systems":
    from state import Settings, SettingsDataError
else:
    from ..state import Settings, SettingsDataError


SETTINGS_DIRECTORY = Path.home() / ".config" / ".pyxel" / "dungeon-antiqua-zero"
SETTINGS_PATH = SETTINGS_DIRECTORY / "settings.json"


class SettingsSystemError(RuntimeError):
    """Raised when device settings cannot be read or written safely."""


class SettingsRepository:
    """Load and atomically persist one device-settings document."""

    def __init__(self, path: Path = SETTINGS_PATH) -> None:
        if not isinstance(path, Path):
            raise TypeError("settings path must be a pathlib.Path")
        self.path = path

    def load(self) -> Settings:
        """Load persisted settings, using defaults when no file exists."""

        if not self.path.is_file():
            return Settings()
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
            return Settings.from_dict(document)
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
            SettingsDataError,
            TypeError,
            ValueError,
        ) as error:
            raise SettingsSystemError("failed to read device settings") from error

    def save(self, settings: Settings) -> None:
        """Atomically replace the persisted device-settings document."""

        if not isinstance(settings, Settings):
            raise TypeError("settings must be Settings")
        serialized = json.dumps(
            settings.to_dict(),
            ensure_ascii=False,
            indent=2,
        ) + "\n"
        temporary_path = self.path.with_suffix(".json.tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path.write_text(serialized, encoding="utf-8")
            temporary_path.replace(self.path)
        except OSError as error:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise SettingsSystemError("failed to write device settings") from error


__all__ = [
    "SETTINGS_DIRECTORY",
    "SETTINGS_PATH",
    "SettingsRepository",
    "SettingsSystemError",
]
