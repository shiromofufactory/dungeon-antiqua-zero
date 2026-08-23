from __future__ import annotations

import unittest
from unittest.mock import patch

from app.ui.window import (
    GRADIENT_COLORS,
    GRADIENT_DITHER_RATIOS,
    GRADIENT_STAGE_COUNT,
    Window,
    WindowText,
    _gradient_bands,
)


class WindowTest(unittest.TestCase):
    def test_text_uses_fine_grid_relative_to_frame_origin(self) -> None:
        window = Window(2, 5, 20, 10)
        frame_origin = window.add_text("frame", 0, 0)
        former_content_origin = window.add_text("content", 2, 2)
        text = window.add_text("right", 10, 5)

        self.assertEqual(
            (
                window.pixel_x,
                window.pixel_y,
                window.pixel_width,
                window.pixel_height,
            ),
            (8, 20, 80, 40),
        )
        self.assertEqual(window.text_position(frame_origin), (8, 20))
        self.assertEqual(window.text_position(former_content_origin), (16, 28))
        self.assertEqual(window.text_position(text), (48, 40))

    def test_text_origin_must_be_in_window_area(self) -> None:
        window = Window(0, 0, 8, 6)

        with self.assertRaises(ValueError):
            window.add_text("outside", 8, 0)
        with self.assertRaises(ValueError):
            window.add_text("outside", 0, 6)

    def test_texts_can_use_window_default_and_per_text_fonts(self) -> None:
        default_font = object()
        override_font = object()
        window = Window(
            1,
            2,
            16,
            10,
            (
                WindowText("left", 2, 2),
                WindowText("right", 10, 4, 12, override_font),
            ),
            font=default_font,
        )

        with patch("app.ui.window.pyxel.text") as draw_text:
            window._draw_texts()

        self.assertEqual(
            draw_text.call_args_list[0].args,
            (12, 17, "left", 0, default_font),
        )
        self.assertEqual(
            draw_text.call_args_list[1].args,
            (12, 16, "left", 5, default_font),
        )
        self.assertEqual(
            draw_text.call_args_list[2].args,
            (44, 25, "right", 0, override_font),
        )
        self.assertEqual(
            draw_text.call_args_list[3].args,
            (44, 24, "right", 12, override_font),
        )

    def test_text_shadow_can_be_disabled(self) -> None:
        window = Window(
            0,
            0,
            8,
            6,
            (WindowText("flat", 0, 0, shadow_color=None),),
        )

        with patch("app.ui.window.pyxel.text") as draw_text:
            window._draw_texts()

        self.assertEqual(draw_text.call_count, 1)
        self.assertEqual(draw_text.call_args.args, (0, 0, "flat", 5, None))

    def test_gradient_changes_dither_ratio_between_two_colors(self) -> None:
        window = Window(1, 2, 8, 8)

        with (
            patch("app.ui.window.pyxel.dither") as dither,
            patch("app.ui.window.pyxel.rect") as rect,
        ):
            window._draw_gradient()

        drawn_colors = [call.args[4] for call in rect.call_args_list]
        self.assertEqual(
            drawn_colors,
            [GRADIENT_COLORS[1], GRADIENT_COLORS[0]]
            * len(GRADIENT_DITHER_RATIOS),
        )
        self.assertEqual(
            [call.args[0] for call in dither.call_args_list[1:-1:2]],
            list(GRADIENT_DITHER_RATIOS),
        )
        self.assertTrue(
            all(
                call.args[0] == 8
                and call.args[1] >= 12
                and call.args[2] == 24
                for call in rect.call_args_list
            )
        )
        self.assertEqual(dither.call_args_list[-1].args, (1.0,))

    def test_draw_places_frame_over_gradient(self) -> None:
        window = Window(1, 2, 8, 8)
        draw_order: list[str] = []

        with (
            patch.object(
                window,
                "_draw_gradient",
                side_effect=lambda: draw_order.append("gradient"),
            ),
            patch.object(
                window,
                "_draw_frame",
                side_effect=lambda: draw_order.append("frame"),
            ),
            patch.object(
                window,
                "_draw_texts",
                side_effect=lambda: draw_order.append("texts"),
            ),
        ):
            window.draw()

        self.assertEqual(draw_order, ["gradient", "frame", "texts"])

    def test_transparent_window_draws_only_text(self) -> None:
        window = Window(
            3,
            4,
            20,
            8,
            (WindowText("overlay", 2, 2),),
            transparent=True,
        )
        draw_order: list[str] = []

        with (
            patch.object(
                window,
                "_draw_gradient",
                side_effect=lambda: draw_order.append("gradient"),
            ),
            patch.object(
                window,
                "_draw_frame",
                side_effect=lambda: draw_order.append("frame"),
            ),
            patch.object(
                window,
                "_draw_texts",
                side_effect=lambda: draw_order.append("texts"),
            ),
        ):
            window.draw()

        self.assertEqual(draw_order, ["texts"])
        self.assertEqual(window.text_position(window.texts[0]), (20, 24))

    def test_gradient_stages_are_evenly_distributed(self) -> None:
        height = GRADIENT_STAGE_COUNT * 3 + 1
        bands = _gradient_bands(height)
        band_heights = [band_height for _, _, band_height in bands]

        self.assertEqual(bands[0][0], 0)
        self.assertEqual(bands[-1][0], GRADIENT_STAGE_COUNT - 1)
        self.assertLessEqual(max(band_heights) - min(band_heights), 1)
        self.assertEqual(band_heights, list(reversed(band_heights)))
        self.assertEqual(bands[0][2], bands[-1][2])
        self.assertEqual(sum(band_heights), height)

    def test_frame_uses_expected_four_corner_sources(self) -> None:
        window = Window(1, 2, 8, 6)

        with patch("app.ui.window.pyxel.blt") as blt:
            window._draw_frame()

        corner_calls = blt.call_args_list[-4:]
        self.assertEqual(
            [call.args[:7] for call in corner_calls],
            [
                (4, 8, 0, 16, 0, 8, 8),
                (28, 8, 0, 24, 0, 8, 8),
                (4, 24, 0, 16, 8, 8, 8),
                (28, 24, 0, 24, 8, 8, 8),
            ],
        )

    def test_minimum_window_size_is_enforced(self) -> None:
        with self.assertRaises(ValueError):
            Window(0, 0, 3, 4)
        with self.assertRaises(ValueError):
            Window(0, 0, 4, 3)


if __name__ == "__main__":
    unittest.main()
