"""Tile-aligned field movement independent of Pyxel drawing."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

if __package__:
    from .input import Direction
    from .resources.maps import CompiledMap, MapActor, MapCell
else:
    from input import Direction
    from resources.maps import CompiledMap, MapActor, MapCell


DEFAULT_FIELD_MOVE_SPEED = 1


@dataclass(frozen=True)
class FieldPosition:
    x: int
    y: int


class FieldMovement:
    """Own one character's facing and smooth tile-to-tile movement."""

    def __init__(
        self,
        map_data: CompiledMap,
        *,
        start: FieldPosition | None = None,
        speed: int = DEFAULT_FIELD_MOVE_SPEED,
        facing: Direction = Direction.DOWN,
    ) -> None:
        if not isinstance(map_data, CompiledMap):
            raise TypeError("field map data must be a CompiledMap")
        if isinstance(speed, bool) or not isinstance(speed, int):
            raise TypeError("field movement speed must be an integer")
        if speed <= 0 or map_data.tile_size % speed:
            raise ValueError("field movement speed must divide the map tile size")
        if not isinstance(facing, Direction):
            raise TypeError("field facing must be a Direction")
        if start is None:
            start = self._nearest_passable_position(map_data)
        if not isinstance(start, FieldPosition):
            raise TypeError("field start must be a FieldPosition")
        if map_data.is_blocked(start.x, start.y):
            raise ValueError("field start must be on a passable map cell")

        self.map_data = map_data
        self.position = start
        self.speed = speed
        self.facing = facing
        self.offset_x = 0
        self.offset_y = 0
        self._moving_direction: Direction | None = None
        self._moved_this_frame = False
        self._arrived_position: FieldPosition | None = None

    @staticmethod
    def _nearest_passable_position(map_data: CompiledMap) -> FieldPosition:
        center_x = map_data.width // 2
        center_y = map_data.height // 2
        candidates = (
            (abs(x - center_x) + abs(y - center_y), y, x)
            for y in range(map_data.height)
            for x in range(map_data.width)
            if not map_data.is_blocked(x, y)
        )
        try:
            _distance, y, x = min(candidates)
        except ValueError as error:
            raise ValueError(
                "field map must contain at least one passable cell"
            ) from error
        return FieldPosition(x=x, y=y)

    @property
    def is_moving(self) -> bool:
        return self._moving_direction is not None

    @property
    def is_walking(self) -> bool:
        return self._moved_this_frame

    @property
    def arrived_position(self) -> FieldPosition | None:
        """Return the cell reached by the most recent update, if any."""

        return self._arrived_position

    @property
    def world_x(self) -> int:
        return self.position.x * self.map_data.tile_size + self.offset_x

    @property
    def world_y(self) -> int:
        return self.position.y * self.map_data.tile_size + self.offset_y

    def update(
        self,
        direction: Direction | None,
        *,
        blocked_positions: tuple[FieldPosition, ...] = (),
    ) -> bool:
        """Advance one frame and return whether the character moved."""

        if direction is not None and not isinstance(direction, Direction):
            raise TypeError("field movement direction must be a Direction or None")
        if not isinstance(blocked_positions, tuple) or not all(
            isinstance(position, FieldPosition) for position in blocked_positions
        ):
            raise TypeError("blocked_positions must be a tuple of FieldPosition")
        self._moved_this_frame = False
        self._arrived_position = None
        if self._moving_direction is None:
            if direction is None:
                return False
            self.facing = direction
            destination_x = self.position.x + direction.dx
            destination_y = self.position.y + direction.dy
            if self.map_data.is_blocked(destination_x, destination_y) or FieldPosition(
                destination_x, destination_y
            ) in blocked_positions:
                return False
            self._moving_direction = direction

        active = self._moving_direction
        self.offset_x += active.dx * self.speed
        self.offset_y += active.dy * self.speed
        self._moved_this_frame = True
        reached_next_cell = (
            abs(self.offset_x) == self.map_data.tile_size
            or abs(self.offset_y) == self.map_data.tile_size
        )
        if reached_next_cell:
            self.position = FieldPosition(
                x=self.position.x + active.dx,
                y=self.position.y + active.dy,
            )
            self.offset_x = 0
            self.offset_y = 0
            self._moving_direction = None
            self._arrived_position = self.position
        return True


@dataclass
class FieldActor:
    id: str
    appearance_id: str
    movement: FieldMovement


class FieldActors:
    """Own runtime movement state for map-defined field actors."""

    def __init__(self, map_data: CompiledMap) -> None:
        if not isinstance(map_data, CompiledMap):
            raise TypeError("field actors require a CompiledMap")
        self.map_data = map_data
        self._actors = {
            actor.id: FieldActor(
                actor.id,
                actor.appearance_id,
                FieldMovement(
                    map_data,
                    start=FieldPosition(actor.position.x, actor.position.y),
                    facing=Direction[actor.facing.upper()],
                ),
            )
            for actor in map_data.actors
        }

    @property
    def actors(self) -> tuple[FieldActor, ...]:
        return tuple(self._actors.values())

    @property
    def positions(self) -> Mapping[str, MapCell]:
        return MappingProxyType(
            {
                actor_id: MapCell(actor.movement.position.x, actor.movement.position.y)
                for actor_id, actor in self._actors.items()
            }
        )

    def actor(self, actor_id: str) -> FieldActor:
        try:
            return self._actors[actor_id]
        except KeyError as error:
            raise KeyError(f"unknown field actor: {actor_id}") from error

    def blocked_positions(self, *, excluding: str | None = None) -> tuple[FieldPosition, ...]:
        return tuple(
            actor.movement.position
            for actor_id, actor in self._actors.items()
            if actor_id != excluding
        )

    def update(
        self,
        actor_id: str,
        direction: Direction,
        *,
        party_position: FieldPosition,
    ) -> bool:
        actor = self.actor(actor_id)
        return actor.movement.update(
            direction,
            blocked_positions=(
                party_position,
                *self.blocked_positions(excluding=actor_id),
            ),
        )


__all__ = [
    "DEFAULT_FIELD_MOVE_SPEED",
    "FieldMovement",
    "FieldPosition",
    "FieldActor",
    "FieldActors",
]
