from __future__ import annotations

from contextlib import nullcontext
from types import MappingProxyType
import unittest
from unittest.mock import Mock, call

from app.field import (
    TREASURE_ANIMATION_FRAME_COUNT,
    FieldActors,
    FieldMovement,
    FieldPosition,
)
from app.input import Direction
from app.rendering.character_shadow import (
    CHARACTER_SHADOW_BANK,
    CHARACTER_SHADOW_SOURCE_X,
    CHARACTER_SHADOW_SOURCE_Y,
)
from app.rendering.field import (
    FIELD_ACTOR_CHARACTER_ANIMATION_INTERVAL,
    FIELD_ACTOR_CHARACTER_SET_HEIGHT,
    FIELD_ACTOR_CHARACTER_SET_WIDTH,
    FIELD_CHARACTER_ANIMATION_INTERVAL,
    FIELD_PLAYER_CHARACTER_ANIMATION_INTERVAL,
    FIELD_PLAYER_CHARACTER_SET_HEIGHT,
    FIELD_PLAYER_CHARACTER_SET_WIDTH,
    FieldRenderer,
)
from app.rendering.floating import FLOATING_CHARACTER_FRAME_INTERVAL
from app.resources.maps import (
    CompiledMap,
    MapActor,
    MapCell,
    MapObjectTile,
    MapVisibilityCondition,
    MapTreasureContents,
)


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

    def test_field_actor_can_start_on_a_blocked_map_cell(self) -> None:
        map_data = compiled_map(("111", "101", "111"))
        object.__setattr__(
            map_data,
            "actors",
            (MapActor("keeper", MapCell(0, 1), "stationary", 0, "down"),),
        )

        actors = FieldActors(map_data)

        self.assertEqual(
            actors.actor("keeper").movement.position,
            FieldPosition(0, 1),
        )

    def test_stationary_actor_faces_the_adjacent_party_when_spoken_to(self) -> None:
        map_data = compiled_map(("000", "000", "000"))
        object.__setattr__(
            map_data,
            "actors",
            (MapActor("elder", MapCell(1, 1), "stationary", 0, "up"),),
        )
        actors = FieldActors(map_data)

        previous_facing = actors.face_toward("elder", FieldPosition(2, 1))

        self.assertIs(previous_facing, Direction.UP)
        self.assertIs(actors.actor("elder").movement.facing, Direction.RIGHT)

        actors.restore_stationary_facing("elder", previous_facing)

        self.assertIs(actors.actor("elder").movement.facing, Direction.UP)

    def test_explicit_facing_cancels_an_unfinished_roaming_step_without_changing_cell(self) -> None:
        map_data = compiled_map(("000", "000", "000"))
        object.__setattr__(map_data, "actors", (
            MapActor("elder", MapCell(1, 1), "roaming", 0, "up"),
        ))
        actors = FieldActors(map_data)
        actors.update("elder", Direction.RIGHT, party_position=FieldPosition(0, 0))
        movement = actors.actor("elder").movement
        self.assertTrue(movement.is_moving)

        actors.face("elder", Direction.DOWN)

        self.assertEqual(movement.position, FieldPosition(1, 1))
        self.assertEqual((movement.offset_x, movement.offset_y), (0, 0))
        self.assertFalse(movement.is_moving)
        self.assertFalse(movement.is_walking)
        self.assertIs(movement.facing, Direction.DOWN)

    def test_stationary_actor_faces_party_across_a_counter(self) -> None:
        map_data = compiled_map(("0000", "0000", "0000"))
        object.__setattr__(
            map_data,
            "actors",
            (MapActor("keeper", MapCell(3, 1), "stationary", 0, "up"),),
        )
        actors = FieldActors(map_data)

        actors.face_toward("keeper", FieldPosition(1, 1))

        self.assertIs(actors.actor("keeper").movement.facing, Direction.LEFT)

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
        with self.assertRaisesRegex(ValueError, "prop"):
            actors.face("chest", Direction.RIGHT)

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

    def test_treasure_animation_uses_the_configured_frames_per_image(self) -> None:
        map_data = compiled_map(("000", "000", "000"))
        treasure = MapActor(
            "chest",
            MapCell(1, 1),
            "treasure",
            0,
            contents=MapTreasureContents("gold", amount=10),
        )
        object.__setattr__(map_data, "actors", (treasure,))
        actors = FieldActors(map_data)

        actors.start_treasure_opening("chest")
        self.assertEqual(actors.actor("chest").treasure_frame, 1)
        for _frame in range(TREASURE_ANIMATION_FRAME_COUNT - 1):
            actors.update_treasure_animations()
            self.assertEqual(actors.actor("chest").treasure_frame, 1)
        actors.update_treasure_animations()
        self.assertEqual(actors.actor("chest").treasure_frame, 2)

        for _frame in range(TREASURE_ANIMATION_FRAME_COUNT * 2):
            actors.update_treasure_animations()
        self.assertEqual(actors.actor("chest").treasure_frame, 2)

        actors.start_treasure_closing("chest")
        self.assertEqual(actors.actor("chest").treasure_frame, 1)
        for _frame in range(TREASURE_ANIMATION_FRAME_COUNT - 1):
            actors.update_treasure_animations()
            self.assertEqual(actors.actor("chest").treasure_frame, 1)
        actors.update_treasure_animations()
        self.assertEqual(actors.actor("chest").treasure_frame, 0)

    def test_opened_treasure_starts_on_the_final_image(self) -> None:
        map_data = compiled_map(("000", "000", "000"))
        treasure = MapActor(
            "chest",
            MapCell(1, 1),
            "treasure",
            0,
            contents=MapTreasureContents("item", item_key="POTION"),
        )
        object.__setattr__(map_data, "actors", (treasure,))

        actors = FieldActors(map_data, opened_treasure_ids=("chest",))

        self.assertEqual(actors.actor("chest").treasure_frame, 2)


