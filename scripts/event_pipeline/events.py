"""Validate, compile, and persist authoring-time event sources."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import tempfile
from typing import Any, Iterable, Mapping, Sequence


EVENT_SOURCE_FORMAT_VERSION = 1
EVENT_RUNTIME_FORMAT_VERSION = 1
MAX_BRANCH_DEPTH = 16
LOCAL_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
FULL_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
CHARACTER_KEY_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9 _+!&'\-]*$")
CARDINAL_DIRECTIONS = frozenset(("up", "right", "down", "left"))
FLASH_COLORS = frozenset(("white",))
LAUNCH_MODES = frozenset(("normal", "exhibition", "demo", "beta"))


class EventSourceError(ValueError):
    """Raised when event source data cannot be compiled."""


@dataclass(frozen=True)
class EventDiagnostic:
    severity: str
    code: str
    path: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity,
            "code": self.code,
            "path": self.path,
            "message": self.message,
        }


def _diagnostic(
    diagnostics: list[EventDiagnostic],
    severity: str,
    code: str,
    path: str,
    message: str,
) -> None:
    diagnostics.append(EventDiagnostic(severity, code, path, message))


def _is_positive_int(value: object, *, maximum: int | None = None) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and value > 0
        and (maximum is None or value <= maximum)
    )


def _known_fields(
    value: Mapping[str, object],
    allowed: set[str],
    diagnostics: list[EventDiagnostic],
    path: str,
) -> None:
    for field in value.keys() - allowed:
        _diagnostic(
            diagnostics,
            "error",
            "unknown_field",
            f"{path}.{field}",
            f"未対応の属性です: {field}",
        )


def event_source_paths(content_root: Path) -> tuple[Path, ...]:
    directory = content_root / "events"
    return (
        tuple(
            path
            for path in sorted(directory.glob("*.json"))
            if path.name not in {"flags.json", "messages.json", "missions.json"}
        )
        if directory.is_dir()
        else ()
    )


def load_event_source(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise EventSourceError(
            f"イベントJSONを読み込めません: {path}: {error}"
        ) from error
    if not isinstance(value, dict):
        raise EventSourceError("イベントJSONのルートはobjectである必要があります。")
    return value


def load_event_sources(content_root: Path) -> dict[str, dict[str, Any]]:
    loaded: dict[str, dict[str, Any]] = {}
    for path in event_source_paths(content_root):
        source = load_event_source(path)
        loaded[path.stem] = source
    return loaded


def _validate_condition(
    value: object,
    diagnostics: list[EventDiagnostic],
    path: str,
    *,
    flag_ids: set[str],
    character_keys: set[str],
    item_keys: set[str],
    depth: int = 0,
) -> None:
    if not isinstance(value, Mapping):
        _diagnostic(diagnostics, "error", "invalid_condition", path, "conditionはobjectで指定してください。")
        return
    if depth > MAX_BRANCH_DEPTH:
        _diagnostic(diagnostics, "error", "condition_too_deep", path, f"条件の入れ子は{MAX_BRANCH_DEPTH}段までです。")
        return
    condition_type = value.get("type")
    if condition_type == "launch_mode":
        _known_fields(value, {"type", "mode"}, diagnostics, path)
        mode = value.get("mode")
        if not isinstance(mode, str) or mode not in LAUNCH_MODES:
            _diagnostic(diagnostics, "error", "invalid_launch_mode", f"{path}.mode", "modeはnormal、exhibition、demo、betaのいずれかで指定してください。")
    elif condition_type == "any_member_dead":
        _known_fields(value, {"type"}, diagnostics, path)
    elif condition_type == "flag_set":
        _known_fields(value, {"type", "flag_id"}, diagnostics, path)
        flag_id = value.get("flag_id")
        if not isinstance(flag_id, str) or flag_id not in flag_ids:
            _diagnostic(diagnostics, "error", "unknown_flag", f"{path}.flag_id", f"宣言されていないフラグです: {flag_id}")
    elif condition_type == "member_in_party":
        _known_fields(value, {"type", "character_key"}, diagnostics, path)
        key = value.get("character_key")
        if not isinstance(key, str) or key not in character_keys:
            _diagnostic(diagnostics, "error", "unknown_character", f"{path}.character_key", f"存在しないキャラクターです: {key}")
    elif condition_type == "item_at_least":
        _known_fields(value, {"type", "item_key", "quantity"}, diagnostics, path)
        key = value.get("item_key")
        if not isinstance(key, str) or key not in item_keys:
            _diagnostic(diagnostics, "error", "unknown_item", f"{path}.item_key", f"存在しないアイテムです: {key}")
        if not _is_positive_int(value.get("quantity")):
            _diagnostic(diagnostics, "error", "invalid_quantity", f"{path}.quantity", "quantityは1以上の整数で指定してください。")
    elif condition_type in ("all", "any"):
        _known_fields(value, {"type", "conditions"}, diagnostics, path)
        children = value.get("conditions")
        if not isinstance(children, list) or not children:
            _diagnostic(diagnostics, "error", "empty_condition_group", f"{path}.conditions", "conditionsは1件以上必要です。")
        else:
            for index, child in enumerate(children):
                _validate_condition(
                    child,
                    diagnostics,
                    f"{path}.conditions[{index}]",
                    flag_ids=flag_ids,
                    character_keys=character_keys,
                    item_keys=item_keys,
                    depth=depth + 1,
                )
    elif condition_type == "not":
        _known_fields(value, {"type", "condition"}, diagnostics, path)
        _validate_condition(
            value.get("condition"),
            diagnostics,
            f"{path}.condition",
            flag_ids=flag_ids,
            character_keys=character_keys,
            item_keys=item_keys,
            depth=depth + 1,
        )
    else:
        _diagnostic(diagnostics, "error", "unknown_condition", f"{path}.type", f"未対応のconditionです: {condition_type}")


def _validate_command_list(
    value: object,
    diagnostics: list[EventDiagnostic],
    path: str,
    *,
    flag_ids: set[str],
    character_keys: set[str],
    item_keys: set[str],
    monster_keys: set[str],
    tall_first_monster_keys: set[str],
    shop_keys: set[str],
    message_ids: set[str],
    bgm_ids: set[str],
    se_ids: set[str],
    depth: int = 0,
    battle_context: bool = False,
) -> None:
    if not isinstance(value, list):
        _diagnostic(diagnostics, "error", "invalid_commands", path, "commandsは配列で指定してください。")
        return
    if not value:
        _diagnostic(diagnostics, "warning", "empty_commands", path, "コマンド列が空です。")
    for index, command in enumerate(value):
        command_path = f"{path}[{index}]"
        if not isinstance(command, Mapping):
            _diagnostic(diagnostics, "error", "invalid_command", command_path, "commandはobjectで指定してください。")
            continue
        command_type = command.get("command")
        if battle_context and command_type in {
            "join_party", "leave_party", "open_shop", "move_party", "move_actor",
            "face_party", "face_actor", "start_battle"
        }:
            _diagnostic(diagnostics, "error", "field_only_battle_command", f"{command_path}.command", f"戦闘開始イベントでは使用できないコマンドです: {command_type}")
        if command_type == "set_flag":
            _known_fields(command, {"command", "flag_id"}, diagnostics, command_path)
            flag_id = command.get("flag_id")
            if not isinstance(flag_id, str) or flag_id not in flag_ids:
                _diagnostic(diagnostics, "error", "unknown_flag", f"{command_path}.flag_id", f"宣言されていないフラグです: {flag_id}")
        elif command_type in ("join_party", "leave_party"):
            _known_fields(command, {"command", "character_key"}, diagnostics, command_path)
            key = command.get("character_key")
            if not isinstance(key, str) or key not in character_keys:
                _diagnostic(diagnostics, "error", "unknown_character", f"{command_path}.character_key", f"存在しないキャラクターです: {key}")
            elif command_type == "leave_party" and key == "Fiora":
                _diagnostic(diagnostics, "error", "cannot_remove_fiora", f"{command_path}.character_key", "フィオラをパーティから外すことはできません。")
        elif command_type in ("give_item", "take_item"):
            fields = {"command", "item_key", "quantity"}
            if command_type == "give_item":
                fields.add("show_message")
                if "show_message" in command and not isinstance(command["show_message"], bool):
                    _diagnostic(diagnostics, "error", "invalid_show_message", f"{command_path}.show_message", "show_messageはtrueまたはfalseで指定してください。")
            _known_fields(command, fields, diagnostics, command_path)
            key = command.get("item_key")
            if not isinstance(key, str) or key not in item_keys:
                _diagnostic(diagnostics, "error", "unknown_item", f"{command_path}.item_key", f"存在しないアイテムです: {key}")
            if not _is_positive_int(command.get("quantity")):
                _diagnostic(diagnostics, "error", "invalid_quantity", f"{command_path}.quantity", "quantityは1以上の整数で指定してください。")
        elif command_type == "branch":
            _known_fields(command, {"command", "condition", "then", "else"}, diagnostics, command_path)
            if depth >= MAX_BRANCH_DEPTH:
                _diagnostic(diagnostics, "error", "branch_too_deep", command_path, f"branchの入れ子は{MAX_BRANCH_DEPTH}段までです。")
                continue
            _validate_condition(command.get("condition"), diagnostics, f"{command_path}.condition", flag_ids=flag_ids, character_keys=character_keys, item_keys=item_keys)
            for branch_name in ("then", "else"):
                branch = command.get(branch_name)
                if branch_name == "else" and branch == []:
                    continue
                if (
                    branch_name == "then"
                    and branch == []
                    and isinstance(command.get("else"), list)
                    and command["else"]
                ):
                    continue
                _validate_command_list(branch, diagnostics, f"{command_path}.{branch_name}", flag_ids=flag_ids, character_keys=character_keys, item_keys=item_keys, monster_keys=monster_keys, tall_first_monster_keys=tall_first_monster_keys, shop_keys=shop_keys, message_ids=message_ids, bgm_ids=bgm_ids, se_ids=se_ids, depth=depth + 1, battle_context=battle_context)
        elif command_type in ("end_event", "stop_bgm"):
            _known_fields(command, {"command"}, diagnostics, command_path)
        elif command_type == "message":
            _known_fields(command, {"command", "message_id"}, diagnostics, command_path)
            message_id = command.get("message_id")
            if not isinstance(message_id, str) or message_id not in message_ids:
                _diagnostic(diagnostics, "error", "unknown_message", f"{command_path}.message_id", f"存在しないイベントメッセージです: {message_id}")
        elif command_type == "play_se":
            _known_fields(command, {"command", "se_id"}, diagnostics, command_path)
            se_id = command.get("se_id")
            if not isinstance(se_id, str) or se_id not in se_ids:
                _diagnostic(diagnostics, "error", "unknown_se", f"{command_path}.se_id", f"存在しないSE IDです: {se_id}")
        elif command_type == "change_bgm":
            _known_fields(command, {"command", "bgm_id"}, diagnostics, command_path)
            bgm_id = command.get("bgm_id")
            if not isinstance(bgm_id, str) or bgm_id not in bgm_ids:
                _diagnostic(diagnostics, "error", "unknown_bgm", f"{command_path}.bgm_id", f"存在しないBGM IDです: {bgm_id}")
        elif command_type == "flash_screen":
            _known_fields(command, {"command", "color"}, diagnostics, command_path)
            color = command.get("color")
            if not isinstance(color, str) or color not in FLASH_COLORS:
                _diagnostic(diagnostics, "error", "invalid_flash_color", f"{command_path}.color", "フラッシュ色はwhiteを指定してください。")
        elif command_type == "change_brightness":
            _known_fields(command, {"command", "percent"}, diagnostics, command_path)
            percent = command.get("percent")
            if type(percent) is not int or percent not in (0, 25, 50, 75, 100):
                _diagnostic(diagnostics, "error", "invalid_brightness_percent", f"{command_path}.percent", "明るさは0、25、50、75、100の整数で指定してください。")
        elif command_type in ("wait", "shake_screen"):
            _known_fields(command, {"command", "frames"}, diagnostics, command_path)
            frames = command.get("frames")
            if not _is_positive_int(frames) or frames % 6 != 0:
                _diagnostic(diagnostics, "error", f"invalid_{command_type}_frames", f"{command_path}.frames", "framesは6以上の6の倍数の整数で指定してください。")
        elif command_type == "recover_party":
            _known_fields(command, {"command"}, diagnostics, command_path)
        elif command_type == "open_shop":
            _known_fields(command, {"command", "shop_key"}, diagnostics, command_path)
            shop_key = command.get("shop_key")
            if not isinstance(shop_key, str) or shop_key not in shop_keys:
                _diagnostic(diagnostics, "error", "unknown_shop", f"{command_path}.shop_key", f"存在しないショップです: {shop_key}")
        elif command_type == "start_battle":
            _known_fields(command, {"command", "battle_id", "monster_keys"}, diagnostics, command_path)
            battle_id = command.get("battle_id")
            if not isinstance(battle_id, str) or LOCAL_ID_PATTERN.fullmatch(battle_id) is None:
                _diagnostic(diagnostics, "error", "invalid_battle_id", f"{command_path}.battle_id", "バトルIDはlower_snake_caseで指定してください。")
            lineup = command.get("monster_keys")
            if not isinstance(lineup, list) or not 1 <= len(lineup) <= 5:
                _diagnostic(diagnostics, "error", "invalid_monster_lineup", f"{command_path}.monster_keys", "敵は1〜5体指定してください。")
            else:
                if len(lineup) == 5 and lineup[0] in tall_first_monster_keys:
                    _diagnostic(diagnostics, "error", "oversized_monster_lineup", f"{command_path}.monster_keys", "先頭が64×96のモンスターの場合、敵は4体までです。")
                for monster_index, key in enumerate(lineup):
                    if not isinstance(key, str) or key not in monster_keys:
                        _diagnostic(diagnostics, "error", "unknown_monster", f"{command_path}.monster_keys[{monster_index}]", f"存在しないモンスターです: {key}")
        elif command_type in ("move_party", "move_actor", "face_party", "face_actor"):
            fields = {"command", "direction"}
            if command_type in ("move_party", "move_actor"):
                fields.add("steps")
            if command_type in ("move_actor", "face_actor"):
                fields.add("actor_id")
                actor_id = command.get("actor_id")
                if not isinstance(actor_id, str) or LOCAL_ID_PATTERN.fullmatch(actor_id) is None:
                    _diagnostic(diagnostics, "error", "invalid_actor_id", f"{command_path}.actor_id", "actor IDはlower_snake_caseで指定してください。")
            _known_fields(command, fields, diagnostics, command_path)
            if command.get("direction") not in CARDINAL_DIRECTIONS:
                _diagnostic(diagnostics, "error", "invalid_direction", f"{command_path}.direction", "directionはup、right、down、leftのいずれかです。")
            if "steps" in fields and not _is_positive_int(command.get("steps"), maximum=255):
                _diagnostic(diagnostics, "error", "invalid_steps", f"{command_path}.steps", "stepsは1から255までの整数で指定してください。")
        else:
            _diagnostic(diagnostics, "error", "unknown_command", f"{command_path}.command", f"未対応のcommandです: {command_type}")


def validate_event_sources(
    sources: Mapping[str, Mapping[str, object]],
    *,
    flag_ids: Iterable[str] = (),
    character_keys: Iterable[str] = (),
    item_keys: Iterable[str] = (),
    monster_keys: Iterable[str] = (),
    tall_first_monster_keys: Iterable[str] = (),
    shop_keys: Iterable[str] = (),
    message_ids: Iterable[str] = (),
    bgm_ids: Iterable[str] = (),
    se_ids: Iterable[str] = (),
) -> list[EventDiagnostic]:
    """Validate every source together so cross-file IDs are unambiguous."""

    if not isinstance(sources, Mapping):
        raise TypeError("event sources must be a mapping")
    characters = set(character_keys)
    items = set(item_keys)
    monsters = set(monster_keys)
    tall_monsters = set(tall_first_monster_keys)
    shops = set(shop_keys)
    messages = set(message_ids)
    bgms = set(bgm_ids)
    sounds = set(se_ids)
    diagnostics: list[EventDiagnostic] = []
    flags = set(flag_ids)
    event_ids: set[str] = set()
    battle_start_ids: set[str] = set()

    for filename, source in sources.items():
        root_path = filename
        if not isinstance(source, Mapping):
            _diagnostic(diagnostics, "error", "invalid_root", root_path, "イベントJSONのルートはobjectである必要があります。")
            continue
        _known_fields(source, {"format_version", "namespace", "events"}, diagnostics, root_path)
        if source.get("format_version") != EVENT_SOURCE_FORMAT_VERSION:
            _diagnostic(diagnostics, "error", "unsupported_format_version", f"{root_path}.format_version", f"対応するformat_versionは{EVENT_SOURCE_FORMAT_VERSION}です。")
        namespace = source.get("namespace")
        if not isinstance(namespace, str) or LOCAL_ID_PATTERN.fullmatch(namespace) is None:
            _diagnostic(diagnostics, "error", "invalid_namespace", f"{root_path}.namespace", "namespaceはlower_snake_caseで指定してください。")
            namespace = None
        elif filename != namespace:
            _diagnostic(diagnostics, "error", "namespace_filename_mismatch", f"{root_path}.namespace", "namespaceをファイル名と一致させてください。")

        events = source.get("events")
        if not isinstance(events, list):
            _diagnostic(diagnostics, "error", "invalid_events", f"{root_path}.events", "eventsは配列で指定してください。")
        else:
            local_ids = set()
            for index, event in enumerate(events):
                path = f"{root_path}.events[{index}]"
                if not isinstance(event, Mapping):
                    _diagnostic(diagnostics, "error", "invalid_event", path, "eventはobjectで指定してください。")
                    continue
                local_id = event.get("id")
                if not isinstance(local_id, str) or LOCAL_ID_PATTERN.fullmatch(local_id) is None:
                    _diagnostic(diagnostics, "error", "invalid_event_id", f"{path}.id", "イベントIDはlower_snake_caseで指定してください。")
                    continue
                full_id = f"{namespace}.{local_id}" if namespace else local_id
                if local_id in local_ids or full_id in event_ids:
                    _diagnostic(diagnostics, "error", "duplicate_event_id", f"{path}.id", f"イベントIDが重複しています: {full_id}")
                local_ids.add(local_id)
                event_ids.add(full_id)

    for filename, source in sources.items():
        if not isinstance(source, Mapping):
            continue
        events = source.get("events")
        if not isinstance(events, list):
            continue
        for index, event in enumerate(events):
            path = f"{filename}.events[{index}]"
            if not isinstance(event, Mapping):
                continue
            _known_fields(event, {"id", "note", "commands", "battle_start_id"}, diagnostics, path)
            if "note" in event and not isinstance(event.get("note"), str):
                _diagnostic(diagnostics, "error", "invalid_note", f"{path}.note", "noteは文字列で指定してください。")
            if "battle_start_id" in event:
                battle_id = event["battle_start_id"]
                if not isinstance(battle_id, str) or LOCAL_ID_PATTERN.fullmatch(battle_id) is None:
                    _diagnostic(diagnostics, "error", "invalid_battle_id", f"{path}.battle_start_id", "バトルIDはlower_snake_caseで指定してください。")
                elif battle_id in battle_start_ids:
                    _diagnostic(diagnostics, "error", "duplicate_battle_start_id", f"{path}.battle_start_id", f"バトル開始イベントが重複しています: {battle_id}")
                else:
                    battle_start_ids.add(battle_id)
            _validate_command_list(
                event.get("commands"), diagnostics, f"{path}.commands",
                flag_ids=flags, character_keys=characters, item_keys=items, monster_keys=monsters, tall_first_monster_keys=tall_monsters,
                shop_keys=shops,
                message_ids=messages, bgm_ids=bgms, se_ids=sounds,
                battle_context="battle_start_id" in event,
            )
    return diagnostics


def compile_event_sources(
    sources: Mapping[str, Mapping[str, object]],
    *,
    missions: object = None,
    **catalogs: Iterable[str],
) -> dict[str, object]:
    from .missions import validate_missions

    mission_values = [] if missions is None else missions
    diagnostics = [
        *validate_event_sources(sources, **catalogs),
        *validate_missions(mission_values, **catalogs),
    ]
    errors = [item for item in diagnostics if item.severity == "error"]
    if errors:
        raise EventSourceError(errors[0].message)
    flag_ids = sorted(set(catalogs.get("flag_ids", ())))
    events: dict[str, dict[str, object]] = {}
    battle_start_events: dict[str, str] = {}
    for filename in sorted(sources):
        source = sources[filename]
        namespace = source["namespace"]
        for event in source["events"]:
            full_id = f"{namespace}.{event['id']}"
            events[full_id] = {"commands": event["commands"]}
            if "battle_start_id" in event:
                battle_start_events[event["battle_start_id"]] = full_id
    canonical = json.dumps(
        {"sources": sources, "flags": flag_ids, "missions": mission_values},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "format_version": EVENT_RUNTIME_FORMAT_VERSION,
        "source_sha256": hashlib.sha256(canonical).hexdigest(),
        "flags": flag_ids,
        "missions": [
            {key: value for key, value in mission.items() if key != "note"}
            for mission in mission_values
        ],
        "events": {key: events[key] for key in sorted(events)},
        "battle_start_events": {key: battle_start_events[key] for key in sorted(battle_start_events)},
    }


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent, prefix=f".{path.name}.", delete=False) as temporary:
            temporary.write(content)
            temporary.flush()
            temporary_path = Path(temporary.name)
        temporary_path.replace(path)
    except BaseException:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def save_event_source(path: Path, data: Mapping[str, object]) -> None:
    _atomic_write(path, (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def save_compiled_events(path: Path, data: Mapping[str, object]) -> None:
    _atomic_write(path, (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
