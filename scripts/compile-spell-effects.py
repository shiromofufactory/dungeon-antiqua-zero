#!/usr/bin/env python3
"""Validate or compile authoring-time spell-effect settings."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.spell_effect_pipeline import (  # noqa: E402
    SpellEffectSourceError,
    compile_document,
    load_project_catalogs,
    load_source,
    save_compiled,
    validate_document,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="呪文エフェクト制作設定を検証・生成します。"
    )
    parser.add_argument(
        "--content-root",
        type=Path,
        default=Path(os.environ.get("DA0_CONTENT_DIR", PROJECT_ROOT / "content")),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "app" / "effects" / "spells.json",
    )
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    content_root = args.content_root.resolve()
    source_path = content_root / "effects" / "spells.json"
    try:
        catalogs = load_project_catalogs(PROJECT_ROOT, content_root=content_root)
        source = load_source(source_path)
        diagnostics = validate_document(source, catalogs)
        for item in diagnostics:
            label = f"{item.spell_key}: " if item.spell_key else ""
            print(f"[{item.severity}] {label}{item.message}")
        compiled = compile_document(source, catalogs)
        if not args.validate_only:
            save_compiled(args.output.resolve(), compiled)
    except (OSError, SpellEffectSourceError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1

    configured = len(compiled["effects"])
    if args.validate_only:
        print(f"検証完了: {configured}件の呪文エフェクト設定")
    else:
        print(f"生成完了: {configured}件 → {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
