"""Tile-aligned field movement independent of Pyxel drawing."""

from __future__ import annotations

from dataclasses import dataclass
import random
from types import MappingProxyType
from typing import Mapping

if __package__:
    from .input import Direction
    from .resources.maps import CompiledMap, MapActor, MapCell
else:
    from input import Direction
    from resources.maps import CompiledMap, MapActor, MapCell


DEFAULT_FIELD_MOVE_SPEED = 1
DEFAULT_ROAM_WAIT_MIN = 30
DEFAULT_ROAM_WAIT_MAX = 90


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

    @property
    def destination_position(self) -> FieldPosition | None:
        if self._moving_direction is None:
            return None
        return FieldPosition(
            self.position.x + self._moving_direction.dx,
            self.position.y + self._moving_direction.dy,
        )

    def stop(self) -> None:
        """Cancel an unfinished step and return to the current logical cell."""

        self.offset_x = 0
        self.offset_y = 0
        self._moving_direction = None
        self._moved_this_frame = False
        self._arrived_position = None

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
    kind: str
    sprite_index: int
    movement: FieldMovement
    roam_wait_frames: int = 0


class FieldActors:
    """Own runtime movement state for map-defined field actors."""

    def __init__(
        self,
        map_data: CompiledMap,
        *,
        random_source: random.Random | None = None,
    ) -> None:
        if not isinstance(map_data, CompiledMap):
            raise TypeError("field actors require a CompiledMap")
        self.map_data = map_data
        self._random = random_source or random.Random(f"{map_data.map_id}:actors")
        self._actors = {
            actor.id: FieldActor(
                actor.id,
                actor.kind,
                actor.sprite_index,
                FieldMovement(
                    map_data,
                    start=FieldPosition(actor.position.x, actor.position.y),
                    facing=(
                        Direction.DOWN
                        if actor.facing is None
                        else Direction[actor.facing.upper()]
                    ),
                ),
                self._next_roam_wait() if actor.kind == "roaming" else 0,
            )
            for actor in map_data.actors
        }

    def _next_roam_wait(self) -> int:
        return self._random.randint(DEFAULT_ROAM_WAIT_MIN, DEFAULT_ROAM_WAIT_MAX)

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
        positions = (
            position
            for actor_id, actor in self._actors.items()
            if actor_id != excluding
            for position in (
                actor.movement.position,
                actor.movement.destination_position,
            )
            if position is not None
        )
        return tuple(dict.fromkeys(positions))

    def stop(self, actor_id: str) -> None:
        self.actor(actor_id).movement.stop()

    def face_toward(self, actor_id: str, target: FieldPosition) -> None:
        actor = self.actor(actor_id)
        if actor.kind == "prop":
            return
        actor.movement.stop()
        dx = target.x - actor.movement.position.x
        dy = target.y - actor.movement.position.y
        if abs(dx) + abs(dy) != 1:
            return
        actor.movement.facing = next(
            direction
            for direction in Direction
            if (direction.dx, direction.dy) == (dx, dy)
        )

    def update(
        self,
        actor_id: str,
        direction: Direction,
        *,
        party_position: FieldPosition,
    ) -> bool:
        actor = self.actor(actor_id)
        if actor.kind == "prop":
            raise ValueError("prop field actors cannot move")
        return actor.movement.update(
            direction,
            blocked_positions=(
                party_position,
                *self.blocked_positions(excluding=actor_id),
            ),
        )

    def update_roaming(self, *, party_position: FieldPosition) -> None:
        """Advance autonomous actors once without storing their transient state."""

        for actor_id, actor in self._actors.items():
            if actor.kind == "stationary":
                actor.movement.update(None)
                continue
            if actor.kind != "roaming":
                continue
            blockers = (
                party_position,
                *self.blocked_positions(excluding=actor_id),
            )
            if actor.movement.is_moving:
                actor.movement.update(None, blocked_positions=blockers)
                if not actor.movement.is_moving:
                    actor.roam_wait_frames = self._next_roam_wait()
                continue
            if actor.roam_wait_frames > 0:
                actor.movement.update(None)
                actor.roam_wait_frames -= 1
                continue
            direction = self._random.choice((*Direction, None))
            if direction is None:
                actor.roam_wait_frames = self._next_roam_wait()
                continue
            actor.movement.update(direction, blocked_positions=blockers)
            if not actor.movement.is_moving:
                actor.roam_wait_frames = self._next_roam_wait()


__all__ = [
    "DEFAULT_FIELD_MOVE_SPEED",
    "DEFAULT_ROAM_WAIT_MAX",
    "DEFAULT_ROAM_WAIT_MIN",
    "FieldMovement",
    "FieldPosition",
    "FieldActor",
    "FieldActors",
]
