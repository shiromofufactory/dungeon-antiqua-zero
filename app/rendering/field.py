"""Draw compiled maps and the moving field character."""

from __future__ import annotations

from typing import Any

import pyxel

if __package__ == "rendering":
    from field import FieldMovement
    from input import Direction
    from resources.maps import CompiledMap
else:
    from ..field import FieldMovement
    from ..input import Direction
    from ..resources.maps import CompiledMap


FIELD_CHARACTER_BANK = 0
FIELD_CHARACTER_SOURCE_X = 0
FIELD_CHARACTER_SOURCE_Y = 64
FIELD_CHARACTER_SIZE = 16
FIELD_CHARACTER_COLKEY = 1
FIELD_CHARACTER_ANIMATION_INTERVAL = 16
FIELD_CHARACTER_FACING_ROWS = {
    Direction.UP: 0,
    Direction.RIGHT: 1,
    Direction.DOWN: 2,
    Direction.LEFT: 3,
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

    def draw(self, field: FieldMovement, *, frame_count: int | None = None) -> None:
        if not isinstance(field, FieldMovement):
            raise TypeError("field renderer requires a FieldMovement")
        if field.map_data is not self.map_data:
            raise ValueError("field renderer and movement must use the same map data")
        if frame_count is None:
            frame_count = self._pyxel.frame_count
        if isinstance(frame_count, bool) or not isinstance(frame_count, int):
            raise TypeError("field renderer frame count must be an integer")

        camera_x, camera_y = self.camera_position(field)
        self._draw_ground(camera_x, camera_y, frame_count)
        self._draw_objects(camera_x, camera_y, frame_count)
        self._draw_character(field, camera_x, camera_y, frame_count)

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

    def _draw_objects(self, camera_x: int, camera_y: int, frame_count: int) -> None:
        tile_size = self.map_data.tile_size
        for index, object_tile in enumerate(self.map_data.object_tiles):
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
    ) -> None:
        frame = (frame_count // FIELD_CHARACTER_ANIMATION_INTERVAL) % 2
        row = FIELD_CHARACTER_FACING_ROWS[field.facing]
        self._pyxel.blt(
            field.world_x - camera_x,
            field.world_y - camera_y,
            FIELD_CHARACTER_BANK,
            FIELD_CHARACTER_SOURCE_X + frame * FIELD_CHARACTER_SIZE,
            FIELD_CHARACTER_SOURCE_Y + row * FIELD_CHARACTER_SIZE,
            FIELD_CHARACTER_SIZE,
            FIELD_CHARACTER_SIZE,
            FIELD_CHARACTER_COLKEY,
        )


__all__ = [
    "FIELD_CHARACTER_ANIMATION_INTERVAL",
    "FIELD_CHARACTER_BANK",
    "FIELD_CHARACTER_COLKEY",
    "FIELD_CHARACTER_FACING_ROWS",
    "FIELD_CHARACTER_SIZE",
    "FIELD_CHARACTER_SOURCE_X",
    "FIELD_CHARACTER_SOURCE_Y",
    "FieldRenderer",
]
