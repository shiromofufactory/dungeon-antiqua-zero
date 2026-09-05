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
    OBJECT_DRAW_GROUP_ORDER,
    TILE_SIZE,
    TRANSPARENT_RGB,
    choose_visual_choice,
    ground_stack,
    select_boundary_rule,
)


SOURCE_FORMAT_VERSION = 4
RUNTIME_FORMAT_VERSION = 4
MAX_MAP_DIMENSION = 512
MAX_ANIMATION_PERIOD = 3600
TRANSPARENT_INDEX = 1
ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
CARDINAL_FACINGS = frozenset(("up", "right", "down", "left"))
ACTOR_KINDS = frozenset(("prop", "stationary", "roaming"))
EVENT_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
EVENT_ACTIVATIONS = frozenset(("step", "touch", "interact"))
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


def _valid_point(value: object) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 2
        and all(_is_int(item) for item in value)
    )


def _point_in_bounds(point: Sequence[int], width: int, height: int) -> bool:
    return 0 <= point[0] < width and 0 <= point[1] < height


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
        "sites": [],
        "arrival_points": [],
        "actors": [],
        "event_triggers": [],
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
    valid_instances: list[tuple[int, Mapping[str, Any]]] = []
    object_origins: dict[str, tuple[int, int]] = {}
    for index, instance in enumerate(instances):
        path = f"objects[{index}]"
        if not isinstance(instance, dict):
            _diagnostic(diagnostics, "error", "invalid_object_instance", path, "オブジェクト実体はobjectで指定してください。")
            continue
        instance_id = instance.get("id")
        unique_instance_id = False
        if not _valid_id(instance_id):
            _diagnostic(diagnostics, "error", "invalid_id", f"{path}.id", "実体IDはlower_snake_caseで指定してください。")
        elif instance_id in instance_ids:
            _diagnostic(diagnostics, "error", "duplicate_object_id", f"{path}.id", f"実体IDが重複しています: {instance_id}")
        else:
            instance_ids.add(instance_id)
            unique_instance_id = True

        definition_id = instance.get("definition_id")
        definition = objects_by_id.get(definition_id)
        if definition is None:
            _diagnostic(diagnostics, "error", "unknown_object_definition", f"{path}.definition_id", f"未定義のオブジェクトです: {definition_id}")

        origin = instance.get("origin")
        valid_origin = isinstance(origin, list) and len(origin) == 2 and all(_is_int(value) for value in origin)
        if not valid_origin:
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
        valid_order = _is_int(instance.get("order"))
        if not valid_order:
            _diagnostic(diagnostics, "error", "invalid_object_order", f"{path}.order", "描画順は整数で指定してください。")
        if definition is not None and valid_origin and valid_order:
            valid_instances.append((index, instance))
            if unique_instance_id:
                object_origins[instance_id] = (origin[0], origin[1])

    blocked_by_object: set[tuple[int, int]] = set()
    collision: list[bool] | None = None
    if (
        rows_valid
        and width > 0
        and height > 0
        and all(
            isinstance(row, list)
            and len(row) == width
            and all(ground_id in ground_ids for ground_id in row)
            for row in rows
        )
    ):
        grounds_by_id = {
            ground["id"]: ground
            for ground in ground_definitions
            if isinstance(ground, dict) and isinstance(ground.get("id"), str)
        }
        collision = [
            grounds_by_id[rows[y][x]].get("collision") == "blocked"
            for y in range(height)
            for x in range(width)
        ]
    for source_index, instance in sorted(
        valid_instances,
        key=lambda item: _object_draw_key(item[1], objects_by_id),
    ):
        definition = objects_by_id[instance["definition_id"]]
        for cell_index, cell in enumerate(definition.get("cells", [])):
            if not isinstance(cell, dict):
                continue
            offset = cell.get("offset")
            if not isinstance(offset, list) or len(offset) != 2 or not all(_is_int(value) for value in offset):
                continue
            position = (instance["origin"][0] + offset[0], instance["origin"][1] + offset[1])
            if cell.get("collision") == "blocked":
                blocked_by_object.add(position)
                if collision is not None and _point_in_bounds(position, width, height):
                    collision[position[1] * width + position[0]] = True
            elif cell.get("collision") == "passable_override":
                if position not in blocked_by_object:
                    _diagnostic(
                        diagnostics,
                        "warning",
                        "passable_override_without_blocked_object",
                        f"objects[{source_index}]",
                        f"通行可上書きセル{list(position)}の下に通行不可オブジェクトがありません。",
                    )
                blocked_by_object.discard(position)
                if collision is not None and _point_in_bounds(position, width, height):
                    collision[position[1] * width + position[0]] = False

    _validate_arrival_points(
        data.get("arrival_points"),
        diagnostics,
        width,
        height,
        collision,
    )
    _validate_sites(
        data.get("sites"),
        diagnostics,
        profile,
        width,
        height,
        object_origins,
        collision,
    )
    actor_positions = _validate_actors(
        data.get("actors"),
        diagnostics,
        width,
        height,
        collision,
    )
    _validate_event_triggers(
        data.get("event_triggers"),
        diagnostics,
        width,
        height,
        object_origins,
        actor_positions,
        collision,
    )
    return diagnostics


