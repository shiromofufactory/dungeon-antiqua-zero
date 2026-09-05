"""Validate and compile the event-only localized message catalog."""

from __future__ import annotations

import json
from pathlib import Path
import re
import tempfile
from typing import Mapping, Sequence

from .events import EventDiagnostic, EventSourceError


MESSAGE_ID_PATTERN = re.compile(
    r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$"
)
MESSAGE_FIELDS = frozenset(("message_id", "text_ja", "text_en", "text_zhcn"))
LOCALIZED_FIELDS = ("text_ja", "text_en", "text_zhcn")


def event_messages_path(content_root: Path) -> Path:
    return content_root / "events" / "messages.json"


def load_event_messages(content_root: Path) -> list[dict[str, object]]:
    path = event_messages_path(content_root)
    if not path.is_file():
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise EventSourceError(
            f"イベントメッセージJSONを読み込めません: {path}: {error}"
        ) from error
    if not isinstance(value, list):
        raise EventSourceError("messages.jsonのルートは配列である必要があります。")
    return value


def validate_event_messages(value: object) -> list[EventDiagnostic]:
    diagnostics: list[EventDiagnostic] = []
    if not isinstance(value, list):
        return [
            EventDiagnostic(
                "error",
                "invalid_messages",
                "messages",
                "messages.jsonのルートは配列である必要があります。",
            )
        ]
    seen: set[str] = set()
    for index, record in enumerate(value):
        path = f"messages[{index}]"
        if not isinstance(record, Mapping):
            diagnostics.append(
                EventDiagnostic(
                    "error", "invalid_message", path, "messageはobjectで指定してください。"
                )
            )
            continue
        for field in record.keys() - MESSAGE_FIELDS:
            diagnostics.append(
                EventDiagnostic(
                    "error",
                    "unknown_field",
                    f"{path}.{field}",
                    f"未対応の属性です: {field}",
                )
            )
        message_id = record.get("message_id")
        if (
            not isinstance(message_id, str)
            or MESSAGE_ID_PATTERN.fullmatch(message_id) is None
        ):
            diagnostics.append(
                EventDiagnostic(
                    "error",
                    "invalid_message_id",
                    f"{path}.message_id",
                    "message_idはドット区切りのlower_snake_caseで指定してください。",
                )
            )
        elif message_id in seen:
            diagnostics.append(
                EventDiagnostic(
                    "error",
                    "duplicate_message_id",
                    f"{path}.message_id",
                    f"message_idが重複しています: {message_id}",
                )
            )
        else:
            seen.add(message_id)
        for field in LOCALIZED_FIELDS:
            lines = record.get(field)
            valid_lines = isinstance(lines, list) and all(
                isinstance(line, str) and bool(line.strip()) for line in lines
            )
            if not valid_lines or (field == "text_ja" and not lines):
                diagnostics.append(
                    EventDiagnostic(
                        "error",
                        "invalid_message_text",
                        f"{path}.{field}",
                        (
                            "text_jaは空でない文字列を1行以上指定してください。"
                            if field == "text_ja"
                            else f"{field}は空でない文字列の配列または空配列で指定してください。"
                        ),
                    )
                )
    return diagnostics


def event_message_ids(value: object) -> set[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return set()
    return {
        record["message_id"]
        for record in value
        if isinstance(record, Mapping)
        and isinstance(record.get("message_id"), str)
        and MESSAGE_ID_PATTERN.fullmatch(record["message_id"]) is not None
    }


def compile_event_messages(value: object) -> list[dict[str, object]]:
    diagnostics = validate_event_messages(value)
    errors = [item for item in diagnostics if item.severity == "error"]
    if errors:
        raise EventSourceError(errors[0].message)
    assert isinstance(value, list)
    compiled = []
    for record in value:
        assert isinstance(record, Mapping)
        compiled.append(
            {
                "message_id": record["message_id"],
                **{field: list(record[field]) for field in LOCALIZED_FIELDS},
            }
        )
    return sorted(compiled, key=lambda record: str(record["message_id"]))


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as temporary:
            temporary.write(content)
            temporary.flush()
            temporary_path = Path(temporary.name)
        temporary_path.replace(path)
    except BaseException:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def save_event_messages(path: Path, value: object) -> None:
    _atomic_write(
        path,
        (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
    )


__all__ = [
    "LOCALIZED_FIELDS",
    "MESSAGE_ID_PATTERN",
    "compile_event_messages",
    "event_message_ids",
    "event_messages_path",
    "load_event_messages",
    "save_event_messages",
    "validate_event_messages",
]