class FieldRendererTest(unittest.TestCase):
    def test_visibility_gates_every_object_draw_group_and_reacts_to_flag_changes(self) -> None:
        for group in ("object", "object_y_sorted", "object_foreground", "object_overlay"):
            for value in (True, False):
                with self.subTest(group=group, value=value):
                    tile = MapObjectTile("rock", "rock", 1, 1, group, 0, 0, 1)
                    map_data = compiled_map(("000", "000", "000"), objects=(tile,))
                    object.__setattr__(map_data, "object_conditions", MappingProxyType({"rock": MapVisibilityCondition("story.rock", value)}))
                    flags = set()
                    field = FieldMovement(map_data, start=FieldPosition(0, 0), event_flags=flags)
                    renderer = FieldRenderer(map_data, screen_width=48, screen_height=48, pyxel_api=Mock(frame_count=0))
                    renderer._draw_object_tile = Mock()
                    renderer.draw(field, draw_player=False)
                    self.assertEqual(renderer._draw_object_tile.call_count, int(not value))
                    flags.add("story.rock")
                    renderer._draw_object_tile.reset_mock()
                    renderer.draw(field, draw_player=False)
                    self.assertEqual(renderer._draw_object_tile.call_count, int(value))

    def test_can_draw_field_layers_without_the_player(self) -> None:
        map_data = compiled_map(("000", "000", "000"), profile="dungeon")
        field = FieldMovement(map_data, start=FieldPosition(1, 1))
        renderer = FieldRenderer(
            map_data,
            screen_width=32,
            screen_height=32,
            pyxel_api=Mock(frame_count=0),
        )
        renderer._draw_ground = Mock()  # type: ignore[method-assign]
        renderer._draw_objects = Mock()  # type: ignore[method-assign]
        renderer._draw_player_character = Mock()  # type: ignore[method-assign]

        renderer.draw(field, draw_player=False)

        renderer._draw_ground.assert_called_once()
        self.assertEqual(renderer._draw_objects.call_count, 2)
        renderer._draw_player_character.assert_not_called()

    def test_draws_ground_objects_then_the_requested_character_frame(self) -> None:
        object_tile = MapObjectTile(
            instance_id="tree_1",
            definition_id="tree",
            x=1,
            y=1,
            draw_group="object",
            order=0,
            tile=0,
            sort_y=1,
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

    def test_draws_interior_player_from_battle_sprite_walking_set(self) -> None:
        map_data = compiled_map(("000", "000", "000"), profile="town")
        field = FieldMovement(
            map_data,
            start=FieldPosition(1, 1),
            facing=Direction.DOWN,
        )
        walking_image = Mock(width=384, height=384)
        pyxel = Mock(frame_count=0)
        renderer = FieldRenderer(
            map_data,
            screen_width=32,
            screen_height=32,
            pyxel_api=pyxel,
        )

        renderer.draw(
            field,
            player_character_image=walking_image,
            player_sprite_index=10,
        )

        block_x = (10 % 8) * FIELD_PLAYER_CHARACTER_SET_WIDTH
        block_y = (10 // 8) * FIELD_PLAYER_CHARACTER_SET_HEIGHT
        self.assertEqual(
            pyxel.blt.call_args_list[-1],
            call(
                8,
                -8,
                walking_image,
                block_x + 16,
                block_y,
                16,
                32,
                1,
            ),
        )

    def test_player_palette_shift_is_scoped_to_the_player_sprite(self) -> None:
        map_data = compiled_map(("000", "000", "000"), profile="dungeon")
        field = FieldMovement(map_data, start=FieldPosition(1, 1))
        walking_image = Mock(width=384, height=384)
        pyxel = Mock(frame_count=0)
        palette_shifter = Mock()
        palette_shifter.shifted.return_value = nullcontext()
        renderer = FieldRenderer(
            map_data,
            screen_width=32,
            screen_height=32,
            pyxel_api=pyxel,
        )

        renderer.draw(
            field,
            player_character_image=walking_image,
            player_palette_shifter=palette_shifter,
            player_palette_name="field_fade",
        )

        palette_shifter.shifted.assert_called_once_with("field_fade")

    def test_interior_player_uses_down_up_left_right_rows(
        self,
    ) -> None:
        map_data = compiled_map(("000", "000", "000"), profile="dungeon")
        field = FieldMovement(map_data, start=FieldPosition(1, 1))
        walking_image = Mock(width=384, height=384)
        pyxel = Mock(frame_count=0)
        renderer = FieldRenderer(
            map_data,
            screen_width=32,
            screen_height=32,
            pyxel_api=pyxel,
        )

        for direction, source_y in (
            (Direction.DOWN, 0),
            (Direction.UP, 32),
            (Direction.LEFT, 64),
            (Direction.RIGHT, 96),
        ):
            with self.subTest(direction=direction):
                field.facing = direction
                pyxel.blt.reset_mock()
                renderer.draw(field, player_character_image=walking_image)
                self.assertEqual(
                    pyxel.blt.call_args_list[-1],
                    call(8, -8, walking_image, 16, source_y, 16, 32, 1),
                )

    def test_interior_player_cycles_right_standing_left_standing_while_moving(
        self,
    ) -> None:
        map_data = compiled_map(("0000", "0000", "0000"), profile="town")
        field = FieldMovement(map_data, start=FieldPosition(1, 1))
        walking_image = Mock(width=384, height=384)
        pyxel = Mock(frame_count=0)
        renderer = FieldRenderer(
            map_data,
            screen_width=32,
            screen_height=32,
            pyxel_api=pyxel,
        )

        expected_frames = (32,) * 4 + (16,) * 4 + (0,) * 4 + (16,) * 4
        self.assertEqual(FIELD_PLAYER_CHARACTER_ANIMATION_INTERVAL, 4)
        for source_x in expected_frames:
            field.update(Direction.RIGHT)
            pyxel.blt.reset_mock()
            renderer.draw(field, player_character_image=walking_image)
            self.assertEqual(pyxel.blt.call_args_list[-1].args[3], source_x)

        field.update(None)
        pyxel.blt.reset_mock()
        renderer.draw(field, player_character_image=walking_image)
        self.assertFalse(field.is_moving)
        self.assertEqual(field.walking_frame_count, 0)
        self.assertEqual(pyxel.blt.call_args_list[-1].args[3], 16)

    def test_draws_foreground_objects_after_player_on_the_same_row(self) -> None:
        objects = (
            MapObjectTile("floor_1", "floor", 1, 1, "object", 0, 0, 1),
            MapObjectTile(
                "roof_1",
                "roof",
                1,
                1,
                "object_foreground",
                0,
                0,
                1,
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

    def test_foreground_depth_compares_bottom_y_with_player_and_actor(self) -> None:
        for character_kind in ("player", "actor"):
            for character_y in (0, 1, 2):
                with self.subTest(kind=character_kind, y=character_y):
                    # The upper tile must follow the whole instance's bottom Y.
                    objects = (
                        MapObjectTile("tree_1", "tree", 1, 0, "object_foreground", 0, 0, 1),
                        MapObjectTile("tree_1", "tree", 1, 1, "object_foreground", 0, 0, 1),
                    )
                    map_data = compiled_map(("000", "000", "000"), objects=objects)
                    field = FieldMovement(map_data, start=FieldPosition(1, character_y))
                    object.__setattr__(
                        map_data,
                        "actors",
                        (MapActor("elder", MapCell(1, character_y), "stationary", 0, "down"),),
                    )
                    renderer = FieldRenderer(
                        map_data,
                        screen_width=48,
                        screen_height=48,
                        pyxel_api=Mock(frame_count=0),
                    )
                    draws = Mock()
                    draws.attach_mock(Mock(), "object")
                    draws.attach_mock(Mock(), "character")
                    renderer._draw_object_tile = draws.object
                    renderer._draw_player_character = draws.character
                    renderer._draw_character = draws.character

                    renderer.draw(
                        field,
                        actors=FieldActors(map_data) if character_kind == "actor" else None,
                        draw_player=character_kind == "player",
                    )

                    expected = (
                        ["object", "object", "character"]
                        if character_y > 1
                        else ["character", "object", "object"]
                    )
                    self.assertEqual([item[0] for item in draws.mock_calls], expected)

    def test_same_row_draws_normal_character_foreground_then_overlay(self) -> None:
        groups = ("object_foreground", "object_overlay", "object_y_sorted")
        objects = tuple(
            MapObjectTile(f"part_{index}", "part", 1, 1, group, 100 - index, 0, 1)
            for index, group in enumerate(groups)
        )
        map_data = compiled_map(("000", "000", "000"), objects=objects)
        field = FieldMovement(map_data, start=FieldPosition(1, 1))
        renderer = FieldRenderer(
            map_data,
            screen_width=32,
            screen_height=32,
            pyxel_api=Mock(frame_count=0),
        )
        draws = Mock()
        draws.attach_mock(Mock(), "object")
        draws.attach_mock(Mock(), "character")
        renderer._draw_object_tile = draws.object
        renderer._draw_player_character = draws.character

        renderer.draw(field)

        self.assertEqual(
            [item.args[1].draw_group if item[0] == "object" else "character" for item in draws.mock_calls],
            ["object_y_sorted", "character", "object_foreground", "object_overlay"],
        )

    def test_draws_overlay_objects_after_foreground_objects(self) -> None:
        objects = (
            MapObjectTile(
                "roof_1",
                "roof",
                1,
                1,
                "object_foreground",
                0,
                0,
                1,
            ),
            MapObjectTile(
                "weather_1",
                "weather",
                1,
                1,
                "object_overlay",
                0,
                1,
                1,
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
            call(8, 8, map_data.atlas, 0, 0, 16, 16, 1),
        )
        self.assertEqual(
            pyxel.blt.call_args_list[-1],
            call(8, 8, map_data.atlas, 0, 16, 16, 16, 1),
        )

    def test_y_sorted_object_draws_before_character_on_the_same_row(self) -> None:
        objects = (
            MapObjectTile(
                "counter_1",
                "counter",
                1,
                1,
                "object_y_sorted",
                0,
                0,
                sort_y=1,
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

        player_call = next(
            index for index, draw_call in enumerate(pyxel.blt.call_args_list)
            if draw_call.args[2] == 0
        )
        counter_call = next(
            index for index, draw_call in enumerate(pyxel.blt.call_args_list)
            if draw_call.args[2] is map_data.atlas
            and len(draw_call.args) == 8
        )
        self.assertLess(counter_call, player_call)

    def test_y_sorted_object_draws_before_actor_on_the_same_row(self) -> None:
        objects = (
            MapObjectTile(
                "counter_1",
                "counter",
                1,
                1,
                "object_y_sorted",
                0,
                0,
                sort_y=1,
            ),
        )
        map_data = compiled_map(("000", "000", "000"), objects=objects)
        object.__setattr__(
            map_data,
            "actors",
            (MapActor("elder", MapCell(1, 1), "stationary", 0, "down"),),
        )
        field = FieldMovement(map_data, start=FieldPosition(0, 0))
        actors = FieldActors(map_data)
        character_image = Mock(width=48, height=128)
        pyxel = Mock(frame_count=0)
        renderer = FieldRenderer(
            map_data,
            screen_width=32,
            screen_height=32,
            pyxel_api=pyxel,
        )

        renderer.draw(
            field,
            actors=actors,
            actor_character_image=character_image,
            draw_player=False,
        )

        counter_call = next(
            index for index, draw_call in enumerate(pyxel.blt.call_args_list)
            if draw_call.args[2] is map_data.atlas
            and len(draw_call.args) == 8
        )
        actor_call = next(
            index for index, draw_call in enumerate(pyxel.blt.call_args_list)
            if draw_call.args[2] is character_image
        )
        self.assertLess(counter_call, actor_call)

    def test_y_sorted_object_draws_before_character_on_a_lower_row(self) -> None:
        objects = (
            MapObjectTile(
                "counter_1",
                "counter",
                1,
                1,
                "object_y_sorted",
                0,
                0,
                sort_y=1,
            ),
        )
        map_data = compiled_map(("000", "000", "000"), objects=objects)
        field = FieldMovement(map_data, start=FieldPosition(1, 2))
        pyxel = Mock(frame_count=0)
        renderer = FieldRenderer(
            map_data,
            screen_width=32,
            screen_height=32,
            pyxel_api=pyxel,
        )

        renderer.draw(field)

        player_call = next(
            index for index, draw_call in enumerate(pyxel.blt.call_args_list)
            if draw_call.args[2] == 0
        )
        counter_call = next(
            index for index, draw_call in enumerate(pyxel.blt.call_args_list)
            if draw_call.args[2] is map_data.atlas
            and len(draw_call.args) == 8
        )
        self.assertLess(counter_call, player_call)

    def test_floating_player_animates_while_idle_without_offsetting_draw_y(self) -> None:
        map_data = compiled_map(("000", "000", "000"), profile="town")
        field = FieldMovement(map_data, start=FieldPosition(1, 1))
        walking_image = Mock(width=384, height=384)
        pyxel = Mock(frame_count=0)
        renderer = FieldRenderer(
            map_data,
            screen_width=32,
            screen_height=32,
            pyxel_api=pyxel,
        )

        expected = (
            (0, 32, -8),
            (FLOATING_CHARACTER_FRAME_INTERVAL, 16, -8),
            (FLOATING_CHARACTER_FRAME_INTERVAL * 2, 0, -8),
            (FLOATING_CHARACTER_FRAME_INTERVAL * 3, 16, -8),
            (FLOATING_CHARACTER_FRAME_INTERVAL * 4, 32, -8),
        )
        for frame_count, source_x, draw_y in expected:
            with self.subTest(frame_count=frame_count):
                pyxel.blt.reset_mock()
                renderer.draw(
                    field,
                    player_character_image=walking_image,
                    player_floating=True,
                    frame_count=frame_count,
                )
                self.assertEqual(
                    pyxel.blt.call_args_list[-1],
                    call(8, draw_y, walking_image, source_x, 0, 16, 32, 1),
                )
                self.assertEqual(
                    pyxel.blt.call_args_list[-2],
                    call(
                        8,
                        8,
                        CHARACTER_SHADOW_BANK,
                        CHARACTER_SHADOW_SOURCE_X,
                        CHARACTER_SHADOW_SOURCE_Y,
                        16,
                        16,
                        1,
                    ),
                )

        self.assertEqual(field.position, FieldPosition(1, 1))

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
        character_image = Mock(width=192, height=128)
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

        character_calls = pyxel.blt.call_args_list[-6:]
        self.assertEqual(
            character_calls[0],
            call(0, 0, prop_image, 16, 0, 16, 16, 1),
        )
        self.assertEqual(
            character_calls[1],
            call(
                16,
                0,
                CHARACTER_SHADOW_BANK,
                CHARACTER_SHADOW_SOURCE_X,
                CHARACTER_SHADOW_SOURCE_Y,
                16,
                16,
                1,
            ),
        )
        self.assertEqual(
            character_calls[2],
            call(16, -16, character_image, 112, 0, 16, 32, 1),
        )
        self.assertEqual(
            character_calls[3],
            call(
                32,
                0,
                CHARACTER_SHADOW_BANK,
                CHARACTER_SHADOW_SOURCE_X,
                CHARACTER_SHADOW_SOURCE_Y,
                16,
                16,
                1,
            ),
        )
        self.assertEqual(
            character_calls[4],
            call(32, -16, character_image, 160, 64, 16, 32, 1),
        )
        self.assertEqual(
            character_calls[5],
            call(16, 16, 0, 0, 96, 16, 16, 1),
        )

    def test_actor_character_uses_pc_format_rows_and_walking_frames(self) -> None:
        map_data = compiled_map(("0000", "0000", "0000"), profile="town")
        movement = FieldMovement(
            map_data,
            start=FieldPosition(1, 1),
            facing=Direction.DOWN,
        )
        character_image = Mock(
            width=FIELD_ACTOR_CHARACTER_SET_WIDTH * 2,
            height=FIELD_ACTOR_CHARACTER_SET_HEIGHT,
        )
        pyxel = Mock(frame_count=0)
        renderer = FieldRenderer(
            map_data,
            screen_width=64,
            screen_height=48,
            pyxel_api=pyxel,
        )

        for direction, source_y in (
            (Direction.DOWN, 0),
            (Direction.UP, 32),
            (Direction.LEFT, 64),
            (Direction.RIGHT, 96),
        ):
            with self.subTest(direction=direction):
                movement.facing = direction
                pyxel.blt.reset_mock()
                renderer._draw_character(
                    movement,
                    0,
                    0,
                    0,
                    image=character_image,
                    sprite_index=1,
                )
                self.assertEqual(
                    pyxel.blt.call_args_list,
                    [
                        call(
                            16,
                            16,
                            CHARACTER_SHADOW_BANK,
                            CHARACTER_SHADOW_SOURCE_X,
                            CHARACTER_SHADOW_SOURCE_Y,
                            16,
                            16,
                            1,
                        ),
                        call(
                            16,
                            0,
                            character_image,
                            FIELD_ACTOR_CHARACTER_SET_WIDTH + 16,
                            source_y,
                            16,
                            32,
                            1,
                        ),
                    ],
                )

        movement.stop()
        expected_frames = (32,) * 4 + (16,) * 4 + (0,) * 4 + (16,) * 4
        self.assertEqual(FIELD_ACTOR_CHARACTER_ANIMATION_INTERVAL, 4)
        for source_offset in expected_frames:
            movement.update(Direction.RIGHT)
            pyxel.blt.reset_mock()
            renderer._draw_character(
                movement,
                0,
                0,
                0,
                image=character_image,
                sprite_index=1,
            )
            self.assertEqual(
                pyxel.blt.call_args.args[3],
                FIELD_ACTOR_CHARACTER_SET_WIDTH + source_offset,
            )

        movement.update(None)
        pyxel.blt.reset_mock()
        renderer._draw_character(
            movement,
            0,
            0,
            0,
            image=character_image,
            sprite_index=1,
        )
        self.assertEqual(
            pyxel.blt.call_args.args[3],
            FIELD_ACTOR_CHARACTER_SET_WIDTH + 16,
        )

    def test_actor_character_selects_pc_walking_sheet(self) -> None:
        map_data = compiled_map(("000", "000", "000"), profile="town")
        object.__setattr__(
            map_data,
            "actors",
            (
                MapActor(
                    "alvan",
                    MapCell(1, 0),
                    "stationary",
                    1,
                    "down",
                    sprite_source="pc",
                ),
            ),
        )
        field = FieldMovement(map_data, start=FieldPosition(1, 1))
        actors = FieldActors(map_data)
        npc_image = Mock(width=96, height=128)
        pc_image = Mock(width=384, height=384)
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
            actor_character_image=npc_image,
            actor_pc_character_image=pc_image,
        )

        pyxel.blt.assert_any_call(
            16,
            -16,
            pc_image,
            FIELD_ACTOR_CHARACTER_SET_WIDTH + 16,
            0,
            16,
            32,
            1,
        )

    def test_nonfloating_fairy_pc_actor_does_not_draw_a_shadow(self) -> None:
        map_data = compiled_map(("0000", "0000", "0000"), profile="town")
        object.__setattr__(
            map_data,
            "actors",
            (
                MapActor(
                    "resting_fairy",
                    MapCell(0, 0),
                    "stationary",
                    1,
                    "down",
                    sprite_source="pc",
                    floating=False,
                ),
                MapActor(
                    "floating_fairy",
                    MapCell(1, 0),
                    "stationary",
                    1,
                    "down",
                    sprite_source="pc",
                    floating=True,
                ),
                MapActor(
                    "human",
                    MapCell(2, 0),
                    "stationary",
                    3,
                    "down",
                    sprite_source="pc",
                    floating=False,
                ),
            ),
        )
        field = FieldMovement(map_data, start=FieldPosition(3, 1))
        actors = FieldActors(map_data)
        pc_image = Mock(width=384, height=384)
        pyxel = Mock(frame_count=0)
        renderer = FieldRenderer(
            map_data,
            screen_width=64,
            screen_height=48,
            pyxel_api=pyxel,
        )

        renderer.draw(
            field,
            actors=actors,
            actor_pc_character_image=pc_image,
            actor_pc_fairy_sprite_indices=(0, 1, 2),
            draw_player=False,
        )

        shadow_calls = [
            draw_call
            for draw_call in pyxel.blt.call_args_list
            if draw_call.args[2] == CHARACTER_SHADOW_BANK
            and draw_call.args[3] == CHARACTER_SHADOW_SOURCE_X
            and draw_call.args[4] == CHARACTER_SHADOW_SOURCE_Y
        ]
        self.assertEqual(
            shadow_calls,
            [
                call(
                    16,
                    0,
                    CHARACTER_SHADOW_BANK,
                    CHARACTER_SHADOW_SOURCE_X,
                    CHARACTER_SHADOW_SOURCE_Y,
                    16,
                    16,
                    1,
                ),
                call(
                    32,
                    0,
                    CHARACTER_SHADOW_BANK,
                    CHARACTER_SHADOW_SOURCE_X,
                    CHARACTER_SHADOW_SOURCE_Y,
                    16,
                    16,
                    1,
                ),
            ],
        )

    def test_actor_floating_phase_varies_by_stable_actor_identity(self) -> None:
        map_data = compiled_map(("000", "000", "000"), profile="town")
        object.__setattr__(
            map_data,
            "actors",
            (
                MapActor(
                    "fairy",
                    MapCell(1, 0),
                    "stationary",
                    0,
                    "down",
                    sprite_source="npc",
                    floating=True,
                ),
                MapActor(
                    "bed_fairy",
                    MapCell(2, 0),
                    "stationary",
                    1,
                    "down",
                    sprite_source="pc",
                    floating=True,
                ),
            ),
        )
        field = FieldMovement(map_data, start=FieldPosition(1, 1))
        actors = FieldActors(map_data)
        npc_image = Mock(width=96, height=128)
        pc_image = Mock(width=384, height=384)
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
            actor_character_image=npc_image,
            actor_pc_character_image=pc_image,
        )

        pyxel.blt.assert_any_call(16, -16, npc_image, 0, 0, 16, 32, 1)
        pyxel.blt.assert_any_call(32, -16, pc_image, 80, 0, 16, 32, 1)

    def test_draws_the_current_treasure_animation_frame(self) -> None:
        map_data = compiled_map(("000", "000", "000"))
        treasure = MapActor(
            "chest",
            MapCell(1, 0),
            "treasure",
            0,
            contents=MapTreasureContents("gold", amount=10),
        )
        object.__setattr__(map_data, "actors", (treasure,))
        field = FieldMovement(map_data, start=FieldPosition(1, 1))
        actors = FieldActors(map_data)
        actors.start_treasure_opening("chest")
        treasure_image = Mock(width=48, height=16)
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
            treasure_image=treasure_image,
        )

        pyxel.blt.assert_any_call(
            16,
            0,
            treasure_image,
            16,
            0,
            16,
            16,
            1,
        )


if __name__ == "__main__":
    unittest.main()