def _validate_actors(
    value: object,
    diagnostics: list[Diagnostic],
    width: int,
    height: int,
    collision: Sequence[bool] | None,
) -> dict[str, tuple[int, int]]:
    if not isinstance(value, list):
        _diagnostic(diagnostics, "error", "invalid_actors", "actors", "actorsは配列で指定してください。")
        return {}
    actors: dict[str, tuple[int, int]] = {}
    occupied: set[tuple[int, int]] = set()
    for index, actor in enumerate(value):
        path = f"actors[{index}]"
        if not isinstance(actor, dict):
            _diagnostic(diagnostics, "error", "invalid_actor", path, "actorはobjectで指定してください。")
            continue
        actor_id = actor.get("id")
        valid_actor_id = _valid_id(actor_id)
        if not valid_actor_id:
            _diagnostic(diagnostics, "error", "invalid_actor_id", f"{path}.id", "actor IDはlower_snake_caseで指定してください。")
        elif actor_id in actors:
            _diagnostic(diagnostics, "error", "duplicate_actor_id", f"{path}.id", f"actor IDが重複しています: {actor_id}")
            valid_actor_id = False
        position = actor.get("position")
        valid_position = _valid_point(position)
        if not valid_position:
            _diagnostic(diagnostics, "error", "invalid_actor_position", f"{path}.position", "actor位置は[x, y]の整数2要素で指定してください。")
        elif not _point_in_bounds(position, width, height):
            _diagnostic(diagnostics, "error", "actor_out_of_bounds", f"{path}.position", "actorがマップ範囲外です。")
            valid_position = False
        else:
            point = (position[0], position[1])
            if collision is not None and collision[position[1] * width + position[0]]:
                _diagnostic(diagnostics, "error", "actor_on_blocked_cell", f"{path}.position", "actorは通行可能セルに置いてください。")
            if point in occupied:
                _diagnostic(diagnostics, "error", "overlapping_actors", f"{path}.position", "同じセルに複数のactorを配置できません。")
            occupied.add(point)
        kind = actor.get("kind")
        if kind not in ACTOR_KINDS:
            _diagnostic(
                diagnostics,
                "error",
                "invalid_actor_kind",
                f"{path}.kind",
                "actor kindはprop、stationary、roamingのいずれかです。",
            )
        if kind == "prop":
            if "facing" in actor:
                _diagnostic(
                    diagnostics,
                    "error",
                    "prop_actor_has_facing",
                    f"{path}.facing",
                    "prop actorは向きを持ちません。facingを省略してください。",
                )
        elif actor.get("facing") not in CARDINAL_FACINGS:
            _diagnostic(diagnostics, "error", "invalid_actor_facing", f"{path}.facing", "stationaryとroaming actorの向きはup、right、down、leftのいずれかです。")
        sprite_index = actor.get("sprite_index")
        if not _is_int(sprite_index) or sprite_index < 0:
            _diagnostic(
                diagnostics,
                "error",
                "invalid_actor_sprite_index",
                f"{path}.sprite_index",
                "sprite_indexは0以上の整数で指定してください。",
            )
        if "appearance_id" in actor:
            _diagnostic(
                diagnostics,
                "error",
                "deprecated_actor_appearance_id",
                f"{path}.appearance_id",
                "appearance_idは廃止されました。共通シート内のsprite_indexを使用してください。",
            )
        if valid_actor_id and valid_position:
            actors[actor_id] = (position[0], position[1])
    return actors


