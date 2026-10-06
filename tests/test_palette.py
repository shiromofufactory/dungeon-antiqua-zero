from __future__ import annotations

import unittest
from unittest.mock import Mock, call

from app.rendering.palette import PaletteShifter, grayscale_color, mix_color


class PaletteShifterTest(unittest.TestCase):
    def test_brightness_composes_with_fades_flash_and_variants_then_restores_exact_colors(self) -> None:
        colors = [0x80C040]
        shifter = PaletteShifter(colors, Mock())
        shifter.define_mix("dimmed", base_rate=0.5, target_color=0)
        shifter.set_brightness(0.5)
        self.assertEqual(colors, [0x406020, 0x203010])
        shifter.set_global_mix(base_rate=0.0, target_color=0xFFFFFF)
        self.assertEqual(colors, [0x7F7F7F, 0x7F7F7F])
        shifter.set_global_mix(base_rate=0.0, target_color=0)
        self.assertEqual(colors, [0, 0])
        shifter.set_global_mix(base_rate=1.0, target_color=0)
        self.assertEqual(colors, [0x406020, 0x203010])
        shifter.define_variant("new", (0x204060,))
        self.assertEqual(colors[-1], 0x102030)
        shifter.set_brightness(0.0)
        self.assertEqual(colors, [0, 0, 0])
        shifter.set_global_mix(base_rate=0.0, target_color=0xFFFFFF)
        self.assertEqual(colors, [0, 0, 0])
        shifter.set_global_mix(base_rate=1.0, target_color=0)
        shifter.set_brightness(1.0)
        self.assertEqual(colors, [0x80C040, 0x406020, 0x204060])

    def test_brightness_rejects_invalid_rates_without_changing_colors(self) -> None:
        colors = [0x80C040]
        shifter = PaletteShifter(colors, Mock())
        for rate in (True, "50", -0.1, 1.1, float("nan")):
            with self.subTest(rate=rate), self.assertRaises((TypeError, ValueError)):
                shifter.set_brightness(rate)
        self.assertEqual(colors, [0x80C040])

    def test_grayscale_color_preserves_luminance_as_equal_channels(self) -> None:
        self.assertEqual(grayscale_color(0x80C040), 0x9E9E9E)

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

    def test_removing_variant_compacts_later_blocks_for_reuse(self) -> None:
        colors = [0x000000, 0x101010, 0x202020]
        remap = Mock()
        shifter = PaletteShifter(colors, remap)
        shifter.define_variant("first", (0x303030, 0x404040, 0x505050))
        shifter.define_variant("second", (0x606060, 0x707070, 0x808080))

        self.assertTrue(shifter.remove_variant("first"))
        self.assertFalse(shifter.remove_variant("missing"))
        self.assertEqual(
            colors,
            [0x000000, 0x101010, 0x202020, 0x606060, 0x707070, 0x808080],
        )
        with shifter.shifted("second"):
            pass
        self.assertEqual(
            remap.call_args_list,
            [call(0, 3), call(1, 4), call(2, 5), call()],
        )

    def test_released_sixty_two_color_block_avoids_pyxel_index_overflow(self) -> None:
        colors = list(range(62))
        remap = Mock()
        shifter = PaletteShifter(colors, remap)
        variant = tuple(range(62))
        shifter.define_variant("dimmed", variant)
        shifter.define_variant("unselectable", variant)
        shifter.define_variant("spell", variant)
        self.assertEqual(len(colors), 248)

        with self.assertRaisesRegex(ValueError, "0-255"):
            shifter.define_variant("death", variant)

        self.assertTrue(shifter.remove_variant("spell"))
        shifter.define_variant("death", variant)
        with shifter.shifted("death"):
            pass
        self.assertLessEqual(
            max(call_item.args[1] for call_item in remap.call_args_list[:-1]),
            255,
        )

    def test_rejects_unknown_variant(self) -> None:
        shifter = PaletteShifter([0x000000], Mock())

        with self.assertRaisesRegex(KeyError, "missing"):
            with shifter.shifted("missing"):
                pass

    def test_global_mix_updates_base_and_variant_without_accumulating(self) -> None:
        colors = [0x204060, 0xFFFFFF]
        shifter = PaletteShifter(colors, Mock())
        shifter.define_variant("dimmed", (0x102030, 0x808080))

        shifter.set_global_mix(base_rate=0.5, target_color=0x000000)

        self.assertEqual(
            colors,
            [0x102030, 0x7F7F7F, 0x081018, 0x404040],
        )
        self.assertEqual(shifter.global_base_rate, 0.5)

        shifter.set_global_mix(base_rate=1.0, target_color=0x000000)

        self.assertEqual(
            colors,
            [0x204060, 0xFFFFFF, 0x102030, 0x808080],
        )

    def test_variant_defined_during_global_mix_uses_the_active_rate(self) -> None:
        colors = [0x204060]
        shifter = PaletteShifter(colors, Mock())
        shifter.set_global_mix(base_rate=0.5, target_color=0x000000)

        shifter.define_variant("flash", (0x80C040,))

        self.assertEqual(colors, [0x102030, 0x406020])

    def test_global_mix_validates_rate_and_target(self) -> None:
        shifter = PaletteShifter([0x000000], Mock())

        for base_rate in (True, "dark"):
            with self.subTest(base_rate=base_rate):
                with self.assertRaises(TypeError):
                    shifter.set_global_mix(  # type: ignore[arg-type]
                        base_rate=base_rate,
                        target_color=0,
                    )
        for base_rate in (-0.1, 1.1):
            with self.subTest(base_rate=base_rate):
                with self.assertRaises(ValueError):
                    shifter.set_global_mix(
                        base_rate=base_rate,
                        target_color=0,
                    )
        with self.assertRaises(ValueError):
            shifter.set_global_mix(base_rate=1.0, target_color=0x1000000)


if __name__ == "__main__":
    unittest.main()
