"""Tile-aligned field movement independent of Pyxel drawing."""

from __future__ import annotations

from dataclasses import dataclass
import random
from types import MappingProxyType
from typing import Collection, Iterable, Mapping

if __package__:
    from .actor_placement import actor_overlaps_map
    from .input import Direction
    from .resources.maps import CompiledMap, MapActor, MapCell
else:
    from actor_placement import actor_overlaps_map
    from input import Direction
    from resources.maps import CompiledMap, MapActor, MapCell


DEFAULT_FIELD_MOVE_SPEED = 1
INTERIOR_FIELD_MOVE_SPEED = 2
DEFAULT_ROAM_WAIT_MIN = 30
DEFAULT_ROAM_WAIT_MAX = 90
TREASURE_ANIMATION_FRAME_COUNT = 4


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
        speed: int | None = None,
        facing: Direction = Direction.DOWN,
        allow_blocked_start: bool = False,
        allow_outside_start: bool = False,
        event_flags: Collection[str] = (),
    ) -> None:
        if not isinstance(map_data, CompiledMap):
            raise TypeError("field map data must be a CompiledMap")
        if speed is None:
            if map_data.profile == "world":
                speed = DEFAULT_FIELD_MOVE_SPEED
            elif map_data.profile in ("dungeon", "town"):
                speed = INTERIOR_FIELD_MOVE_SPEED
            else:
                raise ValueError(f"unsupported field map profile: {map_data.profile}")
        if isinstance(speed, bool) or not isinstance(speed, int):
            raise TypeError("field movement speed must be an integer")
        if speed <= 0 or map_data.tile_size % speed:
            raise ValueError("field movement speed must divide the map tile size")
        if not isinstance(facing, Direction):
            raise TypeError("field facing must be a Direction")
        if not isinstance(allow_blocked_start, bool):
            raise TypeError("allow_blocked_start must be a boolean")
        if not isinstance(allow_outside_start, bool):
            raise TypeError("allow_outside_start must be a boolean")
        if start is None:
            start = self._nearest_passable_position(map_data, event_flags)
        if not isinstance(start, FieldPosition):
            raise TypeError("field start must be a FieldPosition")
        start_is_blocked = map_data.is_blocked(start.x, start.y, event_flags=event_flags)
        if not allow_outside_start and not (0 <= start.x < map_data.width and 0 <= start.y < map_data.height):
            raise ValueError("field start must be within the map bounds")
        if start_is_blocked and not allow_blocked_start:
            raise ValueError("field start must be on a passable map cell")

        self.map_data = map_data
        self.event_flags = event_flags
        self.position = start
        self.speed = speed
        self.facing = facing
        self.offset_x = 0
        self.offset_y = 0
        self._moving_direction: Direction | None = None
        self._moved_this_frame = False
        self._walking_frame_count = 0
        self._arrived_position: FieldPosition | None = None

    @staticmethod
    def _nearest_passable_position(
        map_data: CompiledMap, event_flags: Collection[str] = ()
    ) -> FieldPosition:
        center_x = map_data.width // 2
        center_y = map_data.height // 2
        candidates = (
            (abs(x - center_x) + abs(y - center_y), y, x)
            for y in range(map_data.height)
            for x in range(map_data.width)
            if not map_data.is_blocked(x, y, event_flags=event_flags)
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
    def walking_frame_count(self) -> int:
        return self._walking_frame_count

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
        self._walking_frame_count = 0
        self._arrived_position = None

    def face(self, direction: Direction) -> None:
        """Turn in place, cancelling any unfinished step."""

        if not isinstance(direction, Direction):
            raise TypeError("field facing must be a Direction")
        self.stop()
        self.facing = direction

    def update_animation(self) -> None:
        """Advance the sprite state while position and facing stay paused."""

        self._moved_this_frame = False
        self._arrived_position = None
        if self.is_moving:
            self._walking_frame_count += 1
        else:
            self._walking_frame_count = 0

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
                self._walking_frame_count = 0
                return False
            self.facing = direction
            destination_x = self.position.x + direction.dx
            destination_y = self.position.y + direction.dy
            if self.map_data.is_blocked(
                destination_x, destination_y, event_flags=self.event_flags
            ) or FieldPosition(
                destination_x, destination_y
            ) in blocked_positions:
                self._walking_frame_count = 0
                return False
            self._moving_direction = direction

        active = self._moving_direction
        self.offset_x += active.dx * self.speed
        self.offset_y += active.dy * self.speed
        self._moved_this_frame = True
        self._walking_frame_count += 1
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
    sprite_source: str
    floating: bool
    movement: FieldMovement
    roam_wait_frames: int = 0
    treasure_frame: int = 0
    treasure_animation: tuple[int, ...] = ()
    treasure_animation_elapsed: int = 0


class FieldActors:
    """Own runtime movement state for map-defined field actors."""

    def __init__(
        self,
        map_data: CompiledMap,
        *,
        random_source: random.Random | None = None,
        opened_treasure_ids: Iterable[str] = (),
        event_flags: Collection[str] = (),
    ) -> None:
        if not isinstance(map_data, CompiledMap):
            raise TypeError("field actors require a CompiledMap")
        self.map_data = map_data
        self._random = random_source or random.Random(f"{map_data.map_id}:actors")
        self._event_flags = event_flags
        opened_ids = frozenset(opened_treasure_ids)
        if not all(isinstance(actor_id, str) and actor_id for actor_id in opened_ids):
            raise TypeError("opened treasure IDs must be non-empty strings")
        self._actors = {
            actor.id: FieldActor(
                actor.id,
                actor.kind,
                actor.sprite_index,
                actor.sprite_source,
                actor.floating,
                FieldMovement(
                    map_data,
                    start=FieldPosition(actor.position.x, actor.position.y),
                    facing=(
                        Direction.DOWN
                        if actor.facing is None
                        else Direction[actor.facing.upper()]
                    ),
                    allow_blocked_start=True,
                    allow_outside_start=actor_overlaps_map(
                        actor.kind, actor.position.x, actor.position.y,
                        map_data.width, map_data.height,
                    ),
                    event_flags=event_flags,
                ),
                self._next_roam_wait() if actor.kind == "roaming" else 0,
                2 if actor.kind == "treasure" and actor.id in opened_ids else 0,
            )
            for actor in map_data.actors
        }

    def _next_roam_wait(self) -> int:
        return self._random.randint(DEFAULT_ROAM_WAIT_MIN, DEFAULT_ROAM_WAIT_MAX)

    @property
    def actors(self) -> tuple[FieldActor, ...]:
        return tuple(self._actors.values())

    @property
    def visible_actors(self) -> tuple[FieldActor, ...]:
        return tuple(
            actor for actor in self._actors.values()
            if self.map_data.is_actor_visible(actor.id, self._event_flags)
        )

    @property
    def positions(self) -> Mapping[str, MapCell]:
        return MappingProxyType(
            {
                actor.id: MapCell(actor.movement.position.x, actor.movement.position.y)
                for actor in self.visible_actors
            }
        )

    def actor(self, actor_id: str) -> FieldActor:
        try:
            return self._actors[actor_id]
        except KeyError as error:
            raise KeyError(f"unknown field actor: {actor_id}") from error

    def actor_at(self, x: int, y: int) -> FieldActor | None:
        return next(
            (
                actor
                for actor in self.visible_actors
                if actor.movement.position == FieldPosition(x, y)
            ),
            None,
        )

    def blocked_positions(self, *, excluding: str | None = None) -> tuple[FieldPosition, ...]:
        positions = (
            position
            for actor in self.visible_actors
            if actor.id != excluding
            for position in (
                actor.movement.position,
                actor.movement.destination_position,
            )
            if position is not None
        )
        return tuple(dict.fromkeys(positions))

    def stop(self, actor_id: str) -> None:
        self.actor(actor_id).movement.stop()

    def face(self, actor_id: str, direction: Direction) -> None:
        actor = self.actor(actor_id)
        if actor.kind in ("prop", "treasure"):
            raise ValueError("prop/treasure field actors cannot turn")
        actor.movement.face(direction)

    def face_toward(
        self,
        actor_id: str,
        target: FieldPosition,
    ) -> Direction | None:
        actor = self.actor(actor_id)
        if actor.kind in ("prop", "treasure"):
            return None
        actor.movement.stop()
        previous_facing = actor.movement.facing
        dx = target.x - actor.movement.position.x
        dy = target.y - actor.movement.position.y
        if (dx == 0) == (dy == 0):
            return previous_facing
        step_x = 0 if dx == 0 else (1 if dx > 0 else -1)
        step_y = 0 if dy == 0 else (1 if dy > 0 else -1)
        actor.movement.facing = next(
            direction
            for direction in Direction
            if (direction.dx, direction.dy) == (step_x, step_y)
        )
        return previous_facing

    def restore_stationary_facing(
        self,
        actor_id: str,
        facing: Direction,
    ) -> None:
        """Restore a stationary actor after a player-initiated conversation."""

        if not isinstance(facing, Direction):
            raise TypeError("restored actor facing must be a Direction")
        actor = self.actor(actor_id)
        if actor.kind != "stationary":
            raise ValueError("only stationary field actors restore their facing")
        actor.movement.stop()
        actor.movement.facing = facing

    def update(
        self,
        actor_id: str,
        direction: Direction,
        *,
        party_position: FieldPosition,
        party_destination: FieldPosition | None = None,
    ) -> bool:
        actor = self.actor(actor_id)
        if actor.kind in ("prop", "treasure"):
            raise ValueError("prop/treasure field actors cannot move")
        return actor.movement.update(
            direction,
            blocked_positions=(
                party_position,
                *((party_destination,) if party_destination is not None else ()),
                *self.blocked_positions(excluding=actor_id),
            ),
        )

    def update_roaming(
        self,
        *,
        party_position: FieldPosition,
        party_destination: FieldPosition | None = None,
        excluding: Collection[str] = (),
    ) -> None:
        """Advance autonomous actors once without storing their transient state."""

        for actor in self.visible_actors:
            actor_id = actor.id
            if actor_id in excluding:
                continue
            if actor.kind == "stationary":
                actor.movement.update(None)
                continue
            if actor.kind != "roaming":
                continue
            blockers = (
                party_position,
                *((party_destination,) if party_destination is not None else ()),
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

    def start_treasure_opening(self, actor_id: str) -> None:
        actor = self.actor(actor_id)
        if actor.kind != "treasure":
            raise ValueError("treasure animation requires a treasure actor")
        if actor.treasure_frame != 0 or actor.treasure_animation:
            raise ValueError("treasure actor is not closed")
        actor.treasure_frame = 1
        actor.treasure_animation = (2,)
        actor.treasure_animation_elapsed = 0

    def start_treasure_closing(self, actor_id: str) -> None:
        actor = self.actor(actor_id)
        if actor.kind != "treasure":
            raise ValueError("treasure animation requires a treasure actor")
        if actor.treasure_frame == 1 and actor.treasure_animation == (2,):
            actor.treasure_animation = (2, 1, 0)
            return
        if actor.treasure_frame != 2 or actor.treasure_animation:
            raise ValueError("treasure actor is not ready to close")
        actor.treasure_frame = 1
        actor.treasure_animation = (0,)
        actor.treasure_animation_elapsed = 0

    def update_treasure_animations(self) -> None:
        for actor in self.visible_actors:
            if not actor.treasure_animation:
                continue
            actor.treasure_animation_elapsed += 1
            if actor.treasure_animation_elapsed < TREASURE_ANIMATION_FRAME_COUNT:
                continue
            actor.treasure_frame = actor.treasure_animation[0]
            actor.treasure_animation = actor.treasure_animation[1:]
            actor.treasure_animation_elapsed = 0


__all__ = [
    "DEFAULT_FIELD_MOVE_SPEED",
    "DEFAULT_ROAM_WAIT_MAX",
    "DEFAULT_ROAM_WAIT_MIN",
    "TREASURE_ANIMATION_FRAME_COUNT",
    "FieldMovement",
    "FieldPosition",
    "FieldActor",
    "FieldActors",
]
