from __future__ import annotations

import unittest

from app.rendering.mosaic_fade import MosaicFadeOut


class MosaicFadeOutTest(unittest.TestCase):
    def test_increases_block_size_while_fading_to_black(self) -> None:
        fade = MosaicFadeOut(4, maximum_block_size=8)

        rates = [fade.visible_rate]
        blocks = [fade.block_size]
        for _frame in range(4):
            fade.update()
            rates.append(fade.visible_rate)
            blocks.append(fade.block_size)

        self.assertEqual(rates, [1.0, 0.75, 0.5, 0.25, 0.0])
        self.assertEqual(blocks[0], 1)
        self.assertGreaterEqual(blocks[1], 2)
        self.assertEqual(blocks[-1], 8)
        self.assertEqual(blocks, sorted(blocks))
        self.assertTrue(fade.is_finished)

    def test_rejects_invalid_sizes(self) -> None:
        for frame_count in (True, 0, -1, 1.5):
            with self.subTest(frame_count=frame_count):
                with self.assertRaises(ValueError):
                    MosaicFadeOut(frame_count)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            MosaicFadeOut(maximum_block_size=1)


if __name__ == "__main__":
    unittest.main()
