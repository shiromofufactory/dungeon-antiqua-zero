"""Display the production window frame, gradient, and text layouts."""

from __future__ import annotations

import argparse
from pathlib import Path

import pyxel

from tools._bootstrap import APP_ROOT
from resources import ImageResourceError, ImageResources
from ui import Window, WindowText

SCREEN_WIDTH = 256
SCREEN_HEIGHT = 240
BACKGROUND_IMAGE_ID = "background/bg_nector"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ウィンドウ枠、グラデーション、テキスト配置を表示します。"
    )
    parser.add_argument(
        "--screenshot",
        type=Path,
        help="初期表示をPNGへ保存して終了します。",
    )
    return parser.parse_args()


class WindowViewer:
    def __init__(self, screenshot: Path | None = None) -> None:
        if screenshot is not None:
            screenshot = screenshot.resolve()

        pyxel.init(
            SCREEN_WIDTH,
            SCREEN_HEIGHT,
            title="Dungeon Antiqua ZERO Window Viewer",
        )
        pyxel.load(str(APP_ROOT / "assets.pyxres"))
        pyxel.load_pal(str(APP_ROOT / "assets.pyxpal"))

        resources = ImageResources()
        background_entry = resources.entry(BACKGROUND_IMAGE_ID)
        if (
            background_entry.width != SCREEN_WIDTH
            or background_entry.height != SCREEN_HEIGHT
        ):
            raise ImageResourceError(
                f"背景画像のサイズが画面と一致しません: {BACKGROUND_IMAGE_ID} "
                f"{background_entry.width}x{background_entry.height} / "
                f"{SCREEN_WIDTH}x{SCREEN_HEIGHT}"
            )
        self.background = resources.image(BACKGROUND_IMAGE_ID)

        font_6x8 = pyxel.Font(str(APP_ROOT / "fonts" / "k6x8_gothic.bdf"))
        font_8x12 = pyxel.Font(str(APP_ROOT / "fonts" / "k8x12S.bdf"))

        self.windows = (
            Window(
                4,
                40,
                120,
                19,
                (
                    WindowText("フィオラ", 0, 0, font=font_8x12),
                    WindowText("セリオン", 0, 3, font=font_8x12),
                    WindowText("アルヴァン", 0, 6, font=font_8x12),
                    WindowText("ラグナ", 0, 9, font=font_8x12),
                    WindowText("エリカ", 0, 12, font=font_8x12),
                ),
            ),
        )

        if screenshot is not None:
            self.draw()
            screenshot.parent.mkdir(parents=True, exist_ok=True)
            pyxel.screen.save(str(screenshot), 1)
            print(f"スクリーンショットを保存しました: {screenshot}")
            return

        pyxel.run(self.update, self.draw)

    @staticmethod
    def update() -> None:
        if pyxel.btnp(pyxel.KEY_Q) or pyxel.btnp(pyxel.KEY_ESCAPE):
            pyxel.quit()

    def draw(self) -> None:
        pyxel.blt(
            0,
            0,
            self.background,
            0,
            0,
            SCREEN_WIDTH,
            SCREEN_HEIGHT,
        )
        for window in self.windows:
            window.draw()


def main() -> int:
    args = parse_args()
    try:
        WindowViewer(args.screenshot)
        return 0
    except ImageResourceError as error:
        print(error)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
