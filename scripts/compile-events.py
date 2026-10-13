#!/usr/bin/env python3
"""Compile event source files into one runtime catalog."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

# app パッケージ（app.audio_catalog など）を読み込めるよう、プロジェクトルートを通す。
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.append(_PROJECT_ROOT)

from event_pipeline import (
    compile_event_flags,
    compile_event_sources,
    compile_event_messages,
    event_source_paths,
    load_missions,
    validate_missions,
    load_event_flags,
    load_event_source,
    load_event_messages,
    reference_catalogs,
    save_compiled_events,
    save_event_messages,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description="制作用イベントからゲーム用イベントを生成します。")
    parser.add_argument("--content-root", type=Path, default=Path(os.environ.get("DA0_CONTENT_DIR", PROJECT_ROOT / "content")))
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "app" / "events" / "events.json")
    parser.add_argument(
        "--messages-output",
        type=Path,
        default=PROJECT_ROOT / "app" / "events" / "messages.json",
    )
    args = parser.parse_args()
    try:
        content_root = args.content_root.resolve()
        paths = event_source_paths(content_root)
        sources = {path.stem: load_event_source(path) for path in paths}
        missions = load_missions(content_root)
        flags = load_event_flags(content_root)
        messages = load_event_messages(content_root)
        compiled_flags = compile_event_flags(flags)
        catalogs = reference_catalogs(
            content_root, app_root=PROJECT_ROOT / "app"
        )
        catalogs["flag_ids"] = set(compiled_flags)
        compiled = compile_event_sources(
            sources,
            missions=missions,
            **catalogs,
        )
        compiled_messages = compile_event_messages(
            messages,
            character_keys=catalogs["character_keys"],
        )
        save_compiled_events(args.output.resolve(), compiled)
        save_event_messages(args.messages_output.resolve(), compiled_messages)
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    print(
        f"生成完了: {len(compiled['events'])} event, "
        f"{len(compiled_flags)} flag, {len(compiled_messages)} message, "
        f"{len(compiled['missions'])} mission "
        f"→ {args.output.resolve()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
