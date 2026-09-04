#!/usr/bin/env python3
"""Validate tilesets and authoring-time map sources without starting editors."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

from map_pipeline import (
    load_map_source,
    load_tileset,
    resolve_source_image,
    validate_map_source,
    validate_map_links,
    validate_map_event_links,
    validate_tileset,
)
from event_pipeline import (
    compile_event_sources,
    load_event_sources,
    reference_catalogs,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    content_root = Path(
        os.environ.get("DA0_CONTENT_DIR", PROJECT_ROOT / "content")
    ).resolve()
    parser = argparse.ArgumentParser(
        description="content/maps/tilesetsのマップチップメタデータを検証します。"
    )
    parser.add_argument("--content-root", type=Path, default=content_root)
    parser.add_argument(
        "--tileset",
        help="指定したタイルセットIDだけを検証します。",
    )
    parser.add_argument("--map", dest="map_id", help="指定した制作用マップIDだけを検証します。")
    return parser.parse_args()


def tileset_paths(content_root: Path, tileset_id: str | None) -> list[Path]:
    source_dir = content_root / "maps" / "tilesets"
    if tileset_id is not None:
        if not tileset_id or not tileset_id.replace("_", "a").isalnum():
            raise ValueError("タイルセットIDが不正です。")
        path = source_dir / f"{tileset_id}.json"
        if not path.is_file():
            raise ValueError(f"タイルセットが見つかりません: {path}")
        return [path]
    if not source_dir.is_dir():
        raise ValueError(f"タイルセットディレクトリが見つかりません: {source_dir}")
    paths = sorted(source_dir.glob("*.json"))
    if not paths:
        raise ValueError(f"タイルセットJSONがありません: {source_dir}")
    return paths


def map_paths(content_root: Path, map_id: str | None) -> list[Path]:
    source_dir = content_root / "maps" / "sources"
    if map_id is not None:
        if not map_id or not map_id.replace("_", "a").isalnum():
            raise ValueError("マップIDが不正です。")
        path = source_dir / f"{map_id}.json"
        if not path.is_file():
            raise ValueError(f"制作用マップが見つかりません: {path}")
        return [path]
    return sorted(source_dir.glob("*.json")) if source_dir.is_dir() else []


def main() -> int:
    args = parse_args()
    content_root = args.content_root.resolve()
    palette_path = PROJECT_ROOT / "app" / "assets.pyxpal"
    errors = 0
    warnings = 0
    try:
        paths = tileset_paths(content_root, args.tileset)
        loaded_tilesets = {}
        for path in paths:
            data = load_tileset(path)
            if isinstance(data.get("tileset_id"), str):
                loaded_tilesets[data["tileset_id"]] = data
            image_id = data.get("source_image_id")
            image_path = (
                resolve_source_image(content_root, image_id)
                if isinstance(image_id, str)
                else content_root / "images" / "__missing__.png"
            )
            diagnostics, _ = validate_tileset(data, image_path, palette_path)
            print(path.relative_to(content_root).as_posix())
            if not diagnostics:
                print("  OK")
            for diagnostic in diagnostics:
                label = "ERROR" if diagnostic.severity == "error" else "WARNING"
                print(f"  {label} {diagnostic.path}: {diagnostic.message}")
                if diagnostic.severity == "error":
                    errors += 1
                else:
                    warnings += 1
        sources = map_paths(content_root, args.map_id)
        for path in sources:
            data = load_map_source(path)
            tileset_id = data.get("tileset_id")
            tileset = loaded_tilesets.get(tileset_id)
            if tileset is None and isinstance(tileset_id, str):
                tileset_path = content_root / "maps" / "tilesets" / f"{tileset_id}.json"
                if tileset_path.is_file():
                    tileset = load_tileset(tileset_path)
            print(path.relative_to(content_root).as_posix())
            if tileset is None:
                print(f"  ERROR tileset_id: タイルセットが見つかりません: {tileset_id}")
                errors += 1
                continue
            diagnostics = validate_map_source(data, tileset)
            if not diagnostics:
                print("  OK")
            for diagnostic in diagnostics:
                label = "ERROR" if diagnostic.severity == "error" else "WARNING"
                print(f"  {label} {diagnostic.path}: {diagnostic.message}")
                if diagnostic.severity == "error":
                    errors += 1
                else:
                    warnings += 1
        all_sources = {}
        for path in map_paths(content_root, None):
            source = load_map_source(path)
            map_id = source.get("map_id")
            if isinstance(map_id, str):
                all_sources[map_id] = source
        link_diagnostics = validate_map_links(all_sources)
        event_sources = load_event_sources(content_root)
        event_catalog = compile_event_sources(
            event_sources,
            **reference_catalogs(content_root, app_root=PROJECT_ROOT / "app"),
        )
        link_diagnostics.extend(
            validate_map_event_links(all_sources, event_catalog["events"])
        )
        if link_diagnostics:
            print("map links")
        for diagnostic in link_diagnostics:
            label = "ERROR" if diagnostic.severity == "error" else "WARNING"
            print(f"  {label} {diagnostic.path}: {diagnostic.message}")
            if diagnostic.severity == "error":
                errors += 1
            else:
                warnings += 1
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1

    print(f"検証完了: {len(paths)} tileset, {len(sources)} map, {errors} error, {warnings} warning")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
