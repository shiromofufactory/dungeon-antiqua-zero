"""Load localized messages used only by typed game events."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from types import MappingProxyType
from typing import Iterable, Mapping

if __package__ == "resources":
    from localization import Localizer
    from text_catalog import TextCatalog, TextCatalogError
else:
    from ..localization import Localizer
    from ..text_catalog import TextCatalog, TextCatalogError


MESSAGE_ID_PATTERN = re.compile(
    r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$"
)
LOCALIZED_FIELDS = ("text_ja", "text_en", "text_zhcn")
FACE_SIZE = 32
FACE_SHEET_WIDTH = 128
FACE_SHEET_HEIGHT = 256


class EventMessageResourceError(RuntimeError):
    """Raised when the generated event-message catalog is malformed."""


@dataclass(frozen=True)
class EventMessageCatalog:
    _texts: TextCatalog
    _ids: tuple[str, ...]
    _portrait_character_keys: Mapping[str, str | None]
    _portrait_positions: Mapping[str, tuple[int, int] | None]

    @classmethod
    def from_records(
        cls, records: Iterable[Mapping[str, object]]
    ) -> EventMessageCatalog:
        if isinstance(records, (str, bytes, Mapping)):
            raise EventMessageResourceError("messages must be an array of objects")
        converted = []
        ids: list[str] = []
        portrait_character_keys: dict[str, str | None] = {}
        portrait_positions: dict[str, tuple[int, int] | None] = {}
        try:
            iterator = iter(records)
        except TypeError as error:
            raise EventMessageResourceError(
                "messages must be an array of objects"
            ) from error
        for index, record in enumerate(iterator):
            if not isinstance(record, Mapping):
                raise EventMessageResourceError(f"messages[{index}]が不正です。")
            if not set(record) <= {
                "message_id",
                "portrait_character_key",
                "portrait_x",
                "portrait_y",
                *LOCALIZED_FIELDS,
            } or not {"message_id", *LOCALIZED_FIELDS} <= set(record):
                raise EventMessageResourceError(
                    f"messages[{index}]の属性が不正です。"
                )
            message_id = record.get("message_id")
            if (
                not isinstance(message_id, str)
                or MESSAGE_ID_PATTERN.fullmatch(message_id) is None
            ):
                raise EventMessageResourceError(
                    f"messages[{index}].message_idが不正です。"
                )
            portrait = record.get("portrait_character_key")
            if portrait is not None and (
                not isinstance(portrait, str) or not portrait
            ):
                raise EventMessageResourceError(
                    f"messages[{index}].portrait_character_keyが不正です。"
                )
            has_portrait_x = "portrait_x" in record
            has_portrait_y = "portrait_y" in record
            if portrait is not None and (has_portrait_x or has_portrait_y):
                raise EventMessageResourceError(
                    f"messages[{index}]の顔指定が重複しています。"
                )
            if has_portrait_x != has_portrait_y:
                raise EventMessageResourceError(
                    f"messages[{index}]の顔座標が不正です。"
                )
            portrait_position: tuple[int, int] | None = None
            if has_portrait_x:
                coordinates = (
                    ("portrait_x", record.get("portrait_x"), FACE_SHEET_WIDTH),
                    ("portrait_y", record.get("portrait_y"), FACE_SHEET_HEIGHT),
                )
                if any(
                    not isinstance(coordinate, int)
                    or isinstance(coordinate, bool)
                    or coordinate < 0
                    or coordinate % FACE_SIZE != 0
                    or coordinate + FACE_SIZE > limit
                    for _field, coordinate, limit in coordinates
                ):
                    raise EventMessageResourceError(
                        f"messages[{index}]の顔座標が不正です。"
                    )
                portrait_position = (
                    record["portrait_x"],
                    record["portrait_y"],
                )
            ids.append(message_id)
            portrait_character_keys[message_id] = portrait
            portrait_positions[message_id] = portrait_position
            converted.append(
                {
                    "text_key": message_id,
                    **{field: record[field] for field in LOCALIZED_FIELDS},
                }
            )
        try:
            texts = TextCatalog.from_records(converted)
        except TextCatalogError as error:
            raise EventMessageResourceError(str(error)) from error
        return cls(
            texts,
            tuple(ids),
            MappingProxyType(portrait_character_keys),
            MappingProxyType(portrait_positions),
        )

    @classmethod
    def from_json(cls, path: Path | None = None) -> EventMessageCatalog:
        if path is None:
            path = Path(__file__).resolve().parents[1] / "events" / "messages.json"
        if not isinstance(path, Path):
            raise TypeError("event message path must be a pathlib.Path")
        if not path.is_file():
            return cls.from_records(())
        try:
            records = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise EventMessageResourceError(
                f"イベントメッセージJSONを読み込めません: {path}: {error}"
            ) from error
        return cls.from_records(records)

    @property
    def ids(self) -> tuple[str, ...]:
        return self._ids

    def lines(self, message_id: str, localizer: Localizer) -> tuple[str, ...]:
        return self._texts.lines(message_id, localizer)

    def formatted_lines(
        self,
        message_id: str,
        localizer: Localizer,
        values: Mapping[str, str],
    ) -> tuple[str, ...]:
        """Resolve a logged event message with its saved arguments."""

        return self._texts.formatted_lines(message_id, localizer, values)

    def portrait_character_key(self, message_id: str) -> str | None:
        try:
            return self._portrait_character_keys[message_id]
        except KeyError as error:
            raise KeyError(f"unknown event message: {message_id}") from error

    def portrait_position(self, message_id: str) -> tuple[int, int] | None:
        try:
            return self._portrait_positions[message_id]
        except KeyError as error:
            raise KeyError(f"unknown event message: {message_id}") from error


__all__ = [
    "EventMessageCatalog",
    "EventMessageResourceError",
    "MESSAGE_ID_PATTERN",
]
