#!/usr/bin/env python3
"""PNG内の完全一致するRGB色を別の色へ置換する。"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import tempfile

try:
    from PIL import Image, UnidentifiedImageError
except ImportError as error:  # pragma: no cover - depends on the local toolchain
    raise SystemExit(
        "Pillowが見つかりません。python3 -m pip install -r requirements-tools.txt "
        "を実行してください。"
    ) from error


RGB = tuple[int, int, int]


def parse_color(value: str) -> RGB:
    normalized = value.removeprefix("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", normalized):
        raise argparse.ArgumentTypeError(
            f"色はRRGGBBまたは#RRGGBB形式で指定してください: {value}"
        )
    return tuple(bytes.fromhex(normalized))  # type: ignore[return-value]


def color_hex(color: RGB) -> str:
    return "#" + "".join(f"{component:02x}" for component in color)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="PNG内で完全一致するRGB色を置換します。"
    )
    parser.add_argument("image", type=Path, help="変換するPNGファイル")
    parser.add_argument("source", type=parse_color, help="置換元色 (RRGGBB)")
    parser.add_argument("target", type=parse_color, help="置換先色 (RRGGBB)")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="出力先。省略時は入力ファイルを上書きします。",
    )
    return parser.parse_args()


def replace_palette_color(image: Image.Image, source: RGB, target: RGB) -> int:
    palette = image.getpalette()
    if palette is None:
        raise ValueError("インデックスカラー画像のパレットを取得できません。")

    matched_indexes: set[int] = set()
    for index in range(len(palette) // 3):
        offset = index * 3
        if tuple(palette[offset : offset + 3]) == source:
            palette[offset : offset + 3] = target
            matched_indexes.add(index)

    if not matched_indexes:
        return 0

    replaced_pixels = sum(
        1 for palette_index in image.getdata() if palette_index in matched_indexes
    )
    image.putpalette(palette)
    return replaced_pixels


def replace_direct_color(image: Image.Image, source: RGB, target: RGB) -> int:
    replaced_pixels = 0
    converted: list[tuple[int, ...]] = []
    for pixel in image.getdata():
        if pixel[:3] == source:
            converted.append(target + pixel[3:])
            replaced_pixels += 1
        else:
            converted.append(pixel)
    image.putdata(converted)
    return replaced_pixels


def replace_color(image: Image.Image, source: RGB, target: RGB) -> int:
    if image.mode == "P":
        return replace_palette_color(image, source, target)
    if image.mode in {"RGB", "RGBA"}:
        return replace_direct_color(image, source, target)
    raise ValueError(
        f"未対応の画像モードです: {image.mode} (対応モード: P, RGB, RGBA)"
    )


def save_png(image: Image.Image, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    save_options = {
        key: image.info[key]
        for key in ("transparency", "dpi", "icc_profile")
        if key in image.info
    }

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=output.parent,
            prefix=f".{output.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
        image.save(temporary_path, format="PNG", **save_options)
        temporary_path.replace(output)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def main() -> int:
    args = parse_args()
    source_path = args.image.resolve()
    output_path = (args.output or args.image).resolve()

    if source_path.suffix.lower() != ".png":
        raise SystemExit(f"PNGファイルを指定してください: {source_path}")

    try:
        with Image.open(source_path) as source_image:
            source_image.load()
            image = source_image.copy()
    except FileNotFoundError:
        raise SystemExit(f"画像が見つかりません: {source_path}") from None
    except UnidentifiedImageError:
        raise SystemExit(f"PNG画像を読み込めません: {source_path}") from None

    try:
        replaced_pixels = replace_color(image, args.source, args.target)
        if replaced_pixels == 0:
            raise ValueError(f"置換元色 {color_hex(args.source)} が見つかりません。")
        save_png(image, output_path)
    except ValueError as error:
        raise SystemExit(str(error)) from error

    print(
        f"{source_path} の {color_hex(args.source)} を {color_hex(args.target)} へ "
        f"{replaced_pixels:,}ピクセル置換しました: {output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
