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
    def test_fade_stop_lowers_gain_then_stays_silent_until_next_play(self) -> None:
        player = BgmPlayer(self.audio_dir, pyxel_api=self.pyxel)
        player.play("da3-field")
        self.assertTrue(player.fade_out_and_stop())
        self.assertEqual(self.pyxel.channels[2].gain, 0.6)
        for frame in range(1, 30):
            self.assertFalse(player.update())
            self.assertEqual(player.current_id, "da3-field")
            self.assertAlmostEqual(self.pyxel.channels[2].gain, 0.6 * (30 - frame) / 30)
            self.assertTrue(player.is_fading_out)
        self.assertTrue(player.update())
        self.assertFalse(player.is_fading_out)
        self.assertIsNone(player.current_id)
        self.assertIsNone(self.pyxel.play_position)
        self.assertEqual(self.pyxel.stop_calls, [2, 2])
        for _ in range(60):
            self.assertFalse(player.update())
        player.pause()
        player.resume()
        self.assertEqual(len(self.pyxel.play_calls), 1)
        player.play("da3-field")
        self.assertEqual(len(self.pyxel.play_calls), 2)
        self.assertEqual(self.pyxel.channels[2].gain, 0.6)
        self.assertEqual([channel.gain for index, channel in enumerate(self.pyxel.channels) if index != 2], [0.125] * 3)

    def test_fade_stop_cancels_queued_music_even_if_jingle_finishes_early(self) -> None:
        player = BgmPlayer(self.audio_dir, pyxel_api=self.pyxel)
        player.play_once_then("da3-welcome", "da3-field")
        player.fade_out_and_stop()
        self.pyxel.play_position = None
        for _ in range(30):
            player.update()
        self.assertIsNone(player.current_id)
        self.assertFalse(player.update())
        self.assertEqual(len(self.pyxel.play_calls), 1)

    def test_fade_stop_pauses_with_playback_and_resumes_remaining_frames(self) -> None:
        player = BgmPlayer(self.audio_dir, pyxel_api=self.pyxel)
        player.play("da3-field")
        player.fade_out_and_stop()
        for _ in range(10):
            player.update()
        gain = self.pyxel.channels[2].gain
        self.pyxel.play_position = (0, 1.5)
        player.pause()
        for _ in range(60):
            player.update()
        self.assertEqual(self.pyxel.channels[2].gain, gain)
        player.resume()
        self.assertEqual(self.pyxel.play_calls[-1][2], 1.5)
        for _ in range(19):
            player.update()
            self.assertTrue(player.is_fading_out)
        player.update()
        self.assertIsNone(player.current_id)

    def test_play_during_fade_stop_cancels_stop_for_same_or_different_track(self) -> None:
        for next_id in ("da3-field", "da3-welcome"):
            with self.subTest(next_id=next_id):
                player = BgmPlayer(self.audio_dir, pyxel_api=self.pyxel)
                player.play("da3-field")
                player.fade_out_and_stop()
                player.update()
                player.play(next_id)
                self.assertFalse(player.is_fading_out)
                self.assertEqual(self.pyxel.channels[2].gain, 0.6)
                for _ in range(60):
                    player.update()
                self.assertEqual(player.current_id, next_id)

    def test_fade_stop_uses_current_gain_and_immediate_stop_clears_the_fade(self) -> None:
        player = BgmPlayer(self.audio_dir, pyxel_api=self.pyxel)
        self.assertFalse(player.fade_out_and_stop())
        self.assertFalse(player.is_fading_out)
        player.play("da3-field")
        player.set_fade_rate(0.5)
        player.fade_out_and_stop()
        player.update()
        self.assertAlmostEqual(self.pyxel.channels[2].gain, 0.3 * 29 / 30)
        player.set_volume(4)
        self.assertAlmostEqual(self.pyxel.channels[2].gain, 0.4 * 29 / 30)
        player.stop()
        self.assertFalse(player.is_fading_out)
        player.play("da3-welcome")
        self.assertEqual(self.pyxel.channels[2].gain, 0.8)

    def test_fade_stop_rejects_invalid_durations(self) -> None:
        player = BgmPlayer(self.audio_dir, pyxel_api=self.pyxel)
        for frames in (None, True, 30.0, "30", 0, -1):
            with self.subTest(frames=frames), self.assertRaises(ValueError):
                player.fade_out_and_stop(frames)

    def test_pause_resume_preserves_position_sound_loop_and_volume(self) -> None:
        player = BgmPlayer(self.audio_dir, pyxel_api=self.pyxel)
        player.play("da3-field")
        sound = self.pyxel.created_sounds[-1]
        self.pyxel.play_position = (0, 12.5)
        player.set_fade_rate(0.5)
        player.pause()
        player.pause()
        self.assertEqual(player.playback_position_sec, 12.5)
        self.assertIsNone(self.pyxel.play_position)
        self.assertEqual(player.current_id, "da3-field")
        self.assertFalse(player.update())
        player.resume()
        player.resume()
        self.assertEqual(self.pyxel.play_calls[-1], (2, sound, 12.5, True))
        self.assertEqual(len(self.pyxel.play_calls), 2)
        self.assertEqual(len(self.pyxel.created_sounds), 1)
        self.assertAlmostEqual(self.pyxel.channels[2].gain, 0.3)

    def test_paused_one_shot_keeps_queued_bgm_until_resumed_and_finished(self) -> None:
        player = BgmPlayer(self.audio_dir, pyxel_api=self.pyxel)
        player.play_once_then("da3-welcome", "da3-field")
        self.pyxel.play_position = (0, 1.25)
        player.pause()
        self.assertFalse(player.update())
        player.resume()
        self.assertEqual(self.pyxel.play_calls[-1][2:], (1.25, False))
        self.assertFalse(player.update())
        self.pyxel.play_position = None
        self.assertTrue(player.update())
        self.assertEqual(player.current_id, "da3-field")

    def test_pause_after_one_shot_finishes_does_not_restart_it(self) -> None:
        player = BgmPlayer(self.audio_dir, pyxel_api=self.pyxel)
        player.play_once_then("da3-welcome", "da3-field")
        self.pyxel.play_position = None
        player.pause()
        player.resume()
        self.assertEqual(len(self.pyxel.play_calls), 1)
        self.assertTrue(player.update())
        self.assertEqual(player.current_id, "da3-field")

    def test_stop_while_paused_discards_suspended_track(self) -> None:
        player = BgmPlayer(self.audio_dir, pyxel_api=self.pyxel)
        player.play("da3-field")
        player.pause()
        player.stop()
        player.resume()
        self.assertEqual(len(self.pyxel.play_calls), 1)
        self.assertIsNone(player.current_id)

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
        self.assertIn("da3-battle2", list_bgm_ids())

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
                "battle_hide",
                "battle_hit",
                "battle_identify",
                "battle_monster_death",
                "battle_weapon_blunt",
                "battle_weapon_slash",
                "confirm",
                "result_increment",
                "teleport",
                "treasure_open",
            }
            <= set(list_se_ids())
        )
        self.assertEqual(se_channel_and_sound("confirm"), (1, 9))
        self.assertEqual(se_channel_and_sound("battle_escape"), (0, 26))
        self.assertEqual(se_channel_and_sound("battle_focus"), (0, 37))
        self.assertEqual(se_channel_and_sound("battle_hide"), (0, 30))
        self.assertEqual(se_channel_and_sound("battle_identify"), (0, 20))
        self.assertEqual(se_channel_and_sound("battle_monster_death"), (0, 10))
        self.assertEqual(se_channel_and_sound("battle_weapon_slash"), (0, 11))
        self.assertEqual(se_channel_and_sound("battle_weapon_blunt"), (0, 29))
        self.assertEqual(se_channel_and_sound("result_increment"), (1, 2))
        self.assertEqual(se_channel_and_sound("save_complete"), (1, 6))
        self.assertEqual(se_channel_and_sound("auto_equip_complete"), (1, 6))
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

    def test_resumes_an_interrupted_loop_after_one_shot(self) -> None:
        player = BgmPlayer(self.audio_dir, pyxel_api=self.pyxel)
        player.play("da3-field")
        self.pyxel.play_position = (0, 12.5)

        player.play_once_then("da3-welcome", "da3-field")
        self.pyxel.play_position = None
        player.update()

        self.assertEqual(player.current_id, "da3-field")
        self.assertEqual(self.pyxel.play_calls[-1][2:], (12.5, True))

    def test_battle_jingles_resume_the_saved_field_position(self) -> None:
        player = BgmPlayer(self.audio_dir, pyxel_api=self.pyxel)
        player.play("da3-field")
        self.pyxel.play_position = (0, 12.5)
        saved_position = player.playback_position_sec
        player.play("da3-welcome", loop=False)
        player.play("dungeon/floor1")

        player.play_once_then(
            "da3-welcome", "da3-field", next_start_sec=saved_position,
        )
        # A level-up jingle interrupts the victory jingle before the field resumes.
        player.play_once_then("dungeon/floor1", "da3-field")
        self.assertFalse(player.transition_to("da3-field", start_sec=12.5))
        self.pyxel.play_position = None
        player.update()

        self.assertEqual(player.current_id, "da3-field")
        self.assertEqual(self.pyxel.play_calls[-1][2:], (12.5, True))

    def test_jingle_uses_live_field_position_instead_of_older_battle_position(self) -> None:
        player = BgmPlayer(self.audio_dir, pyxel_api=self.pyxel)
        player.play("da3-field", start_sec=12.5)
        self.pyxel.play_position = (0, 16.0)

        player.play_once_then("da3-welcome", "da3-field", next_start_sec=12.5)
        self.pyxel.play_position = None
        player.update()

        self.assertEqual(self.pyxel.play_calls[-1][2:], (16.0, True))

    def test_transition_resumes_saved_position_but_keeps_an_already_resumed_track(self) -> None:
        player = BgmPlayer(self.audio_dir, pyxel_api=self.pyxel)
        player.play("dungeon/floor1")
        player.stop()

        self.assertTrue(player.transition_to("da3-field", start_sec=12.5))
        self.assertEqual(self.pyxel.play_calls[-1][2:], (12.5, True))
        self.pyxel.play_position = (0, 16.0)
        self.assertFalse(player.transition_to("da3-field", start_sec=12.5))
        self.assertEqual(player.playback_position_sec, 16.0)
        self.assertEqual(len(self.pyxel.play_calls), 2)

    def test_different_jingle_successor_does_not_reuse_saved_position(self) -> None:
        player = BgmPlayer(self.audio_dir, pyxel_api=self.pyxel)
        player.play_once_then("da3-welcome", "da3-field", next_start_sec=12.5)
        player.play_once_then("da3-welcome", "dungeon/floor1")
        self.pyxel.play_position = None
        player.update()

        self.assertEqual(player.current_id, "dungeon/floor1")
        self.assertEqual(self.pyxel.play_calls[-1][2:], (0.0, True))

    def test_jingle_rejects_invalid_successor_positions_before_playing(self) -> None:
        player = BgmPlayer(self.audio_dir, pyxel_api=self.pyxel)
        for value, error in ((True, TypeError), ("12", TypeError), (-1, ValueError)):
            with self.subTest(value=value), self.assertRaises(error):
                player.play_once_then("da3-welcome", "da3-field", next_start_sec=value)
        self.assertEqual(self.pyxel.play_calls, [])

    def test_matching_scene_transition_does_not_interrupt_one_shot(self) -> None:
        player = BgmPlayer(self.audio_dir, pyxel_api=self.pyxel)
        player.play_once_then("da3-welcome", "da3-field")

        changed = player.transition_to("da3-field")

        self.assertFalse(changed)
        self.assertEqual(player.current_id, "da3-welcome")
        self.assertEqual(len(self.pyxel.play_calls), 1)

    def test_clears_an_unqueued_one_shot_after_it_finishes(self) -> None:
        player = BgmPlayer(self.audio_dir, pyxel_api=self.pyxel)
        player.play("da3-welcome", loop=False)
        self.pyxel.play_position = None

        changed = player.update()

        self.assertTrue(changed)
        self.assertIsNone(player.current_id)
        self.assertFalse(player.is_playing)

    def test_new_one_shot_interrupts_the_current_one_shot(self) -> None:
        player = BgmPlayer(self.audio_dir, pyxel_api=self.pyxel)
        player.play_once_then("da3-welcome", "da3-field")

        player.play_once_then("dungeon/floor1", "da3-field")

        self.assertEqual(player.current_id, "dungeon/floor1")
        self.assertEqual(len(self.pyxel.play_calls), 2)

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
