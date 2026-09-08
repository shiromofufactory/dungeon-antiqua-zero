"""Run the Pyxel spell-effect editor from the repository root."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import pyxel

from app.resources import FontResourceError, ImageResourceError
from scripts.spell_effect_pipeline import SpellEffectSourceError
from tools.spell_effect_editor.app import SpellEffectEditor


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pyxel呪文エフェクト設定ツール")
    parser.add_argument(
        "--content-root",
        type=Path,
        default=Path(os.environ.get("DA0_CONTENT_DIR", PROJECT_ROOT / "content")),
        help=argparse.SUPPRESS,
    )
    return parser.parse_args(argv)


def run_editor(*, content_root: Path) -> None:
    editor = SpellEffectEditor(PROJECT_ROOT, content_root=content_root)
    pyxel.run(editor.update, editor.draw)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        run_editor(content_root=args.content_root.resolve())
        return 0
    except (FontResourceError, ImageResourceError, SpellEffectSourceError, ValueError) as error:
        print(error)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
