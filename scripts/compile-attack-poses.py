#!/usr/bin/env python3
"""Validate or compile authoring-time attack-pose settings."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Mapping


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.attack_pose import (  # noqa: E402
    ATTACK_POSE_FORMAT_VERSION,
    AttackPoseDataError,
    AttackPoseDefinition,
    load_attack_poses,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="攻撃ポーズ制作設定を検証・生成します。"
    )
    parser.add_argument(
        "--content-root",
        type=Path,
        default=Path(os.environ.get("DA0_CONTENT_DIR", PROJECT_ROOT / "content")),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "app" / "effects" / "attack_poses.json",
    )
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args(argv)


def _save(path: Path, poses: Mapping[str, AttackPoseDefinition]) -> None:
    document = {
        "format_version": ATTACK_POSE_FORMAT_VERSION,
        "poses": [pose.to_record() for pose in poses.values()],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as temporary:
        json.dump(document, temporary, ensure_ascii=False, indent=2)
        temporary.write("\n")
        temporary_path = Path(temporary.name)
    temporary_path.replace(path)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    source = args.content_root.resolve() / "battle" / "attack_poses.json"
    try:
        poses = load_attack_poses(source)
        if not args.validate_only:
            _save(args.output.resolve(), poses)
    except (OSError, AttackPoseDataError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    if args.validate_only:
        print(f"検証完了: {len(poses)}件の攻撃ポーズ設定")
    else:
        print(f"生成完了: {len(poses)}件 → {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
