"""Launch the sound-balance preview without modifying production data."""

from __future__ import annotations

import argparse
from pathlib import Path

import pyxel

from app.audio_catalog import AudioCatalogError
from app.resources import AudioResourceError, FontResourceError
from tools.sound_test.app import SoundTestApp


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="BGMとSEの音量バランスを試聴します。")
    parser.add_argument("--screenshot", type=Path, help="初期画面をPNGへ保存して終了します。")
    args = parser.parse_args(argv)
    try:
        app = SoundTestApp(PROJECT_ROOT)
        if args.screenshot is not None:
            app.draw()
            path = args.screenshot.resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            pyxel.screen.save(str(path), 1)
            app.session.close()
        else:
            pyxel.run(app.update, app.draw)
        return 0
    except (AudioResourceError, AudioCatalogError, FontResourceError, OSError, ValueError) as error:
        print(error)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
