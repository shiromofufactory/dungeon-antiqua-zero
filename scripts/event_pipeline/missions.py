"""Ordered mission sources sharing event conditions and message references."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Mapping

from .events import (
    EventDiagnostic,
    EventSourceError,
    LOCAL_ID_PATTERN,
    _atomic_write,
    _diagnostic,
    _known_fields,
    _validate_condition,
)


def load_missions(content_root: Path) -> object:
    path = content_root / "events" / "missions.json"
    if not path.is_file():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise EventSourceError(f"ミッションJSONを読み込めません: {path}: {error}") from error


def validate_missions(
    missions: object,
    *,
    flag_ids: Iterable[str] = (),
    character_keys: Iterable[str] = (),
    item_keys: Iterable[str] = (),
    message_ids: Iterable[str] = (),
    **unused_catalogs: Iterable[str],
) -> list[EventDiagnostic]:
    diagnostics: list[EventDiagnostic] = []
    if not isinstance(missions, list):
        _diagnostic(diagnostics, "error", "invalid_missions", "missions", "ミッションは配列で指定してください。")
        return diagnostics
    seen: set[str] = set()
    messages = set(message_ids)
    flags = set(flag_ids)
    characters = set(character_keys)
    items = set(item_keys)
    for index, mission in enumerate(missions):
        path = f"missions[{index}]"
        if not isinstance(mission, Mapping):
            _diagnostic(diagnostics, "error", "invalid_mission", path, "ミッションはobjectで指定してください。")
            continue
        _known_fields(mission, {"id", "note", "condition", "message_id"}, diagnostics, path)
        mission_id = mission.get("id")
        if not isinstance(mission_id, str) or not LOCAL_ID_PATTERN.fullmatch(mission_id):
            _diagnostic(diagnostics, "error", "invalid_mission_id", f"{path}.id", "ミッションIDはlower_snake_caseで指定してください。")
        elif mission_id in seen:
            _diagnostic(diagnostics, "error", "duplicate_mission_id", f"{path}.id", f"ミッションIDが重複しています: {mission_id}")
        else:
            seen.add(mission_id)
        if "note" in mission and not isinstance(mission["note"], str):
            _diagnostic(diagnostics, "error", "invalid_note", f"{path}.note", "noteは文字列で指定してください。")
        if "condition" in mission:
            _validate_condition(
                mission["condition"], diagnostics, f"{path}.condition",
                flag_ids=flags, character_keys=characters, item_keys=items,
            )
        message_id = mission.get("message_id")
        if not isinstance(message_id, str) or message_id not in messages:
            _diagnostic(diagnostics, "error", "unknown_message", f"{path}.message_id", f"存在しないイベントメッセージです: {message_id}")
    return diagnostics


def save_missions(path: Path, missions: object) -> None:
    _atomic_write(path, (json.dumps(missions, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
