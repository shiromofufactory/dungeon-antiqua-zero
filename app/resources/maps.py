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


FORMAT_VERSION = 1
PIXEL_FORMAT = "pyxel-palette-index-u8"
MAP_TILE_SIZE = 16
MAP_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


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

    def is_blocked(self, x: int, y: int) -> bool:
        if not isinstance(x, int) or isinstance(x, bool):
            raise TypeError("map x must be an integer")
        if not isinstance(y, int) or isinstance(y, bool):
            raise TypeError("map y must be an integer")
        if x < 0 or y < 0 or x >= self.width or y >= self.height:
            return True
        return self.collision_rows[y][x] == "1"

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
        ground_animations, object_animations = self._animations(
            runtime.get("animations"),
            cell_count,
            len(object_tiles),
            atlas_tile_count,
        )
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
        )

    @staticmethod
    def _required_id(record: Mapping[str, object], key: str) -> str:
        value = record.get(key)
        if not isinstance(value, str) or not value:
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
            loaded.append(
                MapObjectTile(
                    instance_id=cls._required_id(record, "instance_id"),
                    definition_id=cls._required_id(record, "definition_id"),
                    x=position[0],
                    y=position[1],
                    draw_group=cls._required_id(record, "draw_group"),
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
            raise MapResourceError("マップJSONのcollision_rowsが不正です。")
        return tuple(value)

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
    "MapAnimation",
    "MapAnimationFrame",
    "MAP_TILE_SIZE",
    "MapObjectTile",
    "MapResourceError",
    "MapResources",
]
