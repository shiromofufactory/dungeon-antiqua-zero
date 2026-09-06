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


def _condition_is_valid(value: object) -> bool:
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
            and all(_condition_is_valid(child) for child in children)
        )
    if condition_type == "not":
        return set(value) == {"type", "condition"} and _condition_is_valid(
            value.get("condition")
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
            if (
                set(command) != {"command", "item_key", "quantity"}
                or not isinstance(command.get("item_key"), str)
                or not command["item_key"]
                or not _positive_integer(command.get("quantity"))
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
        elif command_type == "recover_party":
            if set(command) != {"command"}:
                return False
        elif command_type == "open_shop":
            if set(command) != {"command", "shop_key"} or not isinstance(
                command.get("shop_key"), str
            ) or not command["shop_key"]:
                return False
        elif command_type in ("move_party", "move_actor"):
            fields = {"command", "direction", "steps"}
            if command_type == "move_actor":
                fields.add("actor_id")
            if (
                set(command) != fields
                or command.get("direction") not in MOVEMENT_DIRECTIONS
                or not _positive_integer(command.get("steps"), maximum=255)
            ):
                return False
            if command_type == "move_actor" and (
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


class EventCatalog:
    """Own immutable, fully qualified event definitions."""

    def __init__(
        self,
        events: Mapping[str, EventDefinition] | None = None,
        *,
        flag_ids: frozenset[str] = frozenset(),
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
        self._events = MappingProxyType(normalized)
        self._flag_ids = flag_ids

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(self._events)

    @property
    def flag_ids(self) -> frozenset[str]:
        return self._flag_ids

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
        if set(document) != {"format_version", "source_sha256", "flags", "events"}:
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
        return cls(loaded, flag_ids=frozenset(flag_values))


__all__ = [
    "EVENT_FORMAT_VERSION",
    "EventCatalog",
    "EventDefinition",
    "EventResourceError",
]
