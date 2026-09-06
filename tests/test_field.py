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
    profile: str = "world",
) -> CompiledMap:
    width = len(collision_rows[0])
    height = len(collision_rows)
    return CompiledMap(
        map_id="test_map",
        profile=profile,
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
    def test_town_and_dungeon_move_twice_as_fast_as_world(self) -> None:
        movements = {
            profile: FieldMovement(
                compiled_map(("000", "000", "000"), profile=profile),
                start=FieldPosition(1, 1),
            )
            for profile in ("world", "town", "dungeon")
        }

        self.assertEqual(movements["world"].speed, 1)
        self.assertEqual(movements["town"].speed, 2)
        self.assertEqual(movements["dungeon"].speed, 2)
        for movement in movements.values():
            for _frame in range(8):
                movement.update(Direction.RIGHT)
        self.assertEqual(movements["world"].position, FieldPosition(1, 1))
        self.assertEqual(movements["town"].position, FieldPosition(2, 1))
        self.assertEqual(movements["dungeon"].position, FieldPosition(2, 1))

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

    def test_rejects_an_explicit_blocked_start_by_default(self) -> None:
        map_data = compiled_map(("111", "100", "111"))

        with self.assertRaisesRegex(ValueError, "passable map cell"):
            FieldMovement(map_data, start=FieldPosition(0, 1))

    def test_can_resume_on_a_blocked_cell_and_move_to_a_passable_cell(self) -> None:
        map_data = compiled_map(("111", "100", "111"))
        field = FieldMovement(
            map_data,
            start=FieldPosition(0, 1),
            allow_blocked_start=True,
        )

        for _frame in range(map_data.tile_size):
            field.update(Direction.RIGHT)

        self.assertEqual(field.position, FieldPosition(1, 1))

    def test_blocked_start_override_does_not_allow_out_of_bounds_start(self) -> None:
        map_data = compiled_map(("000", "000", "000"))

        with self.assertRaisesRegex(ValueError, "within the map bounds"):
            FieldMovement(
                map_data,
                start=FieldPosition(-1, 1),
                allow_blocked_start=True,
            )

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
            (MapActor("elder", MapCell(1, 1), "roaming", 0, "down"),),
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

    def test_stationary_actor_faces_the_adjacent_party_when_spoken_to(self) -> None:
        map_data = compiled_map(("000", "000", "000"))
        object.__setattr__(
            map_data,
            "actors",
            (MapActor("elder", MapCell(1, 1), "stationary", 0, "up"),),
        )
        actors = FieldActors(map_data)

        actors.face_toward("elder", FieldPosition(2, 1))

        self.assertIs(actors.actor("elder").movement.facing, Direction.RIGHT)

    def test_prop_actor_has_no_facing_or_movement(self) -> None:
        map_data = compiled_map(("000", "000", "000"))
        object.__setattr__(
            map_data,
            "actors",
            (MapActor("chest", MapCell(1, 1), "prop", 0),),
        )
        actors = FieldActors(map_data)

        actors.face_toward("chest", FieldPosition(2, 1))
        with self.assertRaisesRegex(ValueError, "prop"):
            actors.update(
                "chest",
                Direction.RIGHT,
                party_position=FieldPosition(0, 0),
            )

        self.assertEqual(actors.actor("chest").movement.position, FieldPosition(1, 1))

    def test_roaming_actor_chooses_and_starts_an_autonomous_step(self) -> None:
        map_data = compiled_map(("000", "000", "000"))
        object.__setattr__(
            map_data,
            "actors",
            (MapActor("villager", MapCell(1, 1), "roaming", 0, "down"),),
        )
        random_source = Mock()
        random_source.randint.return_value = 30
        random_source.choice.return_value = Direction.RIGHT
        actors = FieldActors(map_data, random_source=random_source)
        actors.actor("villager").roam_wait_frames = 0

        actors.update_roaming(party_position=FieldPosition(0, 0))

        self.assertEqual(actors.actor("villager").movement.world_x, 17)
        self.assertTrue(actors.actor("villager").movement.is_moving)


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

    def test_draws_foreground_objects_after_player(self) -> None:
        objects = (
            MapObjectTile("floor_1", "floor", 1, 1, "object", 0, 0),
            MapObjectTile(
                "roof_1",
                "roof",
                1,
                1,
                "object_foreground",
                0,
                0,
            ),
        )
        map_data = compiled_map(("000", "000", "000"), objects=objects)
        field = FieldMovement(map_data, start=FieldPosition(1, 1))
        pyxel = Mock(frame_count=0)
        renderer = FieldRenderer(
            map_data,
            screen_width=32,
            screen_height=32,
            pyxel_api=pyxel,
        )

        renderer.draw(field)

        self.assertEqual(
            pyxel.blt.call_args_list[-2],
            call(8, 8, 0, 0, 96, 16, 16, 1),
        )
        self.assertEqual(
            pyxel.blt.call_args_list[-1],
            call(8, 8, map_data.atlas, 0, 0, 16, 16, 1),
        )

    def test_draws_actor_common_sheets_and_player_character_bank(self) -> None:
        map_data = compiled_map(("000", "000", "000"))
        object.__setattr__(
            map_data,
            "actors",
            (
                MapActor("chest", MapCell(0, 0), "prop", 1),
                MapActor("elder", MapCell(1, 0), "stationary", 2, "down"),
                MapActor("guide", MapCell(2, 0), "roaming", 3, "left"),
            ),
        )
        field = FieldMovement(map_data, start=FieldPosition(1, 1))
        actors = FieldActors(map_data)
        prop_image = Mock(width=32, height=16)
        character_image = Mock(width=128, height=64)
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
            prop_image=prop_image,
            actor_character_image=character_image,
        )

        character_calls = pyxel.blt.call_args_list[-4:]
        self.assertEqual(
            character_calls[0],
            call(0, 0, prop_image, 16, 0, 16, 16, 1),
        )
        self.assertEqual(
            character_calls[1],
            call(16, 0, character_image, 64, 32, 16, 16, 1),
        )
        self.assertEqual(
            character_calls[2],
            call(32, 0, character_image, 96, 48, 16, 16, 1),
        )
        self.assertEqual(
            character_calls[3],
            call(16, 16, 0, 0, 96, 16, 16, 1),
        )


if __name__ == "__main__":
    unittest.main()
