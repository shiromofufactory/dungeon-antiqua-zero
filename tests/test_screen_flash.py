from __future__ import annotations

import unittest

from app.rendering.screen_flash import ScreenFlash


class ScreenFlashTest(unittest.TestCase):
    def test_fades_into_color_and_back_over_six_frames_each(self) -> None:
        flash = ScreenFlash(0xFFFFFF)

        self.assertEqual(flash.visible_rate, 1.0)
        self.assertTrue(flash.is_active)
        rates = []
        for _ in range(12):
            flash.update()
            rates.append(flash.visible_rate)
        self.assertEqual(
            rates,
            [5 / 6, 4 / 6, 3 / 6, 2 / 6, 1 / 6, 0.0,
             1 / 6, 2 / 6, 3 / 6, 4 / 6, 5 / 6, 1.0],
        )
        self.assertFalse(flash.is_active)


if __name__ == "__main__":
    unittest.main()
