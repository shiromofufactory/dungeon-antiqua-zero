"""Validate and persist map-chip tileset authoring metadata.

This module deliberately has no Pyxel or UI dependency. The metadata editor,
future map editor, and non-interactive checks are expected to share it.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import tempfile
from typing import Any, Iterable, Mapping, Sequence

from PIL import Image, UnidentifiedImageError


FORMAT_VERSION = 2
TILE_SIZE = 16
TRANSPARENT_RGB = (255, 0, 128)
ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
DIRECTIONS = ("n", "ne", "e", "se", "s", "sw", "w", "nw")
NEIGHBOR_STATES = frozenset(("same", "different", "any"))
GROUND_COLLISION_STATES = frozenset(("passable", "blocked"))
OBJECT_COLLISION_STATES = frozenset(("passable", "blocked", "passable_override"))
OBJECT_DRAW_GROUPS = frozenset(("object", "object_overlay", "object_foreground"))
OBJECT_DRAW_GROUP_ORDER = {
    "object": 0,
    "object_overlay": 1,
    "object_foreground": 2,
}
SUPPORTED_PROFILES = frozenset(("world", "dungeon", "town"))
SUPPORTED_IMAGE_SUFFIXES = (".png", ".gif")


@dataclass(frozen=True)
class Diagnostic:
    severity: str
    code: str
    path: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity,
            "code": self.code,
            "path": self.path,
            "message": self.message,
        }


@dataclass(frozen=True)
class ImageInfo:
    width: int
    height: int
    columns: int
    rows: int
    remainder_x: int
    remainder_y: int
    source: str

    def as_dict(self) -> dict[str, int | str]:
        return {
            "width": self.width,
            "height": self.height,
            "columns": self.columns,
            "rows": self.rows,
            "remainder_x": self.remainder_x,
            "remainder_y": self.remainder_y,
            "source": self.source,
        }


class TilesetValidationError(ValueError):
    """Raised when invalid metadata is passed to a resolving operation."""


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _diag(
    diagnostics: list[Diagnostic],
    severity: str,
    code: str,
    path: str,
    message: str,
) -> None:
    diagnostics.append(Diagnostic(severity, code, path, message))


def _validate_id(
    value: object,
    path: str,
    diagnostics: list[Diagnostic],
) -> bool:
    if not isinstance(value, str) or ID_PATTERN.fullmatch(value) is None:
        _diag(
            diagnostics,
            "error",
            "invalid_id",
            path,
            "IDは英小文字で始まるlower_snake_caseで指定してください。",
        )
        return False
    return True


def _validate_tile(
    value: object,
    path: str,
    columns: int | None,
    rows: int | None,
    diagnostics: list[Diagnostic],
) -> bool:
    if (
        not isinstance(value, list)
        or len(value) != 2
        or not all(_is_int(part) for part in value)
    ):
        _diag(
            diagnostics,
            "error",
            "invalid_tile",
            path,
            "チップ座標は[列, 行]の整数2要素で指定してください。",
        )
        return False
    column, row = value
    if column < 0 or row < 0:
        _diag(
            diagnostics,
            "error",
            "tile_out_of_bounds",
            path,
            "チップ座標に負数は指定できません。",
        )
        return False
    if columns is not None and rows is not None and (
        column >= columns or row >= rows
    ):
        _diag(
            diagnostics,
            "error",
            "tile_out_of_bounds",
            path,
            f"チップ座標[{column}, {row}]は選択可能範囲{columns}×{rows}外です。",
        )
        return False
    return True


def _validate_visual(
    value: object,
    path: str,
    columns: int | None,
    rows: int | None,
    diagnostics: list[Diagnostic],
) -> None:
    if not isinstance(value, dict):
        _diag(
            diagnostics,
            "error",
            "invalid_visual",
            path,
            "表示定義はobjectで指定してください。",
        )
        return

    interval = value.get("frame_interval")
    if not _is_int(interval) or interval <= 0:
        _diag(
            diagnostics,
            "error",
            "invalid_frame_interval",
            f"{path}.frame_interval",
            "フレーム間隔は1以上の整数で指定してください。",
        )

    choices = value.get("choices")
    if not isinstance(choices, list) or not choices:
        _diag(
            diagnostics,
            "error",
            "missing_choices",
            f"{path}.choices",
            "表示候補を1件以上設定してください。",
        )
        return

    choice_ids: set[str] = set()
    positive_weight = False
    for choice_index, choice in enumerate(choices):
        choice_path = f"{path}.choices[{choice_index}]"
        if not isinstance(choice, dict):
            _diag(
                diagnostics,
                "error",
                "invalid_choice",
                choice_path,
                "表示候補はobjectで指定してください。",
            )
            continue

        choice_id = choice.get("id")
        if _validate_id(choice_id, f"{choice_path}.id", diagnostics):
            if choice_id in choice_ids:
                _diag(
                    diagnostics,
                    "error",
                    "duplicate_choice_id",
                    f"{choice_path}.id",
                    f"表示候補IDが重複しています: {choice_id}",
                )
            choice_ids.add(choice_id)

        weight = choice.get("weight")
        if not _is_int(weight) or weight < 0:
            _diag(
                diagnostics,
                "error",
                "invalid_weight",
                f"{choice_path}.weight",
                "重みは0以上の整数で指定してください。",
            )
        elif weight > 0:
            positive_weight = True

        frames = choice.get("frames")
        if not isinstance(frames, list) or not frames:
            _diag(
                diagnostics,
                "error",
                "missing_frames",
                f"{choice_path}.frames",
                "フレームを1件以上設定してください。",
            )
            continue
        for frame_index, frame in enumerate(frames):
            frame_path = f"{choice_path}.frames[{frame_index}]"
            if not isinstance(frame, dict):
                _diag(
                    diagnostics,
                    "error",
                    "invalid_frame",
                    frame_path,
                    "フレームはobjectで指定してください。",
                )
                continue
            _validate_tile(
                frame.get("tile"),
                f"{frame_path}.tile",
                columns,
                rows,
                diagnostics,
            )

    if not positive_weight:
        _diag(
            diagnostics,
            "error",
            "zero_total_weight",
            f"{path}.choices",
            "少なくとも1件の表示候補に1以上の重みを設定してください。",
        )


def _boundary_pattern(rule: Mapping[str, Any]) -> tuple[str, ...] | None:
    neighbors = rule.get("neighbors")
    if not isinstance(neighbors, dict):
        return None
    if set(neighbors) != set(DIRECTIONS):
        return None
    pattern = tuple(neighbors[direction] for direction in DIRECTIONS)
    if not all(state in NEIGHBOR_STATES for state in pattern):
        return None
    return pattern


def _matches(pattern: Sequence[str], state: Sequence[bool]) -> bool:
    return all(
        expected == "any"
        or (expected == "same" and actual)
        or (expected == "different" and not actual)
        for expected, actual in zip(pattern, state)
    )


def _analyze_boundary_rules(
    rules: Sequence[object],
    path: str,
    diagnostics: list[Diagnostic],
) -> None:
    analyzable: list[tuple[int, str, tuple[str, ...]]] = []
    for index, raw_rule in enumerate(rules):
        if not isinstance(raw_rule, dict):
            continue
        pattern = _boundary_pattern(raw_rule)
        rule_id = raw_rule.get("id")
        if pattern is None or not isinstance(rule_id, str):
            continue
        if all(state == "any" for state in pattern):
            continue
        analyzable.append((index, rule_id, pattern))

    reached: set[int] = set()
    for mask in range(1 << len(DIRECTIONS)):
        state = tuple(bool(mask & (1 << index)) for index in range(len(DIRECTIONS)))
        for index, _rule_id, pattern in analyzable:
            if _matches(pattern, state):
                reached.add(index)
                break

    for index, rule_id, _pattern in analyzable:
        if index not in reached:
            _diag(
                diagnostics,
                "warning",
                "unreachable_boundary_rule",
                f"{path}[{index}]",
                f"境界ルール `{rule_id}` はどの周辺条件でも単独採用されません。",
            )


def _validate_ground(
    ground: object,
    index: int,
    columns: int | None,
    rows: int | None,
    diagnostics: list[Diagnostic],
) -> str | None:
    path = f"grounds[{index}]"
    if not isinstance(ground, dict):
        _diag(diagnostics, "error", "invalid_ground", path, "地面定義はobjectです。")
        return None
    ground_id = ground.get("id")
    valid_id = _validate_id(ground_id, f"{path}.id", diagnostics)
    parent_id = ground.get("parent_id")
    if parent_id is not None:
        _validate_id(parent_id, f"{path}.parent_id", diagnostics)
    if ground.get("collision") not in GROUND_COLLISION_STATES:
        _diag(
            diagnostics,
            "error",
            "invalid_collision",
            f"{path}.collision",
            "通行設定はpassableまたはblockedで指定してください。",
        )
    _validate_visual(
        ground.get("base_visual"),
        f"{path}.base_visual",
        columns,
        rows,
        diagnostics,
    )

    boundaries = ground.get("boundaries")
    if not isinstance(boundaries, list):
        _diag(
            diagnostics,
            "error",
            "invalid_boundaries",
            f"{path}.boundaries",
            "境界ルールは配列で指定してください。",
        )
        return ground_id if valid_id else None

    rule_ids: set[str] = set()
    for rule_index, rule in enumerate(boundaries):
        rule_path = f"{path}.boundaries[{rule_index}]"
        if not isinstance(rule, dict):
            _diag(
                diagnostics,
                "error",
                "invalid_boundary_rule",
                rule_path,
                "境界ルールはobjectで指定してください。",
            )
            continue
        rule_id = rule.get("id")
        if _validate_id(rule_id, f"{rule_path}.id", diagnostics):
            if rule_id in rule_ids:
                _diag(
                    diagnostics,
                    "error",
                    "duplicate_boundary_id",
                    f"{rule_path}.id",
                    f"境界ルールIDが重複しています: {rule_id}",
                )
            rule_ids.add(rule_id)
        neighbors = rule.get("neighbors")
        if not isinstance(neighbors, dict) or set(neighbors) != set(DIRECTIONS):
            _diag(
                diagnostics,
                "error",
                "invalid_neighbors",
                f"{rule_path}.neighbors",
                "周辺条件には8方向すべてを指定してください。",
            )
        elif any(value not in NEIGHBOR_STATES for value in neighbors.values()):
            _diag(
                diagnostics,
                "error",
                "invalid_neighbor_state",
                f"{rule_path}.neighbors",
                "周辺条件はsame、different、anyのいずれかです。",
            )
        elif all(value == "any" for value in neighbors.values()):
            _diag(
                diagnostics,
                "error",
                "empty_boundary_rule",
                f"{rule_path}.neighbors",
                "全方向anyの境界ルールは設定できません。",
            )
        _validate_visual(
            rule.get("visual"),
            f"{rule_path}.visual",
            columns,
            rows,
            diagnostics,
        )
    _analyze_boundary_rules(boundaries, f"{path}.boundaries", diagnostics)
    return ground_id if valid_id else None


def _validate_object(
    object_value: object,
    index: int,
    columns: int | None,
    rows: int | None,
    diagnostics: list[Diagnostic],
) -> str | None:
    path = f"objects[{index}]"
    if not isinstance(object_value, dict):
        _diag(diagnostics, "error", "invalid_object", path, "オブジェクト定義はobjectです。")
        return None
    object_id = object_value.get("id")
    valid_id = _validate_id(object_id, f"{path}.id", diagnostics)
    size = object_value.get("size")
    valid_size = (
        isinstance(size, list)
        and len(size) == 2
        and all(_is_int(part) and part > 0 for part in size)
    )
    if not valid_size:
        _diag(
            diagnostics,
            "error",
            "invalid_object_size",
            f"{path}.size",
            "オブジェクト寸法は1以上の[幅, 高さ]で指定してください。",
        )
    draw_group = object_value.get("default_draw_group")
    valid_draw_group = _validate_id(
        draw_group,
        f"{path}.default_draw_group",
        diagnostics,
    )
    if valid_draw_group and draw_group not in OBJECT_DRAW_GROUPS:
        _diag(
            diagnostics,
            "error",
            "invalid_object_draw_group",
            f"{path}.default_draw_group",
            "描画グループはobject、object_overlay、object_foregroundのいずれかで指定してください。",
        )
    cells = object_value.get("cells")
    if not isinstance(cells, list) or not cells:
        _diag(
            diagnostics,
            "error",
            "missing_object_cells",
            f"{path}.cells",
            "構成セルを1件以上設定してください。",
        )
        return object_id if valid_id else None

    offsets: set[tuple[int, int]] = set()
    object_visuals: list[tuple[str, Mapping[str, Any]]] = []
    static_visual_paths: list[str] = []
    for cell_index, cell in enumerate(cells):
        cell_path = f"{path}.cells[{cell_index}]"
        if not isinstance(cell, dict):
            _diag(
                diagnostics,
                "error",
                "invalid_object_cell",
                cell_path,
                "構成セルはobjectで指定してください。",
            )
            continue
        offset = cell.get("offset")
        valid_offset = (
            isinstance(offset, list)
            and len(offset) == 2
            and all(_is_int(part) for part in offset)
        )
        if not valid_offset:
            _diag(
                diagnostics,
                "error",
                "invalid_object_offset",
                f"{cell_path}.offset",
                "相対位置は[列, 行]の整数2要素で指定してください。",
            )
        else:
            offset_key = (offset[0], offset[1])
            if offset_key in offsets:
                _diag(
                    diagnostics,
                    "error",
                    "duplicate_object_offset",
                    f"{cell_path}.offset",
                    f"相対位置{list(offset_key)}が重複しています。",
                )
            offsets.add(offset_key)
            if valid_size and not (
                0 <= offset[0] < size[0] and 0 <= offset[1] < size[1]
            ):
                _diag(
                    diagnostics,
                    "error",
                    "object_offset_out_of_bounds",
                    f"{cell_path}.offset",
                    "相対位置がオブジェクト寸法外です。",
                )

        if cell.get("collision") not in OBJECT_COLLISION_STATES:
            _diag(
                diagnostics,
                "error",
                "invalid_collision",
                f"{cell_path}.collision",
                "オブジェクトの通行設定はpassable、blocked、passable_overrideのいずれかで指定してください。",
            )
        has_tile = "tile" in cell
        has_visual = "visual" in cell
        if has_tile and has_visual:
            _diag(
                diagnostics,
                "error",
                "multiple_cell_visuals",
                cell_path,
                "tileとvisualは同時に指定できません。",
            )
        elif has_tile:
            _validate_tile(
                cell.get("tile"),
                f"{cell_path}.tile",
                columns,
                rows,
                diagnostics,
            )
            static_visual_paths.append(cell_path)
        elif has_visual:
            _validate_visual(
                cell.get("visual"),
                f"{cell_path}.visual",
                columns,
                rows,
                diagnostics,
            )
            if isinstance(cell.get("visual"), dict):
                object_visuals.append((cell_path, cell["visual"]))
        elif cell.get("collision") in ("blocked", "passable_override"):
            collision = cell.get("collision")
            _diag(
                diagnostics,
                "warning",
                "invisible_blocked_cell" if collision == "blocked" else "invisible_passable_override_cell",
                cell_path,
                "表示なしの通行不可セルです。意図した当たり判定か確認してください。"
                if collision == "blocked"
                else "表示なしの通行可上書きセルです。意図した判定か確認してください。",
            )
        else:
            _diag(
                diagnostics,
                "warning",
                "empty_object_cell",
                cell_path,
                "表示も当たり判定もない構成セルです。",
            )

    if object_visuals:
        first_path, first_visual = object_visuals[0]
        first_choices = first_visual.get("choices")
        synchronized = any(
            isinstance(visual.get("choices"), list)
            and (
                len(visual["choices"]) > 1
                or any(
                    isinstance(choice, dict)
                    and isinstance(choice.get("frames"), list)
                    and len(choice["frames"]) > 1
                    for choice in visual["choices"]
                )
            )
            for _visual_path, visual in object_visuals
        )
        if synchronized and static_visual_paths:
            for static_path in static_visual_paths:
                _diag(
                    diagnostics,
                    "error",
                    "unsynchronized_object_visual",
                    static_path,
                    "複数候補またはアニメーションを持つオブジェクトでは、表示セルをすべて同じvisual構造にしてください。",
                )

        if synchronized and isinstance(first_choices, list):
            expected = (
                first_visual.get("frame_interval"),
                [
                    (
                        choice.get("id"),
                        choice.get("weight"),
                        len(choice.get("frames", []))
                        if isinstance(choice, dict)
                        and isinstance(choice.get("frames"), list)
                        else None,
                    )
                    for choice in first_choices
                    if isinstance(choice, dict)
                ],
            )
            for visual_path, visual in object_visuals[1:]:
                choices = visual.get("choices")
                actual = (
                    visual.get("frame_interval"),
                    [
                        (
                            choice.get("id"),
                            choice.get("weight"),
                            len(choice.get("frames", []))
                            if isinstance(choice, dict)
                            and isinstance(choice.get("frames"), list)
                            else None,
                        )
                        for choice in choices
                        if isinstance(choice, dict)
                    ]
                    if isinstance(choices, list)
                    else None,
                )
                if actual != expected:
                    _diag(
                        diagnostics,
                        "error",
                        "unsynchronized_object_visual",
                        visual_path,
                        f"オブジェクトの表示候補ID、重み、フレーム数、間隔を{first_path}.visualと揃えてください。",
                    )
    return object_id if valid_id else None


def _validate_ground_graph(
    grounds: Sequence[object],
    diagnostics: list[Diagnostic],
) -> dict[str, Mapping[str, Any]]:
    by_id: dict[str, Mapping[str, Any]] = {}
    for index, value in enumerate(grounds):
        if not isinstance(value, dict) or not isinstance(value.get("id"), str):
            continue
        ground_id = value["id"]
        if ground_id in by_id:
            _diag(
                diagnostics,
                "error",
                "duplicate_ground_id",
                f"grounds[{index}].id",
                f"地面IDが重複しています: {ground_id}",
            )
        else:
            by_id[ground_id] = value

    for index, value in enumerate(grounds):
        if not isinstance(value, dict):
            continue
        parent_id = value.get("parent_id")
        if parent_id is not None and parent_id not in by_id:
            _diag(
                diagnostics,
                "error",
                "missing_parent_ground",
                f"grounds[{index}].parent_id",
                f"親地面がありません: {parent_id}",
            )

    for ground_id in by_id:
        seen: list[str] = []
        current: str | None = ground_id
        while current is not None and current in by_id:
            if current in seen:
                cycle = " → ".join(seen[seen.index(current) :] + [current])
                _diag(
                    diagnostics,
                    "error",
                    "ground_parent_cycle",
                    f"grounds.{ground_id}.parent_id",
                    f"地面の親子関係が循環しています: {cycle}",
                )
                break
            seen.append(current)
            parent = by_id[current].get("parent_id")
            current = parent if isinstance(parent, str) else None
    return by_id


def _validate_world_profile(
    profile: object,
    grounds: Sequence[object],
    by_id: Mapping[str, Mapping[str, Any]],
    diagnostics: list[Diagnostic],
) -> None:
    if profile != "world":
        return
    first_ground_id = (
        grounds[0].get("id")
        if grounds and isinstance(grounds[0], Mapping)
        else None
    )
    if first_ground_id != "sea":
        _diag(
            diagnostics,
            "error",
            "world_base_ground_not_sea",
            "grounds[0].id",
            "world profileのベース地面（先頭地面）は`sea`である必要があります。",
        )
    expected = {
        "sea": (None, "blocked"),
        "plain": ("sea", "passable"),
        "sand": ("plain", "passable"),
    }
    for ground_id, (parent_id, collision) in expected.items():
        ground = by_id.get(ground_id)
        if ground is None:
            _diag(
                diagnostics,
                "error",
                "missing_world_ground",
                "grounds",
                f"world profileには地面 `{ground_id}` が必要です。",
            )
            continue
        if ground.get("parent_id") != parent_id:
            _diag(
                diagnostics,
                "error",
                "invalid_world_ground_parent",
                f"grounds.{ground_id}.parent_id",
                f"`{ground_id}` の親は {parent_id!r} である必要があります。",
            )
        if ground.get("collision") != collision:
            _diag(
                diagnostics,
                "error",
                "invalid_world_ground_collision",
                f"grounds.{ground_id}.collision",
                f"`{ground_id}` の通行設定は `{collision}` です。",
            )
    for ground_id in ("plain", "sand"):
        ground = by_id.get(ground_id)
        if ground is not None and ground.get("boundaries") == []:
            _diag(
                diagnostics,
                "warning",
                "missing_world_boundaries",
                f"grounds.{ground_id}.boundaries",
                f"`{ground_id}` の境界ルールがまだ設定されていません。",
            )


def _read_palette(path: Path | None) -> set[tuple[int, int, int]] | None:
    if path is None or not path.is_file():
        return None
    colors: set[tuple[int, int, int]] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        value = line.strip().removeprefix("#")
        if not value or value.startswith("//") or len(value) != 6:
            continue
        try:
            color = int(value, 16)
        except ValueError:
            continue
        colors.add(((color >> 16) & 255, (color >> 8) & 255, color & 255))
    return colors


def inspect_source_image(
    image_path: Path,
    palette_path: Path | None = None,
) -> tuple[ImageInfo | None, list[Diagnostic]]:
    diagnostics: list[Diagnostic] = []
    try:
        with Image.open(image_path) as opened:
            image = opened.convert("RGBA")
    except FileNotFoundError:
        _diag(
            diagnostics,
            "error",
            "missing_source_image",
            "source_image_id",
            f"元画像が見つかりません: {image_path}",
        )
        return None, diagnostics
    except (OSError, UnidentifiedImageError) as error:
        _diag(
            diagnostics,
            "error",
            "invalid_source_image",
            "source_image_id",
            f"元画像を読み込めません: {error}",
        )
        return None, diagnostics

    width, height = image.size
    columns, rows = width // TILE_SIZE, height // TILE_SIZE
    info = ImageInfo(
        width=width,
        height=height,
        columns=columns,
        rows=rows,
        remainder_x=width % TILE_SIZE,
        remainder_y=height % TILE_SIZE,
        source=image_path.as_posix(),
    )
    if columns == 0 or rows == 0:
        _diag(
            diagnostics,
            "error",
            "source_image_too_small",
            "source_image_id",
            "元画像には16×16pxの完全なチップがありません。",
        )

    pixels = image.load()
    margin_non_transparent = 0
    partial_alpha = 0
    colors: dict[tuple[int, int, int], int] = {}
    for y in range(height):
        for x in range(width):
            red, green, blue, alpha = pixels[x, y]
            if alpha not in (0, 255):
                partial_alpha += 1
            if alpha == 255:
                rgb = (red, green, blue)
                colors[rgb] = colors.get(rgb, 0) + 1
            if x >= columns * TILE_SIZE or y >= rows * TILE_SIZE:
                if alpha != 0 and (red, green, blue) != TRANSPARENT_RGB:
                    margin_non_transparent += 1

    if partial_alpha:
        _diag(
            diagnostics,
            "warning",
            "partial_alpha",
            "source_image_id",
            f"半透明画素が{partial_alpha:,}pxあります。画像ビルド前に修正してください。",
        )
    if margin_non_transparent:
        _diag(
            diagnostics,
            "warning",
            "non_transparent_image_margin",
            "source_image_id",
            f"選択不能な端数領域に透過色以外が{margin_non_transparent:,}pxあります。",
        )

    palette = _read_palette(palette_path)
    if palette is not None:
        outside_palette = sorted(
            ((count, rgb) for rgb, count in colors.items() if rgb not in palette),
            reverse=True,
        )
        for count, rgb in outside_palette[:8]:
            color = "#" + "".join(f"{part:02X}" for part in rgb)
            _diag(
                diagnostics,
                "warning",
                "palette_mismatch",
                "source_image_id",
                f"パレット外色 {color} が{count:,}pxあります。画像修正後に再確認してください。",
            )
        if len(outside_palette) > 8:
            _diag(
                diagnostics,
                "warning",
                "palette_mismatch_more",
                "source_image_id",
                f"ほかに{len(outside_palette) - 8}色のパレット外色があります。",
            )
    return info, diagnostics


def validate_tileset(
    data: object,
    image_path: Path | None = None,
    palette_path: Path | None = None,
) -> tuple[list[Diagnostic], ImageInfo | None]:
    diagnostics: list[Diagnostic] = []
    image_info: ImageInfo | None = None
    if image_path is not None:
        image_info, image_diagnostics = inspect_source_image(image_path, palette_path)
        diagnostics.extend(image_diagnostics)
    columns = image_info.columns if image_info else None
    rows = image_info.rows if image_info else None

    if not isinstance(data, dict):
        _diag(
            diagnostics,
            "error",
            "invalid_root",
            "$",
            "タイルセットJSONのルートはobjectである必要があります。",
        )
        return diagnostics, image_info

    if data.get("format_version") != FORMAT_VERSION:
        _diag(
            diagnostics,
            "error",
            "unsupported_format_version",
            "format_version",
            f"対応するformat_versionは{FORMAT_VERSION}です。",
        )
    _validate_id(data.get("tileset_id"), "tileset_id", diagnostics)
    source_image_id = data.get("source_image_id")
    if (
        not isinstance(source_image_id, str)
        or not source_image_id
        or source_image_id.startswith("/")
        or ".." in Path(source_image_id).parts
    ):
        _diag(
            diagnostics,
            "error",
            "invalid_source_image_id",
            "source_image_id",
            "画像IDはcontent/imagesからの拡張子なし相対パスで指定してください。",
        )
    if data.get("tile_size") != TILE_SIZE:
        _diag(
            diagnostics,
            "error",
            "invalid_tile_size",
            "tile_size",
            "チップサイズは16固定です。",
        )

    profile = data.get("profile")
    if not isinstance(profile, str) or profile not in SUPPORTED_PROFILES:
        _diag(
            diagnostics,
            "error",
            "invalid_profile",
            "profile",
            "profileはworld、dungeon、townのいずれかです。",
        )

    grounds = data.get("grounds")
    if not isinstance(grounds, list) or not grounds:
        _diag(
            diagnostics,
            "error",
            "missing_grounds",
            "grounds",
            "地面定義を1件以上設定してください。",
        )
        grounds = []
    for index, ground in enumerate(grounds):
        _validate_ground(ground, index, columns, rows, diagnostics)
    if grounds and isinstance(grounds[0], Mapping) and grounds[0].get("parent_id") is not None:
        _diag(
            diagnostics,
            "error",
            "base_ground_has_parent",
            "grounds[0].parent_id",
            "ベース地面（先頭地面）には親地面を設定できません。",
        )
    by_id = _validate_ground_graph(grounds, diagnostics)
    _validate_world_profile(profile, grounds, by_id, diagnostics)

    objects = data.get("objects")
    if not isinstance(objects, list):
        _diag(
            diagnostics,
            "error",
            "invalid_objects",
            "objects",
            "オブジェクト定義は配列で指定してください。",
        )
        objects = []
    object_ids: set[str] = set()
    for index, object_value in enumerate(objects):
        object_id = _validate_object(
            object_value,
            index,
            columns,
            rows,
            diagnostics,
        )
        if object_id is not None:
            if object_id in object_ids:
                _diag(
                    diagnostics,
                    "error",
                    "duplicate_object_id",
                    f"objects[{index}].id",
                    f"オブジェクトIDが重複しています: {object_id}",
                )
            object_ids.add(object_id)
    if profile == "world" and not objects:
        _diag(
            diagnostics,
            "warning",
            "missing_world_objects",
            "objects",
            "ワールド用の森、山、町などのオブジェクトがまだ設定されていません。",
        )
    return diagnostics, image_info


def ground_stack(
    grounds: Sequence[Mapping[str, Any]],
    ground_id: str,
) -> list[Mapping[str, Any]]:
    by_id = {ground["id"]: ground for ground in grounds if "id" in ground}
    stack: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    current: str | None = ground_id
    while current is not None:
        if current in seen:
            raise TilesetValidationError("地面の親子関係が循環しています。")
        seen.add(current)
        try:
            ground = by_id[current]
        except KeyError as error:
            raise TilesetValidationError(f"地面IDがありません: {current}") from error
        stack.append(ground)
        parent = ground.get("parent_id")
        current = parent if isinstance(parent, str) else None
    stack.reverse()
    return stack


def select_boundary_rule(
    rules: Sequence[Mapping[str, Any]],
    neighbors: Mapping[str, bool],
) -> Mapping[str, Any] | None:
    state = tuple(bool(neighbors[direction]) for direction in DIRECTIONS)
    for rule in rules:
        pattern = _boundary_pattern(rule)
        if pattern is not None and _matches(pattern, state):
            return rule
    return None


def choose_visual_choice(
    visual: Mapping[str, Any],
    seed_parts: Iterable[object],
) -> Mapping[str, Any]:
    choices = visual.get("choices")
    if not isinstance(choices, list):
        raise TilesetValidationError("表示候補がありません。")
    weighted = [
        choice
        for choice in choices
        if isinstance(choice, dict)
        and _is_int(choice.get("weight"))
        and choice["weight"] > 0
    ]
    total = sum(choice["weight"] for choice in weighted)
    if total <= 0:
        raise TilesetValidationError("表示候補の重み合計が0です。")
    encoded = json.dumps(
        list(seed_parts),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    selected = int.from_bytes(hashlib.sha256(encoded).digest(), "big") % total
    cursor = 0
    for choice in weighted:
        cursor += choice["weight"]
        if selected < cursor:
            return choice
    raise AssertionError("weighted choice resolution failed")


def resolve_source_image(content_root: Path, image_id: str) -> Path:
    if not image_id or image_id.startswith("/") or ".." in Path(image_id).parts:
        raise ValueError("不正な画像IDです。")
    images_root = (content_root / "images").resolve()
    matches = [
        (images_root / f"{image_id}{suffix}").resolve()
        for suffix in SUPPORTED_IMAGE_SUFFIXES
        if (images_root / f"{image_id}{suffix}").is_file()
    ]
    if not matches:
        raise FileNotFoundError(f"画像IDが見つかりません: {image_id}")
    if len(matches) > 1:
        raise ValueError(f"同じ画像IDのPNGとGIFが存在します: {image_id}")
    if images_root not in matches[0].parents:
        raise ValueError("画像パスがcontent/images外です。")
    return matches[0]


def _normalize_boundary_rule_order(data: Mapping[str, Any]) -> dict[str, Any]:
    """Migrate legacy numeric priorities to first-match array order."""
    normalized = deepcopy(dict(data))
    grounds = normalized.get("grounds")
    if not isinstance(grounds, list):
        return normalized
    for ground in grounds:
        if not isinstance(ground, dict):
            continue
        boundaries = ground.get("boundaries")
        if not isinstance(boundaries, list):
            continue
        if any(isinstance(rule, dict) and "priority" in rule for rule in boundaries):
            decorated = list(enumerate(boundaries))

            def legacy_order(item: tuple[int, object]) -> tuple[int, int, int]:
                index, rule = item
                if not isinstance(rule, dict):
                    return (0, 0, index)
                priority = rule.get("priority")
                pattern = _boundary_pattern(rule)
                specificity = (
                    sum(value != "any" for value in pattern)
                    if pattern is not None
                    else 0
                )
                return (
                    -(priority if _is_int(priority) else 0),
                    -specificity,
                    index,
                )

            decorated.sort(key=legacy_order)
            boundaries[:] = [rule for _index, rule in decorated]
        for rule in boundaries:
            if isinstance(rule, dict):
                rule.pop("priority", None)
    return normalized


def load_tileset(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except json.JSONDecodeError as error:
        raise ValueError(f"タイルセットJSONを読み込めません: {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError("タイルセットJSONのルートはobjectである必要があります。")
    return _normalize_boundary_rule_order(value)


def save_tileset(path: Path, data: Mapping[str, Any]) -> None:
    normalized = _normalize_boundary_rule_order(data)
    content = (json.dumps(normalized, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as temporary:
            temporary.write(content)
            temporary.flush()
            temporary_path = Path(temporary.name)
        temporary_path.replace(path)
    except BaseException:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def _single_tile_visual(column: int, row: int) -> dict[str, Any]:
    return {
        "frame_interval": 1,
        "choices": [
            {
                "id": "default",
                "weight": 1,
                "frames": [{"tile": [column, row]}],
            }
        ],
    }


def initial_worldmap_tileset() -> dict[str, Any]:
    """Return a valid minimal world tileset ready for interactive expansion."""
    return {
        "format_version": FORMAT_VERSION,
        "tileset_id": "worldmap",
        "source_image_id": "mapchips/worldmap",
        "tile_size": TILE_SIZE,
        "profile": "world",
        "grounds": [
            {
                "id": "sea",
                "parent_id": None,
                "collision": "blocked",
                "base_visual": _single_tile_visual(0, 0),
                "boundaries": [],
            },
            {
                "id": "plain",
                "parent_id": "sea",
                "collision": "passable",
                "base_visual": _single_tile_visual(1, 2),
                "boundaries": [],
            },
            {
                "id": "sand",
                "parent_id": "plain",
                "collision": "passable",
                "base_visual": _single_tile_visual(1, 5),
                "boundaries": [],
            },
        ],
        "objects": [],
    }


def initial_tileset(
    tileset_id: str,
    source_image_id: str,
    profile: str,
    base_ground_id: str,
    base_collision: str = "blocked",
) -> dict[str, Any]:
    """Return editable metadata for a new tileset with a fixed base ground."""

    if not isinstance(tileset_id, str) or ID_PATTERN.fullmatch(tileset_id) is None:
        raise ValueError("タイルセットIDはlower_snake_caseで指定してください。")
    if not isinstance(base_ground_id, str) or ID_PATTERN.fullmatch(base_ground_id) is None:
        raise ValueError("ベース地面IDはlower_snake_caseで指定してください。")
    if base_collision not in GROUND_COLLISION_STATES:
        raise ValueError("ベース地面の通行設定が不正です。")
    if not isinstance(profile, str) or profile not in SUPPORTED_PROFILES:
        raise ValueError("profileはworld、dungeon、townのいずれかです。")
    if (
        not isinstance(source_image_id, str)
        or not source_image_id
        or source_image_id.startswith("/")
        or ".." in Path(source_image_id).parts
    ):
        raise ValueError("ソース画像IDが不正です。")
    if profile == "world" and base_ground_id != "sea":
        raise ValueError("world profileのベース地面IDはseaです。")

    def ground(
        ground_id: str,
        parent_id: str | None,
        collision: str,
    ) -> dict[str, Any]:
        return {
            "id": ground_id,
            "parent_id": parent_id,
            "collision": collision,
            "base_visual": {
                "frame_interval": 1,
                "choices": [
                    {
                        "id": "default",
                        "weight": 1,
                        "frames": [{"tile": [0, 0]}],
                    }
                ],
            },
            "boundaries": [],
        }

    grounds = [ground(base_ground_id, None, base_collision)]
    if profile == "world":
        grounds.extend(
            (
                ground("plain", "sea", "passable"),
                ground("sand", "plain", "passable"),
            )
        )
    return {
        "format_version": FORMAT_VERSION,
        "tileset_id": tileset_id,
        "source_image_id": source_image_id,
        "tile_size": TILE_SIZE,
        "profile": profile,
        "grounds": grounds,
        "objects": [],
    }
