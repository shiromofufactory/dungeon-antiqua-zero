"""Validated debug-only dungeon definitions and map-free exploration progress."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import random
import re
from typing import Collection

if __package__:
    from .resources.maps import MapActor, MapCell, MapRandomEncounter, MapTreasureContents
else:
    from resources.maps import MapActor, MapCell, MapRandomEncounter, MapTreasureContents


DEFAULT_PATH = Path(__file__).resolve().parent / "debug" / "dungeons.json"
ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
DEFAULT_ENCOUNTER = {
    "monster_level": 1, "danger": "low", "polarity": "neutral",
    "allow_demons": False, "allow_humans": False,
    "allow_giants": False, "allow_large_animals": True,
}


class DebugDungeonDataError(ValueError):
    """Invalid debug dungeon source or reference."""


@dataclass(frozen=True)
class DungeonStep:
    id: str
    type: str
    count: int = 1
    encounter: MapRandomEncounter | None = None
    contents: MapTreasureContents | None = None
    battle_id: str | None = None

    def treasure_actor(self) -> MapActor:
        return MapActor(self.id, MapCell(0, 0), "treasure", 0, contents=self.contents)


@dataclass(frozen=True)
class DebugDungeon:
    id: str
    name: str
    bgm_id: str
    steps: tuple[DungeonStep, ...]

    @property
    def treasure_map_id(self) -> str:
        # A dot prevents collisions with real map IDs (which use underscores).
        return f"debug_dungeon.{self.id}"


def _require(condition: bool, path: str, message: str) -> None:
    if not condition:
        raise DebugDungeonDataError(f"{path}: {message}")


def _fields(value: object, expected: set[str], path: str) -> dict:
    _require(isinstance(value, dict), path, "objectが必要です")
    _require(set(value) == expected, path, f"必要な項目: {', '.join(sorted(expected))}")
    return value


def _id(value: object, path: str) -> str:
    _require(isinstance(value, str) and ID_PATTERN.fullmatch(value) is not None,
             path, "英小文字で始まる英小文字・数字・_のIDが必要です")
    return value


def _integer(value: object, low: int, high: int, path: str) -> int:
    _require(type(value) is int and low <= value <= high,
             path, f"{low}〜{high}の整数が必要です")
    return value


def parse_dungeons(
    document: object, *, item_keys: Collection[str] | None = None,
    battle_ids: Collection[str] = (), bgm_ids: Collection[str] | None = None,
) -> tuple[DebugDungeon, ...]:
    root = _fields(document, {"format_version", "dungeons"}, "root")
    _require(type(root["format_version"]) is int and root["format_version"] == 1,
             "format_version", "version 1が必要です")
    _require(isinstance(root["dungeons"], list), "dungeons", "配列が必要です")
    result = []
    dungeon_ids = set()
    for index, raw in enumerate(root["dungeons"]):
        path = f"dungeons[{index}]"
        raw = _fields(raw, {"id", "name", "bgm_id", "steps"}, path)
        dungeon_id = _id(raw["id"], f"{path}.id")
        _require(dungeon_id not in dungeon_ids, path, "ダンジョンIDが重複しています")
        dungeon_ids.add(dungeon_id)
        _require(isinstance(raw["name"], str) and bool(raw["name"].strip())
                 and len(raw["name"]) <= 24 and not any(c in raw["name"] for c in "\r\n"),
                 path, "名前は空白だけでない24文字以内の1行にしてください")
        bgm = raw["bgm_id"]
        _require(isinstance(bgm, str) and bool(bgm) and (bgm_ids is None or bgm in bgm_ids),
                 path, "存在するBGMを指定してください")
        _require(isinstance(raw["steps"], list), path, "stepsには配列が必要です")
        steps = []
        step_ids = set()
        for step_index, step in enumerate(raw["steps"]):
            current = f"{path}.steps[{step_index}]"
            _require(isinstance(step, dict), current, "objectが必要です")
            kind = step.get("type")
            _require(kind in ("random_encounter", "treasure", "event_battle"),
                     current, "種類が不正です")
            extra = {"random_encounter": {"count", "encounter"},
                     "treasure": {"contents"}, "event_battle": {"battle_id"}}[kind]
            _fields(step, {"id", "type"} | extra, current)
            step_id = _id(step["id"], current)
            _require(step_id not in step_ids, current, "ステップIDが重複しています")
            step_ids.add(step_id)
            if kind == "random_encounter":
                count = _integer(step["count"], 1, 9999, current)
                settings = _fields(step["encounter"], set(DEFAULT_ENCOUNTER), current)
                level = settings["monster_level"]
                _require(level == "dynamic" or (type(level) is int and 1 <= level <= 9),
                         current, "モンスターレベルは1〜9またはdynamicです")
                _require(settings["danger"] in ("low", "high"), current, "危険度が不正です")
                _require(settings["polarity"] in ("yang", "neutral", "yin"), current, "傾向が不正です")
                for key in ("allow_demons", "allow_humans", "allow_giants", "allow_large_animals"):
                    _require(type(settings[key]) is bool, current, f"{key}にはbooleanが必要です")
                steps.append(DungeonStep(step_id, kind, count=count, encounter=MapRandomEncounter(**settings)))
            elif kind == "treasure":
                contents = step["contents"]
                _require(isinstance(contents, dict), current, "contentsにはobjectが必要です")
                if contents.get("type") == "gold":
                    _fields(contents, {"type", "amount"}, current)
                    _integer(contents["amount"], 1, 999999, current)
                else:
                    _fields(contents, {"type", "item_key"}, current)
                    key = contents["item_key"]
                    _require(contents["type"] == "item" and isinstance(key, str) and bool(key)
                             and (item_keys is None or key in item_keys), current, "アイテムが不正です")
                steps.append(DungeonStep(step_id, kind, contents=MapTreasureContents(**contents)))
            else:
                battle_id = _id(step["battle_id"], current)
                _require(battle_id in battle_ids, current, f"未登録のイベントバトルです: {battle_id}")
                steps.append(DungeonStep(step_id, kind, battle_id=battle_id))
        result.append(DebugDungeon(dungeon_id, raw["name"], bgm, tuple(steps)))
    return tuple(result)


def load_dungeons(path: Path = DEFAULT_PATH, **catalogs) -> tuple[DebugDungeon, ...]:
    if not path.exists():
        return ()
    try:
        return parse_dungeons(json.loads(path.read_text(encoding="utf-8")), **catalogs)
    except (OSError, ValueError) as error:
        raise DebugDungeonDataError(str(error)) from error


class DungeonProgress:
    """One visit; only treasure ownership lives beyond this object."""

    def __init__(self, dungeon: DebugDungeon, *, random_source=None) -> None:
        self.dungeon = dungeon
        self.index = 0
        self.completed_in_step = 0
        self.fade_active = False
        self.random = random_source or random.Random()

    @property
    def current(self) -> DungeonStep | None:
        return self.dungeon.steps[self.index] if self.index < len(self.dungeon.steps) else None

    @property
    def remaining_battles(self) -> int:
        return sum(step.count if step.type == "random_encounter" else int(step.type == "event_battle")
                   for step in self.dungeon.steps[self.index:]) - self.completed_in_step

    def complete(self) -> None:
        step = self.current
        if step is None:
            raise RuntimeError("dungeon is already finished")
        self.completed_in_step += 1
        if self.completed_in_step == step.count:
            self.index += 1
            self.completed_in_step = 0

    def activate_fade(self) -> bool:
        if self.fade_active:
            return False
        self.fade_active = True
        return True

    def skip_random_battle(self) -> bool:
        return bool(self.current and self.current.type == "random_encounter"
                    and self.fade_active and self.random.randrange(2) == 0)


def reset_treasures(dungeon: DebugDungeon, opened: set[tuple[str, str]]) -> None:
    opened.difference_update(pair for pair in tuple(opened) if pair[0] == dungeon.treasure_map_id)
