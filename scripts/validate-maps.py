#!/usr/bin/env python3
"""Validate map tileset authoring metadata without starting the editor."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

from map_pipeline import load_tileset, resolve_source_image, validate_tileset


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


def main() -> int:
    args = parse_args()
    content_root = args.content_root.resolve()
    palette_path = PROJECT_ROOT / "app" / "assets.pyxpal"
    errors = 0
    warnings = 0
    try:
        paths = tileset_paths(content_root, args.tileset)
        for path in paths:
            data = load_tileset(path)
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
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1

    print(f"検証完了: {len(paths)} tileset, {errors} error, {warnings} warning")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
