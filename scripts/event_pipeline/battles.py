"""One authoring definition per event battle, shared by events and debug trials."""

import json
from pathlib import Path
from typing import Iterable

from .events import EventDiagnostic, FULL_ID_PATTERN, LOCAL_ID_PATTERN, _atomic_write, _diagnostic, _known_fields


def load_event_battles(content_root: Path) -> object:
    path = content_root / "events" / "battles.json"
    if not path.is_file():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def validate_event_battles(
    battles: object, *, monster_keys: Iterable[str] = (),
    field_event_ids: Iterable[str] = (), **unused,
) -> list[EventDiagnostic]:
    diagnostics: list[EventDiagnostic] = []
    if not isinstance(battles, list):
        _diagnostic(diagnostics, "error", "invalid_battles", "battles", "イベントバトルは配列で指定してください。")
        return diagnostics
    seen, monsters = set(), set(monster_keys)
    field_events = set(field_event_ids)
    for index, battle in enumerate(battles):
        path = f"battles[{index}]"
        if not isinstance(battle, dict):
            _diagnostic(diagnostics, "error", "invalid_battle", path, "イベントバトルはobjectで指定してください。")
            continue
        _known_fields(battle, {"battle_id", "note", "monster_keys", "defeat_event_id", "mode"}, diagnostics, path)
        battle_id = battle.get("battle_id")
        if not isinstance(battle_id, str) or LOCAL_ID_PATTERN.fullmatch(battle_id) is None:
            _diagnostic(diagnostics, "error", "invalid_battle_id", path, "バトルIDはlower_snake_caseで指定してください。")
        elif battle_id in seen:
            _diagnostic(diagnostics, "error", "duplicate_battle_id", path, f"バトルIDが重複しています: {battle_id}")
        else:
            seen.add(battle_id)
        if "note" in battle and not isinstance(battle["note"], str):
            _diagnostic(diagnostics, "error", "invalid_note", path, "制作メモは文字列で指定してください。")
        if "defeat_event_id" in battle:
            event_id = battle["defeat_event_id"]
            event_path = f"{path}.defeat_event_id"
            if not isinstance(event_id, str) or FULL_ID_PATTERN.fullmatch(event_id) is None:
                _diagnostic(diagnostics, "error", "invalid_defeat_event_id", event_path, "全滅時イベントは完全IDで指定してください。")
            elif event_id not in field_events:
                _diagnostic(diagnostics, "error", "unknown_defeat_event", event_path, f"全滅時イベントは登録済みのフィールドイベントを指定してください: {event_id}")
        mode = battle.get("mode", "normal")
        if mode not in ("normal", "knockout"):
            _diagnostic(diagnostics, "error", "invalid_battle_mode", f"{path}.mode", "バトル形式が不正です。")
        lineup = battle.get("monster_keys")
        minimum = 5 if mode == "knockout" else 1
        if not isinstance(lineup, list) or not minimum <= len(lineup) <= 5:
            message = "勝ち抜き戦の敵は出場順に5体指定してください。" if mode == "knockout" else "敵は1〜5体指定してください。"
            _diagnostic(diagnostics, "error", "invalid_monster_lineup", path, message)
            continue
        for i, key in enumerate(lineup):
            if not isinstance(key, str) or key not in monsters:
                _diagnostic(diagnostics, "error", "unknown_monster", f"{path}.monster_keys[{i}]", f"存在しないモンスターです: {key}")
    return diagnostics


def event_battle_ids(battles: object) -> set[str]:
    return {entry["battle_id"] for entry in battles if isinstance(entry, dict)
            and isinstance(entry.get("battle_id"), str)} if isinstance(battles, list) else set()


def save_event_battles(path: Path, battles: object) -> None:
    _atomic_write(path, (json.dumps(battles, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
