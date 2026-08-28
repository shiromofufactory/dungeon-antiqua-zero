"""Display and capture the current status-screen layout mock."""

from __future__ import annotations

import argparse
from pathlib import Path

import pyxel

from tools._bootstrap import APP_ROOT
from resources import ImageResourceError, ImageResources
from ui import Window, WindowText

SCREEN_WIDTH = 256
SCREEN_HEIGHT = 240


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ステータス画面のレイアウトモックを表示します。"
    )
    parser.add_argument(
        "--screenshot",
        type=Path,
        help="初期表示をPNGへ保存して終了します。",
    )
    return parser.parse_args()


class StatusScreenMock:
    def __init__(self, screenshot: Path | None = None) -> None:
        if screenshot is not None:
            screenshot = screenshot.resolve()

        pyxel.init(
            SCREEN_WIDTH,
            SCREEN_HEIGHT,
            title="Dungeon Antiqua ZERO Status Screen Mock",
        )
        pyxel.load(str(APP_ROOT / "assets.pyxres"))
        pyxel.load_pal(str(APP_ROOT / "assets.pyxpal"))

        resources = ImageResources()

        font_6x8 = pyxel.Font(str(APP_ROOT / "fonts" / "k6x8_gothic.bdf"))
        font_8x12 = pyxel.Font(str(APP_ROOT / "fonts" / "k8x12S.bdf"))
        self.windows = [
            Window(
                0,
                0,
                64,
                19,
                (
                    WindowText("フィオラ", 2, 2, font=font_8x12),
                    WindowText("　ぼうぎょ", 2, 5, font=font_8x12),
                    WindowText("　じゅもん", 2, 8, font=font_8x12),
                    WindowText("　にげる", 16, 2, font=font_8x12),
                    WindowText("　アイテム", 16, 5, font=font_8x12),
                ),
            )
        ]
        pyxel.run(self.update, self.draw)

    @staticmethod
    def update() -> None:
        if pyxel.btnp(pyxel.KEY_Q) or pyxel.btnp(pyxel.KEY_ESCAPE):
            pyxel.quit()

    def draw(self) -> None:
        # ウィンドウ
        for window in self.windows:
            window.draw()


def main() -> int:
    args = parse_args()
    try:
        StatusScreenMock(args.screenshot)
        return 0
    except ImageResourceError as error:
        print(error)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
