"""Display and capture the current status-screen layout mock."""

from __future__ import annotations

import argparse
from pathlib import Path

import pyxel

from tools._bootstrap import APP_ROOT
from resources import (
    TRANSPARENT_INDEX,
    FontResourceError,
    FontResources,
    ImageResourceError,
    ImageResources,
)
from state import Settings
from ui import WindowFactory, WindowText

SCREEN_WIDTH = 256
SCREEN_HEIGHT = 240
FPS = 60
FACES_IMAGE_ID = "faces/faces_pc"


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
            fps=FPS,
        )
        pyxel.load(str(APP_ROOT / "assets.pyxres"))
        pyxel.load_pal(str(APP_ROOT / "assets.pyxpal"))

        resources = ImageResources()
        self.faces = resources.image(FACES_IMAGE_ID)

        settings = Settings()
        fonts = FontResources()
        windows = WindowFactory(fonts.font_for(settings.language))
        self.windows = [
            windows.create(
                0,
                0,
                64,
                60,
                (
                    WindowText("フィオラ", 12, 2),
                    WindowText("ようせい", 12, 5),
                    WindowText("おんな", 28, 5),
                    WindowText("ＨＰ　９９９／９９９", 6, 11),
                    WindowText("ＭＰ　２５５／２５５", 6, 14),
                    WindowText("じょうたい　　　ＯＫ", 6, 17),
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
        # 顔
        pyxel.blt(
            8,
            8,
            self.faces,
            0,
            0,
            32,
            32,
            TRANSPARENT_INDEX,
        )


def main() -> int:
    args = parse_args()
    try:
        StatusScreenMock(args.screenshot)
        return 0
    except (FontResourceError, ImageResourceError) as error:
        print(error)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
