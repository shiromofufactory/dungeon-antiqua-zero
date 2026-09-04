from __future__ import annotations

from types import MappingProxyType
import unittest
from unittest.mock import Mock, call

from app.field import FieldActors, FieldMovement, FieldPosition
from app.input import Direction
from app.rendering.field import (
    FIELD_CHARACTER_ANIMATION_INTERVAL,
    FieldRenderer,
)
from app.resources.maps import CompiledMap, MapActor, MapCell, MapObjectTile


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
        self.assertEqual((field.world_x, field.world_y), (16 + field.speed, 16))
        self.assertTrue(field.is_moving)
        self.assertTrue(field.is_walking)
        self.assertIs(field.facing, Direction.RIGHT)
        for _frame in range(map_data.tile_size // field.speed - 1):
            field.update(None)

        self.assertEqual(field.position, FieldPosition(2, 1))
        self.assertEqual((field.offset_x, field.offset_y), (0, 0))
        self.assertFalse(field.is_moving)
        self.assertEqual(field.arrived_position, FieldPosition(2, 1))
        field.update(None)
        self.assertFalse(field.is_walking)
        self.assertIsNone(field.arrived_position)

    def test_ignores_a_new_direction_until_the_current_step_finishes(self) -> None:
        map_data = compiled_map(("11111", "10001", "10001", "11111"))
        field = FieldMovement(map_data, start=FieldPosition(1, 1))

        field.update(Direction.RIGHT)
        for _frame in range(map_data.tile_size // field.speed - 1):
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

    def test_dynamic_blocker_prevents_entering_an_actor_cell(self) -> None:
        map_data = compiled_map(("000", "000", "000"))
        field = FieldMovement(map_data, start=FieldPosition(1, 1))

        self.assertFalse(
            field.update(
                Direction.RIGHT,
                blocked_positions=(FieldPosition(2, 1),),
            )
        )
        self.assertEqual(field.position, FieldPosition(1, 1))

    def test_field_actor_moves_without_entering_party_cell(self) -> None:
        map_data = compiled_map(("000", "000", "000"))
        object.__setattr__(
            map_data,
            "actors",
            (MapActor("elder", MapCell(1, 1), "down", "elder"),),
        )
        actors = FieldActors(map_data)

        self.assertFalse(
            actors.update(
                "elder",
                Direction.RIGHT,
                party_position=FieldPosition(2, 1),
            )
        )
        self.assertEqual(actors.actor("elder").movement.position, FieldPosition(1, 1))


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

        self.assertEqual(FIELD_CHARACTER_ANIMATION_INTERVAL, 16)
        for frame_count, source_x in (
            (FIELD_CHARACTER_ANIMATION_INTERVAL - 1, 0),
            (FIELD_CHARACTER_ANIMATION_INTERVAL, 16),
            (FIELD_CHARACTER_ANIMATION_INTERVAL * 2, 0),
        ):
            with self.subTest(frame_count=frame_count):
                pyxel.blt.reset_mock()
                renderer.draw(field, frame_count=frame_count)
                self.assertEqual(
                    pyxel.blt.call_args_list[-1],
                    call(8, 8, 0, source_x, 96, 16, 16, 1),
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

    def test_draws_actor_image_and_falls_back_to_field_character_bank(self) -> None:
        map_data = compiled_map(("000", "000", "000"))
        object.__setattr__(
            map_data,
            "actors",
            (
                MapActor("elder", MapCell(1, 0), "down", "elder"),
                MapActor("guide", MapCell(2, 0), "left", "guide"),
            ),
        )
        field = FieldMovement(map_data, start=FieldPosition(1, 1))
        actors = FieldActors(map_data)
        elder_image = object()
        pyxel = Mock(frame_count=0)
        renderer = FieldRenderer(
            map_data,
            screen_width=48,
            screen_height=48,
            pyxel_api=pyxel,
        )

        renderer.draw(
            field,
            actors=actors,
            actor_images={"elder": elder_image},
        )

        character_calls = pyxel.blt.call_args_list[-3:]
        self.assertEqual(
            character_calls[0],
            call(16, 0, elder_image, 0, 32, 16, 16, 1),
        )
        self.assertEqual(
            character_calls[1],
            call(32, 0, 0, 0, 112, 16, 16, 1),
        )
        self.assertEqual(
            character_calls[2],
            call(16, 16, 0, 0, 96, 16, 16, 1),
        )


if __name__ == "__main__":
    unittest.main()
