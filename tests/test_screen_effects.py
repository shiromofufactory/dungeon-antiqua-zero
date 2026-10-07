from __future__ import annotations

import unittest

from app.rendering.screen_effects import ScreenBrightness, ScreenShake


class ScreenEffectsTest(unittest.TestCase):
    def test_initial_darkness_is_immediate_and_event_brightens_from_zero(self) -> None:
        brightness = ScreenBrightness(initial_percent=0)
        self.assertEqual(brightness.rate, 0.0)
        self.assertFalse(brightness.is_active)
        brightness.update()
        self.assertEqual(brightness.rate, 0.0)

        brightness.start(50)
        self.assertEqual(brightness.rate, 0.0)
        for frame in range(1, 31):
            brightness.update()
            self.assertAlmostEqual(brightness.rate, 0.5 * frame / 30)
        self.assertFalse(brightness.is_active)
        brightness.update()
        self.assertEqual(brightness.rate, 0.5)

    def test_brightness_interpolates_from_current_rate_and_retains_target(self) -> None:
        brightness = ScreenBrightness()
        for percent in (25, 0, 75, 50, 0, 100):
            with self.subTest(percent=percent):
                initial = brightness.rate
                brightness.start(percent)
                self.assertEqual(brightness.rate, initial)
                for frame in range(1, 31):
                    brightness.update()
                    self.assertAlmostEqual(brightness.rate, initial + (percent / 100 - initial) * frame / 30)
                    self.assertEqual(brightness.is_active, frame < 30)
                brightness.update()
                self.assertEqual(brightness.rate, percent / 100)

    def test_shake_moves_both_directions_and_restores_origin_on_last_frame(self) -> None:
        for frames in (6, 18):
            with self.subTest(frames=frames):
                shake = ScreenShake(frames)
                offsets = []
                for frame in range(1, frames + 1):
                    shake.update()
                    offsets.append(shake.camera_x)
                    self.assertEqual(shake.is_active, frame < frames)
                self.assertEqual(min(offsets), -2)
                self.assertEqual(max(offsets), 2)
                self.assertEqual(offsets[-1], 0)
                shake.update()
                self.assertEqual(shake.camera_x, 0)

    def test_invalid_values_and_interrupted_brightness(self) -> None:
        brightness = ScreenBrightness()
        for percent in (None, True, False, 0.0, 25.0, "50", -25, 26, 125):
            with self.subTest(percent=percent), self.assertRaises(ValueError):
                brightness.start(percent)
            with self.subTest(initial_percent=percent), self.assertRaises(ValueError):
                ScreenBrightness(initial_percent=percent)
        for frames in (None, True, 6.0, "6", 0, -6, 7):
            with self.subTest(frames=frames), self.assertRaises(ValueError):
                ScreenShake(frames)
        brightness.start(25)
        brightness.update()
        current = brightness.rate
        brightness.stop()
        brightness.update()
        self.assertFalse(brightness.is_active)
        self.assertEqual(brightness.rate, current)