def _validate_event_triggers(
    value: object,
    diagnostics: list[Diagnostic],
    width: int,
    height: int,
    object_origins: Mapping[str, tuple[int, int]],
    actor_positions: Mapping[str, tuple[int, int]],
    collision: Sequence[bool] | None,
) -> None:
    if not isinstance(value, list):
        _diagnostic(diagnostics, "error", "invalid_event_triggers", "event_triggers", "event_triggersは配列で指定してください。")
        return
    trigger_ids: set[str] = set()
    occupied: dict[tuple[str, int, int], str] = {}
    actor_occupied: dict[tuple[str, str, int, int], str] = {}
    actor_trigger_counts = {actor_id: 0 for actor_id in actor_positions}
    for index, trigger in enumerate(value):
        path = f"event_triggers[{index}]"
        if not isinstance(trigger, dict):
            _diagnostic(diagnostics, "error", "invalid_event_trigger", path, "event triggerはobjectで指定してください。")
            continue
        trigger_id = trigger.get("id")
        if not _valid_id(trigger_id):
            _diagnostic(diagnostics, "error", "invalid_trigger_id", f"{path}.id", "trigger IDはlower_snake_caseで指定してください。")
        elif trigger_id in trigger_ids:
            _diagnostic(diagnostics, "error", "duplicate_trigger_id", f"{path}.id", f"trigger IDが重複しています: {trigger_id}")
        else:
            trigger_ids.add(trigger_id)
        event_id = trigger.get("event_id")
        if not isinstance(event_id, str) or EVENT_ID_PATTERN.fullmatch(event_id) is None:
            _diagnostic(diagnostics, "error", "invalid_event_id", f"{path}.event_id", "event_idはnamespace.local_idで指定してください。")
        activations_value = trigger.get("activations")
        activations: tuple[str, ...] = ()
        if (
            not isinstance(activations_value, list)
            or not activations_value
            or not all(item in EVENT_ACTIVATIONS for item in activations_value)
        ):
            _diagnostic(diagnostics, "error", "invalid_activations", f"{path}.activations", "activationsにはstep、touch、interactを1件以上指定してください。")
        elif len(activations_value) != len(set(activations_value)):
            _diagnostic(diagnostics, "error", "duplicate_activation", f"{path}.activations", "同じactivationを重複して指定できません。")
        else:
            activations = tuple(activations_value)

        anchor = trigger.get("anchor")
        anchor_origin: tuple[int, int] | None = None
        anchor_kind: str | None = None
        moving_actor = False
        moving_actor_id: str | None = None
        if not isinstance(anchor, dict):
            _diagnostic(diagnostics, "error", "invalid_trigger_anchor", f"{path}.anchor", "trigger anchorはobjectで指定してください。")
        elif anchor.get("kind") == "cell":
            anchor_kind = "cell"
            position = anchor.get("position")
            if not _valid_point(position) or not _point_in_bounds(position, width, height):
                _diagnostic(diagnostics, "error", "invalid_trigger_anchor_cell", f"{path}.anchor.position", "cell anchorはマップ内の[x, y]で指定してください。")
            else:
                anchor_origin = (position[0], position[1])
        elif anchor.get("kind") == "object":
            anchor_kind = "object"
            object_id = anchor.get("object_id")
            if not _valid_id(object_id) or object_id not in object_origins:
                _diagnostic(diagnostics, "error", "unknown_trigger_anchor_object", f"{path}.anchor.object_id", f"配置オブジェクトが見つかりません: {object_id}")
            else:
                anchor_origin = object_origins[object_id]
        elif anchor.get("kind") == "actor":
            anchor_kind = "actor"
            actor_id = anchor.get("actor_id")
            if not _valid_id(actor_id) or actor_id not in actor_positions:
                _diagnostic(diagnostics, "error", "unknown_trigger_anchor_actor", f"{path}.anchor.actor_id", f"actorが見つかりません: {actor_id}")
            else:
                anchor_origin = actor_positions[actor_id]
                moving_actor = True
                moving_actor_id = actor_id
                actor_trigger_counts[actor_id] += 1
        else:
            _diagnostic(diagnostics, "error", "invalid_trigger_anchor_kind", f"{path}.anchor.kind", "anchor kindはcell、object、actorのいずれかです。")

        if anchor_kind == "actor":
            if activations_value != ["touch", "interact"]:
                _diagnostic(
                    diagnostics,
                    "error",
                    "invalid_actor_trigger_activations",
                    f"{path}.activations",
                    "actor triggerのactivationsはtouch、interactの固定ペアで指定してください。",
                )
        elif anchor_kind in ("cell", "object") and "interact" in activations:
            _diagnostic(
                diagnostics,
                "error",
                "interact_requires_actor_anchor",
                f"{path}.activations",
                "interactはactorアンカーの自動トリガーにだけ使用できます。",
            )

        offsets = trigger.get("offsets")
        if not isinstance(offsets, list) or not offsets:
            _diagnostic(diagnostics, "error", "invalid_trigger_offsets", f"{path}.offsets", "offsetsは[x, y]を1件以上含む配列で指定してください。")
            continue
        if anchor_kind == "actor" and offsets != [[0, 0]]:
            _diagnostic(
                diagnostics,
                "error",
                "invalid_actor_trigger_offsets",
                f"{path}.offsets",
                "actor triggerのoffsetsは[[0, 0]]に固定してください。",
            )
        seen_offsets: set[tuple[int, int]] = set()
        for offset_index, offset in enumerate(offsets):
            offset_path = f"{path}.offsets[{offset_index}]"
            if not _valid_point(offset):
                _diagnostic(diagnostics, "error", "invalid_trigger_offset", offset_path, "offsetは[x, y]の整数2要素で指定してください。")
                continue
            offset_point = (offset[0], offset[1])
            if offset_point in seen_offsets:
                _diagnostic(diagnostics, "error", "duplicate_trigger_offset", offset_path, "同じoffsetが重複しています。")
                continue
            seen_offsets.add(offset_point)
            if anchor_origin is None:
                continue
            position = (anchor_origin[0] + offset[0], anchor_origin[1] + offset[1])
            if not _point_in_bounds(position, width, height):
                _diagnostic(diagnostics, "error", "trigger_cell_out_of_bounds", offset_path, f"triggerセル{list(position)}がマップ範囲外です。")
                continue
            if "step" in activations and collision is not None and collision[position[1] * width + position[0]]:
                _diagnostic(diagnostics, "error", "step_trigger_on_blocked_cell", offset_path, "step triggerは通行可能セルに置いてください。")
            if moving_actor:
                if moving_actor_id is not None:
                    for activation in activations:
                        key = (moving_actor_id, activation, *offset_point)
                        previous = actor_occupied.get(key)
                        if previous is not None:
                            _diagnostic(
                                diagnostics,
                                "error",
                                "overlapping_event_trigger",
                                offset_path,
                                f"{activation} triggerが{previous}と同じactor offsetで重複しています。",
                            )
                        elif isinstance(trigger_id, str):
                            actor_occupied[key] = trigger_id
                continue
            for activation in activations:
                key = (activation, *position)
                previous = occupied.get(key)
                if previous is not None:
                    _diagnostic(diagnostics, "error", "overlapping_event_trigger", offset_path, f"{activation} triggerが{previous}と同じセルで重複しています。")
                elif isinstance(trigger_id, str):
                    occupied[key] = trigger_id

    for actor_id, trigger_count in actor_trigger_counts.items():
        if trigger_count == 0:
            _diagnostic(
                diagnostics,
                "error",
                "missing_actor_trigger",
                "event_triggers",
                f"actorに対するtouch・interact triggerがありません: {actor_id}",
            )
        elif trigger_count > 1:
            _diagnostic(
                diagnostics,
                "error",
                "multiple_actor_triggers",
                "event_triggers",
                f"actorに対するtriggerは1件だけ指定できます: {actor_id}",
            )


