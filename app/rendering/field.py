"""Draw compiled maps and the moving field character."""

from __future__ import annotations

from typing import Any

import pyxel

if __package__ == "rendering":
    from field import FieldActors, FieldMovement
    from input import Direction
    from rendering.character_shadow import draw_character_shadow
    from rendering.floating import (
        floating_character_frame,
        floating_phase_offset,
    )
    from resources.maps import CompiledMap, MapObjectTile
else:
    from ..field import FieldActors, FieldMovement
    from ..input import Direction
    from ..resources.maps import CompiledMap, MapObjectTile
    from .character_shadow import draw_character_shadow
    from .floating import (
        floating_character_frame,
        floating_phase_offset,
    )


FIELD_CHARACTER_BANK = 0
FIELD_CHARACTER_SOURCE_X = 0
FIELD_CHARACTER_SOURCE_Y = 64
FIELD_CHARACTER_SIZE = 16
FIELD_CHARACTER_COLKEY = 1
FIELD_CHARACTER_ANIMATION_INTERVAL = 16
FIELD_PROP_ASSET_ID = "actors/props"
FIELD_CHARACTER_ASSET_ID = "actors/characters"
FIELD_PLAYER_CHARACTER_ASSET_ID = "characters/ch_walk"
FIELD_TREASURE_ASSET_ID = "actors/treasure"
FIELD_CHARACTER_FACING_ROWS = {
    Direction.UP: 0,
    Direction.RIGHT: 1,
    Direction.DOWN: 2,
    Direction.LEFT: 3,
}
FIELD_ACTOR_CHARACTER_FRAME_COUNT = 3
FIELD_ACTOR_CHARACTER_HEIGHT = 32
FIELD_ACTOR_CHARACTER_SET_WIDTH = (
    FIELD_CHARACTER_SIZE * FIELD_ACTOR_CHARACTER_FRAME_COUNT
)
FIELD_ACTOR_CHARACTER_SET_HEIGHT = FIELD_ACTOR_CHARACTER_HEIGHT * 4
FIELD_ACTOR_CHARACTER_STANDING_FRAME = 1
FIELD_ACTOR_CHARACTER_ANIMATION_INTERVAL = 4
FIELD_ACTOR_CHARACTER_WALKING_FRAMES = (2, 1, 0, 1)
FIELD_ACTOR_CHARACTER_FACING_ROWS = {
    Direction.DOWN: 0,
    Direction.UP: 1,
    Direction.LEFT: 2,
    Direction.RIGHT: 3,
}
FIELD_PLAYER_CHARACTER_FRAME_COUNT = 3
FIELD_PLAYER_CHARACTER_HEIGHT = 32
FIELD_PLAYER_CHARACTER_SET_WIDTH = (
    FIELD_CHARACTER_SIZE * FIELD_PLAYER_CHARACTER_FRAME_COUNT
)
FIELD_PLAYER_CHARACTER_SET_HEIGHT = FIELD_PLAYER_CHARACTER_HEIGHT * 4
FIELD_PLAYER_CHARACTER_SETS_PER_ROW = 8
FIELD_PLAYER_CHARACTER_STANDING_FRAME = 1
FIELD_PLAYER_CHARACTER_ANIMATION_INTERVAL = 8
FIELD_PLAYER_CHARACTER_WALKING_FRAMES = (2, 1, 0, 1)
FIELD_PLAYER_CHARACTER_FACING_ROWS = {
    Direction.DOWN: 0,
    Direction.UP: 1,
    Direction.LEFT: 2,
    Direction.RIGHT: 3,
}


