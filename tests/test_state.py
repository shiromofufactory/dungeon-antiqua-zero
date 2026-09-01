from __future__ import annotations

import unittest

from app.state import (
    DisplayMode,
    Difficulty,
    Language,
    SaveData,
    Settings,
    SettingsDataError,
)


class SettingsTest(unittest.TestCase):
    def test_language_defaults_to_japanese(self) -> None:
        self.assertEqual(Settings().language, Language.JAPANESE)
        self.assertEqual(Settings.from_dict({}).language, Language.JAPANESE)

    def test_language_round_trips_through_json_compatible_data(self) -> None:
        settings = Settings(language=Language.SIMPLIFIED_CHINESE)

        self.assertEqual(
            settings.to_dict(),
            {
                "language": "zhcn",
                "bgm_volume": 3,
                "se_volume": 3,
                "screen_scale": 3,
                "display_mode": "pixel",
            },
        )
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

    def test_da2_desktop_settings_round_trip(self) -> None:
        settings = Settings(
            bgm_volume=2,
            se_volume=4,
            screen_scale=5,
            display_mode=DisplayMode.SMOOTH,
        )

        self.assertEqual(Settings.from_dict(settings.to_dict()), settings)
        self.assertEqual(settings.with_bgm_volume(0).bgm_volume, 0)
        self.assertEqual(settings.with_se_volume(0).se_volume, 0)
        self.assertEqual(settings.with_screen_scale(1).screen_scale, 1)
        self.assertIs(
            settings.with_display_mode(DisplayMode.PIXEL).display_mode,
            DisplayMode.PIXEL,
        )

    def test_invalid_da2_desktop_settings_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            Settings(bgm_volume=5)
        with self.assertRaises(ValueError):
            Settings(se_volume=5)
        with self.assertRaises(ValueError):
            Settings(screen_scale=0)
        with self.assertRaises(TypeError):
            Settings(display_mode="pixel")  # type: ignore[arg-type]
        with self.assertRaises(SettingsDataError):
            Settings.from_dict({"display_mode": "crt"})


class SaveDataTest(unittest.TestCase):
    def test_new_game_defaults_are_owned_by_one_save(self) -> None:
        save_data = SaveData()

        self.assertEqual(save_data.gold, 0)
        self.assertEqual(save_data.experience, 0)
        self.assertEqual(save_data.difficulty, Difficulty.NORMAL)
        self.assertEqual(save_data.play_time_frames, 0)

    def test_play_time_advances_in_frames(self) -> None:
        save_data = SaveData()

        save_data.advance_play_time()
        save_data.advance_play_time(59)

        self.assertEqual(save_data.play_time_frames, 60)

    def test_invalid_game_values_are_rejected(self) -> None:
        invalid_values = (
            {"gold": -1},
            {"experience": True},
            {"play_time_frames": "0"},
            {"difficulty": "normal"},
        )

        for value in invalid_values:
            with self.subTest(value=value), self.assertRaises(
                (TypeError, ValueError)
            ):
                SaveData(**value)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