def _validate_arrival_points(
    value: object,
    diagnostics: list[Diagnostic],
    width: int,
    height: int,
    collision: Sequence[bool] | None,
) -> None:
    if not isinstance(value, list):
        _diagnostic(
            diagnostics,
            "error",
            "invalid_arrival_points",
            "arrival_points",
            "arrival_pointsは配列で指定してください。",
        )
        return

    arrival_ids: set[str] = set()
    for index, arrival in enumerate(value):
        path = f"arrival_points[{index}]"
        if not isinstance(arrival, dict):
            _diagnostic(
                diagnostics,
                "error",
                "invalid_arrival_point",
                path,
                "到着地点はobjectで指定してください。",
            )
            continue
        arrival_id = arrival.get("id")
        if not _valid_id(arrival_id):
            _diagnostic(
                diagnostics,
                "error",
                "invalid_id",
                f"{path}.id",
                "到着地点IDはlower_snake_caseで指定してください。",
            )
        elif arrival_id in arrival_ids:
            _diagnostic(
                diagnostics,
                "error",
                "duplicate_arrival_point_id",
                f"{path}.id",
                f"到着地点IDが重複しています: {arrival_id}",
            )
        else:
            arrival_ids.add(arrival_id)

        position = arrival.get("position")
        if not _valid_point(position):
            _diagnostic(
                diagnostics,
                "error",
                "invalid_arrival_point_position",
                f"{path}.position",
                "到着地点は[x, y]の整数2要素で指定してください。",
            )
        elif not _point_in_bounds(position, width, height):
            _diagnostic(
                diagnostics,
                "error",
                "arrival_point_out_of_bounds",
                f"{path}.position",
                "到着地点がマップ範囲外です。",
            )
        elif collision is not None and collision[position[1] * width + position[0]]:
            _diagnostic(
                diagnostics,
                "error",
                "arrival_point_blocked",
                f"{path}.position",
                "到着地点は通行可能セルに置いてください。",
            )

        if arrival.get("facing") not in CARDINAL_FACINGS:
            _diagnostic(
                diagnostics,
                "error",
                "invalid_facing",
                f"{path}.facing",
                "向きはup、right、down、leftのいずれかで指定してください。",
            )
        teleport_enabled = arrival.get("teleport_enabled")
        if not isinstance(teleport_enabled, bool):
            _diagnostic(
                diagnostics,
                "error",
                "invalid_arrival_teleport_enabled",
                f"{path}.teleport_enabled",
                "テレポート対象フラグはbooleanで指定してください。",
            )
        site_id = arrival.get("site_id")
        if teleport_enabled is True and not _valid_id(site_id):
            _diagnostic(
                diagnostics,
                "error",
                "invalid_arrival_site_id",
                f"{path}.site_id",
                "テレポート対象の到着地点には対応する拠点IDを指定してください。",
            )
        elif teleport_enabled is False and site_id is not None:
            _diagnostic(
                diagnostics,
                "error",
                "unexpected_arrival_site_id",
                f"{path}.site_id",
                "テレポート対象でない到着地点には拠点IDを指定できません。",
            )


