from __future__ import annotations

from types import MappingProxyType
import unittest
from unittest.mock import Mock, call

from app.field import FieldMovement, FieldPosition
from app.input import Direction
from app.rendering.field import FieldRenderer
from app.resources.maps import CompiledMap, MapObjectTile


def compiled_map(
    collision_rows: tuple[str, ...],
    *,
    objects: tuple[MapObjectTile, ...] = (),
) -> CompiledMap:
    width = len(collision_rows[0])
    height = len(collision_rows)
    return CompiledMap(
        map_id="test_map",
        profile="world",
        tileset_id="worldmap",
        tile_size=16,
        width=width,
        height=height,
        atlas=object(),
        atlas_columns=1,
        atlas_tile_count=1,
        ground_tiles=(0,) * (width * height),
        object_tiles=objects,
        collision_rows=collision_rows,
        ground_animations=MappingProxyType({}),
        object_animations=MappingProxyType({}),
    )


class FieldMovementTest(unittest.TestCase):
    def test_starts_on_passable_cell_nearest_the_map_center(self) -> None:
        map_data = compiled_map(
            (
                "11111",
                "11011",
                "11111",
                "10001",
                "11111",
            )
        )

        field = FieldMovement(map_data)

        self.assertEqual(field.position, FieldPosition(2, 1))
        self.assertIs(field.facing, Direction.DOWN)

    def test_moves_one_tile_smoothly_and_finishes_the_active_step(self) -> None:
        map_data = compiled_map(("11111", "10001", "11111"))
        field = FieldMovement(map_data, start=FieldPosition(1, 1))

        self.assertTrue(field.update(Direction.RIGHT))
        self.assertEqual((field.world_x, field.world_y), (18, 16))
        self.assertTrue(field.is_moving)
        self.assertTrue(field.is_walking)
        self.assertIs(field.facing, Direction.RIGHT)
        for _frame in range(7):
            field.update(None)

        self.assertEqual(field.position, FieldPosition(2, 1))
        self.assertEqual((field.offset_x, field.offset_y), (0, 0))
        self.assertFalse(field.is_moving)
        self.assertEqual(field.animation_frame, 1)
        field.update(None)
        self.assertFalse(field.is_walking)

    def test_ignores_a_new_direction_until_the_current_step_finishes(self) -> None:
        map_data = compiled_map(("11111", "10001", "10001", "11111"))
        field = FieldMovement(map_data, start=FieldPosition(1, 1))

        field.update(Direction.RIGHT)
        for _frame in range(7):
            field.update(Direction.DOWN)

        self.assertEqual(field.position, FieldPosition(2, 1))
        self.assertIs(field.facing, Direction.RIGHT)

    def test_faces_but_does_not_enter_blocked_or_out_of_bounds_cells(self) -> None:
        map_data = compiled_map(("111", "101", "111"))
        field = FieldMovement(map_data, start=FieldPosition(1, 1))

        self.assertFalse(field.update(Direction.RIGHT))

        self.assertEqual(field.position, FieldPosition(1, 1))
        self.assertIs(field.facing, Direction.RIGHT)
        self.assertFalse(field.is_walking)


class FieldRendererTest(unittest.TestCase):
    def test_draws_ground_objects_then_the_requested_character_frame(self) -> None:
        object_tile = MapObjectTile(
            instance_id="tree_1",
            definition_id="tree",
            x=1,
            y=1,
            draw_group="object",
            order=0,
            tile=0,
        )
        map_data = compiled_map(("000", "000", "000"), objects=(object_tile,))
        field = FieldMovement(map_data, start=FieldPosition(1, 1))
        pyxel = Mock(frame_count=0)
        renderer = FieldRenderer(
            map_data,
            screen_width=32,
            screen_height=32,
            pyxel_api=pyxel,
        )

        renderer.draw(field)

        self.assertEqual(pyxel.blt.call_count, 11)
        self.assertEqual(
            pyxel.blt.call_args_list[-2],
            call(8, 8, map_data.atlas, 0, 0, 16, 16, 1),
        )
        self.assertEqual(
            pyxel.blt.call_args_list[-1],
            call(8, 8, 0, 0, 96, 16, 16, 1),
        )

        for _frame in range(8):
            field.update(Direction.RIGHT)
        pyxel.blt.reset_mock()
        renderer.draw(field, frame_count=4)

        self.assertEqual(
            pyxel.blt.call_args_list[-1],
            call(16, 8, 0, 16, 80, 16, 16, 1),
        )

    def test_clamps_camera_to_map_edges(self) -> None:
        map_data = compiled_map(("000", "000", "000"))
        field = FieldMovement(map_data, start=FieldPosition(0, 0))
        renderer = FieldRenderer(
            map_data,
            screen_width=32,
            screen_height=32,
            pyxel_api=Mock(),
        )

        self.assertEqual(renderer.camera_position(field), (0, 0))

        far_field = FieldMovement(map_data, start=FieldPosition(2, 2))
        self.assertEqual(renderer.camera_position(far_field), (16, 16))


if __name__ == "__main__":
    unittest.main()
