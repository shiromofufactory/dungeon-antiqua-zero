"""Display and capture the current battle-screen layout mock."""

from __future__ import annotations

import argparse
from pathlib import Path

import pyxel

from tools._bootstrap import APP_ROOT
from input import InputBindings, PyxelInputReader
from resources import TRANSPARENT_INDEX, ImageResourceError, ImageResources
from ui import CursorTarget, Window, WindowText

SCREEN_WIDTH = 256
SCREEN_HEIGHT = 240
FPS = 60
BACKGROUND_IMAGE_ID = "background/bg_nector"
CH_BATTLE_IMAGE_ID = "characters/ch_battle"
MONSTERS_IMAGE_IDS = ["monsters/1"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="戦闘画面のレイアウトモックを表示します。"
    )
    parser.add_argument(
        "--screenshot",
        type=Path,
        help="初期表示をPNGへ保存して終了します。",
    )
    return parser.parse_args()


class BattleScreenMock:
    def __init__(self, screenshot: Path | None = None) -> None:
        if screenshot is not None:
            screenshot = screenshot.resolve()

        pyxel.init(
            SCREEN_WIDTH,
            SCREEN_HEIGHT,
            title="Dungeon Antiqua ZERO Battle Screen Mock",
            fps=FPS,
        )
        pyxel.load(str(APP_ROOT / "assets.pyxres"))
        pyxel.load_pal(str(APP_ROOT / "assets.pyxpal"))
        self.input_reader = PyxelInputReader(
            InputBindings.default().with_cancel(pyxel.KEY_Q)
        )

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
        command_window = Window(
            34,
            0,
            30,
            13,
            (
                WindowText("たたかう", 4, 2, font=font_8x12),
                WindowText("ぼうぎょ", 4, 5, font=font_8x12),
                WindowText("じゅもん", 4, 8, font=font_8x12),
                WindowText("にげる", 18, 2, font=font_8x12),
                WindowText("アイテム", 18, 5, font=font_8x12),
            ),
            thin_frame=True,
            opened=False,
        )
        self.command_window = command_window
        self.command_cursor = command_window.set_cursor(
            (
                CursorTarget(2, 2, key="attack"),
                CursorTarget(2, 5, key="defend"),
                CursorTarget(2, 8, key="spell"),
                CursorTarget(16, 2, key="escape"),
                CursorTarget(16, 5, key="item"),
            )
        )
        self.selected_command: str | None = None
        self.windows = [command_window]

        for i in range(5):
            window = Window(52, 16 + i * 7, 7, 5, transparent=True)
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

    def update(self) -> None:
        input_state = self.input_reader.poll()
        if input_state.cancel.triggered:
            pyxel.quit()
            return

        if input_state.confirm.triggered:
            if self.command_window.is_closed:
                self.command_window.open()
            elif self.command_window.is_open:
                self.selected_command = self.command_cursor.selected_key
                self.command_window.close()

        self.command_window.update(input_state.navigation)

    def draw(self) -> None:
        """Draw the battle screen in explicit back-to-front order."""

        self._draw_background()
        self._draw_party()
        self._draw_monsters()
        self._draw_timeline()
        self._draw_windows()

    def _draw_background(self) -> None:
        pyxel.blt(
            0,
            0,
            self.background,
            0,
            0,
            SCREEN_WIDTH,
            SCREEN_HEIGHT,
        )

    def _draw_party(self) -> None:
        # キャラ絵（仮）
        for i in range(5):
            x = 156 + i * 4 + (16 if i in (1, 2, 4) else 0)
            pyxel.blt(
                x,
                64 + i * 28,
                self.characters,
                0,
                i * 32,
                16,
                32,
                TRANSPARENT_INDEX,
            )

    def _draw_monsters(self) -> None:
        # モンスター絵（仮）
        for i in range(5):
            x = (4, 4, 68, 68, 68)[i]
            y = (56, 120, 24, 88, 152)[i]
            pat = (0, 0, 0, 0, 0)[i]
            pyxel.blt(
                x,
                y,
                self.monsters[pat],
                0,
                0,
                64,
                64,
                TRANSPARENT_INDEX,
            )

    def _draw_timeline(self) -> None:
        # タイムライン（仮）
        base_x, base_y = 70, 220
        for i in range(6):
            u = (0, 2, 1, 3, 0, 0)[i]
            v = (3, 4, 4, 4, 0, 4)[i]
            c = 13 if i in (0, 4) else 49
            pyxel.blt(
                base_x + i * 20,
                base_y,
                1,
                u * 16,
                v * 16,
                16,
                16,
                TRANSPARENT_INDEX,
            )
            pyxel.rect(base_x + i * 20, base_y + 17, 16, 1, c)
            pyxel.rect(base_x + i * 20, base_y + 18, 16, 1, c - 1)
        pyxel.blt(
            base_x + 4,
            base_y - 8,
            0,
            88,
            16,
            8,
            8,
            TRANSPARENT_INDEX,
        )

    def _draw_windows(self) -> None:
        for window in self.windows:
            window.draw()


def main() -> int:
    args = parse_args()
    try:
        BattleScreenMock(args.screenshot)
        return 0
    except ImageResourceError as error:
        print(error)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