def _validate_sites(
    value: object,
    diagnostics: list[Diagnostic],
    profile: object,
    width: int,
    height: int,
    object_origins: Mapping[str, tuple[int, int]],
    collision: Sequence[bool] | None,
) -> None:
    if not isinstance(value, list):
        _diagnostic(
            diagnostics,
            "error",
            "invalid_sites",
            "sites",
            "sitesは配列で指定してください。",
        )
        return
    if value and profile != "world":
        _diagnostic(
            diagnostics,
            "error",
            "sites_require_world_profile",
            "sites",
            "拠点はworld profileのマップにだけ配置できます。",
        )

    site_ids: set[str] = set()
    occupied_entrances: dict[tuple[int, int], str] = {}
    for index, site in enumerate(value):
        path = f"sites[{index}]"
        if not isinstance(site, dict):
            _diagnostic(
                diagnostics,
                "error",
                "invalid_site",
                path,
                "拠点はobjectで指定してください。",
            )
            continue

        site_id = site.get("id")
        if not _valid_id(site_id):
            _diagnostic(
                diagnostics,
                "error",
                "invalid_id",
                f"{path}.id",
                "拠点IDはlower_snake_caseで指定してください。",
            )
        elif site_id in site_ids:
            _diagnostic(
                diagnostics,
                "error",
                "duplicate_site_id",
                f"{path}.id",
                f"拠点IDが重複しています: {site_id}",
            )
        else:
            site_ids.add(site_id)

        if "name_text_key" in site:
            _diagnostic(
                diagnostics,
                "error",
                "site_name_text_key_is_automatic",
                f"{path}.name_text_key",
                "拠点名の文言キーは拠点IDから自動生成されるため指定できません。",
            )
        if "teleport_destination" in site:
            _diagnostic(
                diagnostics,
                "error",
                "deprecated_teleport_destination",
                f"{path}.teleport_destination",
                "移動先はdestinationだけで指定してください。",
            )

        anchor_origin = _validate_site_anchor(
            site.get("anchor"),
            diagnostics,
            f"{path}.anchor",
            width,
            height,
            object_origins,
        )

        offsets = site.get("entrance_offsets")
        if not isinstance(offsets, list) or not offsets:
            _diagnostic(
                diagnostics,
                "error",
                "invalid_site_entrances",
                f"{path}.entrance_offsets",
                "入口セルを1つ以上指定してください。",
            )
        else:
            seen_offsets: set[tuple[int, int]] = set()
            for offset_index, offset in enumerate(offsets):
                offset_path = f"{path}.entrance_offsets[{offset_index}]"
                if not _valid_point(offset):
                    _diagnostic(
                        diagnostics,
                        "error",
                        "invalid_site_entrance_offset",
                        offset_path,
                        "入口オフセットは[x, y]の整数2要素で指定してください。",
                    )
                    continue
                offset_point = (offset[0], offset[1])
                if offset_point in seen_offsets:
                    _diagnostic(
                        diagnostics,
                        "error",
                        "duplicate_site_entrance_offset",
                        offset_path,
                        "同じ入口オフセットが重複しています。",
                    )
                    continue
                seen_offsets.add(offset_point)
                if anchor_origin is not None:
                    position = (
                        anchor_origin[0] + offset[0],
                        anchor_origin[1] + offset[1],
                    )
                    _validate_site_cell(
                        position,
                        diagnostics,
                        offset_path,
                        "入口",
                        width,
                        height,
                        collision,
                    )
                    previous_site = occupied_entrances.get(position)
                    if previous_site is not None:
                        _diagnostic(
                            diagnostics,
                            "error",
                            "overlapping_site_entrance",
                            offset_path,
                            f"入口セル{list(position)}は拠点{previous_site}と重複しています。",
                        )
                    elif isinstance(site_id, str):
                        occupied_entrances[position] = site_id

        _validate_destination(
            site.get("destination"),
            diagnostics,
            f"{path}.destination",
            "移動先",
        )


