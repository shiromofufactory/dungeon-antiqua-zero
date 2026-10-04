#!/usr/bin/env python3
"""Generate palette-exact, numbered spheres for missing development artwork."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import re

from PIL import Image, PngImagePlugin

ROOT = Path(__file__).resolve().parents[1]
# Four consecutive shades, dark to light, in the production palette.
TRIBE_COLORS = {
    'ANIMAL': 22, 'UNDEAD': 2, 'GOBLIN': 26,
    'HUMAN': 38, 'MAGE': 58, 'GIANT': 42,
    'DRAGON': 46, 'ANIMATED': 10, 'DEMON': 54,
}
GLYPHS = {
    '0': ('01110', '10001', '10011', '10101', '11001', '10001', '01110'),
    '1': ('00100', '01100', '00100', '00100', '00100', '00100', '01110'),
    '2': ('01110', '10001', '00001', '00010', '00100', '01000', '11111'),
    '3': ('11110', '00001', '00001', '01110', '00001', '00001', '11110'),
    '4': ('00010', '00110', '01010', '10010', '11111', '00010', '00010'),
    '5': ('11111', '10000', '10000', '11110', '00001', '00001', '11110'),
    '6': ('01110', '10000', '10000', '11110', '10001', '10001', '01110'),
    '7': ('11111', '00001', '00010', '00100', '01000', '01000', '01000'),
    '8': ('01110', '10001', '10001', '01110', '10001', '10001', '01110'),
    '9': ('01110', '10001', '10001', '01111', '00001', '00001', '01110'),
    'n': ('00000', '00000', '11110', '10001', '10001', '10001', '10001'),
    '-': ('00000', '00000', '00000', '11111', '00000', '00000', '00000'),
}


def read_palette(path: Path) -> list[int]:
    colors = [int(line.strip().removeprefix('#'), 16)
              for line in path.read_text().splitlines()
              if line.strip() and not line.strip().startswith('//')]
    if len(colors) != 62 or colors[1] != 0xFF0080:
        raise ValueError('本番の62色パレット・透過色1（FF0080）が必要です。')
    return colors


def definitions(records: list[dict]) -> dict[str, tuple[int, int, str]]:
    result = {}
    for record in records:
        image_id = str(record['image_id'])
        if not re.fullmatch(r'(?:n-)?[0-9]+', image_id):
            raise ValueError(f'未対応の画像番号: {image_id}')
        width, height, tribe = record['width'], record['height'], record['tribe']
        if any(type(value) is not int or value < 32 for value in (width, height)):
            raise ValueError(f'画像サイズが不正です: {image_id}')
        if tribe not in TRIBE_COLORS:
            raise ValueError(f'未対応のtribe: {tribe}')
        spec = (width, height, tribe)
        if image_id in result and result[image_id] != spec:
            raise ValueError(f'同じ画像番号でサイズ・tribeが異なります: {image_id}')
        result[image_id] = spec
    return result


def draw_placeholder(image_id: str, spec: tuple[int, int, str], colors: list[int]) -> Image.Image:
    width, height, tribe = spec
    image = Image.new('P', (width, height), 1)
    palette = [channel for color in colors for channel in
               ((color >> 16) & 255, (color >> 8) & 255, color & 255)]
    image.putpalette(palette + [0] * (768 - len(palette)))
    radius = (min(width, height) - 6) / 2
    cx, cy = (width - 1) / 2, (height - 1) / 2
    for y in range(height):
        for x in range(width):
            nx, ny = (x - cx) / radius, (y - cy) / radius
            distance = nx * nx + ny * ny
            if distance <= 1:
                nz = math.sqrt(1 - distance)
                light = max(0, (-nx - ny + 2 * nz) / math.sqrt(6))
                shade = min(3, int(light * 4))
                image.putpixel((x, y), TRIBE_COLORS[tribe] + shade)
    text_width = len(image_id) * 6 - 1
    scale = min(2, (min(width, height) - 12) // text_width)
    if scale < 1:
        raise ValueError(f'画像番号が画像に収まりません: {image_id}')
    mask = Image.new('1', (text_width, 7))
    for index, character in enumerate(image_id):
        for y, row in enumerate(GLYPHS[character]):
            for x, pixel in enumerate(row):
                if pixel == '1':
                    mask.putpixel((index * 6 + x, y), 1)
    mask = mask.resize((text_width * scale, 7 * scale), Image.Resampling.NEAREST)
    tx, ty = (width - mask.width) // 2, (height - mask.height) // 2
    # Black outline keeps the white digits legible on every tribe color.
    for dx, dy in ((-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)):
        image.paste(0, (tx + dx, ty + dy), mask)
    image.paste(5, (tx, ty), mask)
    return image


def main() -> None:
    content = Path(os.environ.get('DA0_CONTENT_DIR', ROOT / 'content'))
    parser = argparse.ArgumentParser(description='不足モンスター画像だけを仮の球体PNGで補います。')
    parser.add_argument('--check', action='store_true', help='不足一覧のみ表示し、生成しない')
    parser.add_argument('--data', type=Path, default=content / 'data/monsters.json')
    parser.add_argument('--output-dir', type=Path, default=content / 'images/monsters')
    parser.add_argument('--palette', type=Path, default=ROOT / 'app/assets.pyxpal')
    args = parser.parse_args()
    colors = read_palette(args.palette)
    specs = definitions(json.loads(args.data.read_text()))
    existing = {p.stem for p in args.output_dir.glob('*')
                if p.is_file() and p.suffix.lower() in {'.png', '.gif'}}
    missing = {key: spec for key, spec in specs.items() if key not in existing}
    print(f'参照画像: {len(specs)} / 既存: {len(specs.keys() & existing)} / 不足: {len(missing)}')
    for key, (width, height, tribe) in missing.items():
        print(f'{key}.png\t{width}x{height}\t{tribe}')
    if args.check:
        return
    # Render all before writing, so invalid definitions cannot leave partial output.
    images = {key: draw_placeholder(key, spec, colors) for key, spec in missing.items()}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for key, image in images.items():
        metadata = PngImagePlugin.PngInfo()
        metadata.add_text('da0_placeholder', 'monster-sphere-v1')
        metadata.add_text('image_id', key)
        metadata.add_text('tribe', specs[key][2])
        # Exclusive creation also prevents overwriting artwork added during the run.
        with (args.output_dir / f'{key}.png').open('xb') as output:
            image.save(output, format='PNG', pnginfo=metadata)
    print(f'仮画像を{len(images)}点生成しました。')


if __name__ == '__main__':
    main()
