"""Load generated array-form game data shared by the game and tools."""

from __future__ import annotations

import json
from pathlib import Path


class DataResourceError(RuntimeError):
    """Raised when generated game data cannot be loaded as record arrays."""


def load_record_array(
    filename: str,
    data_dir: Path | None = None,
) -> list[dict[str, object]]:
    """Load one generated JSON file whose root must be an object array."""

    if not isinstance(filename, str) or not filename:
        raise ValueError("filename must be a non-empty string")
    if Path(filename).name != filename:
        raise ValueError("filename must not contain a directory")
    if data_dir is not None and not isinstance(data_dir, Path):
        raise TypeError("data_dir must be a pathlib.Path or None")

    app_dir = Path(__file__).resolve().parents[1]
    path = (data_dir or app_dir / "data") / filename
    try:
        records = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise DataResourceError(f"ゲームデータがありません: {path}") from error
    except json.JSONDecodeError as error:
        raise DataResourceError(
            f"ゲームデータを読み込めません: {path}: {error}"
        ) from error

    if not isinstance(records, list) or not all(
        isinstance(record, dict) for record in records
    ):
        raise DataResourceError(
            f"{filename}のルートはオブジェクトの配列である必要があります"
        )
    return records


__all__ = ["DataResourceError", "load_record_array"]