def _validate_destination(
    value: object,
    diagnostics: list[Diagnostic],
    path: str,
    label: str,
) -> None:
    if not isinstance(value, dict):
        _diagnostic(
            diagnostics,
            "error",
            "invalid_destination",
            path,
            f"{label}はobjectで指定してください。",
        )
        return
    for key, field_label in (
        ("map_id", "マップID"),
        ("arrival_id", "到着地点ID"),
    ):
        field_value = value.get(key)
        if field_value in (None, ""):
            _diagnostic(
                diagnostics,
                "error",
                f"missing_destination_{key}",
                f"{path}.{key}",
                f"{label}{field_label.removesuffix('ID')}を選択してください。",
            )
        elif not _valid_id(field_value):
            _diagnostic(
                diagnostics,
                "error",
                f"invalid_destination_{key}",
                f"{path}.{key}",
                f"{label}{field_label}が不正です。一覧から選択し直してください。",
            )


def _validate_site_anchor(
    value: object,
    diagnostics: list[Diagnostic],
    path: str,
    width: int,
    height: int,
    object_origins: Mapping[str, tuple[int, int]],
) -> tuple[int, int] | None:
    if not isinstance(value, dict):
        _diagnostic(
            diagnostics,
            "error",
            "invalid_site_anchor",
            path,
            "拠点アンカーはobjectで指定してください。",
        )
        return None
    kind = value.get("kind")
    if kind == "object":
        object_id = value.get("object_id")
        if not _valid_id(object_id) or object_id not in object_origins:
            _diagnostic(
                diagnostics,
                "error",
                "unknown_site_anchor_object",
                f"{path}.object_id",
                f"アンカーにする配置オブジェクトが見つかりません: {object_id}",
            )
            return None
        return object_origins[object_id]
    if kind == "cell":
        position = value.get("position")
        if not _valid_point(position):
            _diagnostic(
                diagnostics,
                "error",
                "invalid_site_anchor_position",
                f"{path}.position",
                "座標アンカーは[x, y]の整数2要素で指定してください。",
            )
            return None
        if not _point_in_bounds(position, width, height):
            _diagnostic(
                diagnostics,
                "error",
                "site_anchor_out_of_bounds",
                f"{path}.position",
                "座標アンカーがマップ範囲外です。",
            )
            return None
        return position[0], position[1]
    _diagnostic(
        diagnostics,
        "error",
        "invalid_site_anchor_kind",
        f"{path}.kind",
        "拠点アンカー種別はobjectまたはcellで指定してください。",
    )
    return None


def _validate_site_cell(
    position: tuple[int, int],
    diagnostics: list[Diagnostic],
    path: str,
    label: str,
    width: int,
    height: int,
    collision: Sequence[bool] | None,
) -> None:
    if not _point_in_bounds(position, width, height):
        _diagnostic(
            diagnostics,
            "error",
            "site_cell_out_of_bounds",
            path,
            f"{label}セル{list(position)}がマップ範囲外です。",
        )
    elif collision is not None and collision[position[1] * width + position[0]]:
        _diagnostic(
            diagnostics,
            "error",
            "site_cell_blocked",
            path,
            f"{label}セル{list(position)}は通行できません。",
        )


