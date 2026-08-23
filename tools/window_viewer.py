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
CH_BATTLE_IMAGE_ID = "characters/ch_battle"
MONSTERS_IMAGE_IDS = ["monsters/01", "monsters/04", "monsters/09", "monsters/12"]


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
            title="Dungeon Antiqua ZERO Test Viewer",
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
        self.characters = resources.image(CH_BATTLE_IMAGE_ID)
        self.monsters = [resources.image(id) for id in MONSTERS_IMAGE_IDS]
        font_6x8 = pyxel.Font(str(APP_ROOT / "fonts" / "k6x8_gothic.bdf"))
        font_8x12 = pyxel.Font(str(APP_ROOT / "fonts" / "k8x12S.bdf"))
        """
        self.windows = (
            Window(
                0,
                41,
                30,
                19,
                (
                    WindowText("ヒュージスパイダー　　　２", 2, 2, font=font_8x12),
                    WindowText("コヨーテ　　　　　　　　１", 2, 5, font=font_8x12),
                    WindowText("グリフォン　　　　　　　１", 2, 8, font=font_8x12),
                    WindowText("コブラ　　　　　　　　　１", 2, 11, font=font_8x12),
                ),
            ),
            Window(
                30,
                41,
                34,
                19,
                (
                    WindowText("フィオラ　　　９９９／９９９", 2, 2, font=font_8x12),
                    WindowText("セリオン　　　９９９／９９９", 2, 5, font=font_8x12),
                    WindowText("アルヴァン　　９９９／９９９", 2, 8, font=font_8x12),
                    WindowText("エリカ　　　　９９９／９９９", 2, 11, font=font_8x12),
                    WindowText("ラグナ　　　　９９９／９９９", 2, 14, font=font_8x12),
                ),
            ),
        )
        """
        """
        self.windows = [
            Window(
                24,
                11,
                16,
                16,
                (
                    WindowText("　たたかう", 2, 2, font=font_8x12),
                    WindowText("　ぼうぎょ", 2, 5, font=font_8x12),
                    WindowText("　じゅもん", 2, 8, font=font_8x12),
                    WindowText("　アイテム", 2, 11, font=font_8x12),
                ),
            )
        ]
        """
        self.windows = [
            Window(
                34,
                0,
                30,
                13,
                (
                    WindowText("　たたかう", 2, 2, font=font_8x12),
                    WindowText("　ぼうぎょ", 2, 5, font=font_8x12),
                    WindowText("　じゅもん", 2, 8, font=font_8x12),
                    WindowText("　にげる", 16, 2, font=font_8x12),
                    WindowText("　アイテム", 16, 5, font=font_8x12),
                ),
            )
        ]
        """
        self.windows = [
            Window(
                0,
                47,
                30,
                13,
                (
                    WindowText("　たたかう", 2, 2, font=font_8x12),
                    WindowText("　ぼうぎょ", 2, 5, font=font_8x12),
                    WindowText("　じゅもん", 2, 8, font=font_8x12),
                    WindowText("　にげる", 16, 2, font=font_8x12),
                    WindowText("　アイテム", 16, 5, font=font_8x12),
                ),
            )
        ]
                """

        for i in range(5):
            window = Window(52, 14 + i * 8, 7, 5, transparent=True)
            name = ("フィオラ", "セリオン", "アルヴァン", "エリカ", "ラグナ")[i]
            c = 5 if i == 0 else 4
            window.add_text(name, 0, 0, font=font_8x12, color=c)
            window.add_text("９９９／９９９", 0, 4, font=font_6x8, color=c)
            self.windows.append(window)
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
        """
        # キャラ絵（仮）
        for i in range(5):
            x = 200 + i * 4 + (20 if i in (1, 2) else 0)
            pyxel.blt(x, 48 + i * 20, self.characters, 0, i * 32, 16, 32, 1)
        # モンスター絵（仮）
        for i in range(5):
            x = (2, 18, 66, 82, 126)[i]
            y = (36, 100, 36, 100, 36)[i]
            pat = (0, 0, 1, 2, 3)[i]
            pyxel.blt(x, y, self.monsters[pat], 0, 0, 64, 64, 5)
        """
        # キャラ絵（仮）
        for i in range(5):
            x = 160 + i * 4 + (16 if i in (1, 2, 4) else 0)
            pyxel.blt(x, 56 + i * 32, self.characters, 0, i * 32, 16, 32, 1)
        # モンスター絵（仮）
        for i in range(5):
            x = (4, 12, 4, 68, 76)[i]
            y = (28, 92, 156, 60, 124)[i]
            pat = (0, 0, 1, 2, 3)[i]
            pyxel.blt(x, y, self.monsters[pat], 0, 0, 64, 64, 5)
        # タイムライン（仮）
        # base_x, base_y = 136,216
        # base_x, base_y = 8, 8
        base_x, base_y = 72, 216
        for i in range(6):
            u = (0, 2, 1, 3, 0, 0)[i]
            v = (3, 4, 4, 4, 0, 4)[i]
            c = 13 if i in (0, 4) else 49
            pyxel.blt(base_x + i * 20, base_y, 1, u * 16, v * 16, 16, 16, 1)
            pyxel.rect(base_x + i * 20, base_y + 18, 16, 1, c)
            pyxel.rect(base_x + i * 20, base_y + 19, 16, 1, c - 1)
        pyxel.blt(base_x + 4, base_y - 8, 0, 32, 0, 8, 8, 1)
        # ウィンドウ
        for window in self.windows:
            window.draw()
        # カーソル（仮）
        # pyxel.blt(96, 52, 0, 48, 0, 16, 16, 1)
        pyxel.blt(34 * 4, 1 * 4, 0, 48, 0, 16, 16, 1)
        # pyxel.blt(0 * 4, 49 * 4, 0, 48, 0, 16, 16, 1)


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
