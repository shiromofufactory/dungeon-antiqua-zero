from __future__ import annotations

import unittest

from app.state import (
    DisplayMode,
    Difficulty,
    Language,
    SaveData,
    Settings,
    SettingsDataError,
    SpellMode,
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
                "screen_flash_enabled": True,
                "in_game_hints_enabled": True,
                "auto_battle_spell_mode": "use",
                "remember_battle_commands": True,
                "control_guide_device": None,
            },
        )
        self.assertEqual(Settings.from_dict(settings.to_dict()), settings)

    def test_control_guide_device_defaults_migrates_and_round_trips(self) -> None:
        self.assertIsNone(Settings.from_dict({"language": "ja"}).control_guide_device)
        for device in ("keyboard", "gamepad"):
            settings = Settings().with_control_guide_device(device)
            self.assertEqual(Settings.from_dict(settings.to_dict()), settings)
        for invalid in ("mouse", "", 1, True, [], {}):
            with self.subTest(value=invalid), self.assertRaises(SettingsDataError):
                Settings.from_dict({"control_guide_device": invalid})

    def test_old_settings_enable_hints_and_invalid_hint_values_are_rejected(self) -> None:
        self.assertTrue(Settings.from_dict({"language": "ja"}).in_game_hints_enabled)
        disabled = Settings().with_in_game_hints_enabled(False)
        self.assertEqual(Settings.from_dict(disabled.to_dict()), disabled)
        with self.assertRaises(SettingsDataError):
            Settings.from_dict({"in_game_hints_enabled": 1})

    def test_battle_preferences_restore_old_settings_and_validate_new_values(
        self,
    ) -> None:
        old = Settings.from_dict({"language": "ja"})
        self.assertIs(old.auto_battle_spell_mode, SpellMode.USE)
        self.assertTrue(old.remember_battle_commands)
        for mode in SpellMode:
            changed = old.with_auto_battle_spell_mode(
                mode
            ).with_remember_battle_commands(False)
            self.assertEqual(Settings.from_dict(changed.to_dict()), changed)
        for document in (
            {"auto_battle_spell_mode": "invalid"},
            {"auto_battle_spell_mode": 0},
            {"remember_battle_commands": 1},
        ):
            with self.assertRaises(SettingsDataError):
                Settings.from_dict(document)
        with self.assertRaises(TypeError):
            old.with_auto_battle_spell_mode("use")
        with self.assertRaises(TypeError):
            old.with_remember_battle_commands(1)

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
            screen_flash_enabled=False,
        )

        self.assertEqual(Settings.from_dict(settings.to_dict()), settings)
        self.assertEqual(settings.with_bgm_volume(0).bgm_volume, 0)
        self.assertEqual(settings.with_se_volume(0).se_volume, 0)
        self.assertEqual(settings.with_screen_scale(1).screen_scale, 1)
        self.assertIs(
            settings.with_display_mode(DisplayMode.PIXEL).display_mode,
            DisplayMode.PIXEL,
        )
        self.assertTrue(settings.with_screen_flash_enabled(True).screen_flash_enabled)
        self.assertTrue(Settings.from_dict({}).screen_flash_enabled)

    def test_invalid_da2_desktop_settings_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            Settings(bgm_volume=5)
        with self.assertRaises(ValueError):
            Settings(se_volume=5)
        with self.assertRaises(ValueError):
            Settings(screen_scale=0)
        with self.assertRaises(TypeError):
            Settings(display_mode="pixel")  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            Settings(screen_flash_enabled=1)  # type: ignore[arg-type]
        with self.assertRaises(SettingsDataError):
            Settings.from_dict({"display_mode": "crt"})


class SaveDataTest(unittest.TestCase):
    def test_new_game_defaults_are_owned_by_one_save(self) -> None:
        save_data = SaveData()

        self.assertEqual(save_data.gold, 0)
        self.assertEqual(save_data.experience, 0)
        self.assertEqual(save_data.battle_count, 0)
        self.assertEqual(save_data.encounter_count, 0)
        self.assertEqual(save_data.difficulty, Difficulty.NORMAL)
        self.assertEqual(save_data.play_time_frames, 0)
        self.assertEqual(save_data.event_flags, set())
        self.assertEqual(save_data.visited_site_ids, set())
        self.assertEqual(save_data.opened_treasures, set())
        self.assertEqual(save_data.monster_records, {})
        self.assertEqual(save_data.logs, [])

    def test_remembers_visited_sites_once(self) -> None:
        save_data = SaveData()

        save_data.remember_site("sample_town")
        save_data.remember_site("sample_town")

        self.assertEqual(save_data.visited_site_ids, {"sample_town"})

    def test_play_time_advances_in_frames(self) -> None:
        save_data = SaveData()

        save_data.advance_play_time()
        save_data.advance_play_time(59)

        self.assertEqual(save_data.play_time_frames, 60)

    def test_invalid_game_values_are_rejected(self) -> None:
        invalid_values = (
            {"gold": -1},
            {"experience": True},
            {"battle_count": -1},
            {"encounter_count": -1},
            {"play_time_frames": "0"},
            {"difficulty": "normal"},
            {"event_flags": ["prologue_complete"]},
            {"event_flags": {""}},
            {"event_flags": {"Invalid"}},
            {"visited_site_ids": ["sample_town"]},
            {"visited_site_ids": {"Invalid Site"}},
            {"opened_treasures": [("worldmap", "chest_1")]},
            {"opened_treasures": {("", "chest_1")}},
            {"monster_records": {"Giant Spider": ["profile"]}},
            {"monster_records": {"": {"profile"}}},
            {"logs": [{}]},
            {"logs": [{"text_key": "event", "arguments": {"VALUE": []}}]},
            {
                "logs": [{
                    "text_key": "legacy.event",
                    "message_id": "sample.event",
                    "arguments": {},
                }]
            },
        )

        for value in invalid_values:
            with self.subTest(value=value), self.assertRaises(
                (TypeError, ValueError)
            ):
                SaveData(**value)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
