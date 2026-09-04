#!/usr/bin/env python3
"""Compile event source files into one runtime catalog."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

from event_pipeline import (
    compile_event_sources,
    event_source_paths,
    load_event_source,
    reference_catalogs,
    save_compiled_events,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description="制作用イベントからゲーム用イベントを生成します。")
    parser.add_argument("--content-root", type=Path, default=Path(os.environ.get("DA0_CONTENT_DIR", PROJECT_ROOT / "content")))
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "app" / "events" / "events.json")
    args = parser.parse_args()
    try:
        content_root = args.content_root.resolve()
        paths = event_source_paths(content_root)
        sources = {path.stem: load_event_source(path) for path in paths}
        compiled = compile_event_sources(
            sources,
            **reference_catalogs(content_root, app_root=PROJECT_ROOT / "app"),
        )
        save_compiled_events(args.output.resolve(), compiled)
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    print(f"生成完了: {len(compiled['events'])} event → {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
