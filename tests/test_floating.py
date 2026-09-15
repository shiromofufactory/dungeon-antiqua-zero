from __future__ import annotations

import unittest

from app.rendering.floating import (
    FLOATING_CYCLE_FRAMES,
    FLOATING_OFFSETS,
    FLOATING_PHASE_FRAMES,
    floating_offset,
)


class FloatingAnimationTest(unittest.TestCase):
    def test_repeats_the_cursor_pattern_every_96_frames(self) -> None:
        self.assertEqual(FLOATING_OFFSETS, (0, 0, 0, 1, 2, 2, 2, 1))
        self.assertEqual(FLOATING_PHASE_FRAMES, 12)
        self.assertEqual(FLOATING_CYCLE_FRAMES, 96)
        self.assertEqual(
            [floating_offset(frame) for frame in range(0, 109, 12)],
            [0, 0, 0, 1, 2, 2, 2, 1, 0, 0],
        )

    def test_rejects_invalid_frame_counts(self) -> None:
        for value in (True, 1.5, "1"):
            with self.subTest(value=value), self.assertRaises(TypeError):
                floating_offset(value)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            floating_offset(-1)


if __name__ == "__main__":
    unittest.main()
