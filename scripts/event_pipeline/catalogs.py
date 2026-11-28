"""Load stable IDs referenced by event source files."""

from __future__ import annotations

import json
from pathlib import Path

from app.audio_catalog import load_sound_effects
from app.item import EquipmentSlot
from app.member import CharacterType

from .flags import load_event_flags, registered_event_flag_ids


def _load_records(path: Path) -> list[dict[str, object]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError(f"{path}のルートは配列である必要があります。")
    return [record for record in value if isinstance(record, dict)]


def _record_keys(path: Path, field: str) -> set[str]:
    return {
        record[field]
        for record in _load_records(path)
        if isinstance(record.get(field), str)
    }


def _se_ids(path: Path) -> set[str]:
    return set(load_sound_effects(path))


def reference_catalogs(
    content_root: Path,
    *,
    app_root: Path,
) -> dict[str, set[str] | dict[str, set[str]]]:
    """Return every stable ID list shared by validation and authoring tools."""

    audio_dir = app_root / "audio"
    message_path = content_root / "events" / "messages.json"
    characters = {
        record["name_en"]: record.get("type")
        for record in _load_records(content_root / "data" / "characters.json")
        if isinstance(record.get("name_en"), str)
    }
    items = {
        record["name_en"]: record.get("type1")
        for record in _load_records(content_root / "data" / "items.json")
        if isinstance(record.get("name_en"), str)
    }
    return {
        "character_keys": set(characters),
        "npc_keys": {key for key, kind in characters.items() if kind == CharacterType.NPC},
        "item_keys": set(items),
        "equipment_item_keys_by_slot": {
            slot.value: {
                key for key, kind in items.items()
                if isinstance(kind, str) and slot.accepts(kind)
            }
            for slot in EquipmentSlot
        },
        "shop_keys": _record_keys(
            content_root / "data" / "shops.json", "shop_key"
        ),
        "monster_keys": _record_keys(
            content_root / "data" / "monsters.json", "name_en"
        ),
        "flag_ids": registered_event_flag_ids(load_event_flags(content_root)),
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
