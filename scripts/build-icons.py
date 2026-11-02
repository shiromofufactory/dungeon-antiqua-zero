#!/usr/bin/env python3
"""Generate desktop icons from the pixel art in icons/icon_new.gif."""

from pathlib import Path

from PIL import Image


def main() -> None:
    icon_dir = Path(__file__).resolve().parent.parent / "icons"
    with Image.open(icon_dir / "icon_new.gif") as source:
        if source.width != source.height or source.n_frames != 1:
            raise SystemExit("アイコンの原画像には正方形の静止画GIFを使用してください。")
        image = source.convert("RGBA")

    # 各サイズを原画像から直接生成し、エンコーダーの補間によるぼけを防ぐ。
    sizes = (16, 32, 48, 64, 128, 256, 512, 1024)
    images = {
        size: image.resize((size, size), Image.Resampling.NEAREST)
        for size in sizes
    }
    images[256].save(
        icon_dir / "icon.ico",
        sizes=[(size, size) for size in sizes if size <= 256],
        append_images=[images[size] for size in sizes if size < 256],
    )
    images[1024].save(
        icon_dir / "icon.icns",
        append_images=[images[size] for size in sizes if size >= 32],
    )
    print("生成完了: icons/icon.ico, icons/icon.icns")


if __name__ == "__main__":
    main()
