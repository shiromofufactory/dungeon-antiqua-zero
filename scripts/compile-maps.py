#!/usr/bin/env python3
"""Compile authoring-time maps into runtime JSON and palette-index atlases."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

from map_pipeline import (
    compile_map,
    load_map_source,
    load_tileset,
    resolve_source_image,
    save_compiled_map,
    validate_map_source,
    validate_map_links,
    validate_tileset,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    content_root = Path(os.environ.get("DA0_CONTENT_DIR", PROJECT_ROOT / "content")).resolve()
    parser = argparse.ArgumentParser(description="制作用マップからゲーム用マップを生成します。")
    parser.add_argument("--content-root", type=Path, default=content_root)
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "app" / "maps")
    parser.add_argument("--palette", type=Path, default=PROJECT_ROOT / "app" / "assets.pyxpal")
    parser.add_argument("--map", dest="map_id", help="指定したマップIDだけを生成します。")
    return parser.parse_args()


def source_paths(content_root: Path, map_id: str | None) -> list[Path]:
    directory = content_root / "maps" / "sources"
    if map_id:
        path = directory / f"{map_id}.json"
        if not path.is_file():
            raise ValueError(f"制作用マップが見つかりません: {path}")
        return [path]
    paths = sorted(directory.glob("*.json")) if directory.is_dir() else []
    if not paths:
        raise ValueError(f"制作用マップJSONがありません: {directory}")
    return paths


def main() -> int:
    args = parse_args()
    content_root = args.content_root.resolve()
    output_dir = args.output_dir.resolve()
    try:
        paths = source_paths(content_root, args.map_id)
        all_sources = {}
        for source_path in source_paths(content_root, None):
            source = load_map_source(source_path)
            map_id = source.get("map_id")
            if isinstance(map_id, str):
                all_sources[map_id] = source
        link_errors = [
            item
            for item in validate_map_links(all_sources)
            if item.severity == "error"
        ]
        if link_errors:
            details = "\n".join(
                f"- {item.path}: {item.message}" for item in link_errors
            )
            raise ValueError(f"マップ間参照を解決できません:\n{details}")
        for source_path in paths:
            data = load_map_source(source_path)
            tileset_id = data.get("tileset_id")
            if not isinstance(tileset_id, str):
                raise ValueError(f"{source_path}: tileset_idが不正です。")
            tileset_path = content_root / "maps" / "tilesets" / f"{tileset_id}.json"
            tileset = load_tileset(tileset_path)
            image_path = resolve_source_image(content_root, tileset["source_image_id"])
            tileset_diagnostics, _info = validate_tileset(tileset, image_path, args.palette.resolve())
            map_diagnostics = validate_map_source(data, tileset)
            errors = [item for item in (*tileset_diagnostics, *map_diagnostics) if item.severity == "error"]
            if errors:
                details = "\n".join(f"- {item.path}: {item.message}" for item in errors)
                raise ValueError(f"{source_path}を生成できません:\n{details}")
            compiled = compile_map(data, tileset, image_path, args.palette.resolve())
            runtime_path = output_dir / f"{data['map_id']}.json"
            save_compiled_map(runtime_path, compiled)
            print(f"{source_path.relative_to(content_root).as_posix()} → {runtime_path}")
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    print(f"生成完了: {len(paths)} map")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
