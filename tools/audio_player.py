"""Play generated production BGM assets in a small Pyxel window."""

from __future__ import annotations

import argparse

import pyxel

from tools._bootstrap import APP_ROOT
from resources import AudioResourceError, BgmPlayer, list_bgm_ids


SCREEN_WIDTH = 256
SCREEN_HEIGHT = 64


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="app/audioの生成済みBGMを再生します。"
    )
    parser.add_argument(
        "bgm_id",
        nargs="?",
        help="拡張子を除いたBGM ID。省略時は先頭のBGMを再生します。",
    )
    parser.add_argument(
        "--volume",
        type=int,
        choices=range(5),
        default=3,
        help="BGM音量（0〜4、既定値3）。",
    )
    parser.add_argument("--list", action="store_true", help="BGM ID一覧を表示します。")
    return parser.parse_args()


class AudioPlayer:
    def __init__(self, bgm_id: str | None, volume: int) -> None:
        pyxel.init(
            SCREEN_WIDTH,
            SCREEN_HEIGHT,
            title="Dungeon Antiqua ZERO Audio Player",
            quit_key=pyxel.KEY_NONE,
        )
        pyxel.load(str(APP_ROOT / "assets.pyxres"))
        self.bgm = BgmPlayer(volume=volume)
        self.ids = self.bgm.available_ids
        if not self.ids:
            raise AudioResourceError(
                "生成済みBGMがありません。npm run audio:build を実行してください。"
            )
        if bgm_id is None:
            self.index = 0
        else:
            try:
                self.index = self.ids.index(bgm_id)
            except ValueError as error:
                raise AudioResourceError(
                    f"未定義のBGM IDです: {bgm_id}"
                ) from error
        self.bgm.play(self.ids[self.index])
        pyxel.run(self.update, self.draw)

    def update(self) -> None:
        if pyxel.btnp(pyxel.KEY_Q) or pyxel.btnp(pyxel.KEY_ESCAPE):
            self.bgm.stop()
            pyxel.quit()
            return
        if pyxel.btnp(pyxel.KEY_SPACE):
            if self.bgm.is_playing:
                self.bgm.stop()
            else:
                self.bgm.play(self.ids[self.index])
        if pyxel.btnp(pyxel.KEY_N) or pyxel.btnp(pyxel.KEY_RIGHT):
            self.select(1)
        elif pyxel.btnp(pyxel.KEY_P) or pyxel.btnp(pyxel.KEY_LEFT):
            self.select(-1)
        if pyxel.btnp(pyxel.KEY_UP):
            self.bgm.set_volume(min(4, self.bgm.volume + 1))
        elif pyxel.btnp(pyxel.KEY_DOWN):
            self.bgm.set_volume(max(0, self.bgm.volume - 1))

    def select(self, direction: int) -> None:
        self.index = (self.index + direction) % len(self.ids)
        self.bgm.play(self.ids[self.index])

    def draw(self) -> None:
        pyxel.cls(0)
        status = "PLAY" if self.bgm.is_playing else "STOP"
        pyxel.text(8, 8, f"BGM: {self.ids[self.index]}", 7)
        pyxel.text(8, 20, f"STATUS: {status}  VOLUME: {self.bgm.volume}", 11)
        pyxel.text(8, 36, "SPACE PLAY/STOP  LEFT/RIGHT TRACK", 6)
        pyxel.text(8, 48, "UP/DOWN VOLUME  Q/ESC QUIT", 6)


def main() -> int:
    args = parse_args()
    try:
        if args.list:
            for bgm_id in list_bgm_ids():
                print(bgm_id)
            return 0
        AudioPlayer(args.bgm_id, args.volume)
        return 0
    except AudioResourceError as error:
        print(error)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
