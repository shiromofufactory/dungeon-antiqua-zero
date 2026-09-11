from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from app.resources.audio import (
    BGM_VOLUME_GAINS,
    SE_CATALOG,
    AudioResourceError,
    BgmPlayer,
    list_bgm_ids,
    load_se_catalog,
    list_se_ids,
    play_se,
    reload_se_catalog,
    se_channel_and_sound,
)


class FakeSound:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.pcm_paths: list[str] = []

    def pcm(self, path: str) -> None:
        self.pcm_paths.append(path)
        if self.error is not None:
            raise self.error


class FakePyxel:
    def __init__(self, *, sound_error: Exception | None = None) -> None:
        self.channels = [SimpleNamespace(gain=0.125) for _index in range(4)]
        self.sound_error = sound_error
        self.created_sounds: list[FakeSound] = []
        self.play_calls: list[tuple[object, ...]] = []
        self.stop_calls: list[int] = []
        self.play_position: tuple[int, int] | None = None

    def Sound(self) -> FakeSound:
        sound = FakeSound(error=self.sound_error)
        self.created_sounds.append(sound)
        return sound

    def play(
        self,
        channel: int,
        sound: FakeSound,
        *,
        sec: float,
        loop: bool,
    ) -> None:
        self.play_calls.append((channel, sound, sec, loop))
        self.play_position = (0, 0)

    def stop(self, channel: int) -> None:
        self.stop_calls.append(channel)
        self.play_position = None

    def play_pos(self, channel: int) -> tuple[int, int] | None:
        return self.play_position


class BgmPlayerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.audio_dir = Path(self.temporary.name)
        (self.audio_dir / "da3-field.ogg").touch()
        (self.audio_dir / "da3-welcome.ogg").touch()
        (self.audio_dir / "dungeon").mkdir()
        (self.audio_dir / "dungeon" / "floor1.ogg").touch()
        (self.audio_dir / ".temporary.ogg").touch()
        self.pyxel = FakePyxel()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_lists_stable_ids_without_extensions(self) -> None:
        self.assertEqual(
            list_bgm_ids(self.audio_dir),
            ("da3-field", "da3-welcome", "dungeon/floor1"),
        )

    def test_runtime_welcome_bgm_is_available(self) -> None:
        self.assertIn("da3-welcome", list_bgm_ids())

    def test_runtime_battle_bgm_is_available(self) -> None:
        self.assertIn("da3-battle1", list_bgm_ids())

    def test_runtime_encounter_jingle_is_available(self) -> None:
        self.assertIn("da3-encount", list_bgm_ids())

    def test_plays_stable_se_id_from_shared_catalog(self) -> None:
        pyxel = Mock()

        play_se("confirm", pyxel_api=pyxel)

        pyxel.play.assert_called_once_with(1, 9)
        self.assertTrue(
            {
                "alert",
                "battle_escape",
                "battle_focus",
                "battle_hit",
                "battle_monster_death",
                "battle_weapon_blunt",
                "battle_weapon_slash",
                "confirm",
                "teleport",
                "treasure_open",
            }
            <= set(list_se_ids())
        )
        self.assertEqual(se_channel_and_sound("confirm"), (1, 9))
        self.assertEqual(se_channel_and_sound("battle_escape"), (0, 26))
        self.assertEqual(se_channel_and_sound("battle_focus"), (0, 37))
        self.assertEqual(se_channel_and_sound("battle_monster_death"), (0, 10))
        self.assertEqual(se_channel_and_sound("battle_weapon_slash"), (0, 11))
        self.assertEqual(se_channel_and_sound("battle_weapon_blunt"), (0, 29))
        with self.assertRaises(AudioResourceError):
            play_se("missing", pyxel_api=pyxel)
        with self.assertRaises(AudioResourceError):
            se_channel_and_sound("missing")

    def test_reloads_edited_catalog_without_replacing_public_mapping(self) -> None:
        path = self.audio_dir / "catalog.json"
        path.write_text(
            json.dumps(
                {
                    "format_version": 1,
                    "sound_effects": {
                        "spell_fire1": {"channel": 0, "sound": 17},
                    },
                }
            ),
            encoding="utf-8",
        )
        public_mapping = SE_CATALOG

        try:
            loaded = load_se_catalog(path)
            reloaded = reload_se_catalog(path)
            self.assertEqual(loaded["spell_fire1"], (0, 17))
            self.assertIs(reloaded, public_mapping)
            self.assertEqual(se_channel_and_sound("spell_fire1"), (0, 17))
        finally:
            reload_se_catalog()

    def test_loads_and_loops_bgm_on_dedicated_channel(self) -> None:
        player = BgmPlayer(
            self.audio_dir,
            volume=3,
            pyxel_api=self.pyxel,
        )

        changed = player.play("da3-field")

        self.assertTrue(changed)
        self.assertEqual(player.current_id, "da3-field")
        self.assertTrue(player.is_playing)
        self.assertEqual(self.pyxel.channels[2].gain, BGM_VOLUME_GAINS[3])
        self.assertEqual(self.pyxel.stop_calls, [2])
        sound = self.pyxel.created_sounds[0]
        self.assertEqual(
            sound.pcm_paths,
            [str((self.audio_dir / "da3-field.ogg").resolve())],
        )
        self.assertEqual(self.pyxel.play_calls, [(2, sound, 0.0, True)])

    def test_does_not_restart_the_same_looping_bgm(self) -> None:
        player = BgmPlayer(self.audio_dir, pyxel_api=self.pyxel)
        player.play("da3-field")

        changed = player.play("da3-field")

        self.assertFalse(changed)
        self.assertEqual(len(self.pyxel.created_sounds), 1)
        self.assertEqual(len(self.pyxel.play_calls), 1)

    def test_switches_tracks_and_stops_only_the_bgm_channel(self) -> None:
        player = BgmPlayer(self.audio_dir, pyxel_api=self.pyxel)
        player.play("da3-field")
        player.play("dungeon/floor1", loop=False, start_sec=1.25)

        stopped = player.stop()

        self.assertTrue(stopped)
        self.assertIsNone(player.current_id)
        self.assertEqual(self.pyxel.stop_calls, [2, 2, 2])
        self.assertEqual(self.pyxel.play_calls[-1][2:], (1.25, False))

    def test_starts_queued_field_bgm_when_one_shot_finishes(self) -> None:
        player = BgmPlayer(self.audio_dir, pyxel_api=self.pyxel)

        player.play_once_then("da3-welcome", "da3-field")

        self.assertEqual(player.current_id, "da3-welcome")
        self.assertFalse(player.update())
        self.pyxel.play_position = None
        self.assertTrue(player.update())
        self.assertEqual(player.current_id, "da3-field")
        self.assertEqual(self.pyxel.play_calls[-1][2:], (0.0, True))

    def test_missing_or_unsafe_ids_are_rejected(self) -> None:
        player = BgmPlayer(self.audio_dir, pyxel_api=self.pyxel)

        with self.assertRaises(AudioResourceError):
            player.play("missing")
        for bgm_id in ("../secret", "/absolute", "da3-field.ogg"):
            with self.subTest(bgm_id=bgm_id), self.assertRaises(ValueError):
                player.play(bgm_id)
        self.assertEqual(self.pyxel.stop_calls, [])

    def test_decode_errors_are_reported_as_resource_errors(self) -> None:
        pyxel_api = FakePyxel(sound_error=RuntimeError("decode failed"))
        player = BgmPlayer(self.audio_dir, pyxel_api=pyxel_api)

        with self.assertRaisesRegex(AudioResourceError, "読み込めません"):
            player.play("da3-field")

    def test_volume_uses_da2_levels_and_validates_range(self) -> None:
        player = BgmPlayer(self.audio_dir, volume=0, pyxel_api=self.pyxel)
        self.assertEqual(self.pyxel.channels[2].gain, 0.0)

        player.set_volume(4)

        self.assertEqual(player.volume, 4)
        self.assertEqual(self.pyxel.channels[2].gain, 0.8)
        with self.assertRaises(ValueError):
            player.set_volume(5)
        with self.assertRaises(TypeError):
            player.set_volume(True)  # type: ignore[arg-type]

    def test_fade_rate_scales_gain_without_changing_configured_volume(self) -> None:
        player = BgmPlayer(self.audio_dir, volume=3, pyxel_api=self.pyxel)

        player.set_fade_rate(0.5)

        self.assertEqual(player.volume, 3)
        self.assertEqual(player.fade_rate, 0.5)
        self.assertEqual(
            self.pyxel.channels[2].gain,
            BGM_VOLUME_GAINS[3] * 0.5,
        )
        player.set_volume(4)
        self.assertEqual(
            self.pyxel.channels[2].gain,
            BGM_VOLUME_GAINS[4] * 0.5,
        )

        with self.assertRaises(ValueError):
            player.set_fade_rate(1.1)
        with self.assertRaises(TypeError):
            player.set_fade_rate(True)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
