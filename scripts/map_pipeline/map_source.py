"""Validate, resolve, compile, and persist authoring-time map sources."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping, Sequence

from PIL import Image

from .tileset import (
    Diagnostic,
    TILE_SIZE,
    TRANSPARENT_RGB,
    choose_visual_choice,
    ground_stack,
    select_boundary_rule,
)


SOURCE_FORMAT_VERSION = 1
RUNTIME_FORMAT_VERSION = 1
MAX_MAP_DIMENSION = 512
MAX_ANIMATION_PERIOD = 3600
TRANSPARENT_INDEX = 1
ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
DIRECTION_OFFSETS = {
    "n": (0, -1),
    "ne": (1, -1),
    "e": (1, 0),
    "se": (1, 1),
    "s": (0, 1),
    "sw": (-1, 1),
    "w": (-1, 0),
    "nw": (-1, -1),
}


class MapSourceError(ValueError):
    """Raised when a map source cannot be resolved or compiled."""


@dataclass(frozen=True)
class CompiledMap:
    runtime: dict[str, Any]
    atlas: bytes


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _diagnostic(
    diagnostics: list[Diagnostic],
    severity: str,
    code: str,
    path: str,
    message: str,
) -> None:
    diagnostics.append(Diagnostic(severity, code, path, message))


def _valid_id(value: object) -> bool:
    return isinstance(value, str) and ID_PATTERN.fullmatch(value) is not None


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def content_hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def initial_map_source(
    map_id: str,
    tileset: Mapping[str, Any],
    profile: str,
    width: int = 32,
    height: int = 24,
) -> dict[str, Any]:
    if not _valid_id(map_id):
        raise ValueError("マップIDはlower_snake_caseで指定してください。")
    if not _is_int(width) or not _is_int(height) or width <= 0 or height <= 0:
        raise ValueError("マップ寸法は1以上の整数で指定してください。")
    grounds = tileset.get("grounds")
    if not isinstance(grounds, list) or not grounds:
        raise ValueError("タイルセットに地面定義がありません。")
    ground_ids = [ground.get("id") for ground in grounds if isinstance(ground, dict)]
    fill = "sea" if profile == "world" and "sea" in ground_ids else ground_ids[0]
    if not isinstance(fill, str):
        raise ValueError("初期地面を決定できません。")
    return {
        "format_version": SOURCE_FORMAT_VERSION,
        "map_id": map_id,
        "profile": profile,
        "tileset_id": tileset.get("tileset_id"),
        "size": [width, height],
        "visual_seed": 0,
        "grounds": [[fill for _x in range(width)] for _y in range(height)],
        "objects": [],
    }


def validate_map_source(
    data: object,
    tileset: Mapping[str, Any],
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    if not isinstance(data, dict):
        _diagnostic(diagnostics, "error", "invalid_root", "$", "マップJSONのルートはobjectである必要があります。")
        return diagnostics

    if data.get("format_version") != SOURCE_FORMAT_VERSION:
        _diagnostic(
            diagnostics,
            "error",
            "unsupported_format_version",
            "format_version",
            f"対応する制作用マップformat_versionは{SOURCE_FORMAT_VERSION}です。",
        )
    if not _valid_id(data.get("map_id")):
        _diagnostic(diagnostics, "error", "invalid_id", "map_id", "マップIDはlower_snake_caseで指定してください。")
    if data.get("tileset_id") != tileset.get("tileset_id"):
        _diagnostic(diagnostics, "error", "tileset_mismatch", "tileset_id", "起動時に読み込んだタイルセットIDと一致しません。")

    profile = data.get("profile")
    supported_profiles = tileset.get("supported_profiles")
    if not isinstance(profile, str) or not isinstance(supported_profiles, list) or profile not in supported_profiles:
        _diagnostic(diagnostics, "error", "unsupported_profile", "profile", "タイルセットが対応するprofileを指定してください。")

    size = data.get("size")
    width = height = 0
    if (
        not isinstance(size, list)
        or len(size) != 2
        or not all(_is_int(value) for value in size)
        or any(value <= 0 or value > MAX_MAP_DIMENSION for value in size)
    ):
        _diagnostic(
            diagnostics,
            "error",
            "invalid_map_size",
            "size",
            f"マップ寸法は1から{MAX_MAP_DIMENSION}までの整数2要素で指定してください。",
        )
    else:
        width, height = size

    if not _is_int(data.get("visual_seed")) or data.get("visual_seed", 0) < 0:
        _diagnostic(diagnostics, "error", "invalid_visual_seed", "visual_seed", "visual_seedは0以上の整数で指定してください。")

    ground_definitions = tileset.get("grounds")
    ground_ids = {
        ground.get("id")
        for ground in ground_definitions
        if isinstance(ground_definitions, list) and isinstance(ground, dict) and isinstance(ground.get("id"), str)
    } if isinstance(ground_definitions, list) else set()
    rows = data.get("grounds")
    rows_valid = isinstance(rows, list) and len(rows) == height
    if not rows_valid:
        _diagnostic(diagnostics, "error", "invalid_ground_rows", "grounds", "地面行数がマップの高さと一致しません。")
    elif width > 0:
        for y, row in enumerate(rows):
            if not isinstance(row, list) or len(row) != width:
                _diagnostic(diagnostics, "error", "invalid_ground_columns", f"grounds[{y}]", "地面列数がマップの幅と一致しません。")
                continue
            for x, ground_id in enumerate(row):
                if ground_id not in ground_ids:
                    _diagnostic(diagnostics, "error", "unknown_ground", f"grounds[{y}][{x}]", f"未定義の地面IDです: {ground_id}")

    if profile == "world" and rows_valid and width > 0 and height > 0 and "sea" in ground_ids:
        for y, row in enumerate(rows):
            if not isinstance(row, list) or len(row) != width:
                continue
            for x, ground_id in enumerate(row):
                if (x in (0, width - 1) or y in (0, height - 1)) and ground_id != "sea":
                    _diagnostic(diagnostics, "error", "world_edge_not_sea", f"grounds[{y}][{x}]", "ワールドマップの外周はseaである必要があります。")

    object_definitions = tileset.get("objects")
    objects_by_id = {
        item.get("id"): item
        for item in object_definitions
        if isinstance(object_definitions, list) and isinstance(item, dict) and isinstance(item.get("id"), str)
    } if isinstance(object_definitions, list) else {}
    instances = data.get("objects")
    if not isinstance(instances, list):
        _diagnostic(diagnostics, "error", "invalid_objects", "objects", "objectsは配列で指定してください。")
        return diagnostics

    instance_ids: set[str] = set()
    origins: set[tuple[int, int]] = set()
    for index, instance in enumerate(instances):
        path = f"objects[{index}]"
        if not isinstance(instance, dict):
            _diagnostic(diagnostics, "error", "invalid_object_instance", path, "オブジェクト実体はobjectで指定してください。")
            continue
        instance_id = instance.get("id")
        if not _valid_id(instance_id):
            _diagnostic(diagnostics, "error", "invalid_id", f"{path}.id", "実体IDはlower_snake_caseで指定してください。")
        elif instance_id in instance_ids:
            _diagnostic(diagnostics, "error", "duplicate_object_id", f"{path}.id", f"実体IDが重複しています: {instance_id}")
        else:
            instance_ids.add(instance_id)

        definition_id = instance.get("definition_id")
        definition = objects_by_id.get(definition_id)
        if definition is None:
            _diagnostic(diagnostics, "error", "unknown_object_definition", f"{path}.definition_id", f"未定義のオブジェクトです: {definition_id}")

        origin = instance.get("origin")
        if not isinstance(origin, list) or len(origin) != 2 or not all(_is_int(value) for value in origin):
            _diagnostic(diagnostics, "error", "invalid_object_origin", f"{path}.origin", "起点は[x, y]の整数2要素で指定してください。")
        else:
            point = (origin[0], origin[1])
            if point in origins:
                _diagnostic(diagnostics, "error", "duplicate_object_origin", f"{path}.origin", "複数のオブジェクトを同じ起点には配置できません。")
            origins.add(point)
            if definition is not None and width > 0 and height > 0:
                object_size = definition.get("size")
                if isinstance(object_size, list) and len(object_size) == 2:
                    if origin[0] < 0 or origin[1] < 0 or origin[0] + object_size[0] > width or origin[1] + object_size[1] > height:
                        _diagnostic(diagnostics, "error", "object_out_of_bounds", f"{path}.origin", "オブジェクトがマップ範囲外へはみ出しています。")
        if not _is_int(instance.get("order")):
            _diagnostic(diagnostics, "error", "invalid_object_order", f"{path}.order", "描画順は整数で指定してください。")
    return diagnostics


def _resolve_visual(
    visual: Mapping[str, Any],
    seed_parts: Sequence[object],
) -> dict[str, Any]:
    choice = choose_visual_choice(visual, seed_parts)
    frames = choice.get("frames")
    if not isinstance(frames, list) or not frames:
        raise MapSourceError("表示候補にフレームがありません。")
    tiles = [frame.get("tile") for frame in frames if isinstance(frame, dict)]
    if len(tiles) != len(frames):
        raise MapSourceError("表示フレームのチップ座標が不正です。")
    return {
        "choice_id": choice.get("id"),
        "frame_interval": visual.get("frame_interval"),
        "frames": tiles,
    }


def resolve_map(
    data: Mapping[str, Any],
    tileset: Mapping[str, Any],
) -> dict[str, Any]:
    diagnostics = validate_map_source(data, tileset)
    errors = [item for item in diagnostics if item.severity == "error"]
    if errors:
        raise MapSourceError(errors[0].message)

    width, height = data["size"]
    map_id = data["map_id"]
    visual_seed = data["visual_seed"]
    grounds = tileset["grounds"]
    grounds_by_id = {ground["id"]: ground for ground in grounds}
    stack_cache = {ground_id: ground_stack(grounds, ground_id) for ground_id in grounds_by_id}

    ground_cells: list[dict[str, Any]] = []
    for y in range(height):
        for x in range(width):
            layers = []
            for layer in stack_cache[data["grounds"][y][x]]:
                neighbors = {}
                for direction, (dx, dy) in DIRECTION_OFFSETS.items():
                    nx, ny = x + dx, y + dy
                    neighbors[direction] = (
                        0 <= nx < width
                        and 0 <= ny < height
                        and any(item["id"] == layer["id"] for item in stack_cache[data["grounds"][ny][nx]])
                    )
                rule = select_boundary_rule(layer.get("boundaries", []), neighbors)
                visual = rule["visual"] if rule is not None else layer["base_visual"]
                resolved = _resolve_visual(
                    visual,
                    [visual_seed, map_id, "ground", x, y, layer["id"], rule.get("id") if rule else "base"],
                )
                resolved["ground_id"] = layer["id"]
                resolved["rule_id"] = rule.get("id") if rule else None
                layers.append(resolved)
            ground_cells.append({"layers": layers})

    definitions = {item["id"]: item for item in tileset.get("objects", [])}
    sorted_instances = sorted(
        data["objects"],
        key=lambda item: (item["order"], item["origin"][1], item["origin"][0], item["id"]),
    )
    object_cells: list[dict[str, Any]] = []
    collision = [grounds_by_id[data["grounds"][y][x]]["collision"] == "blocked" for y in range(height) for x in range(width)]
    for instance in sorted_instances:
        definition = definitions[instance["definition_id"]]
        for cell in definition.get("cells", []):
            x = instance["origin"][0] + cell["offset"][0]
            y = instance["origin"][1] + cell["offset"][1]
            resolved_cell = {
                "instance_id": instance["id"],
                "definition_id": instance["definition_id"],
                "position": [x, y],
                "offset": cell["offset"],
                "order": instance["order"],
                "draw_group": definition.get("default_draw_group", "object"),
                "collision": cell["collision"],
            }
            if "tile" in cell:
                resolved_cell.update({"choice_id": None, "frame_interval": 1, "frames": [cell["tile"]]})
            elif isinstance(cell.get("visual"), dict):
                resolved_cell.update(_resolve_visual(
                    cell["visual"],
                    [visual_seed, map_id, "object", instance["id"], *cell["offset"]],
                ))
            else:
                resolved_cell.update({"choice_id": None, "frame_interval": 1, "frames": []})
            object_cells.append(resolved_cell)
            if cell["collision"] == "blocked":
                collision[y * width + x] = True

    return {
        "size": [width, height],
        "ground_cells": ground_cells,
        "object_cells": object_cells,
        "collision": collision,
    }


def _source_image(path: Path) -> Image.Image:
    with Image.open(path) as opened:
        image = opened.convert("RGBA")
    pixels = image.load()
    for y in range(image.height):
        for x in range(image.width):
            red, green, blue, alpha = pixels[x, y]
            if alpha == 0 or (red, green, blue) == TRANSPARENT_RGB:
                pixels[x, y] = (red, green, blue, 0)
    return image


def _crop_tile(image: Image.Image, tile: Sequence[int]) -> Image.Image:
    x, y = tile
    return image.crop((x * TILE_SIZE, y * TILE_SIZE, (x + 1) * TILE_SIZE, (y + 1) * TILE_SIZE))


def _animation_segments(layers: Sequence[Mapping[str, Any]], image: Image.Image) -> list[tuple[int, Image.Image]]:
    periods = [len(layer["frames"]) * layer["frame_interval"] for layer in layers if layer["frames"]]
    period = math.lcm(*periods) if periods else 1
    if period > MAX_ANIMATION_PERIOD:
        raise MapSourceError(f"合成後のアニメーション周期が上限{MAX_ANIMATION_PERIOD}フレームを超えます。")
    segments: list[tuple[int, Image.Image]] = []
    previous_bytes: bytes | None = None
    for tick in range(period):
        composite = Image.new("RGBA", (TILE_SIZE, TILE_SIZE), (255, 0, 128, 0))
        for layer in layers:
            frames = layer["frames"]
            if not frames:
                continue
            frame = frames[(tick // layer["frame_interval"]) % len(frames)]
            composite.alpha_composite(_crop_tile(image, frame))
        raw = composite.tobytes()
        if raw == previous_bytes:
            duration, previous = segments[-1]
            segments[-1] = (duration + 1, previous)
        else:
            segments.append((1, composite))
            previous_bytes = raw
    return segments


def _read_palette(path: Path) -> list[tuple[int, int, int]]:
    colors = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        value = raw_line.strip()
        if not value or value.startswith("//"):
            continue
        value = value.removeprefix("#")
        if not re.fullmatch(r"[0-9a-fA-F]{6}", value):
            raise MapSourceError(f"パレット色が不正です: {raw_line}")
        number = int(value, 16)
        colors.append(((number >> 16) & 255, (number >> 8) & 255, number & 255))
    if len(colors) <= TRANSPARENT_INDEX or colors[TRANSPARENT_INDEX] != TRANSPARENT_RGB:
        raise MapSourceError("パレット番号1は透過色#FF0080である必要があります。")
    return colors


def compile_map(
    data: Mapping[str, Any],
    tileset: Mapping[str, Any],
    image_path: Path,
    palette_path: Path,
) -> CompiledMap:
    resolved = resolve_map(data, tileset)
    source = _source_image(image_path)
    palette = _read_palette(palette_path)
    palette_index = {color: index for index, color in enumerate(palette)}
    atlas_tiles: list[Image.Image] = []
    atlas_indexes: dict[bytes, int] = {}

    def register(tile: Image.Image) -> int:
        raw = tile.tobytes()
        existing = atlas_indexes.get(raw)
        if existing is not None:
            return existing
        index = len(atlas_tiles)
        atlas_indexes[raw] = index
        atlas_tiles.append(tile)
        return index

    ground_tiles: list[int] = []
    animations: list[dict[str, Any]] = []
    for cell_index, cell in enumerate(resolved["ground_cells"]):
        segments = _animation_segments(cell["layers"], source)
        compiled_segments = [{"duration": duration, "tile": register(tile)} for duration, tile in segments]
        ground_tiles.append(compiled_segments[0]["tile"])
        if len(compiled_segments) > 1:
            animations.append({"target": "ground", "index": cell_index, "frames": compiled_segments})

    object_tiles = []
    for object_cell in resolved["object_cells"]:
        if not object_cell["frames"]:
            continue
        layers = [{"frames": object_cell["frames"], "frame_interval": object_cell["frame_interval"]}]
        segments = _animation_segments(layers, source)
        compiled_segments = [{"duration": duration, "tile": register(tile)} for duration, tile in segments]
        draw_index = len(object_tiles)
        object_tiles.append({
            "instance_id": object_cell["instance_id"],
            "definition_id": object_cell["definition_id"],
            "position": object_cell["position"],
            "draw_group": object_cell["draw_group"],
            "order": object_cell["order"],
            "tile": compiled_segments[0]["tile"],
        })
        if len(compiled_segments) > 1:
            animations.append({"target": "object", "index": draw_index, "frames": compiled_segments})

    if not atlas_tiles:
        atlas_tiles.append(Image.new("RGBA", (TILE_SIZE, TILE_SIZE), (255, 0, 128, 0)))
    columns = min(16, len(atlas_tiles))
    rows = math.ceil(len(atlas_tiles) / columns)
    bundle = bytearray(columns * rows * TILE_SIZE * TILE_SIZE)
    for tile_index, tile in enumerate(atlas_tiles):
        target_x = (tile_index % columns) * TILE_SIZE
        target_y = (tile_index // columns) * TILE_SIZE
        for y in range(TILE_SIZE):
            for x in range(TILE_SIZE):
                red, green, blue, alpha = tile.getpixel((x, y))
                if alpha == 0:
                    color_index = TRANSPARENT_INDEX
                elif alpha != 255:
                    raise MapSourceError("合成後のマップチップに半透明画素があります。")
                else:
                    try:
                        color_index = palette_index[(red, green, blue)]
                    except KeyError as error:
                        raise MapSourceError(f"合成後のマップチップにパレット外色#{red:02X}{green:02X}{blue:02X}があります。") from error
                atlas_x = target_x + x
                atlas_y = target_y + y
                bundle[atlas_y * columns * TILE_SIZE + atlas_x] = color_index

    width, height = data["size"]
    runtime = {
        "format_version": RUNTIME_FORMAT_VERSION,
        "map_id": data["map_id"],
        "profile": data["profile"],
        "tileset_id": data["tileset_id"],
        "source_hash": content_hash(data),
        "tileset_hash": content_hash(tileset),
        "source_image_id": tileset["source_image_id"],
        "tile_size": TILE_SIZE,
        "size": [width, height],
        "atlas": {
            "file": f"{data['map_id']}.bin",
            "pixel_format": "pyxel-palette-index-u8",
            "width": columns * TILE_SIZE,
            "height": rows * TILE_SIZE,
            "columns": columns,
            "tile_count": len(atlas_tiles),
            "sha256": hashlib.sha256(bundle).hexdigest(),
        },
        "ground_tiles": ground_tiles,
        "object_tiles": object_tiles,
        "animations": animations,
        "collision_rows": [
            "".join("1" if resolved["collision"][y * width + x] else "0" for x in range(width))
            for y in range(height)
        ],
    }
    return CompiledMap(runtime=runtime, atlas=bytes(bundle))


def load_map_source(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"マップJSONを読み込めません: {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError("マップJSONのルートはobjectである必要があります。")
    return value


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent, prefix=f".{path.name}.", delete=False) as temporary:
            temporary.write(content)
            temporary.flush()
            temporary_path = Path(temporary.name)
        temporary_path.replace(path)
    except BaseException:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def save_map_source(path: Path, data: Mapping[str, Any]) -> None:
    _atomic_write(path, (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def save_compiled_map(runtime_path: Path, compiled: CompiledMap) -> None:
    _atomic_write(runtime_path.with_suffix(".bin"), compiled.atlas)
    _atomic_write(runtime_path, (json.dumps(compiled.runtime, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