class FieldRenderer:
    """Render a scrolling field viewport from resolved runtime data."""

    def __init__(
        self,
        map_data: CompiledMap,
        *,
        screen_width: int,
        screen_height: int,
        pyxel_api: Any = pyxel,
    ) -> None:
        if not isinstance(map_data, CompiledMap):
            raise TypeError("field renderer map data must be a CompiledMap")
        for label, value in (
            ("screen width", screen_width),
            ("screen height", screen_height),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"field renderer {label} must be a positive integer")
        self.map_data = map_data
        self.screen_width = screen_width
        self.screen_height = screen_height
        self._pyxel = pyxel_api
        y_sorted_instances: dict[str, list[tuple[int, MapObjectTile]]] = {}
        for index, object_tile in enumerate(map_data.object_tiles):
            if object_tile.draw_group not in ("object_y_sorted", "object_foreground"):
                continue
            y_sorted_instances.setdefault(object_tile.instance_id, []).append(
                (index, object_tile)
            )
        self._y_sorted_object_instances = tuple(
            tuple(indexed_tiles)
            for indexed_tiles in y_sorted_instances.values()
        )

    def draw(
        self,
        field: FieldMovement,
        *,
        actors: FieldActors | None = None,
        prop_image: Any | None = None,
        actor_character_image: Any | None = None,
        actor_pc_character_image: Any | None = None,
        player_character_image: Any | None = None,
        player_sprite_index: int = 0,
        player_floating: bool = False,
        player_floating_phase: int = 0,
        treasure_image: Any | None = None,
        frame_count: int | None = None,
        draw_player: bool = True,
    ) -> None:
        if not isinstance(field, FieldMovement):
            raise TypeError("field renderer requires a FieldMovement")
        if field.map_data is not self.map_data:
            raise ValueError("field renderer and movement must use the same map data")
        if frame_count is None:
            frame_count = self._pyxel.frame_count
        if isinstance(frame_count, bool) or not isinstance(frame_count, int):
            raise TypeError("field renderer frame count must be an integer")
        if not isinstance(draw_player, bool):
            raise TypeError("field renderer draw_player must be a boolean")
        if not isinstance(player_floating, bool):
            raise TypeError("field renderer player_floating must be a boolean")
        if isinstance(player_floating_phase, bool) or not isinstance(
            player_floating_phase, int
        ):
            raise TypeError("field renderer player_floating_phase must be an integer")

        camera_x, camera_y = self.camera_position(field)
        self._draw_ground(camera_x, camera_y, frame_count)
        self._draw_objects(
            camera_x,
            camera_y,
            frame_count,
            draw_groups=("object",),
        )
        characters: list[
            tuple[int, FieldMovement, str, int, Any | None, bool, int]
        ] = []
        if draw_player:
            characters.append(
                (
                    field.world_y,
                    field,
                    "player",
                    player_sprite_index,
                    player_character_image,
                    player_floating,
                    player_floating_phase,
                )
            )
        if actors is not None:
            if actors.map_data is not self.map_data:
                raise ValueError("field renderer and actors must use the same map data")
            for actor in actors.actors:
                if actor.kind == "prop":
                    image = prop_image
                elif actor.kind == "treasure":
                    image = treasure_image
                elif actor.sprite_source == "pc":
                    image = actor_pc_character_image
                else:
                    image = actor_character_image
                characters.append(
                    (
                        actor.movement.world_y,
                        actor.movement,
                        actor.kind,
                        actor.sprite_index,
                        image,
                        actor.floating,
                        floating_phase_offset(
                            f"actor:{self.map_data.map_id}:{actor.id}"
                        ),
                    )
                )
        depth_items: list[tuple[int, int, int, str, Any]] = [
            (character[0], 1, index, f"character:{index}", character)
            for index, character in enumerate(characters)
        ]
        tile_size = self.map_data.tile_size
        for indexed_tiles in self._y_sorted_object_instances:
            first_index, first_tile = indexed_tiles[0]
            depth_items.append(
                (
                    first_tile.sort_y * tile_size,
                    2 if first_tile.draw_group == "object_foreground" else 0,
                    first_tile.order,
                    f"object:{first_index}:{first_tile.instance_id}",
                    indexed_tiles,
                )
            )

        for _depth_y, item_kind, _order, _identity, payload in sorted(depth_items):
            if item_kind != 1:
                for object_index, object_tile in payload:
                    self._draw_object_tile(
                        object_index,
                        object_tile,
                        camera_x,
                        camera_y,
                        frame_count,
                    )
                continue

            (
                _world_y,
                movement,
                kind,
                sprite_index,
                image,
                floating,
                floating_phase,
            ) = payload
            if kind == "player":
                self._draw_player_character(
                    movement,
                    camera_x,
                    camera_y,
                    frame_count,
                    image=image,
                    sprite_index=sprite_index,
                    floating=floating,
                    floating_phase=floating_phase,
                )
            elif kind == "prop":
                self._draw_prop(movement, camera_x, camera_y, sprite_index, image)
            elif kind == "treasure":
                actor = actors.actor_at(
                    movement.position.x,
                    movement.position.y,
                )
                if actor is None:
                    raise ValueError("treasure actor state is missing")
                self._draw_treasure(
                    movement,
                    camera_x,
                    camera_y,
                    actor.treasure_frame,
                    image,
                )
            else:
                self._draw_character(
                    movement,
                    camera_x,
                    camera_y,
                    frame_count,
                    image=image,
                    sprite_index=sprite_index,
                    floating=floating,
                    floating_phase=floating_phase,
                )
        self._draw_objects(
            camera_x,
            camera_y,
            frame_count,
            draw_groups=("object_overlay",),
        )

    def camera_position(self, field: FieldMovement) -> tuple[int, int]:
        player_screen_x = (self.screen_width - FIELD_CHARACTER_SIZE) // 2
        player_screen_y = (self.screen_height - FIELD_CHARACTER_SIZE) // 2
        maximum_x = max(
            0,
            self.map_data.width * self.map_data.tile_size - self.screen_width,
        )
        maximum_y = max(
            0,
            self.map_data.height * self.map_data.tile_size - self.screen_height,
        )
        return (
            min(max(field.world_x - player_screen_x, 0), maximum_x),
            min(max(field.world_y - player_screen_y, 0), maximum_y),
        )

    def _draw_ground(self, camera_x: int, camera_y: int, frame_count: int) -> None:
        tile_size = self.map_data.tile_size
        start_x = camera_x // tile_size
        start_y = camera_y // tile_size
        end_x = min(
            self.map_data.width,
            (camera_x + self.screen_width - 1) // tile_size + 1,
        )
        end_y = min(
            self.map_data.height,
            (camera_y + self.screen_height - 1) // tile_size + 1,
        )
        for y in range(start_y, end_y):
            for x in range(start_x, end_x):
                index = y * self.map_data.width + x
                self._draw_atlas_tile(
                    self.map_data.ground_tile_at(index, frame_count),
                    x * tile_size - camera_x,
                    y * tile_size - camera_y,
                )

    def _draw_objects(
        self,
        camera_x: int,
        camera_y: int,
        frame_count: int,
        *,
        draw_groups: tuple[str, ...],
    ) -> None:
        for index, object_tile in enumerate(self.map_data.object_tiles):
            if object_tile.draw_group not in draw_groups:
                continue
            self._draw_object_tile(
                index,
                object_tile,
                camera_x,
                camera_y,
                frame_count,
            )

    def _draw_object_tile(
        self,
        index: int,
        object_tile: MapObjectTile,
        camera_x: int,
        camera_y: int,
        frame_count: int,
    ) -> None:
        tile_size = self.map_data.tile_size
        x = object_tile.x * tile_size - camera_x
        y = object_tile.y * tile_size - camera_y
        if (
            x <= -tile_size
            or y <= -tile_size
            or x >= self.screen_width
            or y >= self.screen_height
        ):
            return
        self._draw_atlas_tile(
            self.map_data.object_tile_at(index, frame_count),
            x,
            y,
            colkey=FIELD_CHARACTER_COLKEY,
        )

    def _draw_atlas_tile(
        self,
        tile: int,
        x: int,
        y: int,
        *,
        colkey: int | None = None,
    ) -> None:
        tile_size = self.map_data.tile_size
        source_x = (tile % self.map_data.atlas_columns) * tile_size
        source_y = (tile // self.map_data.atlas_columns) * tile_size
        args = (
            x,
            y,
            self.map_data.atlas,
            source_x,
            source_y,
            tile_size,
            tile_size,
        )
        if colkey is None:
            self._pyxel.blt(*args)
        else:
            self._pyxel.blt(*args, colkey)

    def _draw_character(
        self,
        field: FieldMovement,
        camera_x: int,
        camera_y: int,
        frame_count: int,
        *,
        image: Any | None = None,
        sprite_index: int = 0,
        floating: bool = False,
        floating_phase: int = 0,
    ) -> None:
        if not isinstance(floating, bool):
            raise TypeError("actor character floating must be a boolean")
        if image is None:
            frame = (frame_count // FIELD_CHARACTER_ANIMATION_INTERVAL) % 2
            row = FIELD_CHARACTER_FACING_ROWS[field.facing]
            source_x = FIELD_CHARACTER_SOURCE_X + frame * FIELD_CHARACTER_SIZE
            source_y = FIELD_CHARACTER_SOURCE_Y + row * FIELD_CHARACTER_SIZE
            source_image = FIELD_CHARACTER_BANK
            draw_y = field.world_y - camera_y
            draw_height = FIELD_CHARACTER_SIZE
        else:
            if isinstance(sprite_index, bool) or not isinstance(
                sprite_index, int
            ):
                raise TypeError("actor character sprite_index must be an integer")
            if sprite_index < 0:
                raise ValueError("actor character sprite_index must not be negative")
            columns = image.width // FIELD_ACTOR_CHARACTER_SET_WIDTH
            if columns <= 0:
                raise ValueError(
                    "actor character sheet must be at least 48 pixels wide"
                )
            block_x = (
                sprite_index % columns
            ) * FIELD_ACTOR_CHARACTER_SET_WIDTH
            block_y = (
                sprite_index // columns
            ) * FIELD_ACTOR_CHARACTER_SET_HEIGHT
            if (
                block_x + FIELD_ACTOR_CHARACTER_SET_WIDTH > image.width
                or block_y + FIELD_ACTOR_CHARACTER_SET_HEIGHT > image.height
            ):
                raise ValueError("actor character sprite_index is outside the sheet")
            frame = FIELD_ACTOR_CHARACTER_STANDING_FRAME
            if field.is_moving or field.is_walking:
                phase = (
                    (field.walking_frame_count - 1)
                    // FIELD_ACTOR_CHARACTER_ANIMATION_INTERVAL
                    % len(FIELD_ACTOR_CHARACTER_WALKING_FRAMES)
                )
                frame = FIELD_ACTOR_CHARACTER_WALKING_FRAMES[phase]
            elif floating:
                frame = floating_character_frame(
                    frame_count,
                    phase_offset=floating_phase,
                )
            source_x = block_x + frame * FIELD_CHARACTER_SIZE
            source_y = (
                block_y
                + FIELD_ACTOR_CHARACTER_FACING_ROWS[field.facing]
                * FIELD_ACTOR_CHARACTER_HEIGHT
            )
            source_image = image
            draw_y = field.world_y - camera_y - FIELD_CHARACTER_SIZE
            draw_height = FIELD_ACTOR_CHARACTER_HEIGHT
            draw_character_shadow(
                self._pyxel,
                field.world_x - camera_x,
                field.world_y - camera_y,
            )
        self._pyxel.blt(
            field.world_x - camera_x,
            draw_y,
            source_image,
            source_x,
            source_y,
            FIELD_CHARACTER_SIZE,
            draw_height,
            FIELD_CHARACTER_COLKEY,
        )

    def _draw_player_character(
        self,
        field: FieldMovement,
        camera_x: int,
        camera_y: int,
        frame_count: int,
        *,
        image: Any | None,
        sprite_index: int,
        floating: bool = False,
        floating_phase: int = 0,
    ) -> None:
        if not isinstance(floating, bool):
            raise TypeError("player floating must be a boolean")
        if image is None:
            self._draw_character(
                field,
                camera_x,
                camera_y,
                frame_count,
            )
            return
        if isinstance(sprite_index, bool) or not isinstance(sprite_index, int):
            raise TypeError("player sprite_index must be an integer")
        if sprite_index < 0:
            raise ValueError("player sprite_index must not be negative")

        block_x = (
            sprite_index % FIELD_PLAYER_CHARACTER_SETS_PER_ROW
        ) * FIELD_PLAYER_CHARACTER_SET_WIDTH
        block_y = (
            sprite_index // FIELD_PLAYER_CHARACTER_SETS_PER_ROW
        ) * FIELD_PLAYER_CHARACTER_SET_HEIGHT
        if (
            block_x + FIELD_PLAYER_CHARACTER_SET_WIDTH > image.width
            or block_y + FIELD_PLAYER_CHARACTER_SET_HEIGHT > image.height
        ):
            raise ValueError("player sprite_index is outside the walking sheet")

        frame = FIELD_PLAYER_CHARACTER_STANDING_FRAME
        if field.is_moving or field.is_walking:
            phase = (
                (field.walking_frame_count - 1)
                // FIELD_PLAYER_CHARACTER_ANIMATION_INTERVAL
                % len(FIELD_PLAYER_CHARACTER_WALKING_FRAMES)
            )
            frame = FIELD_PLAYER_CHARACTER_WALKING_FRAMES[phase]
        elif floating:
            frame = floating_character_frame(
                frame_count,
                phase_offset=floating_phase,
            )
        source_x = block_x + frame * FIELD_CHARACTER_SIZE
        source_y = (
            block_y
            + FIELD_PLAYER_CHARACTER_FACING_ROWS[field.facing]
            * FIELD_PLAYER_CHARACTER_HEIGHT
        )
        draw_character_shadow(
            self._pyxel,
            field.world_x - camera_x,
            field.world_y - camera_y,
        )
        self._pyxel.blt(
            field.world_x - camera_x,
            field.world_y - camera_y - FIELD_CHARACTER_SIZE,
            image,
            source_x,
            source_y,
            FIELD_CHARACTER_SIZE,
            FIELD_PLAYER_CHARACTER_HEIGHT,
            FIELD_CHARACTER_COLKEY,
        )

    def _draw_prop(
        self,
        field: FieldMovement,
        camera_x: int,
        camera_y: int,
        sprite_index: int,
        image: Any | None,
    ) -> None:
        if image is None:
            raise ValueError("actor prop sheet is required to draw prop actors")
        columns = image.width // FIELD_CHARACTER_SIZE
        if columns <= 0:
            raise ValueError("actor prop sheet must be at least 16 pixels wide")
        source_x = (sprite_index % columns) * FIELD_CHARACTER_SIZE
        source_y = (sprite_index // columns) * FIELD_CHARACTER_SIZE
        if source_y + FIELD_CHARACTER_SIZE > image.height:
            raise ValueError("actor prop sprite_index is outside the sheet")
        self._pyxel.blt(
            field.world_x - camera_x,
            field.world_y - camera_y,
            image,
            source_x,
            source_y,
            FIELD_CHARACTER_SIZE,
            FIELD_CHARACTER_SIZE,
            FIELD_CHARACTER_COLKEY,
        )

    def _draw_treasure(
        self,
        movement: FieldMovement,
        camera_x: int,
        camera_y: int,
        frame: int,
        image: Any | None,
    ) -> None:
        if image is None:
            raise ValueError("treasure actor sheet is required to draw treasure actors")
        if image.width != 48 or image.height != 16:
            raise ValueError("treasure actor sheet must be 48x16 pixels")
        if frame not in (0, 1, 2):
            raise ValueError("treasure animation frame is outside the sheet")
        self._pyxel.blt(
            movement.world_x - camera_x,
            movement.world_y - camera_y,
            image,
            frame * FIELD_CHARACTER_SIZE,
            0,
            FIELD_CHARACTER_SIZE,
            FIELD_CHARACTER_SIZE,
            FIELD_CHARACTER_COLKEY,
        )


__all__ = [
    "FIELD_ACTOR_CHARACTER_ANIMATION_INTERVAL",
    "FIELD_ACTOR_CHARACTER_FACING_ROWS",
    "FIELD_ACTOR_CHARACTER_FRAME_COUNT",
    "FIELD_ACTOR_CHARACTER_HEIGHT",
    "FIELD_ACTOR_CHARACTER_SET_HEIGHT",
    "FIELD_ACTOR_CHARACTER_SET_WIDTH",
    "FIELD_ACTOR_CHARACTER_STANDING_FRAME",
    "FIELD_ACTOR_CHARACTER_WALKING_FRAMES",
    "FIELD_CHARACTER_ANIMATION_INTERVAL",
    "FIELD_CHARACTER_BANK",
    "FIELD_CHARACTER_COLKEY",
    "FIELD_CHARACTER_FACING_ROWS",
    "FIELD_CHARACTER_ASSET_ID",
    "FIELD_CHARACTER_SIZE",
    "FIELD_CHARACTER_SOURCE_X",
    "FIELD_CHARACTER_SOURCE_Y",
    "FIELD_PLAYER_CHARACTER_ASSET_ID",
    "FIELD_PLAYER_CHARACTER_ANIMATION_INTERVAL",
    "FIELD_PLAYER_CHARACTER_FACING_ROWS",
    "FIELD_PLAYER_CHARACTER_FRAME_COUNT",
    "FIELD_PLAYER_CHARACTER_HEIGHT",
    "FIELD_PLAYER_CHARACTER_SET_HEIGHT",
    "FIELD_PLAYER_CHARACTER_SET_WIDTH",
    "FIELD_PLAYER_CHARACTER_SETS_PER_ROW",
    "FIELD_PLAYER_CHARACTER_STANDING_FRAME",
    "FIELD_PLAYER_CHARACTER_WALKING_FRAMES",
    "FIELD_PROP_ASSET_ID",
    "FIELD_TREASURE_ASSET_ID",
    "FieldRenderer",
]
