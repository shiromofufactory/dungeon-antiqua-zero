"""Load stable IDs referenced by event source files."""

from __future__ import annotations

import json
from pathlib import Path


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
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("format_version") != 1:
        raise ValueError(f"{path}のformat_versionが不正です。")
    records = value.get("sound_effects")
    if not isinstance(records, dict) or not records:
        raise ValueError(f"{path}のsound_effectsが不正です。")
    for se_id, record in records.items():
        if not isinstance(se_id, str) or not se_id or not isinstance(record, dict):
            raise ValueError(f"{path}のSEレコードが不正です。")
        if not all(
            isinstance(record.get(field), int)
            and not isinstance(record[field], bool)
            and record[field] >= 0
            for field in ("channel", "sound")
        ):
            raise ValueError(f"{path}のSE channelまたはsoundが不正です: {se_id}")
    return set(records)


def reference_catalogs(
    content_root: Path,
    *,
    app_root: Path,
) -> dict[str, set[str]]:
    """Return every stable ID list shared by validation and authoring tools."""

    audio_dir = app_root / "audio"
    return {
        "character_keys": _record_keys(
            content_root / "data" / "characters.json", "name_en"
        ),
        "item_keys": _record_keys(content_root / "data" / "items.json", "name_en"),
        "text_keys": _record_keys(content_root / "data" / "texts.json", "text_key"),
        "bgm_ids": {
            path.relative_to(audio_dir).with_suffix("").as_posix()
            for path in audio_dir.rglob("*.ogg")
        }
        if audio_dir.is_dir()
        else set(),
        "se_ids": _se_ids(audio_dir / "catalog.json"),
    }


__all__ = ["reference_catalogs"]
