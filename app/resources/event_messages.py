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


class EventMessageResourceError(RuntimeError):
    """Raised when the generated event-message catalog is malformed."""


@dataclass(frozen=True)
class EventMessageCatalog:
    _texts: TextCatalog
    _ids: tuple[str, ...]
    _portrait_character_keys: Mapping[str, str | None]

    @classmethod
    def from_records(
        cls, records: Iterable[Mapping[str, object]]
    ) -> EventMessageCatalog:
        if isinstance(records, (str, bytes, Mapping)):
            raise EventMessageResourceError("messages must be an array of objects")
        converted = []
        ids: list[str] = []
        portrait_character_keys: dict[str, str | None] = {}
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
            ids.append(message_id)
            portrait_character_keys[message_id] = portrait
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


__all__ = [
    "EventMessageCatalog",
    "EventMessageResourceError",
    "MESSAGE_ID_PATTERN",
]
