from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from app.audio_catalog import SoundEffectDefinition
from app.resources.audio import AudioResourceError, BGM_CHANNEL, SE_CHANNEL
from tools.sound_test.app import LIST_Y, PANEL_X, ROW_HEIGHT, SoundTestApp
from tools.sound_test.model import SoundTestSession, pyxel_sound_options, wav_sound_options


class SoundTestCatalogTest(unittest.TestCase):
    def test_all_64_numbers_show_every_current_catalog_alias(self):
        definitions = {
            "alert": SoundEffectDefinition("alert", sound=7),
            "another_alert": SoundEffectDefinition("another_alert", sound=7),
            "file_sound": SoundEffectDefinition("file_sound", wav="hit.wav"),
        }
        options = pyxel_sound_options(definitions)
        self.assertEqual(tuple(option.definition.sound for option in options), tuple(range(64)))
        self.assertEqual(options[0].label, "0")
        self.assertEqual(options[7].label, "7 (alert, another_alert)")
        self.assertEqual(options[63].label, "63")

    def test_wav_choices_include_unregistered_nested_files_with_original_case(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "sub").mkdir()
            for name in ("z.wav", "A.WAV", "sub/hit.wav", "ignored.ogg", ".hidden.wav"):
                (root / name).touch()
            outside = root.parent / f"{root.name}-outside.wav"
            try:
                outside.touch()
                (root / "outside.wav").symlink_to(outside)
                choices = wav_sound_options(root)
                self.assertEqual(tuple(option.label for option in choices),
                                 ("A.WAV", "sub/hit.wav", "z.wav"))
                self.assertEqual(choices[1].definition.wav, "sub/hit.wav")
            finally:
                outside.unlink(missing_ok=True)


