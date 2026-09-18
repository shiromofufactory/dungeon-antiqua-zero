from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from tools._bootstrap import APP_ROOT  # noqa: F401

from state import DisplayMode, Language, Settings, SpellMode
from systems.settings import SettingsRepository, SettingsSystemError


class SettingsRepositoryTest(unittest.TestCase):
    def test_missing_file_uses_default_settings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = SettingsRepository(Path(directory) / "settings.json")

            self.assertEqual(repository.load(), Settings())

    def test_settings_round_trip_through_atomic_file(self) -> None:
        settings = Settings(
            language=Language.ENGLISH,
            bgm_volume=2,
            se_volume=1,
            screen_scale=4,
            display_mode=DisplayMode.SMOOTH,
            screen_flash_enabled=False,
            in_game_hints_enabled=False,
            auto_battle_spell_mode=SpellMode.RECOVERY_ONLY,
            remember_battle_commands=False,
        )
        with tempfile.TemporaryDirectory() as directory:
            repository = SettingsRepository(Path(directory) / "settings.json")

            repository.save(settings)

            self.assertEqual(repository.load(), settings)
            self.assertEqual(
                json.loads(repository.path.read_text(encoding="utf-8")),
                settings.to_dict(),
            )
            self.assertFalse(
                repository.path.with_suffix(".json.tmp").exists()
            )

    def test_invalid_settings_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text('{"language": "fr"}', encoding="utf-8")
            repository = SettingsRepository(path)

            with self.assertRaises(SettingsSystemError):
                repository.load()


if __name__ == "__main__":
    unittest.main()
