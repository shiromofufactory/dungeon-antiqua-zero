"""Display compiled production images with the production Pyxel palette."""

from __future__ import annotations

import argparse
from pathlib import Path

import pyxel

from tools._bootstrap import APP_ROOT
from resources import ImageResourceError, ImageResources


INFO_HEIGHT = 16
CHECKER_SIZE = 8
PAN_STEP = 8
MIN_WIDTH = 160
MIN_HEIGHT = 120
MAX_WIDTH = 512
MAX_HEIGHT = 480


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="app/imagesの生成済み画像をPyxelで表示します。"
    )
    parser.add_argument(
        "image_id",
        nargs="?",
        help="表示する画像ID。省略時はmanifestの先頭を表示します。",
    )
    parser.add_argument("--list", action="store_true", help="画像ID一覧を表示します。")
    parser.add_argument("--width", type=int, help="表示ウィンドウの幅。")
    parser.add_argument("--height", type=int, help="表示ウィンドウの高さ。")
    parser.add_argument(
        "--screenshot",
        type=Path,
        help="初期表示をPNGへ保存して終了します。",
    )
    return parser.parse_args()


class ImageViewer:
    def __init__(
        self,
        resources: ImageResources,
        image_id: str,
        width: int,
        height: int,
        screenshot: Path | None,
    ):
        self.resources = resources
        self.image_ids = resources.ids
        self.index = self.image_ids.index(image_id)
        self.offset_x = 0
        self.offset_y = 0
        self.current_image = resources.image(image_id)
        self.current_entry = resources.entry(image_id)

        pyxel.init(width, height, title="Dungeon Antiqua ZERO Image Viewer")
        pyxel.load_pal(str(APP_ROOT / "assets.pyxpal"))

        if screenshot is not None:
            self.draw()
            screenshot = screenshot.resolve()
            screenshot.parent.mkdir(parents=True, exist_ok=True)
            pyxel.screen.save(str(screenshot), 1)
            print(f"スクリーンショットを保存しました: {screenshot}")
            return

        pyxel.run(self.update, self.draw)

    def select(self, direction: int) -> None:
        self.index = (self.index + direction) % len(self.image_ids)
        image_id = self.image_ids[self.index]
        self.current_entry = self.resources.entry(image_id)
        self.current_image = self.resources.image(image_id)
        self.offset_x = 0
        self.offset_y = 0

    def update(self) -> None:
        if pyxel.btnp(pyxel.KEY_Q) or pyxel.btnp(pyxel.KEY_ESCAPE):
            pyxel.quit()
            return
        if pyxel.btnp(pyxel.KEY_N) or pyxel.btnp(pyxel.KEY_TAB):
            self.select(1)
        elif pyxel.btnp(pyxel.KEY_P):
            self.select(-1)

        if pyxel.btn(pyxel.KEY_LEFT):
            self.offset_x -= PAN_STEP
        if pyxel.btn(pyxel.KEY_RIGHT):
            self.offset_x += PAN_STEP
        if pyxel.btn(pyxel.KEY_UP):
            self.offset_y -= PAN_STEP
        if pyxel.btn(pyxel.KEY_DOWN):
            self.offset_y += PAN_STEP
        self.clamp_offset()

    def clamp_offset(self) -> None:
        viewport_height = pyxel.height - INFO_HEIGHT
        max_x = max(0, self.current_entry.width - pyxel.width)
        max_y = max(0, self.current_entry.height - viewport_height)
        self.offset_x = min(max(self.offset_x, 0), max_x)
        self.offset_y = min(max(self.offset_y, 0), max_y)

    def draw(self) -> None:
        pyxel.cls(2)
        for y in range(INFO_HEIGHT, pyxel.height, CHECKER_SIZE):
            for x in range(0, pyxel.width, CHECKER_SIZE):
                if ((x // CHECKER_SIZE) + (y // CHECKER_SIZE)) % 2:
                    pyxel.rect(x, y, CHECKER_SIZE, CHECKER_SIZE, 3)

        pyxel.blt(
            -self.offset_x,
            INFO_HEIGHT - self.offset_y,
            self.current_image,
            0,
            0,
            self.current_entry.width,
            self.current_entry.height,
            colkey=1,
        )
        pyxel.rect(0, 0, pyxel.width, INFO_HEIGHT, 0)
        label = (
            f"{self.current_entry.id} "
            f"{self.current_entry.width}x{self.current_entry.height} "
            f"[{self.index + 1}/{len(self.image_ids)}]"
        )
        pyxel.text(4, 4, label, 5)


def window_size(entry, width: int | None, height: int | None) -> tuple[int, int]:
    resolved_width = width or min(max(entry.width, MIN_WIDTH), MAX_WIDTH)
    resolved_height = height or min(
        max(entry.height + INFO_HEIGHT, MIN_HEIGHT),
        MAX_HEIGHT,
    )
    if resolved_width <= 0 or resolved_height <= INFO_HEIGHT:
        raise ImageResourceError("viewerのウィンドウサイズが不正です。")
    return resolved_width, resolved_height


def main() -> int:
    args = parse_args()
    try:
        resources = ImageResources()
        if args.list:
            for image_id in resources.ids:
                entry = resources.entry(image_id)
                print(f"{image_id}\t{entry.width}x{entry.height}")
            return 0

        image_id = args.image_id or resources.ids[0]
        entry = resources.entry(image_id)
        width, height = window_size(entry, args.width, args.height)
        ImageViewer(
            resources,
            image_id,
            width,
            height,
            args.screenshot,
        )
        return 0
    except ImageResourceError as error:
        print(error)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
