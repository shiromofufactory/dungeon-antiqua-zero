from __future__ import annotations

import unittest
from unittest.mock import call, patch

from app.input import Direction
from app.ui.window import (
    CURSOR_COLKEY,
    CURSOR_FLOAT_PHASE_FRAMES,
    CURSOR_SIZE,
    CURSOR_X,
    CURSOR_Y,
    CURSOR_SHADOW_X,
    CursorTarget,
    GRADIENT_COLORS,
    GRADIENT_DITHER_RATIOS,
    GRADIENT_STAGE_COUNT,
    WINDOW_ANIMATION_HEIGHT_STEP,
    Window,
    WindowState,
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

    def test_closed_window_opens_from_center_and_draws_through_clip(self) -> None:
        window = Window(1, 2, 8, 6, opened=False)

        self.assertEqual(window.state, WindowState.CLOSED)
        self.assertEqual(window.visible_height, 0)

        window.open()
        self.assertEqual(window.state, WindowState.OPENING)
        window.update()

        self.assertEqual(window.visible_height, WINDOW_ANIMATION_HEIGHT_STEP)
        with (
            patch.object(window, "_draw_animation_contents") as draw_contents,
            patch("app.ui.window.pyxel.clip") as clip,
        ):
            window.draw()

        draw_contents.assert_called_once_with()
        self.assertEqual(
            clip.call_args_list,
            [call(4, 16, 32, 8), call()],
        )

        window.update()
        window.update()

        self.assertTrue(window.is_open)
        self.assertEqual(window.visible_height, window.pixel_height)
        with (
            patch.object(window, "_draw_contents") as draw_contents,
            patch("app.ui.window.pyxel.clip") as clip,
        ):
            window.draw()

        draw_contents.assert_called_once_with()
        clip.assert_not_called()

    def test_opening_frame_moves_with_visible_window_edges(self) -> None:
        window = Window(1, 2, 8, 6, opened=False)
        window.open()
        window.update()

        with (
            patch.object(window, "_draw_gradient") as draw_gradient,
            patch.object(window, "_draw_frame") as draw_frame,
        ):
            window._draw_animation_contents()

        draw_gradient.assert_called_once_with()
        draw_frame.assert_called_once_with(top=16, height=8)

    def test_open_window_closes_to_center_and_stops_drawing(self) -> None:
        window = Window(1, 2, 8, 6)

        window.close()
        window.update()

        self.assertEqual(window.state, WindowState.CLOSING)
        self.assertEqual(window.visible_height, 16)

        window.update()
        window.update()

        self.assertTrue(window.is_closed)
        self.assertEqual(window.visible_height, 0)
        with patch.object(window, "_draw_contents") as draw_contents:
            window.draw()
        draw_contents.assert_not_called()

    def test_opening_and_closing_can_reverse_from_current_height(self) -> None:
        window = Window(0, 0, 8, 8, opened=False)

        window.open()
        window.update()
        window.update()
        self.assertEqual(window.visible_height, 16)

        window.close()
        window.update()
        self.assertEqual(window.visible_height, 8)

        window.open()
        window.update()
        self.assertEqual(window.visible_height, 16)
        self.assertEqual(window.state, WindowState.OPENING)

    def test_draw_does_not_advance_window_animation(self) -> None:
        window = Window(0, 0, 8, 6, opened=False)
        window.open()
        window.update()
        visible_height = window.visible_height

        with (
            patch.object(window, "_draw_animation_contents"),
            patch("app.ui.window.pyxel.clip"),
        ):
            window.draw()
            window.draw()

        self.assertEqual(window.visible_height, visible_height)

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

    def test_thin_frame_uses_thin_frame_sources_for_edges_and_corners(self) -> None:
        window = Window(1, 2, 8, 6, thin_frame=True)

        with patch("app.ui.window.pyxel.blt") as blt:
            window._draw_frame()

        self.assertEqual(blt.call_args_list[0].args[3], 38)
        corner_calls = blt.call_args_list[-4:]
        self.assertEqual(
            [call.args[:7] for call in corner_calls],
            [
                (4, 8, 0, 32, 0, 8, 8),
                (28, 8, 0, 40, 0, 8, 8),
                (4, 24, 0, 32, 8, 8, 8),
                (28, 24, 0, 40, 8, 8, 8),
            ],
        )

    def test_minimum_window_size_is_enforced(self) -> None:
        with self.assertRaises(ValueError):
            Window(0, 0, 3, 4)
        with self.assertRaises(ValueError):
            Window(0, 0, 4, 3)

    def test_cursor_moves_in_rows_and_columns_while_skipping_empty_cell(
        self,
    ) -> None:
        window = Window(0, 0, 20, 12)
        cursor = window.set_cursor(
            (
                CursorTarget(2, 2, key="attack"),
                CursorTarget(2, 5, key="defend"),
                CursorTarget(2, 8, key="spell"),
                CursorTarget(16, 2, key="escape"),
                CursorTarget(16, 5, key="item"),
            )
        )

        self.assertEqual(cursor.selected_key, "attack")
        self.assertTrue(cursor.move_down())
        self.assertEqual(cursor.selected_key, "defend")
        self.assertTrue(cursor.move_down())
        self.assertEqual(cursor.selected_key, "spell")

        self.assertFalse(cursor.move_right())
        self.assertEqual(cursor.selected_key, "spell")

        self.assertTrue(cursor.move_up())
        self.assertTrue(cursor.move_right())
        self.assertEqual(cursor.selected_key, "item")
        self.assertTrue(cursor.move_down())
        self.assertEqual(cursor.selected_key, "escape")
        self.assertTrue(cursor.move_left())
        self.assertEqual(cursor.selected_key, "attack")

    def test_cursor_skips_unselectable_target(self) -> None:
        window = Window(0, 0, 12, 12)
        cursor = window.set_cursor(
            (
                CursorTarget(2, 2, key="first"),
                CursorTarget(2, 5, key="blocked", selectable=False),
                CursorTarget(2, 8, key="last"),
            )
        )

        self.assertTrue(cursor.move_down())
        self.assertEqual(cursor.selected_key, "last")
        self.assertTrue(cursor.move_up())
        self.assertEqual(cursor.selected_key, "first")

    def test_cursor_update_accepts_logical_navigation(self) -> None:
        window = Window(0, 0, 8, 8)
        cursor = window.set_cursor(
            (
                CursorTarget(2, 2, key="first"),
                CursorTarget(2, 5, key="last"),
            )
        )

        self.assertTrue(cursor.update(Direction.DOWN))
        self.assertEqual(cursor.selected_key, "last")
        self.assertEqual(cursor.animation_frame, 1)

    def test_window_updates_cursor_only_while_fully_open(self) -> None:
        window = Window(0, 0, 8, 6, opened=False)
        cursor = window.set_cursor(
            (
                CursorTarget(2, 2, key="first"),
                CursorTarget(2, 5, key="last"),
            )
        )

        self.assertFalse(window.update(Direction.DOWN))
        self.assertEqual(cursor.selected_key, "first")
        self.assertEqual(cursor.animation_frame, 0)

        window.open()
        while window.is_animating:
            self.assertFalse(window.update(Direction.DOWN))

        self.assertEqual(cursor.selected_key, "first")
        self.assertTrue(window.update(Direction.DOWN))
        self.assertEqual(cursor.selected_key, "last")
        self.assertEqual(cursor.animation_frame, 1)

    def test_cursor_target_can_be_selected_without_a_key(self) -> None:
        window = Window(0, 0, 8, 8)
        cursor = window.set_cursor((CursorTarget(2, 2),))

        self.assertIsNotNone(cursor.selected_target)
        self.assertIsNone(cursor.selected_key)

    def test_cursor_with_no_selectable_targets_is_not_drawn(self) -> None:
        window = Window(0, 0, 8, 8)
        cursor = window.set_cursor(
            (CursorTarget(2, 2, key="blocked", selectable=False),)
        )

        with patch("app.ui.window.pyxel.blt") as blt:
            cursor.draw()

        self.assertIsNone(cursor.selected_target)
        blt.assert_not_called()

    def test_cursor_draws_fixed_shadow_and_floating_main_image(self) -> None:
        window = Window(3, 4, 8, 8)
        cursor = window.set_cursor((CursorTarget(2, 2, key="entry"),))
        for _ in range(CURSOR_FLOAT_PHASE_FRAMES * 4):
            cursor.update()

        with patch("app.ui.window.pyxel.blt") as blt:
            cursor.draw()

        self.assertEqual(
            blt.call_args_list,
            [
                call(
                    12,
                    24,
                    0,
                    CURSOR_SHADOW_X,
                    CURSOR_Y,
                    CURSOR_SIZE,
                    CURSOR_SIZE,
                    CURSOR_COLKEY,
                ),
                call(
                    12,
                    22,
                    0,
                    CURSOR_X,
                    CURSOR_Y,
                    CURSOR_SIZE,
                    CURSOR_SIZE,
                    CURSOR_COLKEY,
                ),
            ],
        )
        self.assertEqual(cursor.animation_frame, CURSOR_FLOAT_PHASE_FRAMES * 4)

    def test_cursor_rejects_duplicate_and_outside_targets(self) -> None:
        window = Window(0, 0, 8, 8)

        with self.assertRaises(ValueError):
            window.set_cursor((CursorTarget(2, 2), CursorTarget(2, 2)))
        with self.assertRaises(ValueError):
            window.set_cursor((CursorTarget(8, 2),))


if __name__ == "__main__":
    unittest.main()
