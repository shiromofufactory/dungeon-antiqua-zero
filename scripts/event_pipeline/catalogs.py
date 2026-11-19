"""Load stable IDs referenced by event source files."""

from __future__ import annotations

import json
from pathlib import Path

from app.audio_catalog import load_sound_effects

def _record_keys(path: Path, field: str) -> set[str]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError(f"{path}のルートは配列である必要があります。")
    return {
        record[field]
        for record in value
        if isinstance(record, dict) and isinstance(record.get(field), str)
    }


def _se_ids(path: Path) -> set[str]:
    return set(load_sound_effects(path))


def reference_catalogs(
    content_root: Path,
    *,
    app_root: Path,
) -> dict[str, set[str]]:
    """Return every stable ID list shared by validation and authoring tools."""

    audio_dir = app_root / "audio"
    flag_path = content_root / "events" / "flags.json"
    message_path = content_root / "events" / "messages.json"
    return {
        "character_keys": _record_keys(
            content_root / "data" / "characters.json", "name_en"
        ),
        "item_keys": _record_keys(content_root / "data" / "items.json", "name_en"),
        "shop_keys": _record_keys(
            content_root / "data" / "shops.json", "shop_key"
        ),
        "monster_keys": _record_keys(
            content_root / "data" / "monsters.json", "name_en"
        ),
        "flag_ids": (
            _record_keys(flag_path, "flag_id")
            if flag_path.is_file()
            else set()
        ),
        "message_ids": (
            _record_keys(message_path, "message_id")
            if message_path.is_file()
            else set()
        ),
        "bgm_ids": {
            path.relative_to(audio_dir).with_suffix("").as_posix()
            for path in audio_dir.rglob("*.ogg")
        }
        if audio_dir.is_dir()
        else set(),
        "se_ids": _se_ids(audio_dir / "catalog.json"),
    }


__all__ = ["reference_catalogs"]
