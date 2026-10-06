"""Load the generated event catalog used by the runtime."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from types import MappingProxyType
from typing import Mapping


EVENT_FORMAT_VERSION = 1
EVENT_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
FLAG_ID_PATTERN = re.compile(
    r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*$"
)
MESSAGE_ID_PATTERN = re.compile(
    r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$"
)
LOCAL_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
MOVEMENT_DIRECTIONS = frozenset(("up", "right", "down", "left"))
FLASH_COLORS = frozenset(("white",))


class EventResourceError(RuntimeError):
    """Raised when generated event data is malformed or unavailable."""


def _freeze(value: object) -> object:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _positive_integer(value: object, *, maximum: int | None = None) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and value > 0
        and (maximum is None or value <= maximum)
    )


def _condition_is_valid(value: object, *, depth: int = 0) -> bool:
    if depth > 16:
        return False
    if not isinstance(value, dict) or not isinstance(value.get("type"), str):
        return False
    condition_type = value["type"]
    if condition_type == "flag_set":
        return set(value) == {"type", "flag_id"} and isinstance(
            value.get("flag_id"), str
        ) and FLAG_ID_PATTERN.fullmatch(value["flag_id"]) is not None
    if condition_type == "member_in_party":
        return set(value) == {"type", "character_key"} and isinstance(
            value.get("character_key"), str
        ) and bool(value["character_key"])
    if condition_type == "item_at_least":
        return (
            set(value) == {"type", "item_key", "quantity"}
            and isinstance(value.get("item_key"), str)
            and bool(value["item_key"])
            and _positive_integer(value.get("quantity"))
        )
    if condition_type in ("all", "any"):
        children = value.get("conditions")
        return (
            set(value) == {"type", "conditions"}
            and isinstance(children, list)
            and bool(children)
            and all(_condition_is_valid(child, depth=depth + 1) for child in children)
        )
    if condition_type == "not":
        return set(value) == {"type", "condition"} and _condition_is_valid(
            value.get("condition"), depth=depth + 1
        )
    return False


def _commands_are_valid(value: object, *, depth: int = 0) -> bool:
    if not isinstance(value, list) or depth > 16:
        return False
    for command in value:
        if not isinstance(command, dict):
            return False
        command_type = command.get("command")
        if command_type == "set_flag":
            if set(command) != {"command", "flag_id"} or not isinstance(
                command.get("flag_id"), str
            ) or FLAG_ID_PATTERN.fullmatch(command["flag_id"]) is None:
                return False
        elif command_type in ("join_party", "leave_party"):
            if set(command) != {"command", "character_key"} or not isinstance(
                command.get("character_key"), str
            ) or not command["character_key"]:
                return False
        elif command_type in ("give_item", "take_item"):
            fields = {"command", "item_key", "quantity"}
            if command_type == "give_item" and "show_message" in command:
                fields.add("show_message")
            if (
                set(command) != fields
                or not isinstance(command.get("item_key"), str)
                or not command["item_key"]
                or not _positive_integer(command.get("quantity"))
                or ("show_message" in fields and not isinstance(command["show_message"], bool))
            ):
                return False
        elif command_type == "branch":
            if (
                set(command) != {"command", "condition", "then", "else"}
                or not _condition_is_valid(command.get("condition"))
                or not _commands_are_valid(command.get("then"), depth=depth + 1)
                or not _commands_are_valid(command.get("else"), depth=depth + 1)
            ):
                return False
        elif command_type == "end_event":
            if set(command) != {"command"}:
                return False
        elif command_type == "message":
            if set(command) != {"command", "message_id"}:
                return False
            if (
                not isinstance(command.get("message_id"), str)
                or MESSAGE_ID_PATTERN.fullmatch(command["message_id"]) is None
            ):
                return False
        elif command_type in ("play_se", "change_bgm"):
            key = "se_id" if command_type == "play_se" else "bgm_id"
            if set(command) != {"command", key} or not isinstance(
                command.get(key), str
            ) or not command[key]:
                return False
        elif command_type == "flash_screen":
            color = command.get("color")
            if (
                set(command) != {"command", "color"}
                or not isinstance(color, str)
                or color not in FLASH_COLORS
            ):
                return False
        elif command_type == "wait":
            frames = command.get("frames")
            if (
                set(command) != {"command", "frames"}
                or not _positive_integer(frames)
                or frames % 6 != 0
            ):
                return False
        elif command_type == "recover_party":
            if set(command) != {"command"}:
                return False
        elif command_type == "open_shop":
            if set(command) != {"command", "shop_key"} or not isinstance(
                command.get("shop_key"), str
            ) or not command["shop_key"]:
                return False
        elif command_type == "start_battle":
            lineup = command.get("monster_keys")
            if (
                set(command) != {"command", "battle_id", "monster_keys"}
                or not isinstance(command.get("battle_id"), str)
                or LOCAL_ID_PATTERN.fullmatch(command["battle_id"]) is None
                or not isinstance(lineup, list)
                or not 1 <= len(lineup) <= 5
                or not all(isinstance(key, str) and key for key in lineup)
            ):
                return False
        elif command_type in ("move_party", "move_actor", "face_party", "face_actor"):
            fields = {"command", "direction"}
            if command_type in ("move_party", "move_actor"):
                fields.add("steps")
            if command_type in ("move_actor", "face_actor"):
                fields.add("actor_id")
            if (
                set(command) != fields
                or command.get("direction") not in MOVEMENT_DIRECTIONS
                or ("steps" in fields and not _positive_integer(command.get("steps"), maximum=255))
            ):
                return False
            if command_type in ("move_actor", "face_actor") and (
                not isinstance(command.get("actor_id"), str)
                or LOCAL_ID_PATTERN.fullmatch(command["actor_id"]) is None
            ):
                return False
        else:
            return False
    return True


@dataclass(frozen=True)
class EventDefinition:
    id: str
    commands: tuple[Mapping[str, object], ...]


@dataclass(frozen=True)
class MissionDefinition:
    id: str
    message_id: str
    condition: Mapping[str, object] | None = None


class EventCatalog:
    """Own immutable, fully qualified event definitions."""

    def __init__(
        self,
        events: Mapping[str, EventDefinition] | None = None,
        *,
        flag_ids: frozenset[str] = frozenset(),
        missions: tuple[MissionDefinition, ...] = (),
        battle_start_events: Mapping[str, str] | None = None,
    ) -> None:
        normalized = {} if events is None else dict(events)
        if not all(
            isinstance(key, str)
            and isinstance(value, EventDefinition)
            and value.id == key
            for key, value in normalized.items()
        ):
            raise TypeError("events must map IDs to matching EventDefinition values")
        if not isinstance(flag_ids, frozenset) or not all(
            isinstance(flag_id, str) and FLAG_ID_PATTERN.fullmatch(flag_id)
            for flag_id in flag_ids
        ):
            raise TypeError("flag_ids must be fully qualified event IDs")
        if not isinstance(missions, tuple) or not all(
            isinstance(mission, MissionDefinition) for mission in missions
        ):
            raise TypeError("missions must contain MissionDefinition values")
        self._missions = missions
        self._events = MappingProxyType(normalized)
        self._flag_ids = flag_ids
        triggers = {} if battle_start_events is None else dict(battle_start_events)
        if not all(
            isinstance(battle_id, str)
            and LOCAL_ID_PATTERN.fullmatch(battle_id) is not None
            and event_id in normalized
            for battle_id, event_id in triggers.items()
        ):
            raise TypeError("battle start events must reference known events")
        self._battle_start_events = MappingProxyType(triggers)

    @property
    def missions(self) -> tuple[MissionDefinition, ...]:
        return self._missions

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(self._events)

    @property
    def flag_ids(self) -> frozenset[str]:
        return self._flag_ids

    def battle_start_event(self, battle_id: str) -> str | None:
        return self._battle_start_events.get(battle_id)

    def event(self, event_id: str) -> EventDefinition:
        if not isinstance(event_id, str) or EVENT_ID_PATTERN.fullmatch(event_id) is None:
            raise ValueError("event ID must be namespace.local_id")
        try:
            return self._events[event_id]
        except KeyError as error:
            raise KeyError(f"unknown event: {event_id}") from error

    @classmethod
    def from_json(cls, path: Path | None = None) -> EventCatalog:
        if path is None:
            path = Path(__file__).resolve().parents[1] / "events" / "events.json"
        if not isinstance(path, Path):
            raise TypeError("event catalog path must be a pathlib.Path")
        if not path.is_file():
            return cls()
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise EventResourceError(f"イベントJSONを読み込めません: {path}: {error}") from error
        return cls.from_document(document)

    @classmethod
    def from_document(cls, document: object) -> EventCatalog:
        if not isinstance(document, dict):
            raise EventResourceError("イベントJSONのルートが不正です。")
        if set(document) - {"missions", "battle_start_events"} != {"format_version", "source_sha256", "flags", "events"}:
            raise EventResourceError("イベントJSONのルート属性が不正です。")
        if document.get("format_version") != EVENT_FORMAT_VERSION:
            raise EventResourceError("イベントJSONのformat_versionが不正です。")
        source_hash = document.get("source_sha256")
        if (
            not isinstance(source_hash, str)
            or re.fullmatch(r"[0-9a-f]{64}", source_hash) is None
        ):
            raise EventResourceError("イベントJSONのsource_sha256が不正です。")
        flag_values = document.get("flags")
        if not isinstance(flag_values, list) or not all(
            isinstance(value, str) and FLAG_ID_PATTERN.fullmatch(value)
            for value in flag_values
        ) or len(flag_values) != len(set(flag_values)):
            raise EventResourceError("イベントJSONのflagsが不正です。")
        event_values = document.get("events")
        if not isinstance(event_values, dict):
            raise EventResourceError("イベントJSONのeventsが不正です。")
        loaded: dict[str, EventDefinition] = {}
        for event_id, event in event_values.items():
            if not isinstance(event_id, str) or EVENT_ID_PATTERN.fullmatch(event_id) is None:
                raise EventResourceError(f"イベントIDが不正です: {event_id}")
            if not isinstance(event, dict) or set(event) != {"commands"}:
                raise EventResourceError(f"イベント定義が不正です: {event_id}")
            commands = event.get("commands")
            if not _commands_are_valid(commands):
                raise EventResourceError(f"イベントcommandsが不正です: {event_id}")
            frozen = _freeze(commands)
            if not isinstance(frozen, tuple):
                raise AssertionError("event commands must freeze to a tuple")
            loaded[event_id] = EventDefinition(event_id, frozen)
        mission_values = document.get("missions", [])
        if not isinstance(mission_values, list):
            raise EventResourceError("ミッション一覧が不正です。")
        missions: list[MissionDefinition] = []
        seen: set[str] = set()
        for mission in mission_values:
            if not isinstance(mission, dict) or set(mission) - {"condition"} != {"id", "message_id"}:
                raise EventResourceError("ミッション定義が不正です。")
            mission_id = mission.get("id")
            message_id = mission.get("message_id")
            if (
                not isinstance(mission_id, str)
                or not LOCAL_ID_PATTERN.fullmatch(mission_id)
                or mission_id in seen
            ):
                raise EventResourceError("ミッションIDが不正です。")
            if not isinstance(message_id, str) or not MESSAGE_ID_PATTERN.fullmatch(message_id):
                raise EventResourceError("ミッションメッセージIDが不正です。")
            if "condition" in mission and not _condition_is_valid(mission["condition"]):
                raise EventResourceError("ミッション条件が不正です。")
            seen.add(mission_id)
            missions.append(MissionDefinition(
                mission_id, message_id, _freeze(mission.get("condition"))
            ))
        battle_start_events = document.get("battle_start_events", {})
        if not isinstance(battle_start_events, dict) or not all(
            isinstance(battle_id, str)
            and LOCAL_ID_PATTERN.fullmatch(battle_id) is not None
            and isinstance(event_id, str)
            and event_id in loaded
            for battle_id, event_id in battle_start_events.items()
        ):
            raise EventResourceError("バトル開始イベントの定義が不正です。")
        return cls(loaded, flag_ids=frozenset(flag_values), missions=tuple(missions), battle_start_events=battle_start_events)


__all__ = [
    "EVENT_FORMAT_VERSION",
    "EventCatalog",
    "EventDefinition",
    "EventResourceError",
    "MissionDefinition",
]
