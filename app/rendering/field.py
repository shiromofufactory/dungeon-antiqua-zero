"""Draw compiled maps and the moving field character."""

from __future__ import annotations

from typing import Any

import pyxel

if __package__ == "rendering":
    from field import FieldActors, FieldMovement
    from input import Direction
    from resources.maps import CompiledMap
else:
    from ..field import FieldActors, FieldMovement
    from ..input import Direction
    from ..resources.maps import CompiledMap


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

    def draw(
        self,
        field: FieldMovement,
        *,
        actors: FieldActors | None = None,
        prop_image: Any | None = None,
        actor_character_image: Any | None = None,
        player_character_image: Any | None = None,
        player_sprite_index: int = 0,
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

        camera_x, camera_y = self.camera_position(field)
        self._draw_ground(camera_x, camera_y, frame_count)
        self._draw_objects(
            camera_x,
            camera_y,
            frame_count,
            draw_groups=("object", "object_overlay"),
        )
        characters: list[tuple[int, FieldMovement, str, int, Any | None]] = []
        if draw_player:
            characters.append(
                (
                    field.world_y,
                    field,
                    "player",
                    player_sprite_index,
                    player_character_image,
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
                else:
                    image = actor_character_image
                characters.append(
                    (
                        actor.movement.world_y,
                        actor.movement,
                        actor.kind,
                        actor.sprite_index,
                        image,
                    )
                )
        for _world_y, movement, kind, sprite_index, image in sorted(
            characters, key=lambda item: item[0]
        ):
            if kind == "player":
                self._draw_player_character(
                    movement,
                    camera_x,
                    camera_y,
                    frame_count,
                    image=image,
                    sprite_index=sprite_index,
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
                )
        self._draw_objects(
            camera_x,
            camera_y,
            frame_count,
            draw_groups=("object_foreground",),
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
        tile_size = self.map_data.tile_size
        for index, object_tile in enumerate(self.map_data.object_tiles):
            if object_tile.draw_group not in draw_groups:
                continue
            x = object_tile.x * tile_size - camera_x
            y = object_tile.y * tile_size - camera_y
            if (
                x <= -tile_size
                or y <= -tile_size
                or x >= self.screen_width
                or y >= self.screen_height
            ):
                continue
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
    ) -> None:
        frame = (frame_count // FIELD_CHARACTER_ANIMATION_INTERVAL) % 2
        row = FIELD_CHARACTER_FACING_ROWS[field.facing]
        if image is None:
            source_x = FIELD_CHARACTER_SOURCE_X + frame * FIELD_CHARACTER_SIZE
            source_y = FIELD_CHARACTER_SOURCE_Y + row * FIELD_CHARACTER_SIZE
            source_image = FIELD_CHARACTER_BANK
        else:
            columns = image.width // (FIELD_CHARACTER_SIZE * 2)
            if columns <= 0:
                raise ValueError(
                    "actor character sheet must be at least 32 pixels wide"
                )
            block_x = (sprite_index % columns) * FIELD_CHARACTER_SIZE * 2
            block_y = (sprite_index // columns) * FIELD_CHARACTER_SIZE * 4
            if block_y + FIELD_CHARACTER_SIZE * 4 > image.height:
                raise ValueError("actor character sprite_index is outside the sheet")
            source_x = block_x + frame * FIELD_CHARACTER_SIZE
            source_y = block_y + row * FIELD_CHARACTER_SIZE
            source_image = image
        self._pyxel.blt(
            field.world_x - camera_x,
            field.world_y - camera_y,
            source_image,
            source_x,
            source_y,
            FIELD_CHARACTER_SIZE,
            FIELD_CHARACTER_SIZE,
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
    ) -> None:
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
        source_x = block_x + frame * FIELD_CHARACTER_SIZE
        source_y = (
            block_y
            + FIELD_PLAYER_CHARACTER_FACING_ROWS[field.facing]
            * FIELD_PLAYER_CHARACTER_HEIGHT
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
