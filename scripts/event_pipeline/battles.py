"""One authoring definition per event battle, shared by events and debug trials."""

import json
from pathlib import Path
from typing import Iterable

from .events import EventDiagnostic, LOCAL_ID_PATTERN, _atomic_write, _diagnostic, _known_fields


def load_event_battles(content_root: Path) -> object:
    path = content_root / "events" / "battles.json"
    if not path.is_file():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def validate_event_battles(
    battles: object, *, monster_keys: Iterable[str] = (),
    tall_first_monster_keys: Iterable[str] = (), **unused,
) -> list[EventDiagnostic]:
    diagnostics: list[EventDiagnostic] = []
    if not isinstance(battles, list):
        _diagnostic(diagnostics, "error", "invalid_battles", "battles", "イベントバトルは配列で指定してください。")
        return diagnostics
    seen, monsters, tall = set(), set(monster_keys), set(tall_first_monster_keys)
    for index, battle in enumerate(battles):
        path = f"battles[{index}]"
        if not isinstance(battle, dict):
            _diagnostic(diagnostics, "error", "invalid_battle", path, "イベントバトルはobjectで指定してください。")
            continue
        _known_fields(battle, {"battle_id", "note", "monster_keys"}, diagnostics, path)
        battle_id = battle.get("battle_id")
        if not isinstance(battle_id, str) or LOCAL_ID_PATTERN.fullmatch(battle_id) is None:
            _diagnostic(diagnostics, "error", "invalid_battle_id", path, "バトルIDはlower_snake_caseで指定してください。")
        elif battle_id in seen:
            _diagnostic(diagnostics, "error", "duplicate_battle_id", path, f"バトルIDが重複しています: {battle_id}")
        else:
            seen.add(battle_id)
        if "note" in battle and not isinstance(battle["note"], str):
            _diagnostic(diagnostics, "error", "invalid_note", path, "制作メモは文字列で指定してください。")
        lineup = battle.get("monster_keys")
        if not isinstance(lineup, list) or not 1 <= len(lineup) <= 5:
            _diagnostic(diagnostics, "error", "invalid_monster_lineup", path, "敵は1〜5体指定してください。")
            continue
        for i, key in enumerate(lineup):
            if not isinstance(key, str) or key not in monsters:
                _diagnostic(diagnostics, "error", "unknown_monster", f"{path}.monster_keys[{i}]", f"存在しないモンスターです: {key}")
        if len(lineup) == 5 and isinstance(lineup[0], str) and lineup[0] in tall:
            _diagnostic(diagnostics, "error", "oversized_monster_lineup", path, "先頭が64×96のモンスターの場合、敵は4体までです。")
    return diagnostics


def event_battle_ids(battles: object) -> set[str]:
    return {entry["battle_id"] for entry in battles if isinstance(entry, dict)
            and isinstance(entry.get("battle_id"), str)} if isinstance(battles, list) else set()


def save_event_battles(path: Path, battles: object) -> None:
    _atomic_write(path, (json.dumps(battles, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
