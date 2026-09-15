"""Load compiled map data and palette-index atlases for runtime use."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Mapping

import pyxel


FORMAT_VERSION = 6
PIXEL_FORMAT = "pyxel-palette-index-u8"
MAP_TILE_SIZE = 16
MAP_OBJECT_DRAW_GROUPS = frozenset(
    ("object", "object_overlay", "object_foreground")
)
MAP_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
MAP_FACINGS = frozenset(("up", "right", "down", "left"))
MAP_ACTOR_KINDS = frozenset(("prop", "stationary", "roaming", "treasure"))
MAP_ACTOR_SPRITE_SOURCES = frozenset(("npc", "pc"))
TREASURE_CONTENT_TYPES = frozenset(("gold", "item"))
MAP_EVENT_ACTIVATIONS = frozenset(("step", "touch", "interact"))
EVENT_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")


class MapResourceError(RuntimeError):
    """Raised when a compiled map resource is missing or malformed."""


@dataclass(frozen=True)
class MapAnimationFrame:
    duration: int
    tile: int


@dataclass(frozen=True)
class MapAnimation:
    frames: tuple[MapAnimationFrame, ...]

    @property
    def duration(self) -> int:
        return sum(frame.duration for frame in self.frames)

    def tile_at(self, frame_count: int) -> int:
        if isinstance(frame_count, bool) or not isinstance(frame_count, int):
            raise TypeError("map animation frame count must be an integer")
        elapsed = frame_count % self.duration
        for frame in self.frames:
            if elapsed < frame.duration:
                return frame.tile
            elapsed -= frame.duration
        raise AssertionError("map animation duration must cover every frame")


@dataclass(frozen=True)
class MapObjectTile:
    instance_id: str
    definition_id: str
    x: int
    y: int
    draw_group: str
    order: int
    tile: int


@dataclass(frozen=True)
class MapCell:
    x: int
    y: int


@dataclass(frozen=True)
class MapArrivalPoint:
    id: str
    position: MapCell
    facing: str
    teleport_enabled: bool
    site_id: str | None


@dataclass(frozen=True)
class MapTreasureContents:
    type: str
    amount: int | None = None
    item_key: str | None = None


@dataclass(frozen=True)
class MapActor:
    id: str
    position: MapCell
    kind: str
    sprite_index: int
    facing: str | None = None
    contents: MapTreasureContents | None = None
    sprite_source: str = "npc"
    floating: bool = False


@dataclass(frozen=True)
class MapEventTrigger:
    id: str
    event_id: str
    activations: frozenset[str]
    cells: tuple[MapCell, ...] = ()
    actor_id: str | None = None
    offsets: tuple[MapCell, ...] = ()


@dataclass(frozen=True)
class MapDestination:
    map_id: str
    arrival_id: str


@dataclass(frozen=True)
class WorldSite:
    id: str
    name_text_key: str
    entrance_cells: tuple[MapCell, ...]
    destination: MapDestination


@dataclass(frozen=True)
class CompiledMap:
    """Validated map data optimized for drawing and collision checks."""

    map_id: str
    profile: str
    tileset_id: str
    tile_size: int
    width: int
    height: int
    atlas: Any
    atlas_columns: int
    atlas_tile_count: int
    ground_tiles: tuple[int, ...]
    object_tiles: tuple[MapObjectTile, ...]
    collision_rows: tuple[str, ...]
    ground_animations: Mapping[int, MapAnimation]
    object_animations: Mapping[int, MapAnimation]
    sites: tuple[WorldSite, ...] = ()
    arrival_points: tuple[MapArrivalPoint, ...] = ()
    actors: tuple[MapActor, ...] = ()
    event_triggers: tuple[MapEventTrigger, ...] = ()
    event_trigger_index: Mapping[str, Mapping[tuple[int, int], MapEventTrigger]] = MappingProxyType({})
    actor_event_triggers: Mapping[str, tuple[MapEventTrigger, ...]] = MappingProxyType({})
    bgm_id: str = "da3-field"
    interact_through_rows: tuple[str, ...] = ()

    def is_blocked(self, x: int, y: int) -> bool:
        if not isinstance(x, int) or isinstance(x, bool):
            raise TypeError("map x must be an integer")
        if not isinstance(y, int) or isinstance(y, bool):
            raise TypeError("map y must be an integer")
        if x < 0 or y < 0 or x >= self.width or y >= self.height:
            return True
        return self.collision_rows[y][x] == "1"

    def allows_interaction_through(self, x: int, y: int) -> bool:
        if not isinstance(x, int) or isinstance(x, bool):
            raise TypeError("map x must be an integer")
        if not isinstance(y, int) or isinstance(y, bool):
            raise TypeError("map y must be an integer")
        if x < 0 or y < 0 or x >= self.width or y >= self.height:
            return False
        if not self.interact_through_rows:
            return False
        return self.interact_through_rows[y][x] == "1"

    def ground_tile_at(self, index: int, frame_count: int) -> int:
        animation = self.ground_animations.get(index)
        return (
            self.ground_tiles[index]
            if animation is None
            else animation.tile_at(frame_count)
        )

    def object_tile_at(self, index: int, frame_count: int) -> int:
        animation = self.object_animations.get(index)
        return (
            self.object_tiles[index].tile
            if animation is None
            else animation.tile_at(frame_count)
        )

    def arrival_point(self, arrival_id: str) -> MapArrivalPoint:
        if not isinstance(arrival_id, str) or not arrival_id:
            raise ValueError("arrival point ID must be a non-empty string")
        try:
            return next(
                arrival
                for arrival in self.arrival_points
                if arrival.id == arrival_id
            )
        except StopIteration as error:
            raise KeyError(f"unknown arrival point: {arrival_id}") from error

    def event_trigger_at(
        self,
        activation: str,
        x: int,
        y: int,
        *,
        actor_positions: Mapping[str, MapCell] | None = None,
    ) -> MapEventTrigger | None:
        """Return the sole trigger resolved for an activation and current cell."""

        if activation not in MAP_EVENT_ACTIVATIONS:
            raise ValueError(f"unsupported map event activation: {activation}")
        trigger = self.event_trigger_index.get(activation, {}).get((x, y))
        if trigger is not None:
            return trigger
        positions = {} if actor_positions is None else actor_positions
        for actor_id, triggers in self.actor_event_triggers.items():
            actor_position = positions.get(actor_id)
            if actor_position is None:
                continue
            for candidate in triggers:
                if activation not in candidate.activations:
                    continue
                if any(
                    actor_position.x + offset.x == x
                    and actor_position.y + offset.y == y
                    for offset in candidate.offsets
                ):
                    return candidate
        return None


class MapResources:
    """Own compiled map files and lazily create their Pyxel atlases."""

    def __init__(
        self,
        maps_dir: Path | None = None,
        *,
        verify: bool = True,
        pyxel_api: Any = pyxel,
    ) -> None:
        app_dir = Path(__file__).resolve().parents[1]
        self.maps_dir = (maps_dir or app_dir / "maps").resolve()
        self.verify = verify
        self._pyxel = pyxel_api
        self._cache: dict[str, CompiledMap] = {}

    def map(self, map_id: str) -> CompiledMap:
        if not isinstance(map_id, str) or MAP_ID_PATTERN.fullmatch(map_id) is None:
            raise ValueError("map ID must be lower_snake_case")
        cached = self._cache.get(map_id)
        if cached is not None:
            return cached
        loaded = self._load(map_id)
        self._cache[map_id] = loaded
        return loaded

    def map_ids(self) -> tuple[str, ...]:
        """Return compiled map IDs available in the runtime directory."""

        if not self.maps_dir.is_dir():
            return ()
        return tuple(
            path.stem
            for path in sorted(self.maps_dir.glob("*.json"))
            if MAP_ID_PATTERN.fullmatch(path.stem) is not None
        )

    def teleport_destination(self, site_id: str) -> MapDestination:
        """Find the sole teleport-enabled arrival linked to a world site."""

        if not isinstance(site_id, str) or MAP_ID_PATTERN.fullmatch(site_id) is None:
            raise ValueError("world site ID must be lower_snake_case")
        matches = [
            MapDestination(map_id, arrival.id)
            for map_id in self.map_ids()
            for arrival in self.map(map_id).arrival_points
            if arrival.teleport_enabled and arrival.site_id == site_id
        ]
        if not matches:
            raise KeyError(f"world site has no teleport arrival: {site_id}")
        if len(matches) > 1:
            raise MapResourceError(
                f"拠点{site_id}のテレポート到着地点が重複しています。"
            )
        return matches[0]

    def _load(self, map_id: str) -> CompiledMap:
        runtime_path = self.maps_dir / f"{map_id}.json"
        try:
            runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise MapResourceError(
                f"マップ生成物がありません: {runtime_path}\n"
                "npm run maps:build を実行してください。"
            ) from error
        except json.JSONDecodeError as error:
            raise MapResourceError(
                f"マップJSONを読み込めません: {runtime_path}: {error}"
            ) from error
        if not isinstance(runtime, dict):
            raise MapResourceError("マップJSONのルートはobjectである必要があります。")
        if runtime.get("format_version") != FORMAT_VERSION:
            raise MapResourceError(
                f"未対応のマップformat_versionです: {runtime.get('format_version')}"
            )
        if runtime.get("map_id") != map_id:
            raise MapResourceError("マップJSONのmap_idがファイル名と一致しません。")

        profile = self._required_id(runtime, "profile")
        tileset_id = self._required_id(runtime, "tileset_id")
        bgm_id = self._required_bgm_id(runtime, "bgm_id")
        tile_size = self._positive_integer(runtime.get("tile_size"), "tile_size")
        if tile_size != MAP_TILE_SIZE:
            raise MapResourceError(
                f"未対応のマップtile_sizeです: {tile_size}（対応値: {MAP_TILE_SIZE}）"
            )
        width, height = self._size(runtime.get("size"), "size")
        atlas_record = runtime.get("atlas")
        if not isinstance(atlas_record, dict):
            raise MapResourceError("マップJSONのatlasが不正です。")
        atlas, atlas_columns, atlas_tile_count = self._load_atlas(
            atlas_record,
            runtime_path,
            tile_size,
        )

        cell_count = width * height
        ground_tiles = self._tile_indexes(
            runtime.get("ground_tiles"),
            expected_length=cell_count,
            tile_count=atlas_tile_count,
            label="ground_tiles",
        )
        object_tiles = self._object_tiles(
            runtime.get("object_tiles"),
            width,
            height,
            atlas_tile_count,
        )
        collision_rows = self._collision_rows(
            runtime.get("collision_rows"),
            width,
            height,
        )
        interact_through_rows = self._binary_rows(
            runtime.get("interact_through_rows", ["0" * width] * height),
            width,
            height,
            "interact_through_rows",
        )
        ground_animations, object_animations = self._animations(
            runtime.get("animations"),
            cell_count,
            len(object_tiles),
            atlas_tile_count,
        )
        sites = self._sites(
            runtime.get("sites"),
            width,
            height,
            collision_rows,
        )
        arrival_points = self._arrival_points(
            runtime.get("arrival_points"),
            width,
            height,
            collision_rows,
        )
        actors = self._actors(
            runtime.get("actors"), width, height, collision_rows
        )
        event_triggers = self._event_triggers(
            runtime.get("event_triggers"), width, height, actors
        )
        static_index: dict[str, dict[tuple[int, int], MapEventTrigger]] = {
            activation: {} for activation in MAP_EVENT_ACTIVATIONS
        }
        actor_index: dict[str, list[MapEventTrigger]] = {}
        for trigger in event_triggers:
            if trigger.actor_id is None:
                for activation in trigger.activations:
                    for cell in trigger.cells:
                        key = (cell.x, cell.y)
                        if key in static_index[activation]:
                            raise MapResourceError(
                                f"event triggerが{activation}の{key}で重複しています。"
                            )
                        static_index[activation][key] = trigger
            else:
                actor_index.setdefault(trigger.actor_id, []).append(trigger)
        return CompiledMap(
            map_id=map_id,
            profile=profile,
            tileset_id=tileset_id,
            tile_size=tile_size,
            width=width,
            height=height,
            atlas=atlas,
            atlas_columns=atlas_columns,
            atlas_tile_count=atlas_tile_count,
            ground_tiles=ground_tiles,
            object_tiles=object_tiles,
            collision_rows=collision_rows,
            ground_animations=MappingProxyType(ground_animations),
            object_animations=MappingProxyType(object_animations),
            sites=sites,
            arrival_points=arrival_points,
            actors=actors,
            event_triggers=event_triggers,
            event_trigger_index=MappingProxyType(
                {
                    activation: MappingProxyType(index)
                    for activation, index in static_index.items()
                }
            ),
            actor_event_triggers=MappingProxyType(
                {actor_id: tuple(items) for actor_id, items in actor_index.items()}
            ),
            bgm_id=bgm_id,
            interact_through_rows=interact_through_rows,
        )

    @staticmethod
    def _required_id(record: Mapping[str, object], key: str) -> str:
        value = record.get(key)
        if not isinstance(value, str) or not value:
            raise MapResourceError(f"マップJSONの{key}が不正です。")
        return value

    @staticmethod
    def _required_bgm_id(record: Mapping[str, object], key: str) -> str:
        value = record.get(key)
        if not isinstance(value, str) or not value:
            raise MapResourceError(f"マップJSONの{key}が不正です。")
        relative = Path(value)
        if (
            relative.is_absolute()
            or relative.as_posix() != value
            or relative.suffix
            or any(part in ("", ".", "..") for part in relative.parts)
        ):
            raise MapResourceError(f"マップJSONの{key}が不正です。")
        return value

    @staticmethod
    def _positive_integer(value: object, label: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise MapResourceError(f"マップJSONの{label}は正の整数である必要があります。")
        return value

    @classmethod
    def _size(cls, value: object, label: str) -> tuple[int, int]:
        if not isinstance(value, list) or len(value) != 2:
            raise MapResourceError(f"マップJSONの{label}は2要素の配列である必要があります。")
        return (
            cls._positive_integer(value[0], f"{label}[0]"),
            cls._positive_integer(value[1], f"{label}[1]"),
        )

    def _load_atlas(
        self,
        record: Mapping[str, object],
        runtime_path: Path,
        tile_size: int,
    ) -> tuple[Any, int, int]:
        filename = record.get("file")
        if not isinstance(filename, str) or Path(filename).name != filename:
            raise MapResourceError("マップatlasのfileが不正です。")
        if record.get("pixel_format") != PIXEL_FORMAT:
            raise MapResourceError(
                f"未対応のマップatlas pixel_formatです: {record.get('pixel_format')}"
            )
        width = self._positive_integer(record.get("width"), "atlas.width")
        height = self._positive_integer(record.get("height"), "atlas.height")
        columns = self._positive_integer(record.get("columns"), "atlas.columns")
        tile_count = self._positive_integer(
            record.get("tile_count"), "atlas.tile_count"
        )
        if width % tile_size or height % tile_size or columns != width // tile_size:
            raise MapResourceError("マップatlasの寸法またはcolumnsが不正です。")
        if tile_count > columns * (height // tile_size):
            raise MapResourceError("マップatlasのtile_countが画像範囲を超えています。")

        atlas_path = runtime_path.parent / filename
        try:
            atlas_bytes = atlas_path.read_bytes()
        except FileNotFoundError as error:
            raise MapResourceError(f"マップatlasがありません: {atlas_path}") from error
        if len(atlas_bytes) != width * height:
            raise MapResourceError("マップatlasの画素数が寸法と一致しません。")
        if self.verify:
            expected_hash = record.get("sha256")
            actual_hash = hashlib.sha256(atlas_bytes).hexdigest()
            if not isinstance(expected_hash, str) or actual_hash != expected_hash:
                raise MapResourceError("マップatlasのSHA-256がJSONと一致しません。")

        atlas = self._pyxel.Image(width, height)
        atlas.data_ptr()[:] = atlas_bytes
        return atlas, columns, tile_count

    @staticmethod
    def _tile_indexes(
        value: object,
        *,
        expected_length: int,
        tile_count: int,
        label: str,
    ) -> tuple[int, ...]:
        if not isinstance(value, list) or len(value) != expected_length:
            raise MapResourceError(f"マップJSONの{label}の要素数が不正です。")
        if not all(
            isinstance(tile, int)
            and not isinstance(tile, bool)
            and 0 <= tile < tile_count
            for tile in value
        ):
            raise MapResourceError(f"マップJSONの{label}に不正なチップ番号があります。")
        return tuple(value)

    @classmethod
    def _object_tiles(
        cls,
        value: object,
        width: int,
        height: int,
        tile_count: int,
    ) -> tuple[MapObjectTile, ...]:
        if not isinstance(value, list):
            raise MapResourceError("マップJSONのobject_tilesは配列である必要があります。")
        loaded = []
        for index, record in enumerate(value):
            if not isinstance(record, dict):
                raise MapResourceError(f"object_tiles[{index}]が不正です。")
            position = record.get("position")
            if (
                not isinstance(position, list)
                or len(position) != 2
                or not all(
                    isinstance(item, int) and not isinstance(item, bool)
                    for item in position
                )
                or not (0 <= position[0] < width and 0 <= position[1] < height)
            ):
                raise MapResourceError(f"object_tiles[{index}].positionが不正です。")
            tile = record.get("tile")
            order = record.get("order")
            if (
                isinstance(tile, bool)
                or not isinstance(tile, int)
                or not 0 <= tile < tile_count
            ):
                raise MapResourceError(f"object_tiles[{index}].tileが不正です。")
            if isinstance(order, bool) or not isinstance(order, int):
                raise MapResourceError(f"object_tiles[{index}].orderが不正です。")
            draw_group = cls._required_id(record, "draw_group")
            if draw_group not in MAP_OBJECT_DRAW_GROUPS:
                raise MapResourceError(
                    f"object_tiles[{index}].draw_groupが不正です。"
                )
            loaded.append(
                MapObjectTile(
                    instance_id=cls._required_id(record, "instance_id"),
                    definition_id=cls._required_id(record, "definition_id"),
                    x=position[0],
                    y=position[1],
                    draw_group=draw_group,
                    order=order,
                    tile=tile,
                )
            )
        return tuple(loaded)

    @staticmethod
    def _collision_rows(
        value: object,
        width: int,
        height: int,
    ) -> tuple[str, ...]:
        return MapResources._binary_rows(value, width, height, "collision_rows")

    @staticmethod
    def _binary_rows(
        value: object,
        width: int,
        height: int,
        label: str,
    ) -> tuple[str, ...]:
        if (
            not isinstance(value, list)
            or len(value) != height
            or not all(
                isinstance(row, str)
                and len(row) == width
                and set(row) <= {"0", "1"}
                for row in value
            )
        ):
            raise MapResourceError(f"マップJSONの{label}が不正です。")
        return tuple(value)

    @classmethod
    def _sites(
        cls,
        value: object,
        width: int,
        height: int,
        collision_rows: tuple[str, ...],
    ) -> tuple[WorldSite, ...]:
        if not isinstance(value, list):
            raise MapResourceError("マップJSONのsitesは配列である必要があります。")
        loaded: list[WorldSite] = []
        site_ids: set[str] = set()
        entrance_positions: set[tuple[int, int]] = set()
        for index, record in enumerate(value):
            path = f"sites[{index}]"
            if not isinstance(record, dict):
                raise MapResourceError(f"{path}が不正です。")
            site_id = cls._stable_id(record.get("id"), f"{path}.id")
            if site_id in site_ids:
                raise MapResourceError(f"{path}.idが重複しています。")
            site_ids.add(site_id)
            name_text_key = record.get("name_text_key")
            if not isinstance(name_text_key, str) or not name_text_key:
                raise MapResourceError(f"{path}.name_text_keyが不正です。")

            entrance_records = record.get("entrance_cells")
            if not isinstance(entrance_records, list) or not entrance_records:
                raise MapResourceError(f"{path}.entrance_cellsが不正です。")
            entrance_cells = []
            site_entrances: set[tuple[int, int]] = set()
            for cell_index, cell_record in enumerate(entrance_records):
                cell = cls._map_cell(
                    cell_record,
                    width,
                    height,
                    f"{path}.entrance_cells[{cell_index}]",
                )
                point = (cell.x, cell.y)
                if point in site_entrances or point in entrance_positions:
                    raise MapResourceError(
                        f"{path}.entrance_cells[{cell_index}]が重複しています。"
                    )
                if collision_rows[cell.y][cell.x] == "1":
                    raise MapResourceError(
                        f"{path}.entrance_cells[{cell_index}]は通行できません。"
                    )
                site_entrances.add(point)
                entrance_positions.add(point)
                entrance_cells.append(cell)

            destination = cls._destination(
                record.get("destination"),
                f"{path}.destination",
            )
            loaded.append(
                WorldSite(
                    id=site_id,
                    name_text_key=name_text_key,
                    entrance_cells=tuple(entrance_cells),
                    destination=destination,
                )
            )
        return tuple(loaded)

    @classmethod
    def _arrival_points(
        cls,
        value: object,
        width: int,
        height: int,
        collision_rows: tuple[str, ...],
    ) -> tuple[MapArrivalPoint, ...]:
        if not isinstance(value, list):
            raise MapResourceError(
                "マップJSONのarrival_pointsは配列である必要があります。"
            )
        loaded = []
        arrival_ids: set[str] = set()
        for index, record in enumerate(value):
            path = f"arrival_points[{index}]"
            if not isinstance(record, dict):
                raise MapResourceError(f"{path}が不正です。")
            arrival_id = cls._stable_id(record.get("id"), f"{path}.id")
            if arrival_id in arrival_ids:
                raise MapResourceError(f"{path}.idが重複しています。")
            arrival_ids.add(arrival_id)
            position = cls._map_cell(
                record.get("position"),
                width,
                height,
                f"{path}.position",
            )
            if collision_rows[position.y][position.x] == "1":
                raise MapResourceError(f"{path}.positionは通行できません。")
            teleport_enabled = cls._boolean(
                record.get("teleport_enabled"),
                f"{path}.teleport_enabled",
            )
            site_id = cls._optional_stable_id(
                record.get("site_id"),
                f"{path}.site_id",
            )
            if teleport_enabled != (site_id is not None):
                raise MapResourceError(
                    f"{path}.site_idとteleport_enabledの組み合わせが不正です。"
                )
            loaded.append(
                MapArrivalPoint(
                    id=arrival_id,
                    position=position,
                    facing=cls._facing(record.get("facing"), f"{path}.facing"),
                    teleport_enabled=teleport_enabled,
                    site_id=site_id,
                )
            )
        return tuple(loaded)

    @classmethod
    def _actors(
        cls,
        value: object,
        width: int,
        height: int,
        collision_rows: tuple[str, ...],
    ) -> tuple[MapActor, ...]:
        if not isinstance(value, list):
            raise MapResourceError("マップJSONのactorsは配列である必要があります。")
        loaded = []
        ids: set[str] = set()
        positions: set[tuple[int, int]] = set()
        for index, record in enumerate(value):
            path = f"actors[{index}]"
            if not isinstance(record, dict):
                raise MapResourceError(f"{path}が不正です。")
            actor_id = cls._stable_id(record.get("id"), f"{path}.id")
            if actor_id in ids:
                raise MapResourceError(f"{path}.idが重複しています。")
            position = cls._map_cell(
                record.get("position"), width, height, f"{path}.position"
            )
            point = (position.x, position.y)
            if point in positions or collision_rows[position.y][position.x] == "1":
                raise MapResourceError(f"{path}.positionが配置できないセルです。")
            ids.add(actor_id)
            positions.add(point)
            kind = cls._actor_kind(record.get("kind"), f"{path}.kind")
            loaded.append(
                MapActor(
                    id=actor_id,
                    position=position,
                    kind=kind,
                    sprite_index=(
                        0
                        if kind == "treasure"
                        else cls._non_negative_integer(
                            record.get("sprite_index"), f"{path}.sprite_index"
                        )
                    ),
                    facing=cls._actor_facing(record, path),
                    contents=cls._treasure_contents(record, path),
                    sprite_source=cls._actor_sprite_source(record, path),
                    floating=cls._actor_floating(record, path),
                )
            )
        return tuple(loaded)

    @staticmethod
    def _actor_kind(value: object, label: str) -> str:
        if not isinstance(value, str) or value not in MAP_ACTOR_KINDS:
            raise MapResourceError(
                f"マップJSONの{label}はprop、stationary、roaming、treasureのいずれかである必要があります。"
            )
        return value

    @classmethod
    def _actor_facing(cls, record: Mapping[str, object], path: str) -> str | None:
        if record.get("kind") in ("prop", "treasure"):
            if "facing" in record:
                raise MapResourceError(
                    f"マップJSONの{path}.facingは固定actorに指定できません。"
                )
            return None
        return cls._facing(record.get("facing"), f"{path}.facing")

    @staticmethod
    def _actor_sprite_source(record: Mapping[str, object], path: str) -> str:
        kind = record.get("kind")
        if kind in ("prop", "treasure"):
            if "sprite_source" in record:
                raise MapResourceError(
                    f"マップJSONの{path}.sprite_sourceは人物actorだけに指定できます。"
                )
            return "npc"
        source = record.get("sprite_source", "npc")
        if source not in MAP_ACTOR_SPRITE_SOURCES:
            raise MapResourceError(
                f"マップJSONの{path}.sprite_sourceはnpcまたはpcである必要があります。"
            )
        return source

    @staticmethod
    def _actor_floating(record: Mapping[str, object], path: str) -> bool:
        if record.get("kind") in ("prop", "treasure"):
            if "floating" in record:
                raise MapResourceError(
                    f"マップJSONの{path}.floatingは人物actorだけに指定できます。"
                )
            return False
        floating = record.get("floating", False)
        if not isinstance(floating, bool):
            raise MapResourceError(
                f"マップJSONの{path}.floatingは真偽値である必要があります。"
            )
        return floating

    @classmethod
    def _treasure_contents(
        cls,
        record: Mapping[str, object],
        path: str,
    ) -> MapTreasureContents | None:
        if record.get("kind") != "treasure":
            if "contents" in record:
                raise MapResourceError(
                    f"マップJSONの{path}.contentsはtreasure actorだけに指定できます。"
                )
            return None
        if "sprite_index" in record:
            raise MapResourceError(
                f"マップJSONの{path}.sprite_indexはtreasure actorに指定できません。"
            )
        contents = record.get("contents")
        if not isinstance(contents, dict):
            raise MapResourceError(f"マップJSONの{path}.contentsが不正です。")
        content_type = contents.get("type")
        if content_type not in TREASURE_CONTENT_TYPES:
            raise MapResourceError(f"マップJSONの{path}.contents.typeが不正です。")
        if content_type == "gold":
            if set(contents) != {"type", "amount"}:
                raise MapResourceError(f"マップJSONの{path}.contentsが不正です。")
            amount = cls._positive_integer(
                contents.get("amount"), f"{path}.contents.amount"
            )
            if amount > 999_999:
                raise MapResourceError(
                    f"マップJSONの{path}.contents.amountは999999以下である必要があります。"
                )
            return MapTreasureContents("gold", amount=amount)
        if set(contents) != {"type", "item_key"}:
            raise MapResourceError(f"マップJSONの{path}.contentsが不正です。")
        item_key = contents.get("item_key")
        if not isinstance(item_key, str) or not item_key:
            raise MapResourceError(
                f"マップJSONの{path}.contents.item_keyが不正です。"
            )
        return MapTreasureContents("item", item_key=item_key)

    @staticmethod
    def _non_negative_integer(value: object, label: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise MapResourceError(f"マップJSONの{label}は0以上の整数である必要があります。")
        return value

    @classmethod
    def _event_triggers(
        cls,
        value: object,
        width: int,
        height: int,
        actors: tuple[MapActor, ...],
    ) -> tuple[MapEventTrigger, ...]:
        if not isinstance(value, list):
            raise MapResourceError(
                "マップJSONのevent_triggersは配列である必要があります。"
            )
        loaded = []
        ids: set[str] = set()
        actor_ids = {actor.id for actor in actors}
        actor_kinds = {actor.id: actor.kind for actor in actors}
        actor_trigger_counts = {
            actor.id: 0 for actor in actors if actor.kind != "treasure"
        }
        for index, record in enumerate(value):
            path = f"event_triggers[{index}]"
            if not isinstance(record, dict):
                raise MapResourceError(f"{path}が不正です。")
            trigger_id = cls._stable_id(record.get("id"), f"{path}.id")
            if trigger_id in ids:
                raise MapResourceError(f"{path}.idが重複しています。")
            ids.add(trigger_id)
            event_id = record.get("event_id")
            if not isinstance(event_id, str) or EVENT_ID_PATTERN.fullmatch(event_id) is None:
                raise MapResourceError(f"{path}.event_idが不正です。")
            activation_values = record.get("activations")
            if (
                not isinstance(activation_values, list)
                or not activation_values
                or len(activation_values) != len(set(activation_values))
                or not all(item in MAP_EVENT_ACTIVATIONS for item in activation_values)
            ):
                raise MapResourceError(f"{path}.activationsが不正です。")
            target = record.get("target")
            if not isinstance(target, dict):
                raise MapResourceError(f"{path}.targetが不正です。")
            if target.get("kind") == "cells":
                if "interact" in activation_values:
                    raise MapResourceError(
                        f"{path}.activationsのinteractはactor targetにだけ使用できます。"
                    )
                values = target.get("cells")
                if not isinstance(values, list) or not values:
                    raise MapResourceError(f"{path}.target.cellsが不正です。")
                cells = tuple(
                    cls._map_cell(cell, width, height, f"{path}.target.cells[{cell_index}]")
                    for cell_index, cell in enumerate(values)
                )
                if len(cells) != len({(cell.x, cell.y) for cell in cells}):
                    raise MapResourceError(f"{path}.target.cellsが重複しています。")
                loaded.append(
                    MapEventTrigger(
                        trigger_id,
                        event_id,
                        frozenset(activation_values),
                        cells=cells,
                    )
                )
            elif target.get("kind") == "actor":
                actor_id = cls._stable_id(
                    target.get("actor_id"), f"{path}.target.actor_id"
                )
                if actor_id not in actor_ids:
                    raise MapResourceError(f"{path}.target.actor_idが見つかりません。")
                if actor_kinds[actor_id] == "treasure":
                    raise MapResourceError(
                        f"{path}.target.actor_idにtreasure actorは指定できません。"
                    )
                actor_trigger_counts[actor_id] += 1
                if activation_values != ["touch", "interact"]:
                    raise MapResourceError(
                        f"{path}.activationsはtouch、interactの固定ペアである必要があります。"
                    )
                values = target.get("offsets")
                if values != [[0, 0]]:
                    raise MapResourceError(f"{path}.target.offsetsが不正です。")
                offsets = tuple(
                    cls._offset(cell, f"{path}.target.offsets[{cell_index}]")
                    for cell_index, cell in enumerate(values)
                )
                if len(offsets) != len({(cell.x, cell.y) for cell in offsets}):
                    raise MapResourceError(f"{path}.target.offsetsが重複しています。")
                loaded.append(
                    MapEventTrigger(
                        trigger_id,
                        event_id,
                        frozenset(activation_values),
                        actor_id=actor_id,
                        offsets=offsets,
                    )
                )
            else:
                raise MapResourceError(f"{path}.target.kindが不正です。")
        for actor_id, trigger_count in actor_trigger_counts.items():
            if trigger_count != 1:
                raise MapResourceError(
                    f"actor {actor_id}のトリガーは1件である必要があります。"
                )
        return tuple(loaded)

    @classmethod
    def _destination(cls, value: object, path: str) -> MapDestination:
        if not isinstance(value, dict):
            raise MapResourceError(f"{path}が不正です。")
        return MapDestination(
            map_id=cls._stable_id(value.get("map_id"), f"{path}.map_id"),
            arrival_id=cls._stable_id(
                value.get("arrival_id"),
                f"{path}.arrival_id",
            ),
        )

    @staticmethod
    def _stable_id(value: object, path: str) -> str:
        if not isinstance(value, str) or MAP_ID_PATTERN.fullmatch(value) is None:
            raise MapResourceError(f"{path}が不正です。")
        return value

    @staticmethod
    def _optional_stable_id(value: object, path: str) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str) or MAP_ID_PATTERN.fullmatch(value) is None:
            raise MapResourceError(f"{path}が不正です。")
        return value

    @staticmethod
    def _facing(value: object, path: str) -> str:
        if not isinstance(value, str) or value not in MAP_FACINGS:
            raise MapResourceError(f"{path}が不正です。")
        return value

    @staticmethod
    def _boolean(value: object, path: str) -> bool:
        if not isinstance(value, bool):
            raise MapResourceError(f"{path}が不正です。")
        return value

    @staticmethod
    def _map_cell(
        value: object,
        width: int,
        height: int,
        path: str,
    ) -> MapCell:
        if (
            not isinstance(value, list)
            or len(value) != 2
            or not all(
                isinstance(item, int) and not isinstance(item, bool)
                for item in value
            )
            or not (0 <= value[0] < width and 0 <= value[1] < height)
        ):
            raise MapResourceError(f"{path}が不正です。")
        return MapCell(x=value[0], y=value[1])

    @staticmethod
    def _offset(value: object, path: str) -> MapCell:
        if (
            not isinstance(value, list)
            or len(value) != 2
            or not all(
                isinstance(item, int) and not isinstance(item, bool)
                for item in value
            )
        ):
            raise MapResourceError(f"{path}が不正です。")
        return MapCell(x=value[0], y=value[1])

    @classmethod
    def _animations(
        cls,
        value: object,
        ground_count: int,
        object_count: int,
        tile_count: int,
    ) -> tuple[dict[int, MapAnimation], dict[int, MapAnimation]]:
        if not isinstance(value, list):
            raise MapResourceError("マップJSONのanimationsは配列である必要があります。")
        groups: dict[str, dict[int, MapAnimation]] = {
            "ground": {},
            "object": {},
        }
        limits = {"ground": ground_count, "object": object_count}
        for animation_index, record in enumerate(value):
            if not isinstance(record, dict) or record.get("target") not in groups:
                raise MapResourceError(f"animations[{animation_index}].targetが不正です。")
            target = record["target"]
            index = record.get("index")
            if (
                isinstance(index, bool)
                or not isinstance(index, int)
                or not 0 <= index < limits[target]
                or index in groups[target]
            ):
                raise MapResourceError(f"animations[{animation_index}].indexが不正です。")
            frame_records = record.get("frames")
            if not isinstance(frame_records, list) or not frame_records:
                raise MapResourceError(f"animations[{animation_index}].framesが不正です。")
            frames = []
            for frame_index, frame in enumerate(frame_records):
                if not isinstance(frame, dict):
                    raise MapResourceError(
                        f"animations[{animation_index}].frames[{frame_index}]が不正です。"
                    )
                duration = frame.get("duration")
                tile = frame.get("tile")
                if (
                    isinstance(duration, bool)
                    or not isinstance(duration, int)
                    or duration <= 0
                    or isinstance(tile, bool)
                    or not isinstance(tile, int)
                    or not 0 <= tile < tile_count
                ):
                    raise MapResourceError(
                        f"animations[{animation_index}].frames[{frame_index}]の値が不正です。"
                    )
                frames.append(MapAnimationFrame(duration=duration, tile=tile))
            groups[target][index] = MapAnimation(tuple(frames))
        return groups["ground"], groups["object"]


__all__ = [
    "CompiledMap",
    "MAP_ACTOR_KINDS",
    "TREASURE_CONTENT_TYPES",
    "MapArrivalPoint",
    "MapActor",
    "MapAnimation",
    "MapAnimationFrame",
    "MapCell",
    "MapDestination",
    "MapEventTrigger",
    "MAP_EVENT_ACTIVATIONS",
    "MAP_FACINGS",
    "MAP_TILE_SIZE",
    "MapObjectTile",
    "MapResourceError",
    "MapResources",
    "MapTreasureContents",
    "WorldSite",
]
