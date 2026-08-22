#!/usr/bin/env python3
"""Compile shared PNG/GIF sources into palette-indexed runtime image data."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

try:
    from PIL import Image, UnidentifiedImageError
except ImportError as error:  # pragma: no cover - depends on the local toolchain
    raise SystemExit(
        "Pillowが見つかりません。python3 -m pip install -r requirements-tools.txt "
        "を実行してください。"
    ) from error


FORMAT_VERSION = 1
BUNDLE_NAME = "graphics.bin"
MANIFEST_NAME = "manifest.json"
TRANSPARENT_INDEX = 1
TRANSPARENT_RGB = 0xFF0080
SUPPORTED_EXTENSIONS = {".gif", ".png"}


@dataclass(frozen=True)
class PaletteIssue:
    source: str
    rgb: int
    pixels: int
    nearest_index: int
    nearest_rgb: int


def parse_args() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parent.parent
    content_root = Path(
        os.environ.get("DA0_CONTENT_DIR", project_root / "content")
    ).resolve()

    parser = argparse.ArgumentParser(
        description="content/imagesのPNG/GIFをPyxelパレット番号へ変換します。"
    )
    parser.add_argument(
        "--allow-palette-mismatch",
        action="store_true",
        help=(
            "パレット外色を最近傍色へ変換します。試作確認専用で、"
            "通常の生成・配布には使用しません。"
        ),
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=content_root / "images",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=project_root / "app" / "images",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--palette",
        type=Path,
        default=project_root / "app" / "assets.pyxpal",
        help=argparse.SUPPRESS,
    )
    return parser.parse_args()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def rgb_hex(rgb: int) -> str:
    return f"#{rgb:06X}"


def read_palette(path: Path) -> tuple[list[int], bytes]:
    try:
        raw = path.read_bytes()
    except FileNotFoundError as error:
        raise ValueError(f"パレットが見つかりません: {path}") from error

    colors: list[int] = []
    for line_no, raw_line in enumerate(raw.decode("utf-8").splitlines(), start=1):
        value = raw_line.strip()
        if not value or value.startswith("//"):
            continue
        value = value.removeprefix("#")
        if not re.fullmatch(r"[0-9a-fA-F]{6}", value):
            raise ValueError(
                f"{path}:{line_no}: 色はRRGGBB形式で指定してください: {raw_line}"
            )
        colors.append(int(value, 16))

    if not colors:
        raise ValueError(f"パレットに色がありません: {path}")
    if len(colors) > 256:
        raise ValueError(f"パレットは256色以下である必要があります: {len(colors)}色")

    duplicates = [
        rgb_hex(color)
        for color, count in Counter(colors).items()
        if count > 1
    ]
    if duplicates:
        raise ValueError(
            "パレット内に重複色があります: " + ", ".join(duplicates)
        )
    if len(colors) <= TRANSPARENT_INDEX or colors[TRANSPARENT_INDEX] != TRANSPARENT_RGB:
        actual = (
            rgb_hex(colors[TRANSPARENT_INDEX])
            if len(colors) > TRANSPARENT_INDEX
            else "未定義"
        )
        raise ValueError(
            f"透過色はパレット[{TRANSPARENT_INDEX}] "
            f"{rgb_hex(TRANSPARENT_RGB)}である必要があります: {actual}"
        )

    return colors, raw


def color_distance(left: int, right: int) -> int:
    lr, lg, lb = (left >> 16) & 0xFF, (left >> 8) & 0xFF, left & 0xFF
    rr, rg, rb = (right >> 16) & 0xFF, (right >> 8) & 0xFF, right & 0xFF
    return (lr - rr) ** 2 + (lg - rg) ** 2 + (lb - rb) ** 2


def nearest_color(rgb: int, palette: list[int]) -> tuple[int, int]:
    index = min(range(len(palette)), key=lambda i: color_distance(rgb, palette[i]))
    return index, palette[index]


def compile_image(
    path: Path,
    source_name: str,
    palette: list[int],
) -> tuple[int, int, bytes, list[PaletteIssue]]:
    try:
        with Image.open(path) as source_image:
            source_format = source_image.format
            background_rgb: tuple[int, int, int] | None = None
            if source_format == "GIF":
                frame_count = getattr(source_image, "n_frames", 1)
                if frame_count != 1:
                    raise ValueError(
                        f"{source_name}: アニメーションGIFは未対応です: "
                        f"{frame_count}フレーム"
                    )
                background_index = source_image.info.get("background")
                source_palette = source_image.getpalette()
                if not isinstance(background_index, int) or source_palette is None:
                    raise ValueError(
                        f"{source_name}: GIFの背景色を取得できません。"
                    )
                palette_offset = background_index * 3
                if palette_offset + 3 > len(source_palette):
                    raise ValueError(
                        f"{source_name}: GIFの背景色indexが範囲外です: "
                        f"{background_index}"
                    )
                background_rgb = tuple(
                    source_palette[palette_offset : palette_offset + 3]
                )
            image = source_image.convert("RGBA")
    except UnidentifiedImageError as error:
        raise ValueError(f"画像ファイルを読み込めません: {path}") from error

    pixels = list(image.getdata())
    counts = Counter(pixels)
    palette_indexes = {rgb: index for index, rgb in enumerate(palette)}
    color_map: dict[tuple[int, int, int, int], int] = {}
    issues: list[PaletteIssue] = []
    partial_alpha = Counter()

    for rgba, pixel_count in counts.items():
        red, green, blue, alpha = rgba
        if alpha == 0 or (
            background_rgb is not None
            and (red, green, blue) == background_rgb
        ):
            color_map[rgba] = TRANSPARENT_INDEX
            continue
        if alpha != 255:
            partial_alpha[alpha] += pixel_count
            continue

        rgb = (red << 16) | (green << 8) | blue
        target_index = palette_indexes.get(rgb)
        if target_index is None:
            target_index, nearest_rgb = nearest_color(rgb, palette)
            issues.append(
                PaletteIssue(
                    source=source_name,
                    rgb=rgb,
                    pixels=pixel_count,
                    nearest_index=target_index,
                    nearest_rgb=nearest_rgb,
                )
            )
        color_map[rgba] = target_index

    if partial_alpha:
        details = ", ".join(
            f"alpha={alpha}: {count:,}px"
            for alpha, count in sorted(partial_alpha.items())
        )
        raise ValueError(
            f"{source_name}: 半透明ピクセルは使用できません: {details}\n"
            f"完全透明または透過色{rgb_hex(TRANSPARENT_RGB)}を使用してください。"
        )

    converted = bytes(color_map[pixel] for pixel in pixels)
    return image.width, image.height, converted, issues


def compile_images(
    source_dir: Path,
    palette_path: Path,
) -> tuple[bytes, bytes, list[PaletteIssue]]:
    if not source_dir.is_dir():
        raise ValueError(f"画像ディレクトリが見つかりません: {source_dir}")

    palette, palette_raw = read_palette(palette_path)
    image_files = sorted(
        (
            path
            for path in source_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
        ),
        key=lambda path: path.relative_to(source_dir).as_posix(),
    )
    if not image_files:
        raise ValueError(f"PNG/GIF画像がありません: {source_dir}")

    bundle = bytearray()
    entries = []
    all_issues: list[PaletteIssue] = []
    ids: set[str] = set()

    for path in image_files:
        source_name = path.relative_to(source_dir).as_posix()
        image_id = source_name.removesuffix(path.suffix)
        if image_id in ids:
            raise ValueError(f"画像IDが重複しています: {image_id}")
        ids.add(image_id)

        width, height, pixels, issues = compile_image(
            path,
            source_name,
            palette,
        )
        offset = len(bundle)
        bundle.extend(pixels)
        entries.append(
            {
                "id": image_id,
                "source": source_name,
                "width": width,
                "height": height,
                "offset": offset,
                "length": len(pixels),
                "source_sha256": sha256(path.read_bytes()),
            }
        )
        all_issues.extend(issues)

    manifest = {
        "format_version": FORMAT_VERSION,
        "pixel_format": "pyxel-palette-index-u8",
        "bundle": BUNDLE_NAME,
        "bundle_sha256": sha256(bytes(bundle)),
        "palette": {
            "file": "../assets.pyxpal",
            "sha256": sha256(palette_raw),
            "colors": len(palette),
            "transparent_index": TRANSPARENT_INDEX,
            "transparent_color": rgb_hex(TRANSPARENT_RGB),
        },
        "total_pixels": len(bundle),
        "images": entries,
    }
    manifest_bytes = (
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    return bytes(bundle), manifest_bytes, all_issues


def format_issues(issues: list[PaletteIssue], heading: str) -> str:
    lines = [heading]
    for issue in issues:
        lines.append(
            f"- {issue.source}: {rgb_hex(issue.rgb)} "
            f"({issue.pixels:,}px) → 最近傍 [{issue.nearest_index}] "
            f"{rgb_hex(issue.nearest_rgb)}"
        )
    return "\n".join(lines)


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="wb",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as temporary:
        temporary.write(content)
        temporary_path = Path(temporary.name)
    try:
        temporary_path.replace(path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def main() -> int:
    args = parse_args()
    try:
        bundle, manifest, issues = compile_images(
            args.source_dir.resolve(),
            args.palette.resolve(),
        )
        if issues and not args.allow_palette_mismatch:
            raise ValueError(
                format_issues(issues, "パレット外の色が見つかりました:")
                + "\n画像またはapp/assets.pyxpalを修正してください。\n"
                + "変換結果だけを試す場合は npm run images:build:force "
                + "を実行できます。"
            )
        if issues:
            print(
                format_issues(
                    issues,
                    "警告: パレット外色を最近傍色へ変換します（試作確認専用）:",
                ),
                file=sys.stderr,
            )

        output_dir = args.output_dir.resolve()
        for name, content in {
            BUNDLE_NAME: bundle,
            MANIFEST_NAME: manifest,
        }.items():
            atomic_write(output_dir / name, content)
        print(
            f"{len(json.loads(manifest)['images'])}画像、"
            f"{len(bundle):,}画素を{output_dir}へ生成しました。"
        )
        return 0
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