def validate_map_links(
    sources: Mapping[str, Mapping[str, Any]],
) -> list[Diagnostic]:
    """Validate stable site IDs and destinations across map source files."""

    if not isinstance(sources, Mapping):
        raise TypeError("map sources must be a mapping")
    diagnostics: list[Diagnostic] = []
    site_occurrences: dict[str, list[tuple[str, int]]] = {}
    for map_id, source in sources.items():
        sites = source.get("sites")
        if not isinstance(sites, list):
            continue
        for index, site in enumerate(sites):
            if not isinstance(site, Mapping):
                continue
            site_id = site.get("id")
            if isinstance(site_id, str):
                site_occurrences.setdefault(site_id, []).append((map_id, index))

            destination = site.get("destination")
            if not isinstance(destination, Mapping):
                continue
            destination_map_id = destination.get("map_id")
            destination_arrival_id = destination.get("arrival_id")
            if not _valid_id(destination_map_id) or not _valid_id(
                destination_arrival_id
            ):
                continue
            target = sources.get(destination_map_id)
            if target is None:
                _diagnostic(
                    diagnostics,
                    "warning",
                    "missing_destination_map",
                    f"{map_id}.sites[{index}].destination.map_id",
                    f"遷移先マップはまだ作成されていません: {destination_map_id}",
                )
                continue
            arrival_points = target.get("arrival_points")
            if not isinstance(arrival_points, list):
                continue
            arrival_ids = {
                arrival.get("id")
                for arrival in arrival_points
                if isinstance(arrival, Mapping)
            }
            if destination_arrival_id not in arrival_ids:
                _diagnostic(
                    diagnostics,
                    "error",
                    "missing_destination_arrival",
                    f"{map_id}.sites[{index}].destination.arrival_id",
                    f"マップ{destination_map_id}に到着地点{destination_arrival_id}がありません。",
                )

    teleport_arrivals: dict[str, list[tuple[str, int]]] = {}
    for map_id, source in sources.items():
        arrival_points = source.get("arrival_points")
        if not isinstance(arrival_points, list):
            continue
        for index, arrival in enumerate(arrival_points):
            if not isinstance(arrival, Mapping) or arrival.get("teleport_enabled") is not True:
                continue
            site_id = arrival.get("site_id")
            if not isinstance(site_id, str):
                continue
            teleport_arrivals.setdefault(site_id, []).append((map_id, index))
            if site_id not in site_occurrences:
                _diagnostic(
                    diagnostics,
                    "error",
                    "unknown_arrival_site_id",
                    f"{map_id}.arrival_points[{index}].site_id",
                    f"テレポート対象に対応する拠点がありません: {site_id}",
                )
    for site_id, occurrences in teleport_arrivals.items():
        if len(occurrences) <= 1:
            continue
        for map_id, index in occurrences:
            _diagnostic(
                diagnostics,
                "error",
                "duplicate_site_teleport_arrival",
                f"{map_id}.arrival_points[{index}].site_id",
                f"拠点{site_id}のテレポート到着地点が重複しています。",
            )
    for site_id, occurrences in site_occurrences.items():
        owner_maps = {map_id for map_id, _index in occurrences}
        if len(owner_maps) <= 1:
            continue
        for map_id, index in occurrences:
            other_maps = sorted(owner_maps - {map_id})
            _diagnostic(
                diagnostics,
                "error",
                "duplicate_global_site_id",
                f"{map_id}.sites[{index}].id",
                f"拠点IDはマップ{', '.join(other_maps)}でも使用されています: {site_id}",
            )
    return diagnostics


def validate_map_event_links(
    sources: Mapping[str, Mapping[str, Any]],
    events: Mapping[str, Mapping[str, Any]],
) -> list[Diagnostic]:
    """Reject missing events and actor commands invalid for their trigger maps."""

    if not isinstance(sources, Mapping):
        raise TypeError("map sources must be a mapping")
    if not isinstance(events, Mapping) or not all(
        isinstance(event_id, str) and isinstance(event, Mapping)
        for event_id, event in events.items()
    ):
        raise TypeError("events must map event IDs to definitions")
    diagnostics: list[Diagnostic] = []
    checked_actor_links: set[tuple[str, str, str]] = set()
    for map_id, source in sources.items():
        actor_kinds = {
            actor.get("id"): actor.get("kind")
            for actor in source.get("actors", [])
            if isinstance(actor, Mapping) and isinstance(actor.get("id"), str)
        }
        triggers = source.get("event_triggers")
        if not isinstance(triggers, list):
            continue
        for index, trigger in enumerate(triggers):
            if not isinstance(trigger, Mapping):
                continue
            event_id = trigger.get("event_id")
            if (
                isinstance(event_id, str)
                and EVENT_ID_PATTERN.fullmatch(event_id) is not None
                and event_id not in events
            ):
                _diagnostic(
                    diagnostics,
                    "error",
                    "unknown_event_id",
                    f"{map_id}.event_triggers[{index}].event_id",
                    f"イベント定義が見つかりません: {event_id}",
                )
                continue
            if not isinstance(event_id, str) or event_id not in events:
                continue
            commands = events[event_id].get("commands")
            for actor_id in _moved_actor_ids(commands):
                link = (map_id, event_id, actor_id)
                if actor_id in actor_kinds:
                    if actor_kinds[actor_id] == "prop" and link not in checked_actor_links:
                        checked_actor_links.add(link)
                        _diagnostic(
                            diagnostics,
                            "error",
                            "immovable_event_actor",
                            f"{map_id}.event_triggers[{index}].event_id",
                            f"イベント{event_id}は向きのないprop actorを移動できません: {actor_id}",
                        )
                    continue
                if link in checked_actor_links:
                    continue
                checked_actor_links.add(link)
                _diagnostic(
                    diagnostics,
                    "error",
                    "unknown_event_actor_id",
                    f"{map_id}.event_triggers[{index}].event_id",
                    f"イベント{event_id}が参照するactorがこのマップにありません: {actor_id}",
                )
    return diagnostics


