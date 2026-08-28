from __future__ import annotations

import unittest

from app.state import Language, Settings, SettingsDataError


class SettingsTest(unittest.TestCase):
    def test_language_defaults_to_japanese(self) -> None:
        self.assertEqual(Settings().language, Language.JAPANESE)
        self.assertEqual(Settings.from_dict({}).language, Language.JAPANESE)

    def test_language_round_trips_through_json_compatible_data(self) -> None:
        settings = Settings(language=Language.SIMPLIFIED_CHINESE)

        self.assertEqual(settings.to_dict(), {"language": "zhcn"})
        self.assertEqual(Settings.from_dict(settings.to_dict()), settings)

    def test_language_change_returns_a_new_settings_snapshot(self) -> None:
        original = Settings()

        changed = original.with_language(Language.ENGLISH)

        self.assertEqual(original.language, Language.JAPANESE)
        self.assertEqual(changed.language, Language.ENGLISH)

    def test_unknown_persisted_language_is_rejected(self) -> None:
        with self.assertRaisesRegex(SettingsDataError, "unsupported language"):
            Settings.from_dict({"language": "fr"})

    def test_settings_require_a_language_value(self) -> None:
        with self.assertRaises(TypeError):
            Settings(language="ja")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
