"""Validate and persist globally shared event-flag declarations."""

from __future__ import annotations

import json
from pathlib import Path
import re
import tempfile
from typing import Mapping, Sequence

from .events import EventDiagnostic, EventSourceError


FLAG_ID_PATTERN = re.compile(
    r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*$"
)
FLAG_FIELDS = frozenset(("flag_id", "note"))


def event_flags_path(content_root: Path) -> Path:
    return content_root / "events" / "flags.json"


def load_event_flags(content_root: Path) -> list[dict[str, object]]:
    path = event_flags_path(content_root)
    if not path.is_file():
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise EventSourceError(
            f"イベントフラグJSONを読み込めません: {path}: {error}"
        ) from error
    if not isinstance(value, list):
        raise EventSourceError("flags.jsonのルートは配列である必要があります。")
    return value


def validate_event_flags(value: object) -> list[EventDiagnostic]:
    diagnostics: list[EventDiagnostic] = []
    if not isinstance(value, list):
        return [
            EventDiagnostic(
                "error",
                "invalid_flags",
                "flags",
                "flags.jsonのルートは配列である必要があります。",
            )
        ]
    seen: set[str] = set()
    for index, record in enumerate(value):
        path = f"flags[{index}]"
        if not isinstance(record, Mapping):
            diagnostics.append(
                EventDiagnostic(
                    "error",
                    "invalid_flag",
                    path,
                    "flagはobjectで指定してください。",
                )
            )
            continue
        for field in record.keys() - FLAG_FIELDS:
            diagnostics.append(
                EventDiagnostic(
                    "error",
                    "unknown_field",
                    f"{path}.{field}",
                    f"未対応の属性です: {field}",
                )
            )
        flag_id = record.get("flag_id")
        if (
            not isinstance(flag_id, str)
            or FLAG_ID_PATTERN.fullmatch(flag_id) is None
        ):
            diagnostics.append(
                EventDiagnostic(
                    "error",
                    "invalid_flag_id",
                    f"{path}.flag_id",
                    "flag_idはlower_snake_caseまたはドット区切りで指定してください。",
                )
            )
        elif flag_id in seen:
            diagnostics.append(
                EventDiagnostic(
                    "error",
                    "duplicate_flag_id",
                    f"{path}.flag_id",
                    f"flag_idが重複しています: {flag_id}",
                )
            )
        else:
            seen.add(flag_id)
        if "note" in record and not isinstance(record.get("note"), str):
            diagnostics.append(
                EventDiagnostic(
                    "error",
                    "invalid_note",
                    f"{path}.note",
                    "noteは文字列で指定してください。",
                )
            )
    return diagnostics


def event_flag_ids(value: object) -> set[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return set()
    return {
        record["flag_id"]
        for record in value
        if isinstance(record, Mapping)
        and isinstance(record.get("flag_id"), str)
        and FLAG_ID_PATTERN.fullmatch(record["flag_id"]) is not None
    }


def compile_event_flags(value: object) -> list[str]:
    diagnostics = validate_event_flags(value)
    errors = [item for item in diagnostics if item.severity == "error"]
    if errors:
        raise EventSourceError(errors[0].message)
    return sorted(event_flag_ids(value))


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


def save_event_flags(path: Path, value: object) -> None:
    _atomic_write(
        path,
        (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
    )


__all__ = [
    "FLAG_ID_PATTERN",
    "compile_event_flags",
    "event_flag_ids",
    "event_flags_path",
    "load_event_flags",
    "save_event_flags",
    "validate_event_flags",
]