def _moved_actor_ids(commands: object) -> set[str]:
    actor_ids: set[str] = set()
    if not isinstance(commands, (list, tuple)):
        return actor_ids
    for command in commands:
        if not isinstance(command, Mapping):
            continue
        if command.get("command") == "move_actor" and isinstance(
            command.get("actor_id"), str
        ):
            actor_ids.add(command["actor_id"])
        if command.get("command") == "branch":
            actor_ids.update(_moved_actor_ids(command.get("then")))
            actor_ids.update(_moved_actor_ids(command.get("else")))
    return actor_ids


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


def _object_draw_key(
    instance: Mapping[str, Any],
    definitions: Mapping[str, Mapping[str, Any]],
) -> tuple[int, int, int, int, str]:
    """Sort back-to-front by draw group, lower edge, and stable tie breakers."""
    definition = definitions[instance["definition_id"]]
    draw_group = definition.get("default_draw_group", "object")
    group_order = OBJECT_DRAW_GROUP_ORDER.get(draw_group, 0)
    bottom_y = instance["origin"][1] + definition["size"][1] - 1
    return group_order, bottom_y, instance["order"], instance["origin"][0], instance["id"]


def _site_anchor_origin(
    site: Mapping[str, Any],
    instances: Mapping[str, Mapping[str, Any]],
) -> tuple[int, int]:
    anchor = site["anchor"]
    if anchor["kind"] == "object":
        origin = instances[anchor["object_id"]]["origin"]
    else:
        origin = anchor["position"]
    return origin[0], origin[1]


def _resolve_event_triggers(
    triggers: Sequence[Mapping[str, Any]],
    instances: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    resolved = []
    for trigger in triggers:
        anchor = trigger["anchor"]
        if anchor["kind"] == "actor":
            target = {
                "kind": "actor",
                "actor_id": anchor["actor_id"],
                "offsets": [list(offset) for offset in trigger["offsets"]],
            }
        else:
            if anchor["kind"] == "object":
                origin = instances[anchor["object_id"]]["origin"]
            else:
                origin = anchor["position"]
            target = {
                "kind": "cells",
                "cells": [
                    [origin[0] + offset[0], origin[1] + offset[1]]
                    for offset in trigger["offsets"]
                ],
            }
        resolved.append(
            {
                "id": trigger["id"],
                "event_id": trigger["event_id"],
                "activations": list(trigger["activations"]),
                "target": target,
            }
        )
    return resolved


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
    instances_by_id = {item["id"]: item for item in data["objects"]}
    sorted_instances = sorted(
        data["objects"],
        key=lambda item: _object_draw_key(item, definitions),
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
            elif cell["collision"] == "passable_override":
                collision[y * width + x] = False

    resolved_sites = []
    for site in data["sites"]:
        anchor_x, anchor_y = _site_anchor_origin(site, instances_by_id)
        resolved_sites.append({
            "id": site["id"],
            "name_text_key": f"location.{site['id']}",
            "entrance_cells": [
                [anchor_x + offset[0], anchor_y + offset[1]]
                for offset in site["entrance_offsets"]
            ],
            "destination": dict(site["destination"]),
        })

    return {
        "size": [width, height],
        "ground_cells": ground_cells,
        "object_cells": object_cells,
        "collision": collision,
        "sites": resolved_sites,
        "arrival_points": [
            dict(arrival) for arrival in data["arrival_points"]
        ],
        "actors": [dict(actor) for actor in data["actors"]],
        "event_triggers": _resolve_event_triggers(
            data["event_triggers"], instances_by_id
        ),
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
        "sites": resolved["sites"],
        "arrival_points": resolved["arrival_points"],
        "actors": resolved["actors"],
        "event_triggers": resolved["event_triggers"],
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