class SoundTestSessionTest(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        (self.root / "audio").mkdir()
        (self.root / "se").mkdir()
        for name in ("first.ogg", "second.ogg"):
            (self.root / "audio" / name).touch()
        (self.root / "se" / "unregistered.wav").touch()
        (self.root / "audio" / "catalog.json").write_text(json.dumps({
            "format_version": 2, "sound_effects": {"alert": {"sound": 7}},
        }))
        self.px = Mock()
        self.px.channels = [SimpleNamespace(gain=0.0) for _ in range(4)]
        self.session = SoundTestSession(self.root, pyxel_api=self.px)

    def test_bgm_loops_while_raw_pyxel_and_unregistered_wav_use_game_gains(self):
        self.px.play.assert_not_called()
        self.session.play_bgm()
        self.assertEqual(self.px.play.call_args.args[0], BGM_CHANNEL)
        self.assertTrue(self.px.play.call_args.kwargs["loop"])
        self.px.stop.reset_mock()

        self.session.select_se(7)
        self.session.play_se()
        self.px.play.assert_called_with(SE_CHANNEL, 7)
        self.assertAlmostEqual(self.px.channels[SE_CHANNEL].gain, 0.15)
        self.session.use_wav = True
        self.session.play_se()
        self.assertEqual(self.px.play.call_args.args[0], SE_CHANNEL)
        self.px.Sound.return_value.pcm.assert_called_with(
            str(self.root / "se" / "unregistered.wav"))
        self.assertAlmostEqual(self.px.channels[SE_CHANNEL].gain, 0.6)
        self.assertAlmostEqual(self.px.channels[BGM_CHANNEL].gain, 0.6)
        self.assertEqual(self.session.bgm.current_id, "first")
        self.px.stop.assert_not_called()

    def test_live_volumes_are_independent_and_clamped_to_game_range(self):
        self.session.play_bgm()
        self.session.use_wav = True
        self.session.play_se()
        self.session.set_volume(bgm=False, volume=1)
        self.assertAlmostEqual(self.px.channels[SE_CHANNEL].gain, 0.2)
        self.assertAlmostEqual(self.px.channels[BGM_CHANNEL].gain, 0.6)
        self.session.set_volume(bgm=True, volume=4)
        self.assertAlmostEqual(self.px.channels[BGM_CHANNEL].gain, 0.8)
        self.assertAlmostEqual(self.px.channels[SE_CHANNEL].gain, 0.2)
        self.session.set_volume(bgm=False, volume=-1)
        self.session.set_volume(bgm=True, volume=5)
        self.assertEqual(self.px.channels[SE_CHANNEL].gain, 0)
        self.assertEqual(self.session.bgm.volume, 4)

    def test_bgm_selection_switches_only_when_playing_and_stop_se_keeps_bgm(self):
        self.session.select_bgm(1)
        self.px.play.assert_not_called()
        self.session.play_bgm()
        self.assertEqual(self.session.bgm.current_id, "second")
        self.session.select_bgm(0)
        self.assertEqual(self.session.bgm.current_id, "first")
        self.px.stop.reset_mock()
        self.session.stop_se()
        self.px.stop.assert_called_once_with(SE_CHANNEL)
        self.assertEqual(self.session.bgm.current_id, "first")
        self.session.close()
        self.assertIsNone(self.session.bgm.current_id)

    def test_type_switch_retains_selections_and_bounds(self):
        self.session.select_se(100)
        self.assertEqual(self.session.se_index, 63)
        self.session.use_wav = True
        self.session.select_se(100)
        self.assertEqual(self.session.se_index, 0)
        self.session.use_wav = False
        self.assertEqual(self.session.se_index, 63)
        self.session.select_se(-1)
        self.assertEqual(self.session.se_index, 0)

    def test_empty_lists_and_decode_failures_are_explicit(self):
        for path in (self.root / "audio").glob("*.ogg"):
            path.unlink()
        (self.root / "se" / "unregistered.wav").unlink()
        empty = SoundTestSession(self.root, pyxel_api=self.px)
        with self.assertRaisesRegex(AudioResourceError, "BGMがありません"):
            empty.play_bgm()
        empty.use_wav = True
        with self.assertRaisesRegex(AudioResourceError, "WAVがありません"):
            empty.play_se()

        self.session.use_wav = True
        with self.assertRaises(AudioResourceError):
            self.session.play_se()
        (self.root / "se" / "unregistered.wav").touch()
        self.px.Sound.return_value.pcm.side_effect = ValueError("broken WAV")
        with self.assertRaisesRegex(AudioResourceError, "broken WAV"):
            self.session.play_se()

    def test_mouse_selects_scrolled_number_and_buttons_use_local_settings(self):
        app = SoundTestApp.__new__(SoundTestApp)
        app.session = self.session
        app.focus = 0
        self.session.select_se(63)
        fake = SimpleNamespace(mouse_x=PANEL_X[1] + 8,
                               mouse_y=LIST_Y + ROW_HEIGHT * 9 + 1,
                               mouse_wheel=0, MOUSE_BUTTON_LEFT=1,
                               btnp=lambda key: True)
        with patch("tools.sound_test.app.pyxel", fake):
            app._handle_mouse()
        self.assertEqual(app.focus, 1)
        self.assertEqual(self.session.se_index, 63)
        app._activate("volume_1_0")
        self.assertEqual(self.session.se.volume, 0)
        app._activate("wav")
        self.assertTrue(self.session.use_wav)
        app._activate("bgm_play")
        self.assertEqual(self.session.bgm.current_id, "first")
        app._activate("bgm_stop")
        self.assertIsNone(self.session.bgm.current_id)

    def test_keyboard_preview_and_error_recovery_keep_bgm_running(self):
        import pyxel

        app = SoundTestApp.__new__(SoundTestApp)
        app.session = self.session
        app.focus = 0
        app.error = False
        app.status = ""
        app._handle_mouse = Mock()

        def press(*keys):
            with patch("tools.sound_test.app.pyxel.btnp",
                       side_effect=lambda key, *repeat: key in keys):
                app.update()

        press(pyxel.KEY_TAB, pyxel.KEY_PAGEDOWN)
        self.assertEqual(self.session.sound_index, 10)
        press(pyxel.KEY_RIGHT, pyxel.KEY_SPACE, pyxel.KEY_RETURN)
        self.assertTrue(self.session.use_wav)
        self.assertTrue(self.session.bgm.is_playing)
        self.assertEqual(self.px.play.call_args.args[0], SE_CHANNEL)
        (self.root / "se" / "unregistered.wav").unlink()
        press(pyxel.KEY_RETURN)
        self.assertTrue(app.error)
        message = app.status
        press()
        self.assertEqual(app.status, message)
        self.assertTrue(app.error)
        press(pyxel.KEY_LEFT, pyxel.KEY_RETURN)
        self.assertFalse(app.error)
        self.px.play.assert_called_with(SE_CHANNEL, 10)
        self.assertTrue(self.session.bgm.is_playing)


if __name__ == "__main__":
    unittest.main()
