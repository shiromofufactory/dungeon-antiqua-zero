"""Display an empty menu-screen layout mock."""

from __future__ import annotations

import pyxel

from tools._bootstrap import APP_ROOT
from resources import FontResourceError, FontResources
from state import Settings
from ui import WindowFactory

SCREEN_WIDTH = 256
SCREEN_HEIGHT = 240
FPS = 60


class MenuScreenMock:
    def __init__(self) -> None:
        pyxel.init(
            SCREEN_WIDTH,
            SCREEN_HEIGHT,
            title="Dungeon Antiqua ZERO Menu Screen Mock",
            fps=FPS,
        )
        pyxel.load(str(APP_ROOT / "assets.pyxres"))
        pyxel.load_pal(str(APP_ROOT / "assets.pyxpal"))

        settings = Settings()
        fonts = FontResources()
        windows = WindowFactory(fonts.font_for(settings.language))
        self.windows = [windows.create(0, 0, 64, 60)]

        pyxel.run(self.update, self.draw)

    @staticmethod
    def update() -> None:
        if pyxel.btnp(pyxel.KEY_Q) or pyxel.btnp(pyxel.KEY_ESCAPE):
            pyxel.quit()

    def draw(self) -> None:
        for window in self.windows:
            window.draw()


def main() -> int:
    try:
        MenuScreenMock()
        return 0
    except FontResourceError as error:
        print(error)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
