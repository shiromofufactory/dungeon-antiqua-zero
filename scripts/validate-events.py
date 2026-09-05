#!/usr/bin/env python3
"""Validate event sources and their master-data references."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

from event_pipeline import (
    event_source_paths,
    load_event_flags,
    load_event_messages,
    load_event_source,
    reference_catalogs,
    validate_event_sources,
    validate_event_flags,
    validate_event_messages,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description="content/eventsのイベント定義を検証します。")
    parser.add_argument("--content-root", type=Path, default=Path(os.environ.get("DA0_CONTENT_DIR", PROJECT_ROOT / "content")))
    args = parser.parse_args()
    content_root = args.content_root.resolve()
    try:
        paths = event_source_paths(content_root)
        sources = {path.stem: load_event_source(path) for path in paths}
        flags = load_event_flags(content_root)
        messages = load_event_messages(content_root)
        catalogs = reference_catalogs(
            content_root, app_root=PROJECT_ROOT / "app"
        )
        diagnostics = [
            *validate_event_flags(flags),
            *validate_event_messages(
                messages,
                character_keys=catalogs["character_keys"],
            ),
            *validate_event_sources(
                sources,
                **catalogs,
            ),
        ]
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    for path in paths:
        print(path.relative_to(content_root).as_posix())
    for item in diagnostics:
        print(f"  {item.severity.upper()} {item.path}: {item.message}")
    errors = sum(item.severity == "error" for item in diagnostics)
    warnings = sum(item.severity == "warning" for item in diagnostics)
    print(
        f"検証完了: {len(paths)} event source, {len(flags)} flag, "
        f"{len(messages)} message, "
        f"{errors} error, {warnings} warning"
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
