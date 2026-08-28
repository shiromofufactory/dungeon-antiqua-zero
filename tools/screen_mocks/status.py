"""Display the current status-screen layout mock."""

from __future__ import annotations

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


class StatusScreenMock:
    def __init__(self) -> None:
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
                    WindowText("フィオラ", 14, 2),
                    WindowText("ようせい", 14, 5),
                    WindowText("おんな", 14, 8),
                    WindowText("ＨＰ　９９９／９９９", 6, 14),
                    WindowText("ＭＰ　２５５／２５５", 6, 17),
                    WindowText("じょうたい　　　ＯＫ", 6, 20),
                    WindowText("ちから　　　　１７", 6, 26),
                    WindowText("すばやさ　　　２５", 6, 29),
                    WindowText("まりょく　　　２４", 6, 32),
                    WindowText("スキル：", 6, 38),
                    WindowText("　ふくつのとうし", 6, 41),
                    WindowText("　りょうてもち", 6, 44),
                    WindowText("みぎて　：%WAND%デイブリンガー", 30, 8),
                    WindowText("ひだりて：", 30, 11),
                    WindowText("からだ　：エインシーのはごろも", 30, 14),
                    WindowText("あたま　：はなかんむり", 30, 17),
                    WindowText("うで　　：タイニーリング", 30, 20),
                    WindowText("こうげき　　　　９６", 30, 26),
                    WindowText("めいちゅう　　１１６（＋１６）", 30, 29),
                    WindowText("ぼうぎょ　　　　２０", 30, 32),
                    WindowText("かいひりつ　　　１５", 30, 35),
                    WindowText("まほうぼうぎょ　４０", 30, 38),
                    WindowText("たいせい", 30, 41),
                    WindowText("%FIRE%", 32, 44),
                    WindowText("%FREEZE%", 34, 44),
                    WindowText("%DARK%", 36, 44),
                    WindowText("%SLEEP%", 38, 44),
                    WindowText("%POISON%", 40, 44),
                    WindowText("%PARALIZE%", 42, 44),
                    WindowText("%CONFUSE%", 44, 44),
                    WindowText("%SILENCE%", 46, 44),
                    WindowText("%DEATH%", 48, 44),
                    WindowText("%SWORD%：９－９９", 6, 49),
                    WindowText("%KATANA%：９－９９", 20, 49),
                    WindowText("%KNIFE%：９－９９", 34, 49),
                    WindowText("%SPEAR%：９－９９", 48, 49),
                    WindowText("%AXE%：９－９９", 6, 52),
                    WindowText("%HAMMER%：９－９９", 20, 52),
                    WindowText("%THROWING%：９－９９", 34, 52),
                    WindowText("%ROD%：９－９９", 48, 52),
                    WindowText("%WAND%：９－９９", 6, 55),
                    WindowText("%MYSTIC%：９－９９", 20, 55),
                    WindowText("%SACRED%：９－９９", 34, 55),
                    WindowText("%NETHER%：９－９９", 48, 55),
                ),
            ),
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
            16,
            8,
            self.faces,
            0,
            0,
            32,
            32,
            TRANSPARENT_INDEX,
        )


def main() -> int:
    try:
        StatusScreenMock()
        return 0
    except (FontResourceError, ImageResourceError) as error:
        print(error)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
