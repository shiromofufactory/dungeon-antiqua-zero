from __future__ import annotations

import unittest
from unittest.mock import Mock, call

from app.rendering.palette import PaletteShifter, mix_color


class PaletteShifterTest(unittest.TestCase):
    def test_mix_color_uses_da2_channel_formula(self) -> None:
        self.assertEqual(mix_color(0x80C040, 0.5, 0x000000), 0x406020)
        self.assertEqual(mix_color(0x80C040, 0.0, 0x102030), 0x102030)
        self.assertEqual(mix_color(0x80C040, 1.0, 0x102030), 0x80C040)

    def test_variant_appends_destination_colors_and_can_be_replaced(self) -> None:
        colors = [0x000000, 0x204060, 0xFFFFFF]
        shifter = PaletteShifter(colors, Mock())

        shifter.define_mix("dark", base_rate=0.5, target_color=0x000000)
        self.assertEqual(
            colors,
            [
                0x000000,
                0x204060,
                0xFFFFFF,
                0x000000,
                0x102030,
                0x7F7F7F,
            ],
        )

        shifter.define_variant("dark", (0x010101, 0x020202, 0x030303))
        self.assertEqual(colors[-3:], [0x010101, 0x020202, 0x030303])
        self.assertEqual(len(colors), 6)

    def test_shift_is_scoped_and_resets_even_when_drawing_fails(self) -> None:
        colors = [0x000000, 0xFFFFFF]
        remap = Mock()
        shifter = PaletteShifter(colors, remap)
        shifter.define_variant("flash", (0x111111, 0xEEEEEE))

        with self.assertRaisesRegex(RuntimeError, "draw failed"):
            with shifter.shifted("flash"):
                raise RuntimeError("draw failed")

        self.assertEqual(
            remap.call_args_list,
            [call(0, 2), call(1, 3), call()],
        )

    def test_rejects_unknown_variant(self) -> None:
        shifter = PaletteShifter([0x000000], Mock())

        with self.assertRaisesRegex(KeyError, "missing"):
            with shifter.shifted("missing"):
                pass


if __name__ == "__main__":
    unittest.main()
